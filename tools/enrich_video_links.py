"""
enrich_video_links.py — Ajoute aux recos `film` / `serie` leurs FICHES DE
RÉFÉRENCE (IMDb, TMDB, JustWatch), et UNIQUEMENT à partir d'identifiants
renvoyés par l'API TMDB.

RÈGLE FONDATRICE — ZÉRO INVENTION
---------------------------------
Un lien n'est écrit que si un IDENTIFIANT obtenu de l'API le fonde :
  - IMDb      : `external_ids.imdb_id` (ex. `tt0120338`) inséré dans le motif
                canonique `https://www.imdb.com/title/{id}/`. L'identifiant
                vient de l'API ; seul le motif d'URL est constant — le même
                arrangement que `https://api.deezer.com/{kind}/{id}` dans
                `enrich_creators`. IMDb n'expose pas d'API publique gratuite,
                c'est la seule voie honnête.
  - TMDB      : idem avec `https://www.themoviedb.org/{movie|tv}/{id}`.
  - JustWatch : l'URL serait reprise TELLE QUELLE de TMDB
                (`watch/providers` → `results.FR.link`) — aucune construction.
                ⚠️ SOURCE TARIE au 2026-07-31 : ce champ ne renvoie plus une
                URL JustWatch mais la page « où regarder » de TMDB lui-même
                (`themoviedb.org/movie/597-titanic/watch?locale=FR`), aussi
                bien via `append_to_response` que via l'endpoint dédié. Le
                contrôle de host ci-dessous refuse donc systématiquement, et
                ce site ne produit plus aucun lien. Le code est conservé
                intact : si TMDB rétablit le champ, il repartira seul.
                (Conséquence traitée depuis : `enrich_tmdb.py` écrivait ces
                URLs TMDB dans `externalIds.justwatch`, affichées sous le
                label « JustWatch ». Le champ a été renommé `watchPage` et le
                label « Où regarder » — cf. `tools/migrate_watch_page.py`.
                Le présent module, lui, ne pose que des liens dont le host
                EST justwatch.com : son `SITE_JUSTWATCH` reste exact.)

ALLOCINÉ EST HORS DE PORTÉE. Pas d'API publique, et l'identifiant de fiche
(`fichefilm_gen_cfilm=53656`) n'est dérivable d'aucune donnée que nous
possédons. Le deviner ou le scraper produirait des liens faux : cet outil n'en
pose aucun. Les 195 fiches AlloCiné existantes ont été posées à la main et ne
sont pas touchées.

DEUX POPULATIONS, DEUX NIVEAUX DE CONFIANCE
-------------------------------------------
  - `id-existant` : la reco porte déjà `externalIds.tmdb` + `tmdbType`. Un
    seul appel (`append_to_response=external_ids,watch/providers`) ramène à la
    fois les identifiants ET le titre/l'année distants — indispensables, car
    ces ids ont été posés automatiquement par recherche de titre : ils ne sont
    PAS de l'or certifié (cf. `reco-audit-coherence-liens`). Tous les
    garde-fous s'appliquent donc, même ici.
  - `recherche` (`--search`) : la reco n'a aucun id TMDB. On recherche par
    titre, avec les garde-fous CALIBRÉS de `enrich_creators` — réutilisés tels
    quels, jamais réécrits : titre strictement égal (`titles_match_strict`),
    filtre d'année et d'antériorité, unicité exigée, puis les deux seuils de
    popularité d'`obscurity_verdict`. La fiche complète est ensuite
    re-téléchargée et repasse par tous les garde-fous.

GARDE-FOUS (toute violation ⇒ aucun lien écrit)
-----------------------------------------------
  1. `title-mismatch`  : le titre distant contredit celui de la reco.
  2. `year-mismatch`   : l'année de la reco contredit la sortie (±1 an).
  3. `released-after-episode` : l'œuvre est sortie APRÈS l'épisode.
  4. `no-tmdb-type`    : id TMDB sans `tmdbType` — les espaces d'ids `movie` et
     `tv` sont disjoints, deviner fabriquerait un faux.
  5. `search-*`        : cf. `enrich_creators.obscurity_verdict`.
Un `imdb_id` mal formé (`nm…`, chaîne vide) est rejeté : sur `/title/` il
donnerait un 404.

ÉCRITURE
--------
Les liens sont AJOUTÉS à la fin de `links`, jamais en remplacement : un lien
déjà présent vers le même host n'est jamais dupliqué, et rien n'est retiré.
Audit trail `enrichedAt["links"]`. Écriture atomique et idempotente via
`common.write_json_if_changed`.

⚠️ `src/components/RecoCard.astro` n'affiche que les 6 PREMIERS liens, et
`reco.links` non vide remplace les liens auto-générés par `merchants.ts`. Le
rapport signale donc les recos qui franchissent ce plafond : les liens sont
bien écrits, mais les derniers ne seront pas visibles.

Usage :
    python enrich_video_links.py                       # dry-run, ids existants
    python enrich_video_links.py --search              # + recherche par titre
    python enrich_video_links.py --sites imdb          # une seule fiche
    python enrich_video_links.py --json rapport.json   # détail machine
    python enrich_video_links.py --apply               # écrit (prend le verrou)

INTERFACE EN LIGNE DE COMMANDE ET FAÇADE
----------------------------------------
Le travail est réparti en trois modules — ce fichier les réunissait et
dépassait 500 lignes :

    video_links_matching  extrait les fiches et décide (aucun réseau)
    video_links_pipeline  interroge TMDB, écrit, déroule la passe
    video_links_report    compte, classe, met en forme

Tout est RÉ-EXPORTÉ ici : `enrich_video_links` reste la façade publique de
l'outil, et ni les tests ni les scripts n'ont à connaître ce découpage.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import requests
from dotenv import load_dotenv

from common import (
    EPISODES_DIR,
    RECOS_DIR,
    TOOLS_DIR,
    atomic_write_text,
    log,
)

# Les garde-fous de recherche par titre sont CALIBRÉS SUR MESURE RÉELLE dans
# `enrich_creators` (cf. `obscurity_verdict`). On les importe : en écrire
# d'autres reviendrait à recalibrer à l'aveugle.
from enrich_creators import (
    load_episode_years,
    parse_exclude_ids,
)
from review_lock import ServerLockBusy, acquire_pipeline_lock
from video_links_matching import (
    _RE_IMDB_TITLE_ID,
    _VIDEO_TYPES,
    ALL_SITES,
    AMBIGUOUS_REASONS,
    CLE_VISIONNAGE,
    IMDB_URL,
    LINKS_DISPLAY_CAP,
    POPULATION_ID,
    POPULATION_SEARCH,
    RATE_LIMIT_SLEEP,
    REASON_EXCLUDED,
    REASON_FILLED,
    REASON_HTTP_ERROR,
    REASON_NO_API_KEY,
    REASON_NO_NEW_LINK,
    REASON_NO_TMDB_TYPE,
    REASON_NOT_VALIDATED,
    REASON_RELEASED_AFTER_EPISODE,
    REASON_SEARCH_AMBIGUOUS,
    REASON_SEARCH_DISABLED,
    REASON_SEARCH_ECLIPSED,
    REASON_SEARCH_NO_MATCH,
    REASON_SEARCH_TOO_OBSCURE,
    REASON_SEARCH_UNDATED,
    REASON_TITLE_MISMATCH,
    REASON_TYPE_UNSUPPORTED,
    REASON_UNREADABLE,
    REASON_YEAR_MISMATCH,
    SITE_HOSTS,
    SITE_IMDB,
    SITE_JUSTWATCH,
    SITE_KINDS,
    SITE_LABELS,
    SITE_TMDB,
    STRATEGY_TMDB_ID,
    STRATEGY_TMDB_SEARCH,
    TMDB_URL,
    Plan,
    Resolution,
    build_link,
    candidate_links,
    cle_couverture,
    covered_hosts,
    imdb_id_from,
    imdb_url,
    justwatch_url_from,
    link_host,
    merge_links,
    missing_links,
    parse_sites,
    plan,
    tmdb_url,
    video_type,
)
from video_links_pipeline import (
    _links_from_detail,
    _log_resolution,
    _resolve_from_id,
    _resolve_from_search,
    apply_video_links,
    fetch_tmdb_detail,
    resolve_video_links,
    run,
)
from video_links_report import (
    FilledCase,
    Report,
    ReviewCase,
    format_report,
    report_payload,
)

#: Façade publique. Ce `__all__` n'est pas décoratif : sans lui, `ruff --fix`
#: prend les ré-exports pour des imports inutilisés et les SUPPRIME.
__all__ = [
    "ALL_SITES",
    "AMBIGUOUS_REASONS",
    "CLE_VISIONNAGE",
    "IMDB_URL",
    "LINKS_DISPLAY_CAP",
    "POPULATION_ID",
    "POPULATION_SEARCH",
    "RATE_LIMIT_SLEEP",
    "REASON_EXCLUDED",
    "REASON_FILLED",
    "REASON_HTTP_ERROR",
    "REASON_NOT_VALIDATED",
    "REASON_NO_API_KEY",
    "REASON_NO_NEW_LINK",
    "REASON_NO_TMDB_TYPE",
    "REASON_RELEASED_AFTER_EPISODE",
    "REASON_SEARCH_AMBIGUOUS",
    "REASON_SEARCH_DISABLED",
    "REASON_SEARCH_ECLIPSED",
    "REASON_SEARCH_NO_MATCH",
    "REASON_SEARCH_TOO_OBSCURE",
    "REASON_SEARCH_UNDATED",
    "REASON_TITLE_MISMATCH",
    "REASON_TYPE_UNSUPPORTED",
    "REASON_UNREADABLE",
    "REASON_YEAR_MISMATCH",
    "SITE_HOSTS",
    "SITE_IMDB",
    "SITE_JUSTWATCH",
    "SITE_KINDS",
    "SITE_LABELS",
    "SITE_TMDB",
    "STRATEGY_TMDB_ID",
    "STRATEGY_TMDB_SEARCH",
    "TMDB_URL",
    "_RE_IMDB_TITLE_ID",
    "_VIDEO_TYPES",
    "FilledCase",
    "Plan",
    "Report",
    "Resolution",
    "ReviewCase",
    "_links_from_detail",
    "_log_resolution",
    "_resolve_from_id",
    "_resolve_from_search",
    "apply_video_links",
    "build_link",
    "build_parser",
    "candidate_links",
    "cle_couverture",
    "covered_hosts",
    "fetch_tmdb_detail",
    "format_report",
    "imdb_id_from",
    "imdb_url",
    "justwatch_url_from",
    "link_host",
    "main",
    "merge_links",
    "missing_links",
    "parse_sites",
    "plan",
    "report_payload",
    "resolve_video_links",
    "run",
    "tmdb_url",
    "video_type",
]

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Ajoute les fiches IMDb / TMDB / JustWatch aux recos "
                    "film et série, à partir des seuls identifiants renvoyés "
                    "par l'API TMDB (aucune URL devinée, aucun AlloCiné).")
    p.add_argument("--source", default=None,
                   help="Limiter à une source (défaut : toutes).")
    p.add_argument("--limit", type=int, default=None,
                   help="Nombre maximum de recos réellement interrogées.")
    p.add_argument("--apply", action="store_true",
                   help="Écrire les liens trouvés (défaut : dry-run).")
    p.add_argument("--search", action="store_true",
                   help="Repli par recherche de titre TMDB pour les recos "
                        "sans id (titre strictement égal, candidat unique "
                        "exigé). Opt-in : off par défaut.")
    p.add_argument("--sites", default=None,
                   help=f"Fiches à poser, séparées par des virgules "
                        f"(défaut : {','.join(ALL_SITES)}).")
    p.add_argument("--exclude-ids", default=None,
                   help="Ids à ne PAS enrichir : « a,b,c » ou « @fichier ».")
    p.add_argument("--json", dest="json_path", default=None,
                   help="Écrit le rapport détaillé (JSON) à ce chemin.")
    p.add_argument("--ignore-server-lock", action="store_true",
                   help="Ignore le verrou review_server (écritures "
                        "concurrentes possibles).")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        sites = parse_sites(args.sites)
    except ValueError as exc:
        log.error("%s", exc)
        return 2

    load_dotenv(TOOLS_DIR / ".env")
    api_key = os.getenv("TMDB_API_KEY")
    if not api_key:
        log.error("TMDB_API_KEY absent de tools/.env : cet outil ne sait rien "
                  "faire sans TMDB (tous ses identifiants en viennent).")
        return 1

    kwargs = dict(
        root=RECOS_DIR, session=requests.Session(), api_key=api_key,
        source=args.source, limit=args.limit, apply=args.apply,
        exclude_ids=parse_exclude_ids(args.exclude_ids),
        episode_years=load_episode_years(EPISODES_DIR, args.source),
        allow_search=args.search, sites=sites,
    )

    if args.apply:
        # Écriture : coordination avec review_server (cf. tools/review_lock.py).
        try:
            lock = acquire_pipeline_lock(force=args.ignore_server_lock)
        except ServerLockBusy as exc:
            log.error("%s", exc)
            return 1
        with lock:
            report = run(**kwargs)
    else:
        log.info("DRY-RUN — aucune écriture (ajoute --apply pour écrire).")
        report = run(**kwargs)

    log.info("%s", format_report(report))
    if args.json_path:
        import json as _json
        atomic_write_text(Path(args.json_path),
                          _json.dumps(report_payload(report),
                                      ensure_ascii=False, indent=2) + "\n")
        log.info("Rapport détaillé : %s", args.json_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
