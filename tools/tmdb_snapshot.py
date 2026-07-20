"""tmdb_snapshot.py — alimente le cache local TMDB v1 (P1.8).

Pour une source donnée, itère sur les Items, lit ``external_ids.tmdb`` et
``external_ids.tmdb_type ∈ {"movie","tv"}``, appelle l'API publique
TMDB v3, et écrit chaque payload dans
``tools/output/tmdb_cache/<tmdb_id>.json`` au format **v1** attendu par
:mod:`enrich_audit.providers` :

    {
      "_cacheVersion": 1,
      "kind": "movie" | "tv",
      "fetchedAt": "<ISO8601-UTC>",
      "payload": {...payload TMDB brut...}
    }

Idempotence :
  - skip si le fichier existe ET ``fetchedAt`` < 30 jours, sauf ``--refresh``.

Rate-limit :
  - 40 req / 10s côté TMDB v3 — on espace les requêtes à 0.25s en pratique.

Sécurité :
  - clé API lue dans l'environnement (``TMDB_API_KEY``). Jamais touchée.

Codes de sortie :
  - 0  : OK (ou rien à faire en dry-run).
  - 1  : erreur fatale (lock busy, source introuvable…).
  - 2  : ``TMDB_API_KEY`` absent et l'opération en a besoin.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from common import CONTENT_DIR, OUTPUT_DIR, atomic_write_text, log
from enrich_audit.types import TMDB_CACHE_VERSION
from repository.item_repo import ItemRepoJson
from review_lock import ServerLockBusy, acquire_pipeline_lock

_DEFAULT_TMDB_CACHE: Path = OUTPUT_DIR / "tmdb_cache"
_DEFAULT_ITEMS_DIR: Path = CONTENT_DIR / "items"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MISSING_KEY = 2

# TMDB v3 rate limit ≈ 40 req / 10s. 0.25s entre requêtes laisse une marge.
_MIN_INTERVAL_SECONDS = 0.25
# Skip si le snapshot est plus récent que ce délai (sauf --refresh).
_REFRESH_AFTER_DAYS = 30

_TMDB_BASE = "https://api.themoviedb.org/3"


def _utc_now() -> _dt.datetime:
    """Renvoie ``now()`` UTC naive (compat tests existants)."""
    return _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Pure helpers (testables sans I/O réseau)
# ---------------------------------------------------------------------------
def _utcnow_iso(now: Callable[[], _dt.datetime] | None = None) -> str:
    """Renvoie ``now()`` UTC au format ISO8601 (suffixe ``Z``).

    L'injection ``now`` permet aux tests d'être déterministes.
    """
    t = (now or _utc_now)()
    return t.replace(microsecond=0).isoformat() + "Z"


def _parse_iso(value: str) -> _dt.datetime | None:
    """Parse un ISO8601 UTC (avec ``Z`` ou offset). Renvoie None si invalide."""
    if not isinstance(value, str):
        return None
    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_fresh(
    payload: dict | None,
    *,
    max_age_days: int = _REFRESH_AFTER_DAYS,
    now: Callable[[], _dt.datetime] | None = None,
) -> bool:
    """Vrai si ``payload`` est un cache v1 dont ``fetchedAt`` est récent."""
    if not isinstance(payload, dict):
        return False
    if payload.get("_cacheVersion") != TMDB_CACHE_VERSION:
        return False
    fetched_raw = payload.get("fetchedAt")
    fetched = _parse_iso(fetched_raw) if isinstance(fetched_raw, str) else None
    if fetched is None:
        return False
    current = (now or _utc_now)()
    # Coerce les deux côtés en naive UTC pour une comparaison sûre.
    if fetched.tzinfo is not None:
        fetched = fetched.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    if current.tzinfo is not None:
        current = current.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return (current - fetched) < _dt.timedelta(days=max_age_days)


def _build_cache_entry(
    *,
    kind: str,
    payload: dict,
    now: Callable[[], _dt.datetime] | None = None,
) -> dict:
    """Fabrique l'enveloppe v1."""
    return {
        "_cacheVersion": TMDB_CACHE_VERSION,
        "kind": kind,
        "fetchedAt": _utcnow_iso(now=now),
        "payload": payload,
    }


def _read_existing(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Provider HTTP (injectable)
# ---------------------------------------------------------------------------
TmdbFetcher = Callable[[str, int], dict]
"""``(kind, tmdb_id) -> payload``. Lève en cas d'erreur réseau."""


def _make_http_fetcher(api_key: str, *, language: str = "fr-FR") -> TmdbFetcher:
    """Fetcher HTTP réel. Pas testé en CI (cf. tests avec mock)."""

    def _fetch(kind: str, tmdb_id: int) -> dict:
        if kind not in ("movie", "tv"):
            raise ValueError(f"kind invalide: {kind!r}")
        params = urllib.parse.urlencode(
            {"api_key": api_key, "language": language},
        )
        url = f"{_TMDB_BASE}/{kind}/{tmdb_id}?{params}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            data = resp.read().decode("utf-8")
        return json.loads(data)

    return _fetch


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SnapshotStats:
    """Compteurs renvoyés par ``run_snapshot``."""

    seen: int = 0
    written: int = 0
    skipped_fresh: int = 0
    skipped_no_tmdb: int = 0
    errors: int = 0


def run_snapshot(
    *,
    source_id: str,
    items_dir: Path,
    cache_dir: Path,
    fetcher: TmdbFetcher,
    apply: bool,
    refresh: bool = False,
    rate_limit_seconds: float = _MIN_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], _dt.datetime] | None = None,
) -> SnapshotStats:
    """Itère les Items et alimente le cache TMDB. Renvoie des compteurs.

    Args:
        source_id: slug source.
        items_dir: racine des Items JSON.
        cache_dir: dossier cache TMDB.
        fetcher: callable HTTP (ou mock en tests).
        apply: ``False`` = dry-run (aucun fichier écrit).
        refresh: ``True`` = ignore la fraîcheur et ré-écrit tout.
        rate_limit_seconds: délai entre 2 requêtes réseau.
        sleep: injection pour tests.
        now: injection pour tests.
    """
    repo = ItemRepoJson(items_dir, source_id)
    seen = written = skipped_fresh = skipped_no_tmdb = errors = 0
    last_request_at: float | None = None

    for item in repo.iter_all():
        seen += 1
        ext = item.external_ids
        tmdb_id = ext.tmdb
        kind = ext.tmdb_type
        if tmdb_id is None or kind not in ("movie", "tv"):
            skipped_no_tmdb += 1
            continue

        cache_path = cache_dir / f"{tmdb_id}.json"
        if not refresh:
            existing = _read_existing(cache_path)
            if _is_fresh(existing, now=now):
                skipped_fresh += 1
                continue

        # Rate-limit (uniquement entre appels réseau réels).
        if last_request_at is not None:
            elapsed = time.monotonic() - last_request_at
            if elapsed < rate_limit_seconds:
                sleep(rate_limit_seconds - elapsed)

        try:
            payload = fetcher(kind, tmdb_id)
        except (urllib.error.URLError, ValueError, OSError) as exc:
            errors += 1
            log.warning(
                "tmdb_snapshot: échec fetch tmdb_id=%s kind=%s : %s",
                tmdb_id, kind, exc,
            )
            last_request_at = time.monotonic()
            continue
        last_request_at = time.monotonic()

        entry = _build_cache_entry(kind=kind, payload=payload, now=now)
        if apply:
            atomic_write_text(
                cache_path,
                json.dumps(entry, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n",
            )
        written += 1

    return SnapshotStats(
        seen=seen,
        written=written,
        skipped_fresh=skipped_fresh,
        skipped_no_tmdb=skipped_no_tmdb,
        errors=errors,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tmdb_snapshot",
        description="Alimente tools/output/tmdb_cache/ depuis l'API TMDB.",
    )
    p.add_argument("--source", required=True, help="ID de la source (slug).")
    p.add_argument(
        "--items-dir",
        type=Path,
        default=_DEFAULT_ITEMS_DIR,
        help=f"Racine des items JSON (default: {_DEFAULT_ITEMS_DIR}).",
    )
    p.add_argument(
        "--tmdb-cache-dir",
        type=Path,
        default=_DEFAULT_TMDB_CACHE,
        help=f"Dossier cache (default: {_DEFAULT_TMDB_CACHE}).",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Écrit réellement les fichiers cache.",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="N'écrit rien (default). Compatibilité explicite.",
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help="Ignore la fraîcheur (30j) et ré-écrit tout.",
    )
    p.add_argument(
        "--ignore-server-lock",
        action="store_true",
        help="Force le lock même si review_server tourne.",
    )
    return p


def run(args: argparse.Namespace) -> int:
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        log.error(
            "TMDB_API_KEY absent de l'environnement. Définis la variable "
            "avant de relancer (ex. via tools/.env chargé par direnv).",
        )
        return EXIT_MISSING_KEY

    fetcher = _make_http_fetcher(api_key)
    stats = run_snapshot(
        source_id=args.source,
        items_dir=args.items_dir,
        cache_dir=args.tmdb_cache_dir,
        fetcher=fetcher,
        apply=bool(args.apply),
        refresh=bool(args.refresh),
    )
    log.info(
        "tmdb_snapshot %s : seen=%d written=%d fresh=%d no-tmdb=%d errors=%d",
        args.source,
        stats.seen,
        stats.written,
        stats.skipped_fresh,
        stats.skipped_no_tmdb,
        stats.errors,
    )
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with acquire_pipeline_lock(force=args.ignore_server_lock):
            return run(args)
    except ServerLockBusy as exc:
        log.error("%s", exc)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
