"""Tests de `tools/bord_afaire.py` — la liste « À faire d'abord » du tableau de bord.

Le module est pur : chaque test lui donne ses données en dictionnaires, sans
disque ni réseau.
"""
from __future__ import annotations

import pytest

import bord_afaire as ba

EP10 = {"guid": "yt-10", "title": "Dix (Un Bon Moment, S6-E10)", "season": 6, "number": 10}
EP11 = {"guid": "yt-11", "title": "Onze", "season": 6, "number": 11}
EP12 = {"guid": "yt-12", "title": "Douze", "season": 6, "number": 12}
TOUT_COCHE = dict.fromkeys(("instagram", "threads", "spotify", "deezer", "senscritique",
                            "youtube"), "2026-11-28T09:30:00+00:00")


def _appel(**kw):
    """Tout connu et rien à faire, sauf ce que le test change."""
    args = {"episodes": {}, "groups": {}, "recents": [], "coches": {},
            "signalements": [], "liens": [], "sorties": []}
    args.update(kw)
    return ba.a_faire(**args)


def _textes(items):
    return [i["texte"] for i in items]


def test_la_liste_vide_quand_tout_est_connu_et_fait():
    assert _appel() == []
    recent = {"guid": "yt-11", "fusionne": True, "episode": EP11}
    assert _appel(episodes={"yt-11": EP11}, recents=[recent],
                  coches={"yt-11": TOUT_COCHE}) == []


def test_une_reco_ni_validee_ni_ecartee_compte_a_relire():
    groups = {"yt-12": [{"status": "draft"}, {}, {"status": "pending"},
                        {"status": "validated"}, {"status": "discarded"}],
              "yt-11": [{"status": "draft"}]}
    items = _appel(episodes={"yt-11": EP11, "yt-12": EP12}, groups=groups)
    # Le plus récent d'abord, comme l'accueil de la relecture.
    assert _textes(items) == ["relire S6·E12 (3 recos)", "relire S6·E11 (1 reco)"]
    assert [i["guid"] for i in items] == ["yt-12", "yt-11"]
    assert all(i["bloc"] == "relecture" and not i["inconnu"] for i in items)


def test_un_episode_entierement_relu_ne_compte_pas():
    groups = {"yt-12": [{"status": "validated"}, {"status": "discarded"}]}
    assert _appel(episodes={"yt-12": EP12}, groups=groups) == []


def test_publie_pas_encore_fusionne_donne_la_pr_a_fusionner():
    recents = [{"guid": "yt-11", "fusionne": False, "episode": EP11},
               {"guid": "yt-9", "fusionne": False, "episode": None}]
    items = _appel(recents=recents, coches={"yt-11": TOUT_COCHE, "yt-9": TOUT_COCHE})
    assert _textes(items) == ["fusionner la PR de S6·E11", "fusionner la PR de yt-9"]
    assert [i["bloc"] for i in items] == ["publication", "publication"]


def test_les_reseaux_qui_manquent_dans_l_ordre_fixe():
    recents = [{"guid": "yt-11", "fusionne": True, "episode": EP11}]
    coches = {"yt-11": {k: v for k, v in TOUT_COCHE.items()
                        if k not in ("deezer", "senscritique")}}
    items = _appel(episodes={"yt-11": EP11}, recents=recents, coches=coches)
    assert _textes(items) == ["réseaux de S6·E11 : Deezer, SensCritique"]
    assert items[0]["guid"] == "yt-11"


def test_le_libelle_retombe_sur_le_titre_court_puis_le_guid():
    sans_numero = {"guid": "yt-x", "title": "Hors série (Un Bon Moment, S6-E99)"}
    recents = [{"guid": "yt-x", "fusionne": True, "episode": sans_numero},
               {"guid": "yt-y", "fusionne": True, "episode": None}]
    items = _appel(recents=recents, coches={"yt-x": {}, "yt-y": {}})
    assert _textes(items)[0].startswith("réseaux de Hors série : Instagram")
    assert _textes(items)[1].startswith("réseaux de yt-y : ")
    assert _textes(items)[0].endswith("Commentaire YouTube")


def test_l_ordre_des_blocs():
    groups = {"yt-12": [{"status": "draft"}]}
    recents = [{"guid": "yt-11", "fusionne": False, "episode": EP11}]
    items = _appel(episodes={"yt-12": EP12}, groups=groups, recents=recents,
                   coches={"yt-11": {"instagram": "x"}},
                   signalements=["1 signalement"], liens=["3 liens morts"],
                   sorties=["fusionner les sorties de décembre"])
    assert [i["bloc"] for i in items] == ["relecture", "publication", "reseaux",
                                          "signalements", "liens", "sorties"]
    assert _textes(items)[3:] == ["1 signalement", "3 liens morts",
                                  "fusionner les sorties de décembre"]


def test_une_source_inconnue_est_dite_inconnue_jamais_rien_a_faire():
    items = ba.a_faire(episodes={}, groups={}, recents=None, coches=None)
    assert [i["bloc"] for i in items] == ["publication", "reseaux", "signalements",
                                          "liens", "sorties"]
    assert all(i["inconnu"] and "inconnu" in i["texte"] for i in items)
    assert items[0]["texte"] == "publication : inconnu"


def test_des_cases_illisibles_rendent_les_reseaux_inconnus_pas_la_publication():
    recents = [{"guid": "yt-11", "fusionne": False, "episode": EP11}]
    items = _appel(recents=recents, coches=None)
    assert [(i["bloc"], i["inconnu"]) for i in items] == [("publication", False),
                                                          ("reseaux", True)]
    assert items[1]["texte"] == "réseaux : inconnu"


# ---- Les signalements, lus par l'audience (tranche 2c) --------------------

def _audience(etat="ok", signalements=None):
    sig = {"etat": "lu", "enAttente": []} if signalements is None else signalements
    return {"etat": etat, "donnees": {"signalements": sig}}


def _en_attente(n):
    return {"etat": "lu", "enAttente": [{"id": f"rep-{k}", "recoId": "r", "categorie": "error",
                                          "date": "2026-11-27T10:00:00.000Z"} for k in range(n)]}


def test_la_ligne_des_signalements_passe_d_inconnu_a_un_nombre():
    avant = _appel(signalements=ba.lignes_signalements(None))
    assert _textes(avant) == ["signalements : inconnu"] and avant[0]["inconnu"]
    apres = _appel(signalements=ba.lignes_signalements(_audience(signalements=_en_attente(3))))
    assert _textes(apres) == ["3 signalements en attente"] and not apres[0]["inconnu"]
    un = ba.lignes_signalements(_audience(signalements=_en_attente(1)))
    assert un == ["1 signalement en attente"]


def test_aucun_signalement_en_attente_ne_fait_aucune_ligne():
    assert ba.lignes_signalements(_audience()) == []


def test_les_signalements_restent_inconnus_si_l_audience_n_est_pas_a_jour():
    # Des données gardées après une panne ne disent pas ce qui attend maintenant.
    assert ba.lignes_signalements(_audience("panne", _en_attente(2))) is None
    assert ba.lignes_signalements({"etat": "ok", "donnees": None}) is None
    assert ba.lignes_signalements(_audience(signalements={"etat": "inconnu",
                                                          "enAttente": []})) is None


@pytest.mark.parametrize("sig", [
    {"etat": "lu", "enAttente": "pas une liste"},
    {"etat": "lu", "enAttente": {"id": "x"}},
    {"etat": "lu", "enAttente": [{"id": "x"}, "texte"]},
    ["pas", "un", "objet"],
    "texte",
])
def test_une_forme_inattendue_de_signalements_reste_inconnue(sig):
    """Tour 1, M3 : jamais une exception, jamais un compte inventé."""
    assert ba.lignes_signalements(_audience(signalements=sig)) is None
    assert ba.signalements_en_attente(_audience(signalements=sig)) is None


def test_signalements_en_attente_rend_la_liste_lue():
    assert ba.signalements_en_attente(_audience(signalements=_en_attente(2))) ==         _en_attente(2)["enAttente"]
    assert ba.signalements_en_attente(_audience()) == []
    assert ba.signalements_en_attente(None) is None


# ---- Publication, sorties et liens morts (tranche 3d-2) ---------------------

PR_URL = "https://github.com/Etienne-Boursault/Reco/pull/"


def _pr(numero, branche, titre="Un titre", groupe="episodes", adresse=None):
    return {"numero": numero, "titre": titre, "branche": branche, "groupe": groupe,
            "date": "2026-11-28T08:00:00Z", "adresse": adresse or f"{PR_URL}{numero}"}


def _github(episodes=(), sorties=(), coupee=False, etat="ok", ouvertes="defaut",
            fusionnees="aucune", depot="Etienne-Boursault/Reco"):
    if ouvertes == "defaut":
        ouvertes = {"episodes": list(episodes), "sorties": list(sorties), "coupee": coupee}
    return {"etat": etat, "donnees": {"depot": depot, "ouvertes": ouvertes,
                                      "fusionnees": [] if fusionnees == "aucune" else fusionnees}}


def _recent(guid, episode, fusionne=False):
    return {"guid": guid, "fusionne": fusionne, "episode": episode}


def test_la_ligne_de_publication_passe_d_inconnu_a_un_nombre_depuis_github():
    avant = [i for i in _appel(recents=None, coches=None,
                               publication=ba.lignes_publication(None, None))
             if i["bloc"] == "publication"]
    assert _textes(avant) == ["publication : inconnu"] and avant[0]["inconnu"]
    recents = [_recent("yt-11", EP11), _recent("yt-12", EP12)]
    github = _github(episodes=[_pr(41, "contenu/yt-11"), _pr(42, "contenu/yt-12", "Douze")])
    items = _appel(recents=recents, coches={"yt-11": TOUT_COCHE, "yt-12": TOUT_COCHE},
                   publication=ba.lignes_publication(github, recents))
    assert _textes(items) == ["fusionner la PR de S6·E11 (#41)", "fusionner la PR de S6·E12 (#42)"]
    assert not any(i["inconnu"] for i in items)
    assert [i["href"] for i in items] == [f"{PR_URL}41", f"{PR_URL}42"]


def test_la_pr_se_cherche_sous_le_slug_du_guid_pas_sous_le_guid_brut():
    """Tour 1, F1 : `publication.py` pousse `contenu/<slugify(guid)>`, le guid brut garde ses majuscules."""
    ep = {**EP11, "guid": "yt-DNoUz4FJ_Z8"}
    recents = [_recent("yt-DNoUz4FJ_Z8", ep)]
    github = _github(episodes=[_pr(41, "contenu/yt-dnouz4fj-z8", "Titre de la PR")])
    assert ba.lignes_publication(github, recents) == [
        ("fusionner la PR de S6·E11 (#41)", f"{PR_URL}41")]


def test_un_episode_pousse_sans_pr_ouverte_dit_d_ouvrir_la_pr_avec_le_lien_de_comparaison():
    """Tour 1, E2 : venus pousse la branche sans ouvrir de PR (pas de jeton)."""
    recents = [_recent("yt-DNoUz4FJ_Z8", {**EP11, "guid": "yt-DNoUz4FJ_Z8"})]
    lignes = ba.lignes_publication(_github(), recents)
    compare = "https://github.com/Etienne-Boursault/Reco/compare/main...contenu/yt-dnouz4fj-z8"
    assert lignes == [("ouvrir puis fusionner la PR de S6·E11", compare + "?expand=1")]
    items = _appel(recents=recents, coches={"yt-DNoUz4FJ_Z8": TOUT_COCHE}, publication=lignes)
    assert len(items) == 1 and not items[0]["inconnu"] and items[0]["href"].startswith(
        "https://github.com/")


@pytest.mark.parametrize("depot", [None, "", 12, "pas un depot", "a/b/c", "a/b?x=1", "a b/c",
                                   "https://evil.test/a/b"])
def test_le_lien_de_comparaison_n_existe_que_pour_un_depot_sur(depot):
    lignes = ba.lignes_publication(_github(depot=depot), [_recent("yt-11", EP11)])
    assert lignes == [("ouvrir puis fusionner la PR de S6·E11", None)]


def test_un_episode_dont_la_pr_est_fusionnee_ne_donne_aucune_ligne_meme_si_le_clone_est_en_retard():
    """Tour 1, E2 : l'épisode est publié, seul le clone n'a pas encore tiré."""
    recents = [_recent("yt-11", EP11)]
    github = _github(fusionnees=[_pr(40, "contenu/yt-11"), "pas une PR", {"numero": 3}])
    assert ba.lignes_publication(github, recents) == []
    # Un clone à jour (`fusionne`) suffit aussi, même si la liste des PR fusionnées manque.
    assert ba.lignes_publication(_github(), [_recent("yt-11", EP11, fusionne=True)]) == []


def test_une_pr_de_contenu_faite_a_la_main_est_une_vraie_tache():
    """Tour 2, M-2 : une PR ouverte reste à fusionner ou à fermer ; elle compte, avec son lien."""
    import bord_rendu_blocs as bb
    github = _github(episodes=[_pr(41, "contenu/yt-11"),
                               _pr(60, "contenu/liens-rebelle", "Liens de Rebelle"),
                               _pr(61, "contenu/autre", "<b>Autre</b>")])
    lignes = ba.lignes_publication(github, [_recent("yt-11", EP11)])
    assert lignes == [("fusionner la PR de S6·E11 (#41)", f"{PR_URL}41"),
                      ("fusionner la PR #60 : Liens de Rebelle", f"{PR_URL}60"),
                      ("fusionner la PR #61 : <b>Autre</b>", f"{PR_URL}61")]
    contenu, nb = bb.bloc_afaire(_appel(recents=[_recent("yt-11", EP11)],
                                        coches={"yt-11": TOUT_COCHE}, publication=lignes))
    assert nb == 3 and "data-inconnu" not in contenu
    assert "&lt;b&gt;Autre&lt;/b&gt;" in contenu and "<b>" not in contenu


def test_le_titre_d_une_pr_a_la_main_est_coupe_a_l_affichage():
    import bord_rendu_blocs as bb
    lignes = ba.lignes_publication(_github(episodes=[_pr(60, "contenu/x", "é" * 500)]), [])
    contenu, _ = bb.bloc_afaire(_appel(publication=lignes))
    assert "é" * 500 not in contenu and "…" in contenu


def test_une_pr_ouverte_n_affiche_jamais_rien_a_faire():
    import bord_rendu_blocs as bb
    lignes = ba.lignes_publication(_github(episodes=[_pr(60, "contenu/x")]), [])
    assert "Rien à faire" not in bb.bloc_afaire(_appel(publication=lignes))[0]


def test_sans_etat_de_la_chaine_les_pr_ouvertes_se_listent_et_la_publication_est_inconnue():
    """Tour 2, M-2 : `recents` illisible. Aucun « ouvrir puis fusionner », une note grisée qui ne compte pas."""
    import bord_rendu_blocs as bb
    lignes = ba.lignes_publication(_github(episodes=[_pr(41, "contenu/yt-11")]), None)
    assert lignes == [ba.Note("publication des épisodes : inconnu"),
                      ("fusionner la PR #41 : Un titre", f"{PR_URL}41")]
    contenu, nb = bb.bloc_afaire(_appel(recents=None, coches=None, publication=lignes))
    assert nb == 1 and contenu.count("data-inconnu") == 2     # la note et « réseaux : inconnu »
    seul = ba.lignes_publication(_github(), None)
    assert seul == [ba.Note("publication des épisodes : inconnu")]
    assert "Rien à faire" not in bb.bloc_afaire(_appel(publication=seul))[0]


def test_les_pr_fusionnees_non_lues_ne_font_jamais_dire_d_ouvrir_la_pr():
    """Tour 2, M-1 : « inconnu » n'est pas « aucune » ; une PR peut déjà être fusionnée."""
    import bord_rendu_blocs as bb
    recents = [_recent("yt-11", EP11), _recent("yt-12", EP12, fusionne=True)]
    lignes = ba.lignes_publication(_github(fusionnees=None), recents)
    assert lignes == [ba.Note("publication de S6·E11 : inconnu (PR fusionnées non lues)")]
    contenu, nb = bb.bloc_afaire(_appel(recents=recents, publication=lignes,
                                        coches={"yt-11": TOUT_COCHE, "yt-12": TOUT_COCHE}))
    assert nb == 0 and "data-inconnu" in contenu and "Rien à faire" not in contenu
    # Une PR ouverte reste une preuve : « fusionner la PR », même sans la liste des fusionnées.
    ouverte = _github(fusionnees=None, episodes=[_pr(41, "contenu/yt-11")])
    assert ba.lignes_publication(ouverte, recents) == [
        ("fusionner la PR de S6·E11 (#41)", f"{PR_URL}41")]


def test_les_branches_fusionnees_se_lisent_meme_apres_une_panne():
    assert ba.branches_fusionnees(_github(fusionnees=[_pr(1, "contenu/a")], etat="panne")) \
        == {"contenu/a": "2026-11-28T08:00:00Z"}
    for github in (None, "texte", {}, {"donnees": None}, _github(fusionnees=None),
                   _github(fusionnees="x")):
        assert ba.branches_fusionnees(github) is None


def test_sans_github_lisible_la_publication_retombe_sur_l_etat_de_la_chaine():
    recents = [{"guid": "yt-11", "fusionne": False, "episode": EP11}]
    for github in (None, _github(etat="panne"), {"etat": "ok", "donnees": None},
                   _github(ouvertes=None), _github(ouvertes="texte"),
                   _github(ouvertes={"episodes": "x", "sorties": [], "coupee": False}),
                   _github(ouvertes={"episodes": [3], "sorties": [], "coupee": False})):
        assert ba.lignes_publication(github, recents) is None
    items = _appel(recents=recents, coches={"yt-11": TOUT_COCHE},
                   publication=ba.lignes_publication(None, recents))
    assert _textes(items) == ["fusionner la PR de S6·E11"] and not items[0]["inconnu"]


def test_une_liste_de_pr_coupee_le_dit():
    """Tour 1, F6 : le nombre manquant est inconnu ; la ligne est grisée et ne compte pas."""
    import bord_rendu_blocs as bb
    lignes = ba.lignes_publication(_github(coupee=True), [_recent("yt-11", EP11)])
    assert lignes[-1] == "d'autres PR ouvertes ne sont pas listées"
    items = _appel(recents=[_recent("yt-11", EP11)], coches={"yt-11": TOUT_COCHE},
                   publication=lignes)
    assert bb.bloc_afaire(items)[1] == 1  # la ligne « ouvrir… » compte, pas la note
    assert bb.bloc_afaire(_appel(publication=[lignes[-1]]))[1] == 0


def test_une_pr_sans_branche_n_est_rapprochee_d_aucun_episode():
    pr = {"numero": 5, "adresse": f"{PR_URL}5"}
    assert ba.lignes_publication(_github(episodes=[pr]), []) == [
        ("fusionner la PR #5 : sans titre", f"{PR_URL}5")]


def _publies(*numeros):
    """Des épisodes publiés sans PR, du plus récent au plus ancien."""
    return [_recent(f"yt-{n}", {"guid": f"yt-{n}", "title": "T", "season": 6, "number": n})
            for n in numeros]


def test_un_episode_publie_sans_pr_au_dela_des_trois_derniers_reste_signale():
    """Revue globale, E1 : la chaîne ne crée pas de PR ; le plus ancien de 4 ne doit pas disparaître."""
    lignes = ba.lignes_publication(_github(), _publies(14, 13, 12, 11))
    assert [t for t, _ in lignes] == [f"ouvrir puis fusionner la PR de S6·E{n}"
                                      for n in (14, 13, 12, 11)]


def test_au_dela_de_la_fenetre_une_note_grisee_dit_combien_ne_sont_pas_verifies():
    """Revue globale, E1 (F23) : la liste coupée le dit ; la note ne compte pas comme tâche."""
    import bord_rendu_blocs as bb
    lignes = ba.lignes_publication(_github(), [], non_verifies=2)
    assert lignes == [ba.Note("2 épisodes plus anciens non vérifiés (hors des 10 derniers publiés)")]
    assert ba.lignes_publication(_github(), [], non_verifies=1) == [
        ba.Note("1 épisode plus ancien non vérifié (hors des 10 derniers publiés)")]
    assert ba.lignes_publication(_github(), [], non_verifies=0) == []
    assert bb.bloc_afaire(_appel(publication=lignes))[1] == 0


def test_a_faire_depuis_regarde_la_fenetre_pour_la_publication_et_trois_pour_les_reseaux():
    publies = _publies(14, 13, 12, 11)
    items = ba.a_faire_depuis(episodes={}, groups={}, recents=publies[:3], publies=publies,
                              coches={}, audience=None, github=_github(), contenu=None,
                              non_verifies=1)
    publication = [i["texte"] for i in items if i["bloc"] == "publication"]
    assert publication[:4] == [f"ouvrir puis fusionner la PR de S6·E{n}" for n in (14, 13, 12, 11)]
    assert publication[4].startswith("1 épisode plus ancien non vérifié")
    assert [i["texte"].split(" : ")[0] for i in items if i["bloc"] == "reseaux"] == [
        "réseaux de S6·E14", "réseaux de S6·E13", "réseaux de S6·E12"]
    # Sans GitHub lisible, le repli sur l'état de la chaîne regarde aussi la fenêtre.
    repli = ba.a_faire_depuis(episodes={}, groups={}, recents=publies[:3], publies=publies,
                              coches={}, audience=None, github=None, contenu=None)
    assert [i["texte"] for i in repli if i["bloc"] == "publication"] == [
        f"fusionner la PR de S6·E{n}" for n in (14, 13, 12, 11)]


def test_sans_github_lisible_la_note_des_plus_anciens_non_verifies_apparait_aussi():
    """Tour 2, T2-4 (F23) : le repli sur l'état de la chaîne ne tait pas les épisodes hors fenêtre."""
    items = ba.a_faire_depuis(episodes={}, groups={}, recents=_publies(14, 13), coches={},
                              audience=None, github=None, contenu=None, non_verifies=2)
    note = [i for i in items if i["bloc"] == "publication"][-1]
    assert note["texte"] == "2 épisodes plus anciens non vérifiés (hors des 10 derniers publiés)"
    assert note["inconnu"] is True      # grisée, ne compte pas comme tâche


def test_une_panne_isolee_des_pr_fermees_rend_les_fusionnees_inconnues():
    """Revue globale, D4 : la liste gardée d'avant ne dit pas que la dernière lecture est complète."""
    github = _github(fusionnees=[_pr(40, "contenu/yt-11")])
    github["donnees"]["pannes"] = {"fusionnees": {"etat": "panne", "detail": "HTTP 500"}}
    assert ba.branches_fusionnees(github) is None
    # Tour 2, T2-3 : une PR fusionnée le reste ; la chaîne lit la liste gardée malgré la panne.
    assert ba.branches_fusionnees(github, meme_en_panne=True) == {
        "contenu/yt-11": "2026-11-28T08:00:00Z"}
    assert ba.branches_fusionnees({"donnees": {}}, meme_en_panne=True) is None
    assert ba.lignes_publication(github, [_recent("yt-11", EP11)]) == [
        ba.Note("publication de S6·E11 : inconnu (PR fusionnées non lues)")]
    # Une autre panne (CI, déploiement) ne touche pas aux PR fusionnées.
    github["donnees"]["pannes"] = {"ci": {"etat": "panne", "detail": "HTTP 500"}}
    assert ba.branches_fusionnees(github) == {"contenu/yt-11": "2026-11-28T08:00:00Z"}
    github["donnees"]["pannes"] = "x"
    assert ba.branches_fusionnees(github) is not None


def test_la_ligne_des_sorties_passe_d_inconnu_a_un_nombre_depuis_github():
    avant = _appel(sorties=ba.lignes_sorties(None))
    assert _textes(avant) == ["sorties : inconnu"] and avant[0]["inconnu"]
    github = _github(sorties=[_pr(50, "contenu/sorties-2026-12", "Les sorties de décembre",
                                  "sorties")])
    apres = _appel(sorties=ba.lignes_sorties(github))
    assert _textes(apres) == ["fusionner la PR des sorties : Les sorties de décembre (#50)"]
    assert not apres[0]["inconnu"] and apres[0]["href"] == f"{PR_URL}50"
    assert ba.lignes_sorties(_github()) == []
    assert ba.lignes_sorties(_github(etat="limite")) is None
    assert ba.lignes_sorties(_github(ouvertes=None)) is None


def test_la_ligne_des_liens_morts_passe_d_inconnu_a_un_nombre():
    avant = _appel(liens=ba.lignes_liens(None))
    assert _textes(avant) == ["liens morts : inconnu"] and avant[0]["inconnu"]
    liens = {"date": "2026-11-25", "age": 4, "ancien": False, "morts": 3, "liste": []}
    apres = _appel(liens=ba.lignes_liens({"liens": liens}))
    assert _textes(apres) == ["3 liens morts"] and not apres[0]["inconnu"]
    assert ba.lignes_liens({"liens": {**liens, "morts": 1}}) == ["1 lien mort"]
    assert ba.lignes_liens({"liens": {**liens, "morts": 0}}) == []


def test_des_liens_morts_d_un_rapport_ancien_le_disent():
    """Tour 1, F8 : une ligne grisée qui ne compte pas, même si le rapport disait 0."""
    import bord_rendu_blocs as bb
    liens = {"date": "2026-11-10", "age": 19, "ancien": True, "morts": 2, "liste": []}
    assert ba.lignes_liens({"liens": liens}) == ["liens morts : rapport ancien du 10/11"]
    assert ba.lignes_liens({"liens": {**liens, "morts": 0}}) == [
        "liens morts : rapport ancien du 10/11"]
    assert ba.lignes_liens({"liens": {**liens, "date": "?"}}) == ["liens morts : rapport ancien"]
    items = _appel(liens=ba.lignes_liens({"liens": liens}))
    assert bb.bloc_afaire(items)[1] == 0 and items[0]["inconnu"]


@pytest.mark.parametrize("contenu", [{}, {"liens": None}, {"liens": "texte"},
                                     {"liens": {"morts": "3"}}, {"liens": {"morts": True}}])
def test_une_forme_inattendue_des_liens_reste_inconnue(contenu):
    assert ba.lignes_liens(contenu) is None


def test_une_ligne_inconnue_est_grisee_et_ne_compte_pas():
    import bord_rendu_blocs as bb
    items = _appel(liens=ba.lignes_liens(None), sorties=ba.lignes_sorties(None),
                   signalements=["2 signalements en attente"])
    contenu, nb = bb.bloc_afaire(items)
    assert nb == 1 and contenu.count("data-inconnu") == 2


def test_le_lien_d_une_pr_ne_vaut_que_pour_github():
    import bord_rendu_blocs as bb
    bon = {"bloc": "publication", "texte": "x", "guid": None, "inconnu": False,
           "href": f"{PR_URL}1"}
    for mauvais in ("javascript:alert(1)", "http://github.com/a", "https://autre.test/a",
                    '"><script>', "https://[pas-une-ip", None):
        contenu, _ = bb.bloc_afaire([{**bon, "href": mauvais}])
        assert "<a " not in contenu
    contenu, _ = bb.bloc_afaire([bon])
    assert f'href="{PR_URL}1"' in contenu and "Ouvrir la PR" in contenu


# ---- Revue globale, M2 : une source « ok » périmée date ses lignes ----------

def _vieille(source: dict, age: int = 72 * 3600) -> dict:
    """La source telle que `lire()` la rend quand rien n'a été réécrit depuis `age` secondes."""
    return {**source, "lu": "2026-11-27T10:00:00+00:00", "age": age}


def test_une_ligne_de_signalements_d_une_audience_perimee_porte_sa_date():
    audience = _vieille(_audience(signalements=_en_attente(3)))
    assert ba.lignes_signalements(audience) == ["3 signalements en attente"]  # le texte reste
    items = ba.a_faire_depuis(episodes={}, groups={}, recents=[], coches={}, audience=audience,
                              github=None, contenu=None)
    ligne = [i for i in items if i["bloc"] == "signalements"]
    # Une PR ou un signalement vu il y a deux jours reste probablement à traiter : c'est toujours
    # une tâche (`inconnu` faux), mais datée.
    assert _textes(ligne) == ["3 signalements en attente (données du 27/11)"]
    assert not ligne[0]["inconnu"]


def test_les_lignes_de_github_perimee_portent_leur_date_et_gardent_leur_lien():
    github = _vieille(_github(episodes=[_pr(41, "contenu/yt-11")],
                              sorties=[_pr(50, "contenu/sorties-x", "Sorties", "sorties")]))
    items = ba.a_faire_depuis(episodes={}, groups={}, recents=[], publies=[_recent("yt-11", EP11)],
                              coches={}, audience=None, github=github, contenu=None)
    assert [(i["bloc"], i["texte"], i["href"]) for i in items if i["bloc"] in ("publication", "sorties")
            ] == [("publication", "fusionner la PR de S6·E11 (#41) (données du 27/11)", f"{PR_URL}41"),
                  ("sorties", "fusionner la PR des sorties : Sorties (#50) (données du 27/11)",
                   f"{PR_URL}50")]


def test_une_note_d_une_source_perimee_ne_porte_pas_de_date():
    github = _vieille(_github(coupee=True))
    lignes = ba.a_faire_depuis(episodes={}, groups={}, recents=[], coches={}, audience=None,
                               github=github, contenu=None)
    assert "d'autres PR ouvertes ne sont pas listées" in _textes(lignes)


def test_des_sources_fraiches_ne_changent_aucune_ligne():
    audience = _vieille(_audience(signalements=_en_attente(1)), age=20 * 60)
    github = _vieille(_github(sorties=[_pr(50, "contenu/sorties-x", "Sorties", "sorties")]), age=60)
    items = ba.a_faire_depuis(episodes={}, groups={}, recents=[], coches={}, audience=audience,
                              github=github, contenu=None)
    assert "données du" not in " ".join(_textes(items))
    assert ba.lignes_signalements(audience) == ["1 signalement en attente"]
