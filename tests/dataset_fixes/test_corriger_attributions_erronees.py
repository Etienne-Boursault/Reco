"""Tests de `tools/corriger_attributions_erronees.py`.

D'OU VIENNENT CES CAS
---------------------
Trois agents relisaient les 67 oeuvres rangees dans « autre » pour les
retyper (2026-08-19). En cherchant le type, ils ont bute sur des `creator`
qui ne tenaient pas debout : Arte credite comme realisateur d'un documentaire
qu'il a seulement diffuse, Netflix comme auteur d'un spectacle, et Kyan
Khojandi comme realisateur d'un court metrage d'Albert Dupontel — alors que
la citation de l'episode est de Dupontel parlant de son propre film.

CE QUE CES TESTS PROTEGENT
--------------------------
Une table de corrections curee est dangereuse par nature : elle ecrit sans
condition ce qu'un humain y a mis. Les gardes-fous verifies ici sont donc
ceux qui limitent sa portee — n'ecrire que sur la valeur fautive attendue,
ne jamais toucher une oeuvre hors table, ne pas reveiller une reco ecartee.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import corriger_attributions_erronees as cae


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch) -> Path:
    for nom in ("items", "recos"):
        (tmp_path / nom).mkdir()
    monkeypatch.setattr(common, "ITEMS_DIR", tmp_path / "items")
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    return tmp_path


def poser(racine: Path, dossier: str, nom: str, doc: dict) -> Path:
    chemin = racine / dossier / f"{nom}.json"
    chemin.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return chemin


DESIRE = next(c for c in cae.CORRECTIONS if c.item_id == "7033f440")
ANGES = next(c for c in cae.CORRECTIONS if c.item_id == "278b0017")


# ===== La table elle-meme ==================================================
def test_chaque_correction_porte_une_preuve_ouvrable():
    """Sans source, cette table ne vaudrait pas mieux que ce qu'elle corrige."""
    for c in cae.CORRECTIONS:
        assert c.preuve.startswith("https://"), c.item_id


def _fautifs(c) -> tuple:
    faux = c.createur_faux
    return (faux,) if isinstance(faux, str) else (faux or ())


def test_un_champ_VIDE_peut_etre_une_valeur_fautive(corpus: Path):
    """Une passe anterieure avait vide le createur de « LOL », faute
    d'attribution sure. Il en existe une : le champ vide devient a son tour
    une valeur a corriger."""
    lol = next(c for c in cae.CORRECTIONS if None in _fautifs(c))
    reco = poser(corpus, "recos", "r", {
        "id": "ubm-1", "title": lol.titre, "status": "validated"})
    cae.executer(apply=True)
    assert json.loads(reco.read_text(encoding="utf-8"))["creator"] == lol.createur


def test_aucune_correction_ne_remplace_un_nom_par_lui_meme():
    for c in cae.CORRECTIONS:
        if c.createur is None:
            continue          # cette entree corrige un titre ou un lien
        assert c.createur not in _fautifs(c), c.item_id


def test_une_correction_peut_viser_PLUSIEURS_valeurs_fautives(corpus: Path):
    """« LOL » se trompait de deux facons : la fiche creditait la plateforme,
    une reco creditait celui qui la recommande."""
    lol = next(c for c in cae.CORRECTIONS if len(_fautifs(c)) > 1)
    a, b = _fautifs(lol)[:2]
    item = poser(corpus, "items", "i", {
        "id": lol.item_id, "title": lol.titre, "creator": a})
    reco = poser(corpus, "recos", "r", {
        "id": "ubm-1", "title": lol.titre, "creator": b, "status": "validated"})
    cae.executer(apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["creator"] == lol.createur
    assert json.loads(reco.read_text(encoding="utf-8"))["creator"] == lol.createur


def test_chaque_correction_fait_QUELQUE_CHOSE():
    """Une entree qui ne corrige rien serait un oubli silencieux."""
    for c in cae.CORRECTIONS:
        assert (c.createur or c.annee or c.externes_a_retirer
                or c.titre_corrige or c.liens_a_retirer
                or c.retirer_createur or c.liens_a_ajouter), c.item_id


def test_retirer_et_remplacer_s_excluent():
    """Retirer le createur ET en poser un nouveau n'a pas de sens."""
    for c in cae.CORRECTIONS:
        assert not (c.retirer_createur and c.createur), c.item_id


def test_un_createur_faux_SANS_remplacant_est_retire(corpus: Path):
    """Le mecanisme reste teste meme si la table ne l'emploie plus : il sert
    des qu'une valeur est fausse sans attribution sure pour la remplacer."""
    correction = cae.Correction(
        item_id="zz", titre="Test", preuve="https://exemple.fr/",
        createur_faux="Un Diffuseur", retirer_createur=True)
    doc = {"id": "zz", "title": "Test", "creator": "Un Diffuseur",
           "types": ["video"]}
    assert cae._corriger_document(doc, correction) == ["creator"]
    assert "creator" not in doc
    assert doc["types"] == ["video"]        # le reste est intact


def test_un_retrait_ne_touche_pas_un_AUTRE_createur():
    correction = cae.Correction(
        item_id="zz", titre="Test", preuve="https://exemple.fr/",
        createur_faux="Un Diffuseur", retirer_createur=True)
    doc = {"id": "zz", "title": "Test", "creator": "Quelqu'un d'autre"}
    assert cae._corriger_document(doc, correction) == []
    assert doc["creator"] == "Quelqu'un d'autre"


def test_un_titre_corrige_differe_de_l_ancien():
    for c in cae.CORRECTIONS:
        if c.titre_corrige:
            assert c.titre_corrige != c.titre, c.item_id


def test_les_liens_a_ajouter_sont_bien_formes():
    admis = {"buy", "borrow", "streaming", "info", "official", "social"}
    for c in cae.CORRECTIONS:
        for lien in c.liens_a_ajouter:
            assert lien["url"].startswith("https://"), (c.item_id, lien)
            assert lien["kind"] in admis, (c.item_id, lien)
            assert lien["label"].strip(), (c.item_id, lien)


def test_un_lien_n_est_jamais_a_la_fois_ajoute_et_retire():
    for c in cae.CORRECTIONS:
        ajoutes = {lien["url"] for lien in c.liens_a_ajouter}
        assert not (ajoutes & set(c.liens_a_retirer)), c.item_id


def test_des_liens_sont_AJOUTES_a_la_fin(corpus: Path):
    """« Je préférerais trouver des œuvres disponibles sur différentes
    plateformes à donner aux utilisateurs » — pour un corpus sans fiche
    unique, on ouvre la filmographie et deux façons de la regarder."""
    hitch = next(c for c in cae.CORRECTIONS if c.liens_a_ajouter)
    reco = poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": hitch.titre, "status": "validated",
        "links": [{"kind": "info", "label": "Wikipédia",
                   "url": "https://fr.wikipedia.org/wiki/Alfred_Hitchcock"}]})
    cae.executer(apply=True)
    urls = [lien["url"] for lien in json.loads(reco.read_text(encoding="utf-8"))["links"]]
    assert urls[0] == "https://fr.wikipedia.org/wiki/Alfred_Hitchcock"  # inchangé
    assert len(urls) == 1 + len(hitch.liens_a_ajouter)


def test_un_lien_deja_present_n_est_pas_ajoute_deux_fois(corpus: Path):
    hitch = next(c for c in cae.CORRECTIONS if c.liens_a_ajouter)
    deja = dict(hitch.liens_a_ajouter[0])
    reco = poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": hitch.titre, "status": "validated",
        "links": [deja]})
    cae.executer(apply=True)
    urls = [lien["url"] for lien in json.loads(reco.read_text(encoding="utf-8"))["links"]]
    assert urls.count(deja["url"]) == 1


def test_TOUS_les_liens_deja_presents_ne_declenchent_aucune_ecriture(corpus: Path):
    """Une passe rejouee ne doit rien reecrire : c'est ce qui rend l'outil
    sur a relancer apres coup."""
    hitch = next(c for c in cae.CORRECTIONS if c.liens_a_ajouter)
    reco = poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": hitch.titre, "status": "validated",
        "links": [dict(lien) for lien in hitch.liens_a_ajouter]})
    avant = reco.read_text(encoding="utf-8")
    assert cae.executer(apply=True)["recos"] == 0
    assert reco.read_text(encoding="utf-8") == avant


def test_les_liens_a_retirer_sont_des_urls():
    for c in cae.CORRECTIONS:
        for url in c.liens_a_retirer:
            assert url.startswith("https://"), (c.item_id, url)


def test_aucun_item_n_apparait_deux_fois():
    ids = [c.item_id for c in cae.CORRECTIONS]
    assert len(set(ids)) == len(ids)


def test_aucun_titre_n_apparait_deux_fois():
    """Les recos sont rattachees par titre : un doublon rendrait le choix
    dependant de l'ordre de parcours."""
    titres = [c.titre.strip().lower() for c in cae.CORRECTIONS]
    assert len(set(titres)) == len(titres)


# ===== L'item ==============================================================
def test_le_createur_est_corrige(corpus: Path):
    item = poser(corpus, "items", "a", {
        "id": DESIRE.item_id, "title": DESIRE.titre,
        "creator": DESIRE.createur_faux, "types": ["film"]})
    cae.executer(apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["creator"] == "Albert Dupontel"


def test_l_annee_est_corrigee_quand_la_table_en_donne_une(corpus: Path):
    item = poser(corpus, "items", "a", {
        "id": ANGES.item_id, "title": ANGES.titre,
        "creator": ANGES.createur_faux, "year": 1998})
    cae.executer(apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["year"] == 1997


def test_l_identifiant_externe_trompeur_est_retire(corpus: Path):
    """Le compte Instagram etait celui de l'animateur, pas du realisateur."""
    item = poser(corpus, "items", "a", {
        "id": DESIRE.item_id, "title": DESIRE.titre,
        "creator": DESIRE.createur_faux,
        "externalIds": {"instagram": "kyankhojandi", "allocine": "58283"}})
    cae.executer(apply=True)
    externes = json.loads(item.read_text(encoding="utf-8"))["externalIds"]
    assert "instagram" not in externes
    assert externes["allocine"] == "58283"   # le reste est intact


def test_le_reste_du_document_est_intact(corpus: Path):
    item = poser(corpus, "items", "a", {
        "id": DESIRE.item_id, "title": DESIRE.titre,
        "creator": DESIRE.createur_faux, "types": ["film"], "year": 1993})
    cae.executer(apply=True)
    doc = json.loads(item.read_text(encoding="utf-8"))
    assert doc["types"] == ["film"]
    assert doc["year"] == 1993          # pas d'annee dans cette correction


# ===== Les titres et les liens ============================================
def test_un_titre_fautif_est_corrige(corpus: Path):
    """« Shage » venait du transcript ; la chaine du corpus s'appelle
    « PLANET SHAGA »."""
    shaga = next(c for c in cae.CORRECTIONS if c.item_id == "227bf692")
    item = poser(corpus, "items", "a", {
        "id": shaga.item_id, "title": shaga.titre, "types": ["artiste"]})
    cae.executer(apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["title"] == "Shaga"


def test_la_reco_est_retrouvee_par_l_ANCIEN_titre(corpus: Path):
    """Au moment de la passe, elle porte encore la graphie fautive."""
    shaga = next(c for c in cae.CORRECTIONS if c.item_id == "227bf692")
    reco = poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": shaga.titre, "status": "validated"})
    cae.executer(apply=True)
    assert json.loads(reco.read_text(encoding="utf-8"))["title"] == "Shaga"


def test_un_lien_menant_a_une_AUTRE_oeuvre_est_retire(corpus: Path):
    """Le lien Deezer de « Mister Mystère » pointait un single de 2010, pas
    l'album de 2009."""
    mm = next(c for c in cae.CORRECTIONS if c.item_id == "e9d58ce6")
    faux = mm.liens_a_retirer[0]
    reco = poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": mm.titre, "status": "validated",
        "links": [{"kind": "streaming", "label": "Deezer", "url": faux},
                  {"kind": "streaming", "label": "Apple Music",
                   "url": "https://music.apple.com/fr/album/x/1442791256"}]})
    cae.executer(apply=True)
    liens = json.loads(reco.read_text(encoding="utf-8"))["links"]
    assert [lien["url"] for lien in liens] == [
        "https://music.apple.com/fr/album/x/1442791256"]


def test_les_AUTRES_liens_sont_intacts(corpus: Path):
    mm = next(c for c in cae.CORRECTIONS if c.item_id == "e9d58ce6")
    liens = [{"kind": "info", "label": "MusicBrainz", "url": "https://musicbrainz.org/x"},
             {"kind": "social", "label": "Instagram", "url": "https://instagram.com/y"}]
    reco = poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": mm.titre, "status": "validated",
        "links": [dict(lien) for lien in liens]})
    rapport = cae.executer(apply=True)
    assert json.loads(reco.read_text(encoding="utf-8"))["links"] == liens
    assert rapport["recos"] == 0     # rien a retirer, rien a ecrire


# ===== La portee ===========================================================
def test_un_createur_DEJA_correct_n_est_pas_reecrit(corpus: Path):
    item = poser(corpus, "items", "a", {
        "id": DESIRE.item_id, "title": DESIRE.titre, "creator": "Albert Dupontel"})
    avant = item.read_text(encoding="utf-8")
    rapport = cae.executer(apply=True)
    assert item.read_text(encoding="utf-8") == avant
    assert rapport["items"] == 0


def test_un_createur_INATTENDU_n_est_pas_ecrase(corpus: Path):
    """La table corrige UNE valeur fautive connue. Si le champ porte autre
    chose, quelqu'un est passe apres : on ne sait plus quoi corriger."""
    item = poser(corpus, "items", "a", {
        "id": DESIRE.item_id, "title": DESIRE.titre, "creator": "Quelqu'un d'autre"})
    cae.executer(apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["creator"] == "Quelqu'un d'autre"


def test_une_oeuvre_HORS_TABLE_n_est_pas_touchee(corpus: Path):
    item = poser(corpus, "items", "a", {
        "id": "zzzzzzzz", "title": "Autre chose", "creator": "Netflix"})
    avant = item.read_text(encoding="utf-8")
    cae.executer(apply=True)
    assert item.read_text(encoding="utf-8") == avant


def test_la_simulation_n_ecrit_rien(corpus: Path):
    item = poser(corpus, "items", "a", {
        "id": DESIRE.item_id, "title": DESIRE.titre,
        "creator": DESIRE.createur_faux})
    avant = item.read_text(encoding="utf-8")
    rapport = cae.executer(apply=False)
    assert rapport["items"] == 1                       # le rapport annonce
    assert item.read_text(encoding="utf-8") == avant   # rien n'est ecrit


# ===== Les recos ===========================================================
def test_la_reco_est_corrigee_par_son_titre(corpus: Path):
    reco = poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": DESIRE.titre, "creator": DESIRE.createur_faux,
        "status": "validated"})
    rapport = cae.executer(apply=True)
    assert json.loads(reco.read_text(encoding="utf-8"))["creator"] == "Albert Dupontel"
    assert rapport["recos"] == 1


def test_le_titre_est_compare_sans_la_casse(corpus: Path):
    reco = poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": DESIRE.titre.upper(),
        "creator": DESIRE.createur_faux, "status": "validated"})
    cae.executer(apply=True)
    assert json.loads(reco.read_text(encoding="utf-8"))["creator"] == "Albert Dupontel"


def test_une_reco_ECARTEE_n_est_pas_touchee(corpus: Path):
    reco = poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": DESIRE.titre, "creator": DESIRE.createur_faux,
        "status": "discarded"})
    avant = reco.read_text(encoding="utf-8")
    cae.executer(apply=True)
    assert reco.read_text(encoding="utf-8") == avant


def test_une_reco_HORS_TABLE_n_est_pas_touchee(corpus: Path):
    reco = poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": "Un titre sans rapport", "creator": "Netflix",
        "status": "validated"})
    avant = reco.read_text(encoding="utf-8")
    cae.executer(apply=True)
    assert reco.read_text(encoding="utf-8") == avant


def test_une_reco_hors_table_n_interrompt_pas_le_parcours(corpus: Path):
    """Le corpus compte 3 100 recos pour trois corrections : l'immense
    majorite est ignoree, et la passe doit continuer jusqu'au bout."""
    poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": "Sans rapport", "creator": "X",
        "status": "validated"})
    cible = poser(corpus, "recos", "2", {
        "id": "ubm-2", "title": ANGES.titre, "creator": ANGES.createur_faux,
        "status": "validated"})
    assert cae.executer(apply=True)["recos"] == 1
    assert json.loads(cible.read_text(encoding="utf-8"))["creator"] == "Jean-Pierre Thorn"


def test_une_reco_DEJA_correcte_n_est_pas_reecrite(corpus: Path):
    reco = poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": DESIRE.titre, "creator": "Albert Dupontel",
        "status": "validated"})
    avant = reco.read_text(encoding="utf-8")
    assert cae.executer(apply=True)["recos"] == 0
    assert reco.read_text(encoding="utf-8") == avant


def test_un_externalIds_sans_la_cle_visee_est_laisse_tel_quel(corpus: Path):
    item = poser(corpus, "items", "a", {
        "id": DESIRE.item_id, "title": DESIRE.titre,
        "creator": DESIRE.createur_faux, "externalIds": {"allocine": "58283"}})
    cae.executer(apply=True)
    assert json.loads(item.read_text(encoding="utf-8"))["externalIds"] == {
        "allocine": "58283"}


def test_la_simulation_parcourt_TOUTES_les_recos(corpus: Path):
    """Le dry-run doit annoncer l'ensemble du travail, pas s'arreter a la
    premiere correction — c'est sur ce rapport que la decision se prend."""
    a = poser(corpus, "recos", "1", {
        "id": "ubm-1", "title": DESIRE.titre, "creator": DESIRE.createur_faux,
        "status": "validated"})
    b = poser(corpus, "recos", "2", {
        "id": "ubm-2", "title": ANGES.titre, "creator": ANGES.createur_faux,
        "status": "validated"})
    avant = (a.read_text(encoding="utf-8"), b.read_text(encoding="utf-8"))
    assert cae.executer(apply=False)["recos"] == 2
    assert (a.read_text(encoding="utf-8"), b.read_text(encoding="utf-8")) == avant


def test_la_passe_est_idempotente(corpus: Path):
    poser(corpus, "items", "a", {
        "id": DESIRE.item_id, "title": DESIRE.titre,
        "creator": DESIRE.createur_faux})
    cae.executer(apply=True)
    assert cae.executer(apply=True) == {"items": 0, "recos": 0, "champs": []}


def test_un_json_illisible_est_ignore(corpus: Path):
    poser(corpus, "items", "a", {
        "id": DESIRE.item_id, "title": DESIRE.titre,
        "creator": DESIRE.createur_faux})
    (corpus / "items" / "casse.json").write_text("{ pas du json", encoding="utf-8")
    (corpus / "recos" / "casse.json").write_text("{{{", encoding="utf-8")
    assert cae.executer(apply=True)["items"] == 1


def test_des_externalIds_absents_ne_font_pas_echouer(corpus: Path):
    poser(corpus, "items", "a", {
        "id": DESIRE.item_id, "title": DESIRE.titre,
        "creator": DESIRE.createur_faux, "externalIds": None})
    assert cae.executer(apply=True)["items"] == 1


# ===== CLI =================================================================
def test_main_applique(corpus: Path):
    item = poser(corpus, "items", "a", {
        "id": DESIRE.item_id, "title": DESIRE.titre,
        "creator": DESIRE.createur_faux})
    assert cae.main(["--apply"]) == 0
    assert json.loads(item.read_text(encoding="utf-8"))["creator"] == "Albert Dupontel"


def test_main_dry_run(corpus: Path):
    item = poser(corpus, "items", "a", {
        "id": DESIRE.item_id, "title": DESIRE.titre,
        "creator": DESIRE.createur_faux})
    avant = item.read_text(encoding="utf-8")
    assert cae.main([]) == 0
    assert item.read_text(encoding="utf-8") == avant
