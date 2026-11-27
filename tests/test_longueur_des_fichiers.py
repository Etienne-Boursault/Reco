"""Aucun fichier de code ne dépasse 500 lignes (consigne de `CLAUDE.md`, famille F3).

Contrôle écrit après la sixième occurrence de la famille F3 (PR #224, 27/11/2026) :
`docs/capitalisation-constats.md`. Il lit les fichiers suivis par Git de `tools/`,
`src/` et `tests/` (code seulement : ni instantanés, ni JSON, ni `.bin.gz`, ni
Markdown). Les 46 fichiers déjà trop longs ce jour-là sont figés dans `PLAFONDS`,
avec leur taille d'alors : elle ne peut que baisser. Un fichier de la liste qui
repasse à 500 lignes ou moins doit en être retiré, pour que la liste ne garde
jamais un fichier devenu conforme.
"""

import subprocess
from pathlib import Path, PurePosixPath

RACINE = Path(__file__).resolve().parent.parent
MAX_LIGNES = 500
DOSSIERS = {"tools", "src", "tests"}
SUFFIXES = {".py", ".ts", ".astro", ".mjs", ".js"}
REMEDE = "sortir un module, ou découper le fichier de tests par thème"

# Fichiers déjà au-dessus de 500 lignes le 27/11/2026 : leur taille ne doit plus monter.
PLAFONDS = {
    "src/components/ReportForm.astro": 519,
    "src/components/SearchPalette.astro": 611,
    "src/components/SourceCatalog.astro": 867,
    "tests/cache/test_builder.py": 613,
    "tests/dataset_fixes/test_corriger_attributions_erronees.py": 533,
    "tests/dataset_fixes/test_fix_duplicate_links.py": 507,
    "tests/dataset_fixes/test_fix_reco_anomalies.py": 509,
    "tests/episode/test_page_episode_cov.test.ts": 525,
    "tests/registry/test_registry_endpoint_cov.test.ts": 505,
    "tests/reports/test_reports_branches_cov.test.ts": 620,
    "tests/test_enrich_tmdb_main.py": 505,
    "tests/test_eval_local_llm.py": 525,
    "tests/test_extract_recos.py": 1167,
    "tests/test_fetch_episodes.py": 559,
    "tests/test_fusion_items_doublons.py": 666,
    "tests/test_graphies.py": 647,
    "tests/test_match_audit_cli_runner.py": 510,
    "tests/test_migration_reco_parser.py": 974,
    "tests/test_migration_service.py": 743,
    "tests/test_migrations_runner.py": 608,
    "tests/test_poll_rss.py": 702,
    "tests/test_reco_dedup.py": 1462,
    "tests/test_refresh_enrichment.py": 1189,
    "tests/test_review_doubts.py": 743,
    "tests/test_review_edit.py": 871,
    "tests/test_review_guests.py": 841,
    "tests/test_review_server.py": 4123,
    "tests/test_traiter_nouveaux_episodes.py": 1076,
    "tests/test_transcribe.py": 636,
    "tests/utils/test_content_config_cov.test.ts": 917,
    "tests/work/test_page_oeuvre_cov.test.ts": 690,
    "tools/cache/builder.py": 624,
    "tools/corrections_reco_anomalies.py": 1365,
    "tools/enrich_creators.py": 1057,
    "tools/extract_recos.py": 1147,
    "tools/fusion_items_doublons.py": 559,
    "tools/fusionner_doublons_cures.py": 552,
    "tools/match_audit/cli_runner.py": 530,
    "tools/poll_rss.py": 531,
    "tools/reco_dedup_merge.py": 517,
    "tools/refresh_enrichment.py": 619,
    "tools/repository/migration/reco_parser.py": 508,
    "tools/review_client_keyboard.js": 622,
    "tools/review_doubts.py": 562,
    "tools/review_routes.py": 594,
    "tools/traiter_nouveaux_episodes.py": 651,
}


def _longueurs() -> dict[str, int]:
    """Le nombre de lignes de chaque fichier de code suivi par Git."""
    sortie = subprocess.run(
        ["git", "ls-files", "-z"], cwd=RACINE, capture_output=True, check=True
    ).stdout.decode("utf-8")
    longueurs = {}
    for chemin in filter(None, sortie.split("\0")):
        p = PurePosixPath(chemin)
        fichier = RACINE / chemin
        if (
            p.parts[0] in DOSSIERS
            and p.suffix in SUFFIXES
            and "__snapshots__" not in p.parts
            and fichier.is_file()
        ):
            longueurs[chemin] = len(
                fichier.read_text(encoding="utf-8", errors="replace").splitlines()
            )
    return longueurs


def _trop_longs(longueurs: dict[str, int], plafonds: dict[str, int]) -> list[str]:
    """Les fichiers au-dessus de 500 lignes, ou de leur plafond figé s'ils en ont un."""
    return [
        f"{chemin} : {n} lignes (plafond {plafonds.get(chemin, MAX_LIGNES)}) ; remède : {REMEDE}"
        for chemin, n in sorted(longueurs.items())
        if n > plafonds.get(chemin, MAX_LIGNES)
    ]


def _a_retirer(longueurs: dict[str, int], plafonds: dict[str, int]) -> list[str]:
    """Les fichiers de la liste figée qui n'existent plus ou sont repassés à 500 lignes ou moins."""
    return [
        f"{chemin} : {longueurs.get(chemin, 0)} lignes, il est conforme : le retirer de PLAFONDS"
        for chemin in sorted(plafonds)
        if longueurs.get(chemin, 0) <= MAX_LIGNES
    ]


def test_aucun_fichier_ne_depasse_500_lignes_ni_son_plafond():
    assert _trop_longs(_longueurs(), PLAFONDS) == []


def test_un_fichier_redevenu_conforme_sort_de_la_liste_figee():
    assert _a_retirer(_longueurs(), PLAFONDS) == []


def test_les_deux_gardes_voient_un_fichier_trop_long_et_un_fichier_redevenu_conforme():
    # Rouge sur le défaut : sans lui, un fichier neuf de 501 lignes passerait en silence.
    plafonds = {"ancien.py": 600, "conforme.py": 700}
    longueurs = {"neuf.py": 501, "ancien.py": 601, "conforme.py": 500, "ok.py": 500}
    assert [m.split(" : ")[0] for m in _trop_longs(longueurs, plafonds)] == ["ancien.py", "neuf.py"]
    assert [m.split(" : ")[0] for m in _a_retirer(longueurs, plafonds)] == ["conforme.py"]
    assert _trop_longs({"ancien.py": 600}, plafonds) == []
