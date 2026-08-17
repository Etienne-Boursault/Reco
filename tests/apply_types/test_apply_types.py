"""Tests de tools/apply_types.py.

Aucun accès au contenu réel : chaque test construit un dossier de recos
temporaire. Le seul test qui lit le dépôt est le garde-fou de synchronisation
entre `VALID_TYPES` et l'enum `recoType` de `src/content.config.ts`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from apply_types import (
    ARBITRAGES,
    FAMILLES_GELEES,
    VALID_TYPES,
    Decision,
    build_plan,
    build_report,
    decide,
    execute,
    frozen_families,
    index_recos,
    main,
    parse_ids,
    type_distribution,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fabriques
# ---------------------------------------------------------------------------
def write_reco(root: Path, reco_id: str, types, *, status="validated", title=None,
               drop_id=False) -> Path:
    """Écrit un JSON de reco minimal mais conforme aux clés lues par le script."""
    payload = {
        "id": reco_id,
        "sourceId": "un-bon-moment",
        "status": status,
        "title": title or reco_id,
        "types": list(types),
    }
    if drop_id:
        del payload["id"]
    path = root / f"{reco_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


def prop(reco_id, actuels, proposes, *, confiance="certain", title="T", justification="J"):
    return {
        "id": reco_id,
        "title": title,
        "typesActuels": list(actuels),
        "typesProposes": list(proposes),
        "confiance": confiance,
        "justification": justification,
    }


def proposals_file(props, familles=None) -> dict:
    doc = {"propositions": list(props)}
    if familles is not None:
        doc["famillesDArbitrage"] = familles
    return doc


@pytest.fixture
def recos_root(tmp_path) -> Path:
    root = tmp_path / "recos" / "un-bon-moment"
    root.mkdir(parents=True)
    return root


# ---------------------------------------------------------------------------
# Constantes — garde-fous de synchronisation
# ---------------------------------------------------------------------------
def test_valid_types_est_synchronise_avec_le_schema_zod():
    """VALID_TYPES DOIT refléter `recoType` : sinon on écrit du contenu invalide."""
    source = (PROJECT_ROOT / "src" / "content.config.ts").read_text(encoding="utf-8")
    bloc = re.search(r"const recoType = z\.enum\(\[(.*?)\]\)", source, re.DOTALL)
    assert bloc, "enum recoType introuvable dans src/content.config.ts"
    assert set(re.findall(r"'([a-z]+)'", bloc.group(1))) == set(VALID_TYPES)


def test_les_ids_arbitres_sont_uniques_entre_familles():
    """Un id dans deux familles rendrait l'arbitrage appliqué non déterministe."""
    tous = [i for rule in ARBITRAGES.values() for i in rule["ids"]]
    assert len(tous) == len(set(tous))


def test_chaque_famille_arbitree_cible_des_types_valides():
    for famille, rule in ARBITRAGES.items():
        assert rule["types"], f"{famille} : cible vide"
        assert set(rule["types"]) <= VALID_TYPES, famille


# ---------------------------------------------------------------------------
# index_recos
# ---------------------------------------------------------------------------
def test_index_recos_indexe_par_id(recos_root):
    write_reco(recos_root, "ubm-0001", ["autre"])
    write_reco(recos_root, "ubm-0002", ["film"])
    index = index_recos(recos_root.parent)
    assert set(index) == {"ubm-0001", "ubm-0002"}
    assert index["ubm-0002"][1]["types"] == ["film"]


def test_index_recos_ignore_un_json_sans_id(recos_root):
    write_reco(recos_root, "sans-id", ["autre"], drop_id=True)
    assert index_recos(recos_root.parent) == {}


# ---------------------------------------------------------------------------
# frozen_families
# ---------------------------------------------------------------------------
def test_frozen_families_ne_retient_que_les_familles_gelees():
    familles = {
        "musique_vs_album": {"ids": ["ubm-0852", "ubm-1349"]},
        "emission_tv": {"ids": ["ubm-0208"]},        # arbitrée : pas gelée
    }
    assert frozen_families(proposals_file([], familles)) == {
        "ubm-0852": "musique_vs_album", "ubm-1349": "musique_vs_album",
    }


def test_frozen_families_sans_bloc_familles():
    assert frozen_families(proposals_file([])) == {}


def test_les_familles_gelees_ne_recouvrent_pas_les_familles_arbitrees():
    assert FAMILLES_GELEES.isdisjoint(ARBITRAGES)


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------
def doc(types, *, status="validated", title="Titre"):
    return {"types": list(types), "status": status, "title": title}


def test_decide_applique_une_proposition_certaine():
    d = decide(prop("ubm-0001", ["autre", "film"], ["film"]), doc(["autre", "film"]), {}, "all")
    assert d.applied is True
    assert d.target == ("film",)
    assert d.origin == "certain"
    assert d.reason == ""


def test_decide_refuse_une_reco_non_validee():
    d = decide(prop("ubm-0001", ["autre"], ["film"]), doc(["autre"], status="discarded"),
               {}, "all")
    assert d.applied is False
    assert "discarded" in d.reason
    assert d.target == d.current


def test_decide_refuse_un_fichier_desynchronise():
    d = decide(prop("ubm-0001", ["autre"], ["film"]), doc(["autre", "serie"]), {}, "all")
    assert d.applied is False
    assert d.reason.startswith("désynchronisé")


def test_decide_applique_larbitrage_avant_la_proposition():
    """`typesProposes` disait `video` : l'arbitrage court-métrage impose `film`."""
    d = decide(prop("ubm-0815", ["autre", "video"], ["video"]), doc(["autre", "video"]),
               {}, "all")
    assert d.target == ("film",)
    assert d.origin == "arbitrage:court_metrage_en_ligne"
    assert d.applied is True


def test_decide_larbitrage_prime_sur_une_famille_gelee():
    frozen = {"ubm-0708": "categorie_absente"}
    d = decide(prop("ubm-0708", ["autre"], ["autre"]), doc(["autre"]), frozen, "all")
    assert d.origin == "arbitrage:application"
    assert d.target == ("application",)


def test_decide_gele_une_famille_ouverte_meme_certaine():
    frozen = {"ubm-0852": "musique_vs_album"}
    d = decide(prop("ubm-0852", ["autre", "album"], ["album"]), doc(["autre", "album"]),
               frozen, "all")
    assert d.applied is False
    assert d.origin == "famille ouverte"
    assert "musique_vs_album" in d.reason


def test_decide_laisse_une_inference_non_arbitree():
    d = decide(prop("ubm-0001", ["autre"], ["film"], confiance="inference"), doc(["autre"]),
               {}, "all")
    assert d.applied is False
    assert d.origin == "inference"
    assert d.justification == "J"


@pytest.mark.parametrize(("only", "reco_id", "attendu"), [
    ("certain", "ubm-0001", True),      # proposition certaine retenue
    ("certain", "ubm-0708", False),     # arbitrage exclu
    ("arbitrage", "ubm-0708", True),
    ("arbitrage", "ubm-0001", False),
])
def test_decide_respecte_only(only, reco_id, attendu):
    d = decide(prop(reco_id, ["autre"], ["film"]), doc(["autre"]), {}, only)
    assert d.applied is attendu
    if not attendu:
        assert d.reason == f"hors périmètre --only {only}"


# ---------------------------------------------------------------------------
# Validation manuelle (--validated-ids)
#
# Le seul chemin par lequel une `inference` s'applique. C'est la case à cocher
# du tableau de curation qui alimente cette liste : l'humain a regardé la reco.
# ---------------------------------------------------------------------------
def test_decide_applique_une_inference_validee_a_la_main():
    d = decide(prop("ubm-0001", ["autre", "artiste"], ["artiste"], confiance="inference"),
               doc(["autre", "artiste"]), {}, "all", frozenset({"ubm-0001"}))
    assert d.applied is True
    assert d.origin == "validé-main"
    assert d.target == ("artiste",)


def test_decide_une_validation_ne_deplace_pas_les_autres_garde_fous():
    """Valider un id ne rend pas cohérent ce qui ne l'est pas.

    Une reco `discarded`, désynchronisée ou dans une famille encore ouverte
    reste refusée : la validation humaine porte sur le TYPE proposé, pas sur
    l'état du fichier, que l'utilisateur ne voit pas depuis le tableau.
    """
    valides = frozenset({"ubm-0001", "ubm-0852"})
    inf = dict(confiance="inference")

    ecarte = decide(prop("ubm-0001", ["autre"], ["film"], **inf),
                    doc(["autre"], status="discarded"), {}, "all", valides)
    assert ecarte.applied is False and "discarded" in ecarte.reason

    desync = decide(prop("ubm-0001", ["autre"], ["film"], **inf),
                    doc(["autre", "serie"]), {}, "all", valides)
    assert desync.applied is False and desync.reason.startswith("désynchronisé")

    gelee = decide(prop("ubm-0852", ["autre", "album"], ["album"], **inf),
                   doc(["autre", "album"]), {"ubm-0852": "musique_vs_album"}, "all", valides)
    assert gelee.applied is False and gelee.origin == "famille ouverte"


def test_decide_une_inference_validee_est_hors_perimetre_de_only_certain():
    """`--only certain` ne doit pas ramasser les validations manuelles."""
    d = decide(prop("ubm-0001", ["autre"], ["film"], confiance="inference"),
               doc(["autre"]), {}, "certain", frozenset({"ubm-0001"}))
    assert d.applied is False
    assert "--only certain" in d.reason


def test_decide_ignore_une_validation_qui_ne_concerne_pas_la_reco():
    d = decide(prop("ubm-0001", ["autre"], ["film"], confiance="inference"),
               doc(["autre"]), {}, "all", frozenset({"ubm-9999"}))
    assert d.applied is False
    assert d.origin == "inference"


# ---------------------------------------------------------------------------
# parse_ids
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("raw", "attendu"), [
    (None, set()),
    ("", set()),
    ("ubm-0001", {"ubm-0001"}),
    ("ubm-0001,ubm-0002", {"ubm-0001", "ubm-0002"}),
    ("  ubm-0001 , ubm-0002  ", {"ubm-0001", "ubm-0002"}),   # espaces tolérés
    ("ubm-0001,,ubm-0002,", {"ubm-0001", "ubm-0002"}),        # séparateurs vides
    ("ubm-0001\nubm-0002", {"ubm-0001", "ubm-0002"}),         # une ligne par id
])
def test_parse_ids(raw, attendu):
    assert parse_ids(raw) == attendu


def test_parse_ids_lit_un_fichier_prefixe_arobase(tmp_path):
    """« @fichier » : même convention que les `--exclude-ids` du dépôt."""
    f = tmp_path / "valides.txt"
    f.write_text("ubm-0001\nubm-0002\n\nubm-0003\n", encoding="utf-8")
    assert parse_ids(f"@{f}") == {"ubm-0001", "ubm-0002", "ubm-0003"}


def test_main_transmet_les_ids_valides(tmp_path, capsys):
    """Bout en bout : sans le drapeau l'inférence est laissée, avec il s'applique."""
    root = tmp_path / "recos"
    root.mkdir()
    write_reco(root, "ubm-0001", ["autre", "artiste"])
    props = tmp_path / "props.json"
    props.write_text(json.dumps(proposals_file([
        prop("ubm-0001", ["autre", "artiste"], ["artiste"], confiance="inference"),
    ])), encoding="utf-8")
    base = ["--proposals", str(props), "--recos-dir", str(root), "--apply"]

    assert main(base) == 0
    assert json.loads((root / "ubm-0001.json").read_text(encoding="utf-8"))["types"] == [
        "autre", "artiste"]

    assert main([*base, "--validated-ids", "ubm-0001"]) == 0
    assert json.loads((root / "ubm-0001.json").read_text(encoding="utf-8"))["types"] == [
        "artiste"]


def test_decide_refuse_un_type_hors_schema():
    d = decide(prop("ubm-0001", ["autre"], ["exposition"]), doc(["autre"]), {}, "all")
    assert d.applied is False
    assert "hors schéma" in d.reason


def test_decide_refuse_une_cible_vide():
    d = decide(prop("ubm-0001", ["autre"], []), doc(["autre"]), {}, "all")
    assert d.applied is False
    assert "vides" in d.reason


def test_decide_ignore_ce_qui_est_deja_conforme():
    d = decide(prop("ubm-0001", ["film", "autre"], ["autre", "film"]), doc(["film", "autre"]),
               {}, "all")
    assert d.applied is False
    assert d.reason == "déjà conforme"


def test_decide_reprend_le_titre_du_document_si_la_proposition_nen_a_pas():
    p = prop("ubm-0001", ["autre"], ["film"], title="")
    d = decide(p, doc(["autre"], title="Depuis le contenu"), {}, "all")
    assert d.title == "Depuis le contenu"


# ---------------------------------------------------------------------------
# build_plan / execute
# ---------------------------------------------------------------------------
def test_build_plan_signale_une_reco_absente(recos_root):
    plan = build_plan(proposals_file([prop("ubm-9999", ["autre"], ["film"])]),
                      index_recos(recos_root.parent), "all")
    assert plan.applied == []
    assert plan.skipped[0].reason == "reco absente du contenu"


def test_execute_dry_run_nesecrit_rien(recos_root):
    path = write_reco(recos_root, "ubm-0001", ["autre", "film"])
    avant = path.read_text(encoding="utf-8")
    recos = index_recos(recos_root.parent)
    plan = build_plan(proposals_file([prop("ubm-0001", ["autre", "film"], ["film"])]),
                      recos, "all")
    assert execute(plan, dry_run=True) == 1
    assert path.read_text(encoding="utf-8") == avant


def test_execute_ne_touche_que_le_champ_types(recos_root):
    path = write_reco(recos_root, "ubm-0001", ["autre", "film"], title="Yoroï")
    recos = index_recos(recos_root.parent)
    plan = build_plan(proposals_file([prop("ubm-0001", ["autre", "film"], ["film"])]),
                      recos, "all")
    assert execute(plan, dry_run=False) == 1
    apres = json.loads(path.read_text(encoding="utf-8"))
    assert apres["types"] == ["film"]
    assert apres["title"] == "Yoroï"
    assert set(apres) == {"id", "sourceId", "status", "title", "types"}


def test_execute_preserve_le_formatage_du_depot(recos_root):
    """Clés triées, indentation 2, accents conservés, retour à la ligne final."""
    path = write_reco(recos_root, "ubm-0001", ["autre", "film"], title="Été")
    recos = index_recos(recos_root.parent)
    plan = build_plan(proposals_file([prop("ubm-0001", ["autre", "film"], ["film"])]),
                      recos, "all")
    execute(plan, dry_run=False)
    texte = path.read_text(encoding="utf-8")
    assert texte.endswith("}\n")
    assert '"title": "Été"' in texte
    assert texte == json.dumps(json.loads(texte), ensure_ascii=False,
                               indent=2, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------
# type_distribution / build_report
# ---------------------------------------------------------------------------
def test_type_distribution_ignore_les_recos_inactives(recos_root):
    write_reco(recos_root, "ubm-0001", ["film", "autre"])
    write_reco(recos_root, "ubm-0002", ["film"])
    write_reco(recos_root, "ubm-0003", ["serie"], status="discarded")
    assert type_distribution(index_recos(recos_root.parent)) == {"film": 2, "autre": 1}


def test_build_report_resume_le_plan(recos_root):
    write_reco(recos_root, "ubm-0001", ["autre", "film"])
    recos = index_recos(recos_root.parent)
    avant = type_distribution(recos)
    plan = build_plan(proposals_file([
        prop("ubm-0001", ["autre", "film"], ["film"]),
        prop("ubm-0002", ["autre"], ["film"], confiance="inference"),
    ]), recos, "all")
    written = execute(plan, dry_run=True)
    report = build_report(plan, only="all", dry_run=True, recos_dir=recos_root.parent,
                          avant=avant, apres=type_distribution(recos), written=written)
    assert report["mode"] == "dry-run"
    assert report["recosDir"] == str(recos_root.parent)
    assert report["fichiersModifies"] == 1
    assert report["statistiques"]["parOrigine"] == {"certain": 1}
    assert report["repartitionTypes"]["apres"] == {"film": 1}
    assert report["appliquees"][0]["typesCibles"] == ["film"]
    assert report["ignorees"][0]["id"] == "ubm-0002"


def test_decision_as_dict_expose_les_champs_du_rapport():
    d = Decision(reco_id="ubm-0001", title="T", current=("autre",), target=("film",),
                 origin="certain", applied=True, reason="", justification="J",
                 proposed=("film",))
    assert d.as_dict() == {
        "id": "ubm-0001", "titre": "T", "typesActuels": ["autre"],
        "typesProposes": ["film"], "typesCibles": ["film"],
        "origine": "certain", "applique": True, "motif": "", "justification": "J",
    }


def test_une_inference_ignoree_conserve_les_types_proposes():
    """La colonne que l'utilisateur arbitre ne doit pas se perdre au refus."""
    d = decide(prop("ubm-0001", ["autre"], ["serie"], confiance="inference"), doc(["autre"]),
               {}, "all")
    assert d.applied is False
    assert d.target == ("autre",)      # rien n'a bougé
    assert d.proposed == ("serie",)    # mais la proposition reste lisible


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------
def _proposals_on_disk(tmp_path, props, familles=None) -> Path:
    path = tmp_path / "props.json"
    path.write_text(json.dumps(proposals_file(props, familles), ensure_ascii=False),
                    encoding="utf-8")
    return path


def test_main_dry_run_par_defaut(tmp_path, recos_root, capsys):
    path = write_reco(recos_root, "ubm-0001", ["autre", "film"])
    props = _proposals_on_disk(tmp_path, [prop("ubm-0001", ["autre", "film"], ["film"])])
    code = main(["--proposals", str(props), "--recos-dir", str(recos_root.parent)])
    assert code == 0
    assert json.loads(path.read_text(encoding="utf-8"))["types"] == ["autre", "film"]
    sortie = capsys.readouterr().out
    assert "DRY-RUN" in sortie
    assert "ubm-0001 ['autre', 'film'] -> ['film']" in sortie


def test_main_apply_ecrit_et_produit_le_rapport(tmp_path, recos_root, capsys):
    path = write_reco(recos_root, "ubm-0001", ["autre", "film"])
    props = _proposals_on_disk(tmp_path, [prop("ubm-0001", ["autre", "film"], ["film"])])
    rapport = tmp_path / "sous-dossier" / "rapport.json"
    code = main(["--proposals", str(props), "--recos-dir", str(recos_root.parent),
                 "--apply", "--json", str(rapport)])
    assert code == 0
    assert json.loads(path.read_text(encoding="utf-8"))["types"] == ["film"]
    report = json.loads(rapport.read_text(encoding="utf-8"))
    assert report["mode"] == "apply"
    assert report["recosDir"] == str(recos_root.parent)
    assert report["fichiersModifies"] == 1
    sortie = capsys.readouterr().out
    assert "APPLIQUÉ" in sortie
    assert f"cible : {recos_root.parent}" in sortie


def test_main_only_arbitrage_laisse_les_propositions_certaines(tmp_path, recos_root):
    certaine = write_reco(recos_root, "ubm-0001", ["autre", "film"])
    arbitree = write_reco(recos_root, "ubm-2633", ["autre"])
    props = _proposals_on_disk(tmp_path, [
        prop("ubm-0001", ["autre", "film"], ["film"]),
        prop("ubm-2633", ["autre"], ["autre"]),
    ])
    main(["--proposals", str(props), "--recos-dir", str(recos_root.parent),
          "--apply", "--only", "arbitrage"])
    assert json.loads(certaine.read_text(encoding="utf-8"))["types"] == ["autre", "film"]
    assert json.loads(arbitree.read_text(encoding="utf-8"))["types"] == ["application"]


def test_main_refuse_dry_run_et_apply_ensemble(tmp_path, recos_root):
    props = _proposals_on_disk(tmp_path, [])
    with pytest.raises(SystemExit):
        main(["--proposals", str(props), "--recos-dir", str(recos_root.parent),
              "--dry-run", "--apply"])
