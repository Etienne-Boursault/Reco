"""tools/build_meta.py — CLI méta-agrégateur.

Fetche N `reco-registry.json` déclarés dans un fichier (YAML ou JSON), les
valide, et écrit `tools/output/meta/meta_index.json` consommable par les
pages Astro sous `/_meta/`.

Usage:
    python tools/build_meta.py --registries-file fixtures/registries.yaml
    python tools/build_meta.py --registries-file urls.json --dry-run

Exit codes (M24-17) — pattern audit_core :
    0  succès complet (tous les registries fetchés OK)
    1  partial-failure (au moins un fetch OK, au moins une erreur)
    2  total-failure  (aucun fetch OK alors que ≥ 1 URL déclarée)

R-P2-09 : wrappé dans `acquire_pipeline_lock(force=...)` pour cohérence
avec les autres jobs lourds (build_cache, audit_*).

Cf. ADR 0045.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Le script vit dans tools/ ; on garantit l'import de `common`/`meta`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import OUTPUT_DIR, atomic_write_text, log  # noqa: E402
from meta.aggregator import aggregate_entries  # noqa: E402
from meta.fetcher import RegistryFetcher, load_registries_file  # noqa: E402
from review_lock import ServerLockBusy, acquire_pipeline_lock  # type: ignore  # noqa: E402

DEFAULT_OUTPUT_DIR: Path = OUTPUT_DIR / "meta"
DEFAULT_CACHE: Path = OUTPUT_DIR / "http_cache_meta.sqlite"

# M24-17 — exit codes.
EXIT_OK: int = 0
EXIT_PARTIAL: int = 1
EXIT_TOTAL_FAILURE: int = 2


#: B-HIGH-4 — timeouts courts : (connect, read). 5 s pour ouvrir la
#: socket, 15 s pour lire la réponse. Au-delà, on remonte un FetchResult
#: en erreur sans bloquer le pipeline.
_HTTP_TIMEOUT: tuple[float, float] = (5.0, 15.0)

#: B-CRIT-2 — toggle réservé aux tests pour bypasser la garde SSRF
#: (URLs fixtures non-résolvables). NE JAMAIS l'activer en prod.
ALLOW_UNSAFE_URLS_TEST_ONLY: bool = False


def _default_get():  # pragma: no cover — wraps optional deps
    """Retourne un callable `(url) -> (status, text)` avec cache HTTP.

    B-CRIT-2 — la garde SSRF vit dans `RegistryFetcher.fetch_one` :
    cette factory est libre de retourner les bytes tels que reçus.
    """
    try:
        from enrichment.http_cache import build_cached_session  # noqa: PLC0415
    # B-NIT-5 — ImportError est plus précis que RuntimeError pour signaler
    # un module manquant, et préserve le `from exc` pour le traceback.
    except ImportError as exc:
        raise ImportError(
            "enrichment.http_cache indisponible — installer requests-cache."
        ) from exc
    # R-P3-12 — 3600 s, aligné sur le Cache-Control de l'endpoint Astro.
    session = build_cached_session(DEFAULT_CACHE, default_ttl_seconds=3600)

    def _get(url: str) -> tuple[int, str]:
        # B-HIGH-4 — try/except + timeout court. On laisse remonter
        # l'exception : `RegistryFetcher` la classe en `network:`.
        try:
            r = session.get(url, timeout=_HTTP_TIMEOUT)
        except Exception:  # noqa: BLE001 — propagation contrôlée
            raise
        # B-MED-22 — si l'endpoint annonce un Content-Length > DEFAULT_MAX_BYTES,
        # on bail immédiatement sans matérialiser `r.text`.
        cl = r.headers.get("Content-Length") if hasattr(r, "headers") else None
        if cl is not None:
            try:
                length = int(cl)
            except ValueError:
                length = -1
            if length > 0 and length > 256 * 1024:
                # Re-tag via la même forme qu'un payload-too-large fetcher-side.
                raise OverflowError(
                    f"Content-Length annoncé trop grand: {length} octets"
                )
        return r.status_code, r.text

    return _get


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Agrège des reco-registry.json en meta_index.json.",
    )
    p.add_argument(
        "--registries-file",
        required=True,
        type=Path,
        help="Fichier YAML/JSON listant les URLs des registries.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Dossier de sortie (défaut: {DEFAULT_OUTPUT_DIR}).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Affiche le résultat sans écrire.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Force l'acquisition du pipeline lock (debug).",
    )
    return p


def run(
    *,
    registries_file: Path | None = None,
    urls: list[str] | None = None,
    output_dir: Path,
    dry_run: bool = False,
    get_callable=None,
    allow_unsafe_urls: bool = False,
    url_resolver=None,
) -> dict:
    """API testable du CLI. Retourne le `meta_index` produit.

    B-HIGH-6 — `urls` peut être passé directement pour éviter de
    relire le fichier (le caller `main` le lit une fois pour calculer
    `urls_declared`). Sinon, on lit `registries_file` ici.

    Le `meta_index` produit contient :
      - ``schemaVersion``, ``entries``, ``totals`` : alignés avec le
        loader TS (cf. ``meta-loader.ts``) ;
      - ``generatedAt`` : ISO-8601 UTC, timestamp de l'agrégation ;
      - ``errors`` : liste ``{sourceUrl, error}`` des registries en échec.
        Ces deux dernières clés sont **métadonnées de pipeline**
        (B-MED-7) ; le loader TS les ignore (forward-compat).
    """
    if urls is None:
        if registries_file is None:
            raise ValueError("run(): registries_file ou urls requis")
        urls = load_registries_file(registries_file)
    log.info("Registries déclarés : %d", len(urls))

    get = get_callable or _default_get()
    fetcher = RegistryFetcher(
        get=get,
        url_resolver=url_resolver,
        allow_unsafe_urls=allow_unsafe_urls,
    )
    results = fetcher.fetch_many(urls)

    items: list[dict] = []
    errors: list[tuple[str, str]] = []
    for r in results:
        if r.ok:
            items.append({"sourceUrl": r.source_url, "registry": r.registry})
        else:
            errors.append((r.source_url, r.error or "?"))

    index = aggregate_entries(items)
    index["generatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    index["errors"] = [{"sourceUrl": u, "error": e} for u, e in errors]

    log.info(
        "Agrégation : %d podcasts indexés, %d erreurs.",
        index["totals"]["podcasts"],
        len(errors),
    )
    for u, e in errors:
        log.warning("  ↳ %s : %s", u, e)

    if dry_run:
        print(json.dumps(index, ensure_ascii=False, indent=2))
        return index

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "meta_index.json"
    atomic_write_text(out_path, json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    log.info("Écrit : %s", out_path)
    return index


def _exit_code_for(index: dict, urls_declared: int) -> int:
    """M24-17 — calcule l'exit code à partir du résultat.

    B-LOW-7 — invariant défensif : si `urls_declared == 0` on attend
    forcément 0 erreur (rien à fetcher → pas d'échec possible).
    """
    ok_count = index["totals"]["podcasts"]
    error_count = len(index.get("errors", []))
    if urls_declared == 0:
        assert error_count == 0, (
            "Invariant violé : 0 URL déclarée mais errors non-vide"
        )
        return EXIT_OK
    if error_count == 0:
        return EXIT_OK
    if ok_count == 0:
        return EXIT_TOTAL_FAILURE
    return EXIT_PARTIAL


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        with acquire_pipeline_lock(force=args.force):
            # B-HIGH-6 — on lit le fichier UNE seule fois, on passe `urls`
            # à `run()` plutôt que de relire derrière.
            urls = load_registries_file(args.registries_file)
            urls_declared = len(urls)
            index = run(
                urls=urls,
                output_dir=args.output_dir,
                dry_run=args.dry_run,
                allow_unsafe_urls=ALLOW_UNSAFE_URLS_TEST_ONLY,
            )
            return _exit_code_for(index, urls_declared)
    except ServerLockBusy as exc:
        log.error("%s", exc)
        return EXIT_TOTAL_FAILURE
    # B-MED-6 — catch-all : toute exception non gérée → exit 2 (vs 1
    # pour échec fonctionnel comme un lockfile occupé).
    except Exception as exc:  # noqa: BLE001 — CLI boundary
        log.exception("build_meta a échoué : %s", exc)
        return EXIT_TOTAL_FAILURE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
