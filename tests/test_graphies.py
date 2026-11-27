"""Registre des graphies corrigées (`tools/graphies.py`, décision R6 A du 2026-11-27).

Cas réels qui l'ont motivé : sur S6-E10, « Hilleret » pour Hillairet, et sur
S5-E37 « Gat Buzzy » pour Get Busy, corrigés à la main en relecture puis perdus
pour les épisodes suivants.
"""
from __future__ import annotations

import json

import pytest

import common
import graphies

SOURCE = "demo"
# Pris avant que `conftest` ne le détourne vers un dossier temporaire.
_DOSSIER_REEL = graphies._dossier
GUID = "yt-abc"


@pytest.fixture
def sortie(tmp_path, monkeypatch):
    """Dossier de sortie temporaire : jamais le vrai registre de venus."""
    monkeypatch.setattr(common, "OUTPUT_DIR", tmp_path)
    return tmp_path / "graphies"


def _reco(**champs):
    base = {"id": "ubm-0001", "episodeGuid": GUID, "status": "validated",
            "title": "Le Titre", "types": ["film"]}
    base.update(champs)
    return base


def _draft(**champs):
    return _reco(status="draft", **champs)


def _ecrire_reco(tmp_path, monkeypatch, nom, reco):
    """Une reco dans un dossier de recos temporaire (`common.RECOS_DIR`)."""
    recos = tmp_path / "recos"
    (recos / SOURCE).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(common, "RECOS_DIR", recos)
    (recos / SOURCE / nom).write_text(json.dumps(reco), encoding="utf-8")


# ----- corrections : ce que la relecture a changé --------------------------

def test_un_nom_propre_corrige_est_retenu():
    avant = _reco(creator="Pierre Hilleret")
    apres = _reco(creator="Pierre Hillairet")
    assert graphies.corrections(avant, apres) == [
        {"fausse": "Hilleret", "juste": "Hillairet", "champ": "creator"}]


def test_plusieurs_mots_remplaces_ensemble():
    avant = _reco(title="Gat Buzzy")
    apres = _reco(title="Get Busy")
    assert graphies.corrections(avant, apres) == [
        {"fausse": "Gat Buzzy", "juste": "Get Busy", "champ": "title"}]


def test_une_reformulation_n_est_pas_une_graphie():
    avant = _reco(quote="C'est un super film.")
    apres = _reco(quote="C'est un très bon film.")
    assert graphies.corrections(avant, apres) == []


def test_une_autre_oeuvre_n_est_pas_une_graphie():
    avant = _reco(title="Dark Matter")
    apres = _reco(title="Interstellar")
    assert graphies.corrections(avant, apres) == []


def test_une_citation_raccourcie_ne_donne_rien():
    avant = _reco(quote="Alors franchement, Waly Dia, c'est génial, allez-y.")
    apres = _reco(quote="Waly Dia, c'est génial.")
    assert graphies.corrections(avant, apres) == []


def test_dans_une_citation_seuls_les_noms_propres_comptent():
    avant = _reco(quote="J'adore Wally Dia, il est drole.")
    apres = _reco(quote="J'adore Waly Dia, il est drôle.")
    assert graphies.corrections(avant, apres) == [
        {"fausse": "Wally", "juste": "Waly", "champ": "quote"}]


def test_un_petit_mot_courant_n_est_pas_une_graphie():
    avant = _reco(title="Le Misérables")
    apres = _reco(title="Les Misérables")
    assert graphies.corrections(avant, apres) == []


def test_une_forme_fautive_de_moins_de_quatre_signes_est_ecartee():
    assert graphies.corrections(_reco(creator="Bob"), _reco(creator="Rob")) == []


def test_une_forme_fautive_de_mots_courants_est_ecartee_meme_longue():
    avant = _reco(title="De la")
    apres = _reco(title="Des Lois")
    assert graphies.corrections(avant, apres) == []


def test_le_filtre_des_noms_propres_vaut_pour_tous_les_champs():
    avant = _reco(title="Hilleret et fils")
    apres = _reco(title="hillairet et fils")
    assert graphies.corrections(avant, apres) == []


def test_une_simple_casse_n_est_pas_retenue():
    assert graphies.corrections(_reco(creator="orelsan"), _reco(creator="Orelsan")) == []


# ----- brouillon gardé à l'extraction --------------------------------------

def _lu(sortie, reco_id="ubm-0001"):
    return json.loads((sortie / "brouillons" / SOURCE / f"{reco_id}.json")
                      .read_text(encoding="utf-8"))


def test_un_nouveau_passage_ecrase_le_brouillon_d_une_reco_encore_a_relire(sortie):
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    assert graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hillairet")) is True
    garde = _lu(sortie)
    assert garde["creator"] == "Pierre Hillairet"
    assert garde["episodeGuid"] == GUID
    assert "links" not in garde


def test_le_brouillon_d_une_reco_relue_n_est_jamais_ecrase(sortie):
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    for statut in ("validated", "discarded"):
        assert graphies.garder_brouillon(
            SOURCE, _reco(status=statut, creator="Pierre Hillairet")) is False
    assert _lu(sortie)["creator"] == "Pierre Hilleret"


def test_une_reco_sans_statut_compte_comme_un_brouillon(sortie):
    reco = _draft(creator="Pierre Hilleret")
    del reco["status"]
    assert graphies.garder_brouillon(SOURCE, reco) is True


def test_le_brouillon_de_l_episode_ne_garde_que_ses_recos_en_brouillon(
        tmp_path, monkeypatch, sortie):
    _ecrire_reco(tmp_path, monkeypatch, "0001.json", _draft(creator="Pierre Hilleret"))
    _ecrire_reco(tmp_path, monkeypatch, "0002.json", _draft(id="ubm-0002", episodeGuid="yt-autre"))
    _ecrire_reco(tmp_path, monkeypatch, "0003.json", _reco(id="ubm-0003"))
    _ecrire_reco(tmp_path, monkeypatch, "0004.json", ["pas", "une", "reco"])
    assert graphies.garder_brouillons_episode(SOURCE, GUID) == 1
    assert _lu(sortie)["creator"] == "Pierre Hilleret"
    assert sorted(p.name for p in (sortie / "brouillons" / SOURCE).iterdir()) == ["ubm-0001.json"]


def test_une_reco_illisible_ne_bloque_pas_les_brouillons_des_autres(
        tmp_path, monkeypatch, sortie, caplog):
    _ecrire_reco(tmp_path, monkeypatch, "0001.json", _draft())
    (common.RECOS_DIR / SOURCE / "0002.json").write_text("{pas du json", encoding="utf-8")
    assert graphies.garder_brouillons_episode(SOURCE, GUID) == 1
    assert "0002.json" in caplog.text and GUID in caplog.text


def test_pas_de_dossier_de_recos_pas_de_brouillon(tmp_path, monkeypatch, sortie):
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "absent")
    assert graphies.garder_brouillons_episode(SOURCE, GUID) == 0


def test_un_dossier_de_recos_illisible_est_journalise(monkeypatch, sortie, caplog):
    class Illisible:
        def glob(self, _motif):
            raise OSError("accès refusé")
    monkeypatch.setattr(common, "recos_dir_for", lambda _source: Illisible())
    assert graphies.garder_brouillons_episode(SOURCE, GUID) == 0
    assert GUID in caplog.text


# ----- enregistrer : à la finalisation --------------------------------------

def test_la_finalisation_remplit_le_registre(sortie):
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    n = graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")])
    assert n == 1
    assert graphies.charger() == [{
        "fausse": "Hilleret", "juste": "Hillairet", "champs": ["creator"],
        "episodes": [GUID], "vu": 1}]


def test_une_meme_correction_vue_deux_fois_se_cumule(sortie):
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")])
    graphies.garder_brouillon(SOURCE, _draft(id="ubm-0002", episodeGuid="yt-def",
                                             quote="Hilleret est génial."))
    graphies.enregistrer(SOURCE, "yt-def", [_reco(id="ubm-0002", episodeGuid="yt-def",
                                                  quote="Hillairet est génial.")])
    [entree] = graphies.charger()
    assert entree["vu"] == 2
    assert entree["episodes"] == [GUID, "yt-def"]
    assert entree["champs"] == ["creator", "quote"]


def test_un_episode_finalise_deux_fois_ne_compte_qu_une_fois(sortie):
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")])
    assert graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")]) == 0
    assert graphies.charger()[0]["vu"] == 1


def test_une_reco_ecartee_ou_sans_brouillon_est_ignoree(sortie):
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    ecartee = _reco(creator="Pierre Hillairet", status="discarded")
    sans_brouillon = _reco(id="ubm-0009", creator="Jean Valjean")
    assert graphies.enregistrer(SOURCE, GUID, [ecartee, sans_brouillon]) == 0
    assert graphies.charger() == []


def test_un_brouillon_d_un_autre_episode_est_ignore(sortie, caplog):
    """Les identifiants de reco sont réutilisés après une suppression."""
    graphies.garder_brouillon(SOURCE, _draft(episodeGuid="yt-ancien", creator="Pierre Hilleret"))
    assert graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")]) == 0
    assert graphies.charger() == []
    assert "ubm-0001" in caplog.text and "yt-ancien" in caplog.text


def test_un_brouillon_sans_episode_est_ignore(sortie):
    chemin = sortie / "brouillons" / SOURCE / "ubm-0001.json"
    chemin.parent.mkdir(parents=True)
    chemin.write_text(json.dumps({"creator": "Pierre Hilleret"}), encoding="utf-8")
    assert graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")]) == 0


def test_un_brouillon_illisible_ne_bloque_pas_les_autres_recos(sortie, caplog):
    graphies.garder_brouillon(SOURCE, _draft(id="ubm-0002", creator="Pierre Hilleret"))
    (sortie / "brouillons" / SOURCE / "ubm-0001.json").write_text("{pas du json", encoding="utf-8")
    (sortie / "brouillons" / SOURCE / "ubm-0003.json").write_text("[1, 2]", encoding="utf-8")
    recos = [_reco(creator="Pierre Hillairet"),
             _reco(id="ubm-0003", creator="Jean"),
             _reco(id="ubm-0002", creator="Pierre Hillairet")]
    assert graphies.enregistrer(SOURCE, GUID, recos) == 1
    assert "ubm-0001" in caplog.text and "ubm-0003" in caplog.text


def test_registre_absent_ou_illisible_vaut_vide(sortie):
    assert graphies.charger() == []
    sortie.mkdir(parents=True)
    (sortie / "registre.json").write_text("{pas du json", encoding="utf-8")
    assert graphies.charger() == []


# ----- propositions : à la relecture des épisodes suivants ------------------

REGISTRE = [{"fausse": "Hilleret", "juste": "Hillairet", "champs": ["creator"],
             "episodes": [GUID], "vu": 2}]


def test_une_graphie_deja_corrigee_est_proposee():
    reco = _reco(status="draft", quote="Le film de Hilleret, allez le voir.")
    assert graphies.propositions(reco, REGISTRE) == [("Hilleret", "Hillairet", 2)]


def test_pas_de_proposition_au_milieu_d_un_mot():
    reco = _reco(status="draft", quote="Les Hillerets sont là.")
    assert graphies.propositions(reco, REGISTRE) == []


def test_pas_de_proposition_quand_la_bonne_graphie_est_la():
    reco = _reco(status="draft", creator="Hillairet", quote="Hillairet, pas Hilleret.")
    assert graphies.propositions(reco, REGISTRE) == []


def test_une_forme_fautive_a_majuscule_se_cherche_avec_sa_casse():
    """Remplace `test_la_casse_n_empeche_pas_la_proposition` : « Les » n'est pas « les »."""
    reco = _reco(status="draft", title="hilleret")
    assert graphies.propositions(reco, REGISTRE) == []
    assert graphies.propositions(_reco(status="draft", title="Hilleret"), REGISTRE) == [
        ("Hilleret", "Hillairet", 2)]


def test_une_forme_fautive_en_minuscules_se_cherche_sans_tenir_compte_de_la_casse():
    registre = [{"fausse": "gat buzzy", "juste": "Get Busy", "vu": 1}]
    assert graphies.propositions(_reco(status="draft", title="GAT BUZZY"), registre) == [
        ("gat buzzy", "Get Busy", 1)]


def test_pas_de_proposition_si_la_bonne_graphie_est_dans_un_autre_champ():
    reco = _reco(status="draft", creator="Hillairet", quote="Un film de Hilleret.")
    assert graphies.propositions(reco, REGISTRE) == []


# ----- erreurs : le registre ne bloque jamais la chaîne ----------------------

def test_un_brouillon_impossible_a_ecrire_ne_bloque_pas(sortie, monkeypatch, caplog):
    def refuse(*_a, **_k):
        raise OSError("disque plein")
    monkeypatch.setattr(graphies, "write_json_if_changed", refuse)
    graphies.garder_brouillon(SOURCE, _draft())
    assert "ubm-0001" in caplog.text


def test_une_reco_sans_identifiant_n_a_pas_de_brouillon(sortie):
    graphies.garder_brouillon(SOURCE, {"title": "Sans id"})
    assert not (sortie / "brouillons").exists()


def test_noter_un_episode_journalise_une_panne_sans_la_remonter(monkeypatch, caplog):
    def panne(*_a, **_k):
        raise ValueError("registre cassé")
    monkeypatch.setattr(graphies, "enregistrer", panne)
    assert graphies.noter_episode(SOURCE, GUID, []) == 0
    assert GUID in caplog.text


def test_noter_un_episode_rend_les_nouveautes(sortie):
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    assert graphies.noter_episode(SOURCE, GUID, [_reco(creator="Pierre Hillairet")]) == 1


def test_le_registre_ne_garde_que_les_entrees_utilisables(sortie, caplog):
    sortie.mkdir(parents=True)
    bonne = {"fausse": "Hilleret", "juste": "Hillairet", "champs": ["creator"],
             "episodes": [GUID], "vu": 1}
    brutes = [bonne, "texte", None, {"fausse": "Hilleret"}, {"fausse": "", "juste": "x"},
              {"fausse": 3, "juste": "x"}, {"fausse": "Navo", "juste": "Bruno Muschio"},
              {"fausse": "Gat", "juste": "Get", "champs": "creator", "episodes": 4, "vu": True}]
    (sortie / "registre.json").write_text(json.dumps({"entrees": brutes}), encoding="utf-8")
    assert graphies.charger() == [
        bonne,
        {"fausse": "Navo", "juste": "Bruno Muschio", "champs": [], "episodes": [], "vu": 0},
        {"fausse": "Gat", "juste": "Get", "champs": [], "episodes": [], "vu": 0}]
    assert "5 entrée(s) mal formée(s)" in caplog.text


def test_des_entrees_qui_ne_sont_pas_une_liste_valent_vide(sortie, caplog):
    sortie.mkdir(parents=True)
    (sortie / "registre.json").write_text(json.dumps({"entrees": {"a": 1}}), encoding="utf-8")
    assert graphies.charger() == []
    assert "pas une liste" in caplog.text


def test_un_registre_sans_entrees_vaut_vide(sortie):
    sortie.mkdir(parents=True)
    (sortie / "registre.json").write_text("{}", encoding="utf-8")
    assert graphies.charger() == []


def test_un_registre_mal_forme_ne_bloque_pas_la_mise_a_jour(sortie):
    sortie.mkdir(parents=True)
    (sortie / "registre.json").write_text(json.dumps({"entrees": ["texte", {"fausse": "x"}]}),
                                          encoding="utf-8")
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    assert graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")]) == 1
    assert [e["fausse"] for e in graphies.charger()] == ["Hilleret"]


# ----- le cache de la relecture ------------------------------------------------

def test_le_registre_n_est_relu_que_s_il_change(sortie, monkeypatch):
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")])
    lectures = []
    lire = graphies._lire
    monkeypatch.setattr(graphies, "_lire", lambda: lectures.append(1) or lire())
    premiere = graphies.charger()
    assert graphies.charger() is premiere
    assert len(lectures) == 1


def test_le_cache_suit_une_mise_a_jour_du_registre(sortie):
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")])
    assert graphies.charger()[0]["vu"] == 1
    graphies.garder_brouillon(SOURCE, _draft(id="ubm-0002", episodeGuid="yt-def",
                                             creator="Paul Hilleret"))
    graphies.enregistrer(SOURCE, "yt-def", [_reco(id="ubm-0002", episodeGuid="yt-def",
                                                  creator="Paul Hillairet")])
    assert graphies.charger()[0]["vu"] == 2


def test_enregistrer_ne_modifie_pas_la_liste_du_cache(sortie):
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")])
    en_cache = graphies.charger()
    photo = json.loads(json.dumps(en_cache))
    graphies.garder_brouillon(SOURCE, _draft(id="ubm-0002", episodeGuid="yt-def",
                                             quote="Hilleret est génial."))
    graphies.enregistrer(SOURCE, "yt-def", [_reco(id="ubm-0002", episodeGuid="yt-def",
                                                  quote="Hillairet est génial.")])
    assert en_cache == photo


def test_une_entree_incomplete_du_registre_est_ignoree():
    assert graphies.propositions(_reco(title="Hilleret"), [{"fausse": "Hilleret"}]) == []


# ----- branchements ------------------------------------------------------------

def test_l_extraction_ne_garde_pas_encore_le_brouillon(tmp_path, monkeypatch):
    """Avant la réécoute et le calage des citations, le brouillon serait trop tôt."""
    import extract_recos
    recos = tmp_path / "recos"
    (recos / "un-bon-moment").mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", recos)
    extract_recos._persist_recos("un-bon-moment", "EP001",
                                 [{"title": "Get Buzzy", "type": "album", "creator": "Hilleret"}])
    assert not (tmp_path / "graphies").exists()


def test_la_chaine_garde_le_brouillon_apres_la_reecoute_et_le_calage(tmp_path, monkeypatch):
    import traiter_nouveaux_episodes as chaine
    ordre = []

    def preciseur(*_a, **_k):
        ordre.append("réécoute")
        return type("R", (), {"precisees": []})()

    def caleur(*_a, **_k):
        ordre.append("calage")

    monkeypatch.setattr(chaine, "_resume_calage", lambda _r: "")
    monkeypatch.setattr(chaine, "_remove_audio", lambda *_a: None)
    monkeypatch.setattr(graphies, "garder_brouillons_episode",
                        lambda source, guid: ordre.append(("brouillons", source, guid)))
    chaine._extract_one(SOURCE, tmp_path / "ep.json", {"guid": GUID, "title": "Ep"},
                        {"lastErrors": {}, "extracted": []}, lambda msg: ordre.append("notify"),
                        extractor=lambda *_a, **_k: 1, client=None, source=None,
                        model="m", secours=None, preciseur=preciseur, caleur=caleur,
                        review_url="http://relecture")
    assert ordre == ["réécoute", "calage", ("brouillons", SOURCE, GUID), "notify"]


def test_la_publication_d_un_episode_remplit_le_registre(tmp_path, monkeypatch):
    import publier_episode
    content = tmp_path / "content"
    monkeypatch.setattr(common, "CONTENT_DIR", content)
    monkeypatch.setattr(common, "RECOS_DIR", content / "recos")
    for sub in ("recos", "items", "mentions"):
        (content / sub / SOURCE).mkdir(parents=True)
    reco = _reco(sourceId=SOURCE, creator="Pierre Hillairet")
    (content / "recos" / SOURCE / "0001.json").write_text(json.dumps(reco), encoding="utf-8")
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    plan = publier_episode.preparer(SOURCE, GUID, apply=True)
    assert not plan.errors
    assert graphies.charger()[0]["juste"] == "Hillairet"


def test_la_simulation_de_publication_n_ecrit_pas_le_registre(tmp_path, monkeypatch):
    import publier_episode
    content = tmp_path / "content"
    monkeypatch.setattr(common, "CONTENT_DIR", content)
    monkeypatch.setattr(common, "RECOS_DIR", content / "recos")
    for sub in ("recos", "items", "mentions"):
        (content / sub / SOURCE).mkdir(parents=True)
    reco = _reco(sourceId=SOURCE, creator="Pierre Hillairet")
    (content / "recos" / SOURCE / "0001.json").write_text(json.dumps(reco), encoding="utf-8")
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    publier_episode.preparer(SOURCE, GUID, apply=False)
    assert graphies.charger() == []


def test_la_relecture_affiche_la_graphie_deja_corrigee():
    import review_signals
    reco = _reco(status="draft", creator="Hilleret")
    signaux = review_signals.reco_signals(reco, {"title": "Épisode"}, [], [], registre=REGISTRE)
    [graphie] = [s for s in signaux if s.kind == "graphie"]
    assert graphie.message == "Graphie déjà corrigée : « Hilleret » → « Hillairet » (vue 2 fois)."
    assert review_signals.reco_signals(reco, {"title": "Épisode"}, [], []) == [
        s for s in signaux if s.kind != "graphie"]


def test_une_reco_validee_n_affiche_plus_de_graphie():
    import review_signals
    reco = _reco(status="validated", creator="Hilleret")
    signaux = review_signals.reco_signals(reco, {"title": "Épisode"}, [], [], registre=REGISTRE)
    assert [s for s in signaux if s.kind == "graphie"] == []


def test_le_vrai_registre_vit_hors_de_git_dans_tools_output():
    assert _DOSSIER_REEL() == common.OUTPUT_DIR / "graphies"


def test_noter_un_episode_sans_correction_ne_dit_rien(sortie):
    assert graphies.noter_episode(SOURCE, GUID, [_reco()]) == 0
    assert graphies.charger() == []


# ----- tour 2 de la revue de la PR #217 --------------------------------------

def _registre_ecrit(sortie, contenu):
    sortie.mkdir(parents=True, exist_ok=True)
    chemin = sortie / "registre.json"
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def test_un_registre_illisible_n_est_jamais_ecrase(sortie, caplog):
    chemin = _registre_ecrit(sortie, "{pas du json")
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    assert graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")]) == 0
    assert chemin.read_text(encoding="utf-8") == "{pas du json"
    assert "registre.json" in caplog.text and GUID in caplog.text and SOURCE in caplog.text


def test_un_registre_dont_les_entrees_ne_sont_pas_une_liste_n_est_pas_ecrase(sortie):
    contenu = json.dumps({"entrees": {"a": 1}})
    chemin = _registre_ecrit(sortie, contenu)
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    assert graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")]) == 0
    assert chemin.read_text(encoding="utf-8") == contenu


def test_un_registre_illisible_n_est_pas_mis_en_cache(sortie):
    chemin = _registre_ecrit(sortie, "{pas du json")
    assert graphies.charger() == []
    bonne = {"fausse": "Hilleret", "juste": "Hillairet", "champs": [], "episodes": [], "vu": 3}
    chemin.write_text(json.dumps({"entrees": [bonne]}), encoding="utf-8")
    assert graphies.charger() == [bonne]


def test_un_echec_passager_de_lecture_ne_fait_pas_oublier_le_registre(sortie, monkeypatch):
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")])
    assert graphies.charger()[0]["fausse"] == "Hilleret"
    lire = graphies._lire

    def refuse():
        raise graphies.RegistreIllisible("verrouillé")
    monkeypatch.setattr(graphies, "_lire", refuse)
    # Le fichier n'a pas changé : seul un cache à jour le dirait, et il ne doit
    # pas masquer l'échec suivant ; on force donc la relecture.
    graphies._cache["cle"] = None
    assert graphies.charger() == []
    monkeypatch.setattr(graphies, "_lire", lire)
    assert graphies.charger()[0]["fausse"] == "Hilleret"


def test_les_entrees_mal_formees_restent_dans_le_fichier_reecrit(sortie):
    mal_formees = ["texte", {"fausse": "x"}]
    chemin = _registre_ecrit(sortie, json.dumps({"entrees": mal_formees}))
    graphies.garder_brouillon(SOURCE, _draft(creator="Pierre Hilleret"))
    assert graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")]) == 1
    ecrites = json.loads(chemin.read_text(encoding="utf-8"))["entrees"]
    assert ecrites[0]["fausse"] == "Hilleret"
    assert ecrites[1:] == mal_formees


def test_un_champ_qui_n_est_pas_une_chaine_est_ignore_sans_perdre_l_episode(sortie, caplog):
    graphies.garder_brouillon(SOURCE, _draft(id="ubm-0001", creator=5, title="Gat Buzzy"))
    graphies.garder_brouillon(SOURCE, _draft(id="ubm-0002", creator="Pierre Hilleret"))
    recos = [_reco(id="ubm-0001", creator="Pierre Hillairet", title="Get Busy"),
             _reco(id="ubm-0002", creator="Pierre Hillairet")]
    assert graphies.enregistrer(SOURCE, GUID, recos) == 2
    assert sorted(e["fausse"] for e in graphies.charger()) == ["Gat Buzzy", "Hilleret"]
    assert "ubm-0001" in caplog.text and "creator" in caplog.text
    assert SOURCE in caplog.text and "ubm-0001.json" in caplog.text


def test_un_champ_de_la_reco_validee_qui_n_est_pas_une_chaine_est_ignore(sortie, caplog):
    graphies.garder_brouillon(SOURCE, _draft(id="ubm-0001", quote="Hilleret"))
    graphies.garder_brouillon(SOURCE, _draft(id="ubm-0002", creator="Pierre Hilleret"))
    recos = [_reco(id="ubm-0001", quote=["liste"]),
             _reco(id="ubm-0002", creator="Pierre Hillairet")]
    assert graphies.enregistrer(SOURCE, GUID, recos) == 1
    assert "ubm-0001" in caplog.text and "quote" in caplog.text


def test_une_forme_fautive_en_capitales_se_trouve_dans_un_titre_en_capitales():
    reco = _reco(status="draft", title="LE FILM DE HILLERET")
    assert graphies.propositions(reco, REGISTRE) == [("Hilleret", "Hillairet", 2)]
    assert graphies.propositions(_reco(status="draft", title="film de hilleret"), REGISTRE) == []
    assert graphies.propositions(_reco(status="draft", title="HILLERETS"), REGISTRE) == []


def test_une_ancienne_entree_courte_ou_banale_n_est_plus_proposee():
    registre = [{"fausse": "Le", "juste": "Les", "vu": 4},
                {"fausse": "Léa", "juste": "Lea", "vu": 1},
                {"fausse": "Le De", "juste": "Les Des", "vu": 1}]
    reco = _reco(status="draft", title="Le Léa Le De")
    assert graphies.propositions(reco, registre) == []


def test_un_brouillon_non_garde_cite_la_source_et_le_fichier(sortie, monkeypatch, caplog):
    def refuse(*_a, **_k):
        raise OSError("disque plein")
    monkeypatch.setattr(graphies, "write_json_if_changed", refuse)
    graphies.garder_brouillon(SOURCE, _draft())
    assert SOURCE in caplog.text and "ubm-0001.json" in caplog.text


def test_un_brouillon_illisible_cite_la_source_et_le_fichier(sortie, caplog):
    chemin = sortie / "brouillons" / SOURCE / "ubm-0001.json"
    chemin.parent.mkdir(parents=True)
    chemin.write_text("{pas du json", encoding="utf-8")
    graphies.enregistrer(SOURCE, GUID, [_reco(creator="Pierre Hillairet")])
    assert SOURCE in caplog.text and "ubm-0001.json" in caplog.text


def test_une_erreur_inattendue_sur_une_reco_n_arrete_pas_les_autres(
        tmp_path, monkeypatch, sortie, caplog):
    _ecrire_reco(tmp_path, monkeypatch, "0001.json", _draft())
    _ecrire_reco(tmp_path, monkeypatch, "0002.json", _draft(id="ubm-0002"))
    reel = graphies.garder_brouillon

    def casse(source_id, reco):
        if reco["id"] == "ubm-0001":
            raise TypeError("inattendu")
        return reel(source_id, reco)
    monkeypatch.setattr(graphies, "garder_brouillon", casse)
    assert graphies.garder_brouillons_episode(SOURCE, GUID) == 1
    assert SOURCE in caplog.text and GUID in caplog.text and "0001.json" in caplog.text


def _lancer_chaine(tmp_path, monkeypatch, *, preciseur, caleur):
    import traiter_nouveaux_episodes as chaine
    messages = []
    monkeypatch.setattr(chaine, "_remove_audio", lambda *_a: None)
    monkeypatch.setattr(chaine, "_resume_calage", lambda _r: "")
    chaine._extract_one(SOURCE, tmp_path / "ep.json", {"guid": GUID, "title": "Ep"},
                        {"lastErrors": {}, "extracted": []}, messages.append,
                        extractor=lambda *_a, **_k: 1, client=None, source=None,
                        model="m", secours=None, preciseur=preciseur, caleur=caleur,
                        review_url="http://relecture")
    return messages


def test_la_reecoute_et_le_calage_en_panne_n_empechent_ni_brouillon_ni_notification(
        tmp_path, monkeypatch, sortie):
    _ecrire_reco(tmp_path, monkeypatch, "0001.json", _draft(creator="Pierre Hilleret"))

    def panne(*_a, **_k):
        raise RuntimeError("panne")
    messages = _lancer_chaine(tmp_path, monkeypatch, preciseur=panne, caleur=panne)
    assert _lu(sortie)["creator"] == "Pierre Hilleret"
    assert len(messages) == 1 and "1 reco(s) à valider" in messages[0]


def test_une_erreur_interne_des_brouillons_n_empeche_pas_la_notification(
        tmp_path, monkeypatch, sortie):
    _ecrire_reco(tmp_path, monkeypatch, "0001.json", _draft())

    def casse(*_a, **_k):
        raise KeyError("inattendu")
    monkeypatch.setattr(graphies, "garder_brouillon", casse)
    messages = _lancer_chaine(
        tmp_path, monkeypatch,
        preciseur=lambda *_a, **_k: type("R", (), {"precisees": []})(),
        caleur=lambda *_a, **_k: type("C", (), {"calees": []})())
    assert len(messages) == 1 and "reco(s) à valider" in messages[0]
