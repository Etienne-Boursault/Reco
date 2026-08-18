"""Tests de `tools/fusion_items_doublons.py`.

CE QUE FAIT CET OUTIL
---------------------
La collection `items` porte l'oeuvre CANONIQUE : une entree par oeuvre, que
les galeries et les pages `/oeuvre/` affichent. Elle contenait 211 entrees
redondantes sur 179 titres — « Bref » y existait six fois, et les galeries
l'affichaient quatre fois.

Cet outil ne traite que le palier PROUVE : deux items portant le MEME
identifiant TMDB designent la meme oeuvre, sans jugement a rendre.

POURQUOI LES GARDES COMPTENT PLUS QUE LA FUSION
----------------------------------------------
Fusionner est destructeur : on supprime des fichiers et on reporte les
references des mentions. Une erreur ne se voit pas, elle se decouvre des mois
plus tard.

Le releve du 2026-08-18 l'a montre : parmi les 24 groupes prouves par
identifiant, DEUX contenaient des oeuvres differentes, parce que l'identifiant
lui-meme etait faux.

    movie/1018  porte par « Drive » (Nicolas Winding Refn, 2011)
                ... alors que movie/1018 EST « Mulholland Drive » (Lynch, 2001)
    tv/60715    porte par « Bref 2 » (Kyan Khojandi)
                ... alors que tv/60715 EST « Bref » (2011)

Fusionner sur la seule foi de l'identifiant aurait confondu Drive avec
Mulholland Drive. L'outil refuse donc TOUT groupe dont les titres divergent,
sauf variante explicitement justifiee dans `VARIANTES_ADMISES`. Le defaut est
le refus : une variante oubliee laisse un doublon, une fusion abusive detruit.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import fusion_items_doublons as fid


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch):
    """Un corpus minuscule : deux items du meme TMDB, une mention chacun."""
    items = tmp_path / "items"
    mentions = tmp_path / "mentions"
    items.mkdir()
    mentions.mkdir()

    def item(iid, titre, **extra):
        doc = {"id": iid, "title": titre, "types": ["serie"],
               "externalIds": {"tmdb": 1396, "tmdbType": "tv"}}
        doc.update(extra)
        (items / f"{iid}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    def mention(mid, item_id):
        (mentions / f"{mid}.json").write_text(json.dumps(
            {"id": mid, "itemId": item_id, "sourceRef": {"sourceId": "s"}},
            ensure_ascii=False, indent=2), encoding="utf-8")

    item("aaa", "Breaking Bad", creator="Vince Gilligan")
    item("bbb", "Breaking Bad", year=2008)
    mention("m1", "aaa")
    mention("m2", "bbb")
    mention("m3", "bbb")
    return tmp_path, items, mentions


# ===== Normalisation des titres ============================================
@pytest.mark.parametrize(("a", "b"), [
    ("Le Premier Jour du Reste de Ta Vie", "Le premier jour du reste de ta vie"),
    ("The White Lotus", "White Lotus"),
    ("Everything Everywhere All At Once", "Everything Everywhere All at Once"),
    ("Don't F**k with Cats", "Dont F**k with Cats"),
])
def test_ces_titres_sont_le_meme(a, b):
    assert fid.normaliser(a) == fid.normaliser(b)


@pytest.mark.parametrize(("a", "b"), [
    ("Drive", "Mulholland Drive"),      # le cas qui aurait tout casse
    ("Bref", "Bref 2"),
    ("Marty Suprem", "Marty Supreme"),  # variante reelle, mais a justifier
    ("Bagar", "Bagarre"),
])
def test_ces_titres_ne_sont_PAS_le_meme(a, b):
    assert fid.normaliser(a) != fid.normaliser(b)


# ===== La garde centrale ===================================================
def test_un_groupe_aux_titres_divergents_est_REFUSE():
    groupe = [{"id": "x", "title": "Drive"},
              {"id": "y", "title": "Mulholland Drive"}]
    assert fid.fusionnable(("movie", "1018"), groupe) is False


def test_une_variante_explicitement_admise_passe():
    groupe = [{"id": "x", "title": "Marty Suprem"},
              {"id": "y", "title": "Marty Supreme"}]
    assert ("movie", "1317288") in fid.VARIANTES_ADMISES
    assert fid.fusionnable(("movie", "1317288"), groupe) is True


def test_chaque_variante_admise_porte_sa_justification():
    """Sans motif ecrit, personne ne pourra rejuger la decision."""
    for cle, motif in fid.VARIANTES_ADMISES.items():
        assert len(motif) > 30, cle


def test_des_titres_identiques_passent_sans_declaration():
    groupe = [{"id": "x", "title": "Vice"}, {"id": "y", "title": "Vice"}]
    assert fid.fusionnable(("movie", "150540"), groupe) is True


# ===== Choix du survivant ==================================================
def test_le_survivant_est_celui_qui_porte_le_PLUS_DE_MENTIONS():
    """Le plus reference est le mieux etabli : le reporter coute le moins."""
    groupe = [{"id": "aaa"}, {"id": "bbb"}]
    assert fid.choisir_survivant(groupe, {"aaa": 1, "bbb": 3})["id"] == "bbb"


def test_a_egalite_le_survivant_est_deterministe():
    """Sans regle de depart, deux executions donneraient deux corpus
    differents — et le diff deviendrait illisible."""
    groupe = [{"id": "zzz"}, {"id": "aaa"}]
    for _ in range(3):
        assert fid.choisir_survivant(groupe, {"zzz": 2, "aaa": 2})["id"] == "aaa"


# ===== Fusion des champs ===================================================
def test_le_survivant_recupere_les_champs_qui_lui_manquent():
    survivant = {"id": "a", "title": "X", "types": ["serie"]}
    perdants = [{"id": "b", "title": "X", "types": ["serie"],
                 "creator": "Untel", "year": 2008}]
    fid.fusionner(survivant, perdants)
    assert survivant["creator"] == "Untel"
    assert survivant["year"] == 2008


def test_les_champs_du_survivant_ne_sont_JAMAIS_ecrases():
    survivant = {"id": "a", "title": "X", "types": ["serie"], "creator": "Bon"}
    fid.fusionner(survivant, [{"id": "b", "title": "X", "types": ["serie"],
                               "creator": "Autre"}])
    assert survivant["creator"] == "Bon"


def test_les_titres_des_perdants_deviennent_des_alias():
    """Sans cela, une recherche sur l'ancien libelle ne trouverait plus rien."""
    survivant = {"id": "a", "title": "The White Lotus", "types": ["serie"]}
    fid.fusionner(survivant, [{"id": "b", "title": "White Lotus",
                               "types": ["serie"]}])
    assert "White Lotus" in survivant["aliases"]


def test_le_titre_du_survivant_n_est_pas_son_propre_alias():
    survivant = {"id": "a", "title": "Vice", "types": ["serie"]}
    fid.fusionner(survivant, [{"id": "b", "title": "Vice", "types": ["serie"]}])
    assert "Vice" not in (survivant.get("aliases") or [])


def test_les_types_et_les_liens_sont_REUNIS_sans_doublon():
    survivant = {"id": "a", "title": "X", "types": ["serie"],
                 "customLinks": [{"label": "L", "url": "https://a.fr"}]}
    perdants = [{"id": "b", "title": "X", "types": ["autre", "serie"],
                 "customLinks": [{"label": "M", "url": "https://b.fr"},
                                 {"label": "L", "url": "https://a.fr"}]}]
    fid.fusionner(survivant, perdants)
    assert sorted(survivant["types"]) == ["autre", "serie"]
    assert [x["url"] for x in survivant["customLinks"]] == [
        "https://a.fr", "https://b.fr"]


def test_les_identifiants_externes_sont_completes():
    survivant = {"id": "a", "title": "X", "types": ["serie"],
                 "externalIds": {"tmdb": 1396}}
    fid.fusionner(survivant, [{"id": "b", "title": "X", "types": ["serie"],
                               "externalIds": {"tmdb": 1396,
                                               "instagram": "x"}}])
    assert survivant["externalIds"] == {"tmdb": 1396, "instagram": "x"}


# ===== Passe complete ======================================================
def test_dry_run_ne_touche_a_RIEN(corpus):
    tmp, items, mentions = corpus
    avant = {p.name: p.read_text(encoding="utf-8") for p in items.glob("*.json")}
    fid.executer(items, mentions, apply=False)
    assert {p.name: p.read_text(encoding="utf-8")
            for p in items.glob("*.json")} == avant
    assert len(list(items.glob("*.json"))) == 2


def test_apply_supprime_le_perdant_et_reporte_ses_mentions(corpus):
    tmp, items, mentions = corpus
    rapport = fid.executer(items, mentions, apply=True)
    restants = list(items.glob("*.json"))
    assert len(restants) == 1
    survivant = json.loads(restants[0].read_text(encoding="utf-8"))
    assert survivant["id"] == "bbb"  # 2 mentions contre 1
    # AUCUNE mention ne doit pointer dans le vide.
    cibles = {json.loads(p.read_text(encoding="utf-8"))["itemId"]
              for p in mentions.glob("*.json")}
    assert cibles == {"bbb"}
    assert rapport["fusions"] == 1
    assert rapport["mentions_reportees"] == 1


def test_le_survivant_herite_des_donnees_du_perdant(corpus):
    tmp, items, mentions = corpus
    fid.executer(items, mentions, apply=True)
    doc = json.loads(next(items.glob("*.json")).read_text(encoding="utf-8"))
    assert doc["creator"] == "Vince Gilligan"  # venait du perdant « aaa »


def test_la_passe_est_idempotente(corpus):
    tmp, items, mentions = corpus
    fid.executer(items, mentions, apply=True)
    rapport = fid.executer(items, mentions, apply=True)
    assert rapport["fusions"] == 0


def test_un_item_seul_n_est_pas_touche(tmp_path: Path):
    items, mentions = tmp_path / "i", tmp_path / "m"
    items.mkdir(); mentions.mkdir()
    (items / "x.json").write_text(json.dumps(
        {"id": "x", "title": "Seul", "types": ["film"],
         "externalIds": {"tmdb": 42, "tmdbType": "movie"}}), encoding="utf-8")
    assert fid.executer(items, mentions, apply=True)["fusions"] == 0
    assert (items / "x.json").exists()


def test_un_item_SANS_identifiant_tmdb_n_est_jamais_fusionne(tmp_path: Path):
    """Le palier traite ici est celui de la PREUVE. Sans identifiant, il n'y
    en a pas — meme si les titres coincident."""
    items, mentions = tmp_path / "i", tmp_path / "m"
    items.mkdir(); mentions.mkdir()
    for iid in ("a", "b"):
        (items / f"{iid}.json").write_text(json.dumps(
            {"id": iid, "title": "Même titre", "types": ["film"]}),
            encoding="utf-8")
    assert fid.executer(items, mentions, apply=True)["fusions"] == 0
    assert len(list(items.glob("*.json"))) == 2


def test_les_groupes_refuses_sont_RAPPORTES(tmp_path: Path):
    """Un refus silencieux ressemble en tout point a « rien a faire »."""
    items, mentions = tmp_path / "i", tmp_path / "m"
    items.mkdir(); mentions.mkdir()
    for iid, titre in (("a", "Drive"), ("b", "Mulholland Drive")):
        (items / f"{iid}.json").write_text(json.dumps(
            {"id": iid, "title": titre, "types": ["film"],
             "externalIds": {"tmdb": 1018, "tmdbType": "movie"}}),
            encoding="utf-8")
    rapport = fid.executer(items, mentions, apply=True)
    assert rapport["fusions"] == 0
    assert len(rapport["refuses"]) == 1
    assert "Drive" in str(rapport["refuses"][0])


# ===== CLI =================================================================
def test_main_dry_run_par_defaut(corpus, monkeypatch, capsys):
    tmp, items, mentions = corpus
    import common
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(common, "MENTIONS_DIR", mentions)
    assert fid.main([]) == 0
    assert len(list(items.glob("*.json"))) == 2


def test_main_apply(corpus, monkeypatch):
    tmp, items, mentions = corpus
    import common
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(common, "MENTIONS_DIR", mentions)
    assert fid.main(["--apply"]) == 0
    assert len(list(items.glob("*.json"))) == 1


# ===== Donnee heritee ou abimee ============================================
def test_un_fichier_json_illisible_ne_fait_pas_tomber_la_passe(tmp_path: Path):
    """Le corpus contient de la donnee heritee. Un fichier abime doit etre
    ignore, pas interrompre une passe qui ecrit ailleurs."""
    items, mentions = tmp_path / "i", tmp_path / "m"
    items.mkdir(); mentions.mkdir()
    (items / "casse.json").write_text("{ pas du json", encoding="utf-8")
    (mentions / "casse.json").write_text("}{", encoding="utf-8")
    for iid in ("a", "b"):
        (items / f"{iid}.json").write_text(json.dumps(
            {"id": iid, "title": "Vice", "types": ["film"],
             "externalIds": {"tmdb": 150540, "tmdbType": "movie"}}),
            encoding="utf-8")
    assert fid.executer(items, mentions, apply=True)["fusions"] == 1
    assert (items / "casse.json").exists()  # laisse tel quel


def test_un_item_SANS_identifiant_est_ignore(tmp_path: Path):
    """Un item sans `id` ne peut etre ni survivant ni perdant : le reporter
    reviendrait a pointer des mentions vers le vide."""
    items, mentions = tmp_path / "i", tmp_path / "m"
    items.mkdir(); mentions.mkdir()
    (items / "sans_id.json").write_text(json.dumps(
        {"title": "Vice", "types": ["film"],
         "externalIds": {"tmdb": 150540, "tmdbType": "movie"}}),
        encoding="utf-8")
    assert fid.executer(items, mentions, apply=True)["fusions"] == 0
    assert (items / "sans_id.json").exists()


# ===== Titre canonique =====================================================
def test_le_titre_juste_prime_sur_le_hasard_des_mentions(tmp_path: Path):
    """Le survivant est choisi au nombre de MENTIONS, pas a la justesse de son
    titre. La premiere passe a donc promu « Marty Suprem » — la coquille — en
    titre canonique, reléguant « Marty Supreme » au rang d'alias. Le visiteur
    lisait la faute sur la page de l'oeuvre.

    Pour les variantes declarees, on sait quel titre est le bon : l'API TMDB
    le donne. Il prime."""
    items, mentions = tmp_path / "i", tmp_path / "m"
    items.mkdir(); mentions.mkdir()
    (items / "a.json").write_text(json.dumps(
        {"id": "a", "title": "Marty Suprem", "types": ["film"],
         "aliases": ["Marty Supreme"],
         "externalIds": {"tmdb": 1317288, "tmdbType": "movie"}}),
        encoding="utf-8")
    fid.executer(items, mentions, apply=True)
    doc = json.loads((items / "a.json").read_text(encoding="utf-8"))
    assert doc["title"] == "Marty Supreme"
    assert "Marty Suprem" in doc["aliases"], "l'ancien titre reste cherchable"


def test_un_titre_deja_juste_n_est_pas_retouche(tmp_path: Path):
    items, mentions = tmp_path / "i", tmp_path / "m"
    items.mkdir(); mentions.mkdir()
    (items / "a.json").write_text(json.dumps(
        {"id": "a", "title": "Marty Supreme", "types": ["film"],
         "externalIds": {"tmdb": 1317288, "tmdbType": "movie"}}),
        encoding="utf-8")
    fid.executer(items, mentions, apply=True)
    doc = json.loads((items / "a.json").read_text(encoding="utf-8"))
    assert doc["title"] == "Marty Supreme"
    assert not doc.get("aliases")


def test_chaque_titre_canonique_concerne_une_variante_declaree():
    """Un titre impose sur un groupe non declare serait une decision cachee."""
    for cle in fid.TITRE_CANONIQUE:
        assert cle in fid.VARIANTES_ADMISES, cle


def test_un_item_sans_titre_ne_gagne_pas_d_alias_vide():
    """Donnee heritee : un item peut n'avoir aucun titre. Lui imposer le titre
    canonique est juste, mais il n'y a alors PAS d'ancien libelle a conserver
    — et un alias vide polluerait la recherche."""
    item = {"id": "a", "title": "", "types": ["film"]}
    assert fid._imposer_titre(("movie", "1317288"), item) is True
    assert item["title"] == "Marty Supreme"
    assert not item.get("aliases")
