"""Tests de `tools/aligner_types_item_reco.py`.

LE DEFAUT
---------
Une oeuvre porte ses types a deux endroits : sur l'item, que lisent les
galeries, et sur chacune de ses recos, que lisent les cartes de `/recos`. Les
deux ont diverge sur 120 oeuvres visibles — « Takeshi Castle » etait une
video pour la galerie et une serie pour la carte.

CE QUE CES TESTS PROTEGENT
--------------------------
Deux choses, surtout.

D'abord la CONSIGNE : « corriger le type mais bien conserver les liens des
videos associees ». Un outil qui reecrirait `links` en passant detruirait un
travail de verification mene sur plusieurs semaines — d'ou un test dedie.

Ensuite la PEREMPTION : la table a ete etablie a un instant donne. Si les
types d'une oeuvre ont change depuis, la decision ne vaut plus, et l'appliquer
ecraserait un travail plus recent.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import aligner_types_item_reco as ali
import common


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch) -> Path:
    for nom in ("items", "mentions", "recos"):
        (tmp_path / nom).mkdir()
    monkeypatch.setattr(common, "ITEMS_DIR", tmp_path / "items")
    monkeypatch.setattr(common, "MENTIONS_DIR", tmp_path / "mentions")
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    return tmp_path


def poser(racine: Path, dossier: str, nom: str, doc: dict) -> Path:
    chemin = racine / dossier / f"{nom}.json"
    chemin.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return chemin


def monter(racine: Path, *, types_item, types_reco, liens=None,
           statut="validated") -> tuple[Path, Path]:
    item = poser(racine, "items", "abc", {
        "id": "abc", "title": "Stardust", "types": list(types_item)})
    poser(racine, "mentions", "m1", {
        "id": "ubm-1", "itemId": "abc", "status": statut})
    reco = poser(racine, "recos", "r1", {
        "id": "ubm-1", "title": "Stardust", "types": list(types_reco),
        "links": liens if liens is not None else []})
    return item, reco


def decision(cible, avant_item=("video",), motif="createur YouTube") -> dict:
    return {"id": "abc", "titre": "Stardust", "cible": list(cible),
            "avant_item": list(avant_item), "motif": motif}


# ===== La consigne : les liens ne bougent pas ==============================
def test_les_liens_de_la_reco_sont_INTACTS(corpus: Path):
    """« corriger le type mais bien conserver les liens des videos
    associees ». C'est le point le plus important de cette passe."""
    liens = [
        {"kind": "official", "label": "YouTube", "url": "https://youtube.com/@Stardust"},
        {"kind": "streaming", "label": "Une video", "url": "https://youtu.be/abc123"},
    ]
    _, reco = monter(corpus, types_item=["video"], types_reco=["chaine"], liens=liens)
    ali.executer([decision(["chaine"])], apply=True)
    doc = json.loads(reco.read_text(encoding="utf-8"))
    assert doc["links"] == liens
    assert doc["types"] == ["chaine"]


def test_le_reste_du_document_est_intact(corpus: Path):
    item = poser(corpus, "items", "abc", {
        "id": "abc", "title": "Stardust", "types": ["video"],
        "creator": "Quelqu'un", "year": 2019, "externalIds": {"tmdb": 7}})
    ali.executer([decision(["chaine"])], apply=True)
    doc = json.loads(item.read_text(encoding="utf-8"))
    assert doc["creator"] == "Quelqu'un"
    assert doc["year"] == 2019
    assert doc["externalIds"] == {"tmdb": 7}


# ===== L'alignement ========================================================
def test_l_item_ET_ses_recos_convergent(corpus: Path):
    # Les deux partent de valeurs differentes de la cible : c'est le cas ou
    # l'on veut voir bouger les deux collections.
    item, reco = monter(corpus, types_item=["video"], types_reco=["podcast"])
    rapport = ali.executer([decision(["chaine"])], apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["types"] == ["chaine"]
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == ["chaine"]
    assert (rapport["items"], rapport["recos"]) == (1, 1)


def test_la_reco_suit_meme_quand_l_item_avait_deja_raison(corpus: Path):
    """« Takeshi Castle » : l'item disait deja `video`, c'est la reco qui
    disait `serie`."""
    item, reco = monter(corpus, types_item=["video"], types_reco=["serie"])
    rapport = ali.executer(
        [decision(["video"], avant_item=["video"], motif="emission TV")], apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["types"] == ["video"]
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == ["video"]
    assert (rapport["items"], rapport["recos"]) == (0, 1)   # seule la reco bougeait


def test_une_union_garde_les_deux_lectures(corpus: Path):
    """« pour les cas artistes + {autre_type}, ca ne me gene pas de garder les
    deux » : Verino est un artiste ET une chaine."""
    item, reco = monter(corpus, types_item=["chaine"], types_reco=["artiste"])
    ali.executer([decision(["artiste", "chaine"], avant_item=["chaine"],
                           motif="union")], apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["types"] == ["artiste", "chaine"]
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == ["artiste", "chaine"]


def test_toutes_les_recos_de_l_oeuvre_suivent(corpus: Path):
    poser(corpus, "items", "abc", {"id": "abc", "title": "Verino", "types": ["chaine"]})
    for n in (1, 2, 3):
        poser(corpus, "mentions", f"m{n}", {
            "id": f"ubm-{n}", "itemId": "abc", "status": "validated"})
        poser(corpus, "recos", f"r{n}", {
            "id": f"ubm-{n}", "title": "Verino", "types": ["artiste"]})
    rapport = ali.executer([decision(["artiste", "chaine"], avant_item=["chaine"])],
                           apply=True)
    assert rapport["recos"] == 3


def test_la_simulation_n_ecrit_rien(corpus: Path):
    item, reco = monter(corpus, types_item=["video"], types_reco=["podcast"])
    avant = (item.read_text(encoding="utf-8"), reco.read_text(encoding="utf-8"))
    rapport = ali.executer([decision(["chaine"])], apply=False)
    assert (rapport["items"], rapport["recos"]) == (1, 1)   # annonce
    assert (item.read_text(encoding="utf-8"),
            reco.read_text(encoding="utf-8")) == avant      # n'ecrit pas


def test_la_passe_est_idempotente(corpus: Path):
    monter(corpus, types_item=["video"], types_reco=["chaine"])
    ali.executer([decision(["chaine"])], apply=True)
    rapport = ali.executer([decision(["chaine"], avant_item=["chaine"])], apply=True)
    assert (rapport["items"], rapport["recos"]) == (0, 0)


# ===== La peremption =======================================================
def test_un_item_dont_les_types_ont_CHANGE_est_refuse(corpus: Path):
    """La table date d'un instant donne. Si quelqu'un est passe apres, sa
    decision vaut mieux que la notre."""
    item, reco = monter(corpus, types_item=["film"], types_reco=["chaine"])
    rapport = ali.executer([decision(["chaine"], avant_item=["video"])], apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["types"] == ["film"]
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == ["chaine"]
    assert any("types inattendus" in r for r in rapport["refus"])


def test_une_decision_DEJA_appliquee_ne_declenche_pas_un_refus(corpus: Path):
    """Rejouer la passe est legitime. Si l'item porte deja la cible, ce n'est
    pas un conflit — et le journal doit rester lisible pour les vrais."""
    monter(corpus, types_item=["artiste", "chaine"], types_reco=["artiste"])
    rapport = ali.executer(
        [decision(["artiste", "chaine"], avant_item=["chaine"])], apply=True)
    assert rapport["refus"] == []
    assert rapport["items"] == 0          # rien a changer cote item
    assert rapport["recos"] == 1          # la reco, elle, suivait encore


def test_l_ordre_des_types_ne_declenche_pas_un_refus(corpus: Path):
    """`['a','b']` et `['b','a']` disent la meme chose."""
    monter(corpus, types_item=["video", "podcast"], types_reco=["chaine"])
    rapport = ali.executer(
        [decision(["chaine"], avant_item=["podcast", "video"])], apply=True)
    assert rapport["refus"] == []


def test_un_item_introuvable_est_refuse(corpus: Path):
    rapport = ali.executer([{**decision(["chaine"]), "id": "zzz"}], apply=True)
    assert any("introuvable" in r for r in rapport["refus"])


def test_une_decision_sans_avant_item_s_applique_sans_controle(corpus: Path):
    """Le champ est facultatif : sans lui, on fait confiance a la table."""
    item, _ = monter(corpus, types_item=["film"], types_reco=["chaine"])
    ligne = decision(["chaine"])
    del ligne["avant_item"]
    ali.executer([ligne], apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["types"] == ["chaine"]


# ===== La portee ===========================================================
def test_une_mention_ECARTEE_ne_propage_pas(corpus: Path):
    _, reco = monter(corpus, types_item=["video"], types_reco=["chaine"],
                     statut="discarded")
    rapport = ali.executer([decision(["chaine"])], apply=True)
    assert json.loads(reco.read_text(encoding="utf-8"))["types"] == ["chaine"]
    assert rapport["recos"] == 0


def test_une_oeuvre_hors_table_n_est_pas_touchee(corpus: Path):
    autre = poser(corpus, "items", "xyz", {
        "id": "xyz", "title": "Rien a voir", "types": ["video"]})
    monter(corpus, types_item=["video"], types_reco=["chaine"])
    avant = autre.read_text(encoding="utf-8")
    ali.executer([decision(["chaine"])], apply=True)
    assert autre.read_text(encoding="utf-8") == avant


def test_une_mention_sans_reco_ne_fait_pas_echouer(corpus: Path):
    item, _ = monter(corpus, types_item=["video"], types_reco=["chaine"])
    poser(corpus, "mentions", "m9", {
        "id": "ubm-9", "itemId": "abc", "status": "validated"})  # aucune reco
    assert ali.executer([decision(["chaine"])], apply=True)["items"] == 1


def test_un_json_illisible_est_ignore(corpus: Path):
    monter(corpus, types_item=["video"], types_reco=["chaine"])
    for dossier in ("items", "mentions", "recos"):
        (corpus / dossier / "casse.json").write_text("{ pas du json", encoding="utf-8")
    assert ali.executer([decision(["chaine"])], apply=True)["items"] == 1


def test_un_document_sans_id_est_ignore(corpus: Path):
    monter(corpus, types_item=["video"], types_reco=["chaine"])
    poser(corpus, "items", "orphelin", {"title": "Sans id", "types": ["autre"]})
    assert ali.executer([decision(["chaine"])], apply=True)["items"] == 1


# ===== La table livree =====================================================
def test_la_table_du_projet_est_valide():
    """Elle est lue telle quelle par la CLI : une faute de frappe dans un type
    ferait echouer le build Astro, pas ce script."""
    table = ali.charger_table()
    assert len(table) > 40
    for ligne in table:
        assert ligne["titre"], ligne["id"]
        assert ligne["motif"], ligne["id"]


def test_la_table_ne_propose_jamais_un_type_hors_enum(tmp_path: Path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps([{"id": "a", "cible": ["saga"]}]), encoding="utf-8")
    with pytest.raises(ValueError, match="hors enum"):
        ali.charger_table(f)


@pytest.mark.parametrize("ligne, motif", [
    ({"cible": ["film"]}, "sans id"),
    ({"id": "a", "cible": []}, "cible vide"),
    ({"id": "a"}, "cible vide"),
    ({"id": "a", "cible": "film"}, "cible vide"),
    ({"id": "a", "cible": ["film", "film"]}, "type repete"),
])
def test_une_table_mal_formee_est_refusee(tmp_path: Path, ligne, motif):
    f = tmp_path / "t.json"
    f.write_text(json.dumps([ligne]), encoding="utf-8")
    with pytest.raises(ValueError, match=motif):
        ali.charger_table(f)


def test_un_item_present_deux_fois_dans_la_table_est_refuse(tmp_path: Path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps([{"id": "a", "cible": ["film"]},
                             {"id": "a", "cible": ["serie"]}]), encoding="utf-8")
    with pytest.raises(ValueError, match="double"):
        ali.charger_table(f)


# ===== CLI =================================================================
def test_main_applique(corpus: Path, tmp_path: Path):
    item, _ = monter(corpus, types_item=["video"], types_reco=["chaine"])
    f = tmp_path / "t.json"
    f.write_text(json.dumps([decision(["chaine"])]), encoding="utf-8")
    assert ali.main(["--table", str(f), "--apply"]) == 0
    assert json.loads(item.read_text(encoding="utf-8"))["types"] == ["chaine"]


def test_main_dry_run(corpus: Path, tmp_path: Path):
    item, _ = monter(corpus, types_item=["video"], types_reco=["chaine"])
    f = tmp_path / "t.json"
    f.write_text(json.dumps([decision(["chaine"])]), encoding="utf-8")
    avant = item.read_text(encoding="utf-8")
    assert ali.main(["--table", str(f)]) == 0
    assert item.read_text(encoding="utf-8") == avant


def test_main_sort_en_erreur_sur_une_table_invalide(corpus: Path, tmp_path: Path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps([{"id": "a", "cible": ["saga"]}]), encoding="utf-8")
    assert ali.main(["--table", str(f), "--apply"]) == 1


def test_main_sort_en_erreur_sur_une_table_absente(tmp_path: Path):
    assert ali.main(["--table", str(tmp_path / "rien.json"), "--apply"]) == 1


def test_main_journalise_les_refus(corpus: Path, tmp_path: Path, caplog):
    monter(corpus, types_item=["film"], types_reco=["chaine"])
    f = tmp_path / "t.json"
    f.write_text(json.dumps([decision(["chaine"], avant_item=["video"])]),
                 encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert ali.main(["--table", str(f), "--apply"]) == 0
    assert "REFUS" in caplog.text
