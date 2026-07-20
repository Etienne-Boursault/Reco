"""refresh_enrichment.py — Re-enrich proactif TMDB / Music (roadmap item #17).

Pour chaque reco d'une source, regarde le sous-objet `enrichedAt: {field: ISO}`
et rafraîchit UNIQUEMENT les champs stale (plus vieux que `--refresh-older-than`,
ou absents). Préserve les champs non touchés (override manuel via review_server,
liens custom, etc.).

Usage :
    python refresh_enrichment.py --source un-bon-moment --dry-run
    python refresh_enrichment.py --source un-bon-moment --apply --refresh-older-than 90d
    python refresh_enrichment.py --source all --provider tmdb --limit 50 --dry-run

Sécurité :
    - Lockfile pipeline (cf. review_lock.py) — refuse si review_server tourne.
    - `--apply` exige `TMDB_API_KEY` quand provider=tmdb.
    - `--dry-run` (défaut) : aucune écriture, aucun appel réseau.
    - Cache HTTP SQLite : `tools/output/http_cache.sqlite`.

Cf. ADR 0023.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from common import (
    OUTPUT_DIR,
    RECOS_DIR,
    TOOLS_DIR,
    log,
    read_json,
    recos_dir_for,
    write_json_if_changed,
)
from enrichment import EnrichedAtCorruptedError
from enrichment.duration import parse_duration
from enrichment.field_refresher import partial_update, update_nested
from enrichment.http_cache import CachedSession, build_cached_session
from enrichment.settings import RefreshEnrichmentSettings
from enrichment.tracker import now_iso, stale_fields
from review_lock import ServerLockBusy, acquire_pipeline_lock

# Champs candidats au refresh, par provider.
TMDB_FIELDS = [
    "externalIds.tmdb",
    "externalIds.justwatch",
    "watchProviders",
]
MUSIC_FIELDS = [
    "externalIds.deezer",
    "externalIds.spotify",
]


# P0-5 : `EnrichedAtCorruptedError` est défini dans `enrichment` (cf. import
# ci-dessus). Re-exporté ici pour rétro-compatibilité (`ren.EnrichedAtCorruptedError`).


def _ensure_enrichedat_dict(item: dict, *, item_id: str | None = None) -> None:
    """Vérifie que `item["enrichedAt"]` est soit absent, soit un dict.

    P0-5 : si la valeur existe et n'est PAS un dict, log warning et lève
    `EnrichedAtCorruptedError` pour que le caller skip cet item plutôt
    qu'écraser des données potentiellement importantes.
    """
    ea = item.get("enrichedAt")
    if ea is None:
        return
    if not isinstance(ea, dict):
        log.warning(
            "item %s : enrichedAt corrompu (type %s) — skip.",
            item_id or item.get("id") or "?", type(ea).__name__,
        )
        raise EnrichedAtCorruptedError(
            f"enrichedAt must be a dict, got {type(ea).__name__}"
        )


@dataclass
class RefreshStats:
    items_scanned: int = 0
    items_refreshed: int = 0
    fields_refreshed: int = 0
    by_provider: dict[str, int] = field(default_factory=lambda: {"tmdb": 0, "music": 0})
    not_found: int = 0
    # C6 : compteurs not_found séparés par provider (audit ciblé).
    not_found_tmdb: int = 0
    not_found_music: int = 0
    errors: int = 0
    # P0-5 : items skippés car enrichedAt corrompu.
    corrupted_skipped: int = 0

    def summary(self) -> str:
        return (
            f"scanned={self.items_scanned} refreshed={self.items_refreshed} "
            f"fields={self.fields_refreshed} tmdb={self.by_provider['tmdb']} "
            f"music={self.by_provider['music']} not_found={self.not_found} "
            f"not_found_tmdb={self.not_found_tmdb} "
            f"not_found_music={self.not_found_music} "
            f"errors={self.errors} corrupted={self.corrupted_skipped}"
        )


# ----------------------------------------------------------------------------
# Providers : interface minimale (DI-friendly pour tests).
# ----------------------------------------------------------------------------
ProviderName = Literal["tmdb", "music"]


class Provider:
    """Interface : un provider sait dire ses champs et faire un refresh ciblé.

    Sous-classes : voir `TmdbProvider`, `MusicProvider`. Les credentials
    (api_key, OAuth tokens) sont injectés au constructeur — JAMAIS instanciés
    paresseusement (cf. C3, C4).
    """

    name: str = ""
    # L1/P2-15 : tuple immuable au lieu de list mutable au niveau classe.
    fields: tuple[str, ...] = ()

    def applies_to(self, reco: dict) -> bool:
        raise NotImplementedError

    def refresh(
        self, reco: dict, fields: list[str], session: CachedSession,
    ) -> tuple[int, str]:
        """Refresh les `fields` de `reco`. Retourne (n_fields_updated, status).

        `status` ∈ {"ok", "not_found", "error"} — convention C6 alignée
        sur `enrich_one._enrich_status`.
        """
        raise NotImplementedError


class TmdbProvider(Provider):
    name = "tmdb"
    fields = tuple(TMDB_FIELDS)

    def __init__(self, api_key: str | None = None):
        # C3 : api_key injectée à la construction. Le caller (`run()` ou tests)
        # est responsable d'instancier UNE FOIS avec la clé chargée.
        self.api_key = api_key

    def applies_to(self, reco: dict) -> bool:
        types = reco.get("types") or []
        return any(t in ("film", "serie") for t in types)

    def refresh(
        self, reco: dict, fields: list[str], session: CachedSession,
    ) -> tuple[int, str]:
        # Import paresseux pour rester testable sans patcher TMDB.
        from enrich_tmdb import enrich_one as _tmdb_enrich

        before_ext = dict(reco.get("externalIds") or {})
        before_wp = list(reco.get("watchProviders") or [])

        _tmdb_enrich(reco, session=session.session, api_key=self.api_key, force=False)
        status = reco.pop("_enrich_status", None)
        if status == "not_found":
            return 0, "not_found"

        ts = now_iso()
        n = 0
        ext = reco.get("externalIds") or {}

        # C5 : sémantique unifiée. Politique : si l'appel a réussi (status
        # != not_found), on trace `enrichedAt[field]` même si la valeur n'a
        # pas changé — c'est un audit "vérifié à T". Pour idempotence (H6) :
        # si la valeur ET le timestamp existent et la valeur est identique,
        # noop (préserve git diff propre).
        ea_existing = reco.get("enrichedAt") if isinstance(reco.get("enrichedAt"), dict) else {}

        for f in fields:
            if f == "externalIds.tmdb":
                new_v = ext.get("tmdb")
                old_v = before_ext.get("tmdb")
                if new_v != old_v:
                    update_nested(reco, "externalIds.tmdb", new_v, timestamp=ts)
                    n += 1
                elif f not in ea_existing:
                    # Première fois qu'on trace ce champ : pose le timestamp.
                    update_nested(reco, "externalIds.tmdb", new_v, timestamp=ts)
                    n += 1
                else:
                    # Idempotence H6 : valeur ET timestamp déjà présents → noop.
                    pass
            elif f == "externalIds.justwatch":
                new_v = ext.get("justwatch")
                old_v = before_ext.get("justwatch")
                if new_v != old_v:
                    update_nested(reco, "externalIds.justwatch", new_v, timestamp=ts)
                    n += 1
                else:
                    # Trace audit même si inchangé (vérifié à T).
                    ea = reco.get("enrichedAt") if isinstance(reco.get("enrichedAt"), dict) else {}
                    ea["externalIds.justwatch"] = ts
                    reco["enrichedAt"] = ea
                    n += 1
            elif f == "watchProviders":
                wp = reco.get("watchProviders")
                if wp != before_wp:
                    partial_update(
                        reco, "watchProviders", wp, timestamp=ts,
                        delete_if_none=(wp is None and before_wp),
                    )
                    n += 1
                else:
                    ea = reco.get("enrichedAt") if isinstance(reco.get("enrichedAt"), dict) else {}
                    ea["watchProviders"] = ts
                    reco["enrichedAt"] = ea
                    n += 1

        return n, "ok"


class MusicProvider(Provider):
    name = "music"
    fields = tuple(MUSIC_FIELDS)

    def __init__(
        self,
        *,
        spotify_token: str | None = None,
        spotify_client_id: str | None = None,
        spotify_client_secret: str | None = None,
    ):
        # C4 : `spotify_token` (access_token Bearer) DOIT être passé directement.
        # Le caller (`run()`) est responsable de le dériver via
        # `enrich_music.spotify_token(...)` UNE FOIS en amont. NE JAMAIS dériver
        # paresseusement ici (rend les tests difficiles + risque race conditions).
        self.spotify_token = spotify_token
        self.spotify_client_id = spotify_client_id
        self.spotify_client_secret = spotify_client_secret

    def applies_to(self, reco: dict) -> bool:
        types = reco.get("types") or []
        return any(t in ("musique", "album", "artiste") for t in types)

    def refresh(
        self, reco: dict, fields: list[str], session: CachedSession,
    ) -> tuple[int, str]:
        from enrich_music import enrich_one as _music_enrich

        before_ext = dict(reco.get("externalIds") or {})

        # C4 : passe le token Spotify si disponible. Si pas de token, Deezer
        # marche quand même mais Spotify sera systématiquement skip.
        _music_enrich(
            reco, session=session.session,
            spotify_token=self.spotify_token,
        )

        # C6 : aligne sur convention `_enrich_status` ("ok"/"not_found").
        status = reco.pop("_enrich_status", None)
        if status == "not_found":
            return 0, "not_found"

        ts = now_iso()
        n = 0
        ext = reco.get("externalIds") or {}

        for f in fields:
            key = f.split(".", 1)[1] if f.startswith("externalIds.") else f
            new_v = ext.get(key)
            old_v = before_ext.get(key)

            # C4 : si pas de token Spotify, NE PAS tracer `enrichedAt[spotify]`
            # — ce serait un faux audit ("on dit vérifié alors qu'on a skip").
            if key == "spotify" and not self.spotify_token:
                continue

            if new_v != old_v and new_v is not None:
                update_nested(reco, f, new_v, timestamp=ts)
                n += 1
            else:
                # Valeur inchangée OU absente — trace l'audit (vérifié à T)
                # sans toucher à la valeur. Aligne sémantique C5.
                ea = reco.get("enrichedAt") if isinstance(reco.get("enrichedAt"), dict) else {}
                ea[f] = ts
                reco["enrichedAt"] = ea
                n += 1
        return n, "ok"


# ----------------------------------------------------------------------------
# Pipeline
# ----------------------------------------------------------------------------
def _iter_source_ids(source_arg: str) -> list[str]:
    if source_arg == "all":
        return sorted(p.name for p in RECOS_DIR.iterdir() if p.is_dir())
    return [source_arg]


def _build_default_providers(
    *,
    api_key_tmdb: str | None = None,
    spotify_token: str | None = None,
) -> list[Provider]:
    """Instancie les providers par défaut avec leurs credentials.

    C3/C4 : centralise l'instanciation. Le caller passe les credentials chargés
    une seule fois en amont — JAMAIS instanciés par `_candidate_fields_for`.
    """
    return [
        TmdbProvider(api_key=api_key_tmdb),
        MusicProvider(spotify_token=spotify_token),
    ]


def _candidate_fields_for(
    reco: dict, provider_filter: str, providers: Sequence[Provider],
) -> tuple[Provider | None, list[str]]:
    """Renvoie (provider applicable, champs candidats).

    C3 : itère la liste de providers déjà instanciée (avec credentials).
    """
    # L5 : "musicbrainz" est un alias historique pour "music" (le nom canonique).
    norm_filter = "music" if provider_filter == "musicbrainz" else provider_filter
    for p in providers:
        if norm_filter not in ("all", p.name):
            continue
        if p.applies_to(reco):
            return p, list(p.fields)
    return None, []


def plan_refresh(
    reco: dict,
    *,
    older_than: timedelta,
    now: datetime,
    provider_filter: str,
    field_filter: str | None,
    providers: Sequence[Provider] | None = None,
) -> tuple[Provider | None, list[str]]:
    """Décide quels champs refraîchir pour cette reco. Aucun IO.

    Si `providers` n'est pas fourni, instancie des providers sans credentials
    (rétro-compat tests existants). Pour un usage prod, le caller passe des
    providers avec credentials.
    """
    if providers is None:
        providers = _build_default_providers()
    provider, fields = _candidate_fields_for(reco, provider_filter, providers)
    if not provider:
        return None, []
    if field_filter:
        fields = [f for f in fields if f == field_filter]
        if not fields:
            return None, []
    stale = stale_fields(reco, fields, older_than=older_than, now=now)
    return (provider if stale else None), stale


def _resolve_spotify_token(
    *,
    apply: bool,
    provider_filter: str,
    session: CachedSession,
) -> str | None:
    """C4 : tente de récupérer un access_token Spotify si --apply et provider
    music demandé. Retourne None si pas de creds, ou si la requête échoue.
    """
    if not apply:
        return None
    norm = "music" if provider_filter == "musicbrainz" else provider_filter
    if norm not in ("all", "music"):
        return None
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    if not (client_id and client_secret):
        log.warning(
            "SPOTIFY_CLIENT_ID/SECRET absents — refresh Spotify désactivé "
            "(Deezer continuera de fonctionner).",
        )
        return None
    try:
        from enrich_music import spotify_token as _spotify_token
        token = _spotify_token(session.session, client_id, client_secret)
    except Exception as exc:  # noqa: BLE001
        log.warning("Spotify token impossible à récupérer : %s", exc)
        return None
    if not token:
        log.warning("Spotify token vide — refresh Spotify désactivé.")
    return token


def run(
    *,
    source_arg: str,
    older_than: timedelta,
    provider_filter: str,
    field_filter: str | None,
    apply: bool,
    limit: int | None,
    cache_path: Path,
    api_key_tmdb: str | None,
    spotify_token: str | None = None,
    now: datetime | None = None,
    provider_factory=None,
    providers: Sequence[Provider] | None = None,
) -> RefreshStats:
    """Cœur métier. Pas d'argparse ici → directement testable.

    `providers` : injecté en tests pour remplacer TMDB/Music par des fakes.
                  Si None, construit avec les credentials passés.
    `provider_factory(name)` : LEGACY (rétro-compat tests existants). À
                  préférer : passer `providers=[...]` directement.
    """
    now = now or datetime.now(timezone.utc)
    stats = RefreshStats()
    session = build_cached_session(cache_path, backend="sqlite" if apply else "memory")

    # C4 : résout le token Spotify UNE FOIS en amont si --apply.
    if spotify_token is None:
        spotify_token = _resolve_spotify_token(
            apply=apply, provider_filter=provider_filter, session=session,
        )

    # C3/C4 : instancie les providers UNE FOIS avec leurs credentials.
    if providers is None:
        providers = _build_default_providers(
            api_key_tmdb=api_key_tmdb,
            spotify_token=spotify_token,
        )
    providers_by_name = {p.name: p for p in providers}

    try:
        for src_id in _iter_source_ids(source_arg):
            recos_dir = recos_dir_for(src_id)
            if not recos_dir.exists():
                log.warning("Source %s : pas de dossier recos.", src_id)
                continue
            for path in sorted(recos_dir.glob("*.json")):
                if limit is not None and stats.items_scanned >= limit:
                    break
                stats.items_scanned += 1
                reco = read_json(path)

                # P0-5 : refuse silencieusement d'écraser un enrichedAt corrompu.
                try:
                    _ensure_enrichedat_dict(reco, item_id=reco.get("id"))
                except EnrichedAtCorruptedError:
                    stats.corrupted_skipped += 1
                    continue

                provider, fields = plan_refresh(
                    reco,
                    older_than=older_than,
                    now=now,
                    provider_filter=provider_filter,
                    field_filter=field_filter,
                    providers=providers,
                )
                if not provider or not fields:
                    continue

                # Rétro-compat : `provider_factory` peut substituer (tests).
                if provider_factory is not None:
                    sub = provider_factory(provider.name)
                    if sub is not None:
                        provider = sub
                else:
                    # C3 : utilise l'instance déjà construite avec credentials.
                    provider = providers_by_name.get(provider.name, provider)

                log.info(
                    "[%s] %s → refresh %s (%d champs)",
                    src_id, reco.get("id", path.stem),
                    provider.name, len(fields),
                )
                if not apply:
                    stats.items_refreshed += 1
                    stats.fields_refreshed += len(fields)
                    stats.by_provider[provider.name] = stats.by_provider.get(provider.name, 0) + 1
                    continue

                try:
                    n, status = provider.refresh(reco, fields, session)
                except Exception as e:  # noqa: BLE001 — best-effort, log & skip
                    log.error("  erreur %s : %s", provider.name, e)
                    stats.errors += 1
                    continue
                if status == "not_found":
                    stats.not_found += 1
                    # C6 : compteurs séparés par provider.
                    if provider.name == "tmdb":
                        stats.not_found_tmdb += 1
                    elif provider.name == "music":
                        stats.not_found_music += 1
                    continue
                if n > 0:
                    write_json_if_changed(path, reco)
                    stats.items_refreshed += 1
                    stats.fields_refreshed += n
                    stats.by_provider[provider.name] = stats.by_provider.get(provider.name, 0) + 1
    finally:
        if hasattr(session, "stats"):
            log.info(
                "HTTP cache : %d req, %d hits, %d miss (hit_ratio=%.2f)",
                session.stats.requests, session.stats.hits, session.stats.misses,
                session.stats.hit_ratio(),
            )
        session.close()
    return stats


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def _parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Re-enrich proactif TMDB/Music — refresh ciblé par champ stale.",
    )
    p.add_argument("--source", required=True,
                   help="ID source ou 'all'.")
    p.add_argument("--field", default=None,
                   help="Limite à un champ précis (ex. 'watchProviders').")
    p.add_argument("--refresh-older-than", default="90d",
                   help=("Seuil de fraîcheur. Formats : '48h', '30d', '12w', "
                         "'6m' (~180j), '1y' (~365j). Mois et années sont "
                         "des approximations (30j et 365j). Défaut 90d."))
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="N'écrit rien, n'appelle aucune API (défaut).")
    mode.add_argument("--apply", action="store_true",
                      help="Applique réellement (appels API + écritures).")
    p.add_argument("--limit", type=int, default=None,
                   help="Process au max N items (utile pour preview).")
    # L5 : on garde "musicbrainz" comme alias rétro-compat mais documente "music".
    p.add_argument("--provider", choices=["tmdb", "music", "musicbrainz", "all"],
                   default="all",
                   help="Filtre par provider. 'music'/'musicbrainz' = Deezer+Spotify.")
    p.add_argument("--ignore-server-lock", action="store_true",
                   help="Ignore le verrou review_server.")
    return p.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = _parse_args(argv)
    apply = args.apply and not args.dry_run

    try:
        older_than = parse_duration(args.refresh_older_than)
    except ValueError as e:
        log.error("--refresh-older-than invalide : %s", e)
        return 2

    # P3.5-B : Settings centralisés. Les flags CLI restent overrides
    # (rétro-compat). NOTE : on ne lit pas encore SourceConfig.extra ici
    # (CLI global multi-sources). Forward-compat — quand le CLI sera
    # scindé par source, ce read deviendra trivial via
    # ``RefreshEnrichmentSettings.from_source_extra(src.extra, overrides=...)``.
    try:
        settings = RefreshEnrichmentSettings.from_source_extra(
            None,
            overrides={
                "older_than": older_than,
                "provider_filter": args.provider,
            },
        )
    except ValueError as e:
        log.error("Settings invalides : %s", e)
        return 2

    if apply and args.provider in ("tmdb", "all"):
        load_dotenv(TOOLS_DIR / ".env")
        if not os.getenv("TMDB_API_KEY"):
            log.error("TMDB_API_KEY absente — requise pour --apply avec TMDB.")
            return 2

    # C4 : charge les creds Spotify si --apply + provider music ou all.
    if apply and args.provider in ("music", "musicbrainz", "all"):
        load_dotenv(TOOLS_DIR / ".env")
        # Pas de fail si absent — on log warning et on skip Spotify (Deezer OK).

    try:
        lock_ctx = acquire_pipeline_lock(force=args.ignore_server_lock)
        lock_ctx.__enter__()
    except ServerLockBusy as exc:
        log.error("%s", exc)
        return 1

    try:
        cache_path = OUTPUT_DIR / "http_cache.sqlite"
        stats = run(
            source_arg=args.source,
            older_than=settings.older_than,
            provider_filter=settings.provider_filter,
            field_filter=args.field,
            apply=apply,
            limit=args.limit,
            cache_path=cache_path,
            api_key_tmdb=os.getenv("TMDB_API_KEY"),
        )
        log.info("Terminé : %s", stats.summary())
        # M7 : exit code 1 si erreurs en --apply.
        if apply and stats.errors > 0:
            return 1
        return 0
    finally:
        try:
            lock_ctx.__exit__(None, None, None)
        except Exception as exc:  # noqa: BLE001
            # L4 : log warning au lieu de pass silencieux.
            log.warning("Échec release lock pipeline : %s", exc)


if __name__ == "__main__":
    sys.exit(main())
