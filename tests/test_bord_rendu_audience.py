"""Tests de `tools/bord_rendu_audience.py` : l'audience au centre de `/bord`.

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026,
l'audience au centre (plan `pr-tableau-de-bord.md`, § 3, § 6 et § 9, tranche 2c).

Le rendu est pur : chaque test lui donne l'état de `bord_distant.lire()` en
dictionnaire (forme de la note 2b du journal), sans disque ni réseau.
"""
from __future__ import annotations

import html
import re

import pytest

import bord_afaire as ba
import bord_distant
import bord_rendu_audience as bra
import bord_rendu_blocs as bb

CHARGE = '"><script>alert(1)</script>'


def _col(c, i, r):
    return {"confirmes": {"visiteursJours": c, "visites": c * 2},
            "incertains": {"visiteursJours": i, "visites": i * 2},
            "robots": {"visiteursJours": r, "visites": r * 10}}


def _fenetre(**kw):
    f = {"du": "2026-11-22", "au": "2026-11-28", "tri": "trois-colonnes",
         "bascule": "2026-11-20", "panneSignal": [], "colonnes": _col(41, 23, 57),
         "pagesVues": 120, "visiteurs": 60, "visitesRobots": 400, "clics": 20,
         "clicsPour100Visiteurs": 33.3,
         "pages": [{"cle": "/un-bon-moment/films", "n": 7}],
         "provenances": [{"cle": "ailleurs.test", "n": 1}]}
    f.update(kw)
    return f


def _jour(j, c=4, i=2, r=5):
    return {"jour": f"2026-11-{j}", "tri": "trois-colonnes", "visiteurs": c + i,
            "robots": r * 10, "colonnes": _col(c, i, r)}


def _donnees(**kw):
    d = {"genere": "2026-11-28T09:30:00.000Z", "perimetre": "tout le site",
         "sept": _fenetre(),
         "trente": _fenetre(du="2026-10-30", colonnes=_col(410, 230, 570),
                            clicsPour100Visiteurs=12.5),
         "jours": [_jour(j) for j in range(22, 29)], "erreur": None,
         "signalements": {"etat": "lu", "enAttente": []}}
    d.update(kw)
    return d


def _audience(etat="ok", donnees="defaut", age=180, detail=None):
    donnees = _donnees() if donnees == "defaut" else donnees
    return {"source": "audience", "etat": etat,
            "libelle": bord_distant.LIBELLES.get(etat, etat), "detail": detail,
            "donnees": donnees, "lu": "2026-11-28T09:30:00+00:00" if donnees else None,
            "essai": "2026-11-28T09:30:00+00:00", "age": age if donnees else None,
            "relance": False}


def _bloc(**kw):
    return bra.bloc_audience(_audience(**kw))


@pytest.fixture(autouse=True)
def _site(monkeypatch):
    monkeypatch.delenv("SITE_URL", raising=False)


# ---- Les grands chiffres ------------------------------------------------

def test_trois_grands_chiffres_sur_sept_jours_puis_trente_jours_en_dessous():
    bloc = _bloc()
    valeurs = re.findall(r'class="bord-chiffre-valeur">([^<]+)<', bloc)
    assert valeurs[:3] == ["41", "23", "57"]
    assert "visiteurs-jours" in bloc
    for nom in ("Confirmés", "Incertains", "Robots"):
        assert nom in bloc
    sept, trente = bloc.index("7 derniers jours"), bloc.index("30 derniers jours")
    assert sept < trente
    assert bloc.index("410") > trente and "230" in bloc and "570" in bloc


def test_les_colonnes_d_une_fenetre_qui_commence_avant_la_bascule_le_disent():
    bloc = _bloc(donnees=_donnees(sept=_fenetre(bascule="2026-11-25")))
    assert "depuis le 25/11" in bloc


def test_les_clics_pour_cent_visiteurs():
    bloc = _bloc()
    assert "Clics pour 100 visiteurs" in bloc
    assert "33,3" in bloc and "12,5" in bloc


def test_des_clics_pour_cent_visiteurs_inconnus_ne_valent_pas_zero():
    bloc = _bloc(donnees=_donnees(sept=_fenetre(clicsPour100Visiteurs=None)))
    assert "Clics pour 100 visiteurs" in bloc and "—" in bloc


def test_une_fenetre_illisible_sur_le_site_le_dit_avec_son_message():
    d = _donnees(sept=None, jours=[], erreur="lecture impossible " + CHARGE)
    bloc = _bloc(donnees=d)
    assert "7 derniers jours : illisible" in bloc
    assert "lecture impossible" in bloc and "<script>alert" not in bloc
    assert "410" in bloc  # 30 jours reste lu


# ---- L'ancien tri ---------------------------------------------------------

def test_avant_la_bascule_ancien_tri_et_seulement_humains_et_robots():
    ancien = {"tri": "ancien", "bascule": None, "colonnes": None}
    jours = [{"jour": f"2026-11-{j}", "tri": "ancien", "visiteurs": 6, "robots": 40,
              "colonnes": None} for j in range(22, 29)]
    bloc = _bloc(donnees=_donnees(sept=_fenetre(**ancien), trente=_fenetre(**ancien),
                                  jours=jours))
    assert "ancien tri" in bloc
    assert "Confirmés" not in bloc and "Incertains" not in bloc
    assert "Humains (ancien tri)" in bloc and "Passages de robots" in bloc
    valeurs = re.findall(r'class="bord-chiffre-valeur">([^<]+)<', bloc)
    assert valeurs[:2] == ["60", "400"]


def test_la_bascule_se_lit_sur_trente_jours():
    # 7 jours voit une bascule, 30 jours non : le tri reste l'ancien (note 2a-2).
    jours = [{"jour": f"2026-11-{j}", "tri": "ancien", "visiteurs": 6, "robots": 40,
              "colonnes": None} for j in range(22, 29)]
    d = _donnees(trente=_fenetre(tri="ancien", bascule=None, colonnes=None), jours=jours)
    assert "Humains (ancien tri)" in _bloc(donnees=d).split("bord-graphe", 1)[1]


def test_un_jour_d_avant_la_bascule_dans_le_graphique_des_trois_colonnes():
    jours = [_jour(j) for j in range(22, 29)]
    jours[0] = {"jour": "2026-11-22", "tri": "ancien", "visiteurs": 3, "robots": 9,
                "colonnes": None}
    bloc = _bloc(donnees=_donnees(jours=jours))
    ligne = re.search(r"<tr><th scope=\"row\">[^<]*22/11</th>(.*?)</tr>", bloc).group(1)
    assert "ancien tri" in ligne and "3 humains" in ligne and "9 passages de robots" in ligne


# ---- Le graphique ---------------------------------------------------------

def test_sept_barres_et_leur_tableau_pour_le_lecteur_d_ecran():
    bloc = _bloc()
    graphe = bloc.split('class="bord-graphe"', 1)[1]
    assert graphe.count('class="bord-jour"') == 7
    assert 'class="bord-graphe" aria-hidden="true"' in bloc
    table = re.search(r'<table class="bord-lecteur">(.*?)</table>', bloc).group(1)
    assert "<caption>" in table
    assert table.count('<th scope="row">') == 7
    for serie in ("confirmes", "incertains", "robots"):
        assert f'data-serie="{serie}"' in graphe


def test_un_jour_sans_mesure_est_marque_et_ne_compte_pas_pour_zero():
    jours = [_jour(j) for j in range(22, 29) if j != 25]
    bloc = _bloc(donnees=_donnees(jours=jours))
    graphe = bloc.split('class="bord-graphe"', 1)[1]
    assert graphe.count('class="bord-jour"') == 7
    assert graphe.count('data-mesure="non"') == 1
    ligne = re.search(r"<tr><th scope=\"row\">[^<]*25/11</th>(.*?)</tr>", bloc).group(1)
    assert "pas de mesure" in ligne and ">0<" not in ligne


def test_les_sept_jours_finissent_le_jour_du_resume():
    bloc = _bloc(donnees=_donnees(genere="2026-11-30T08:00:00.000Z"))
    lignes = re.findall(r'<tr><th scope="row">([^<]+)</th>', bloc)
    assert lignes[0].endswith("24/11") and lignes[-1].endswith("30/11")
    assert bloc.count("pas de mesure") == 2  # 29 et 30 sans mesure


def test_un_graphique_sans_aucune_valeur_ne_divise_pas_par_zero():
    bloc = _bloc(donnees=_donnees(jours=[_jour(j, 0, 0, 0) for j in range(22, 29)]))
    assert 'style="height:0%"' in bloc


# ---- Pages, provenances, signal ------------------------------------------

def test_pages_et_provenances_en_texte_seul_et_echappees():
    d = _donnees(sept=_fenetre(pages=[{"cle": "/x" + CHARGE, "n": 3}],
                               provenances=[{"cle": 'pi"ege.test' + CHARGE, "n": 2}]))
    bloc = _bloc(donnees=d)
    assert "<script>alert" not in bloc and '"><script>' not in bloc
    assert "&lt;script&gt;" in bloc and "pi&quot;ege.test" in bloc
    listes = bloc.split("Pages les plus vues", 1)[1]
    assert "<a " not in listes.split("bord-audience-lien", 1)[0]


def test_une_page_trop_longue_est_coupee_a_quatre_vingts_signes():
    longue = "/" + "a" * 79 + "B" * 40
    bloc = _bloc(donnees=_donnees(sept=_fenetre(pages=[{"cle": longue, "n": 1}])))
    assert longue[:80] + "…" in bloc and "B" * 2 not in bloc


def _cinq():
    return [{"cle": f"/p{n}", "n": 10 - n} for n in range(5)]


def test_une_liste_de_cinq_dont_le_total_est_cinq_n_est_pas_coupee():
    bloc = _bloc(donnees=_donnees(sept=_fenetre(pages=_cinq(), pagesTotal=5, provenances=[],
                                                 provenancesTotal=0)))
    assert "autres" not in bloc and "premières" not in bloc
    assert re.findall(r"/p(\d)", bloc) == ["0", "1", "2", "3", "4"]  # l'ordre de l'API
    assert "Aucune provenance" in bloc


def test_une_liste_coupee_dit_combien_restent():
    """Tour 1, M5 (F23) : « + N autres », le total vient du site."""
    sept = _fenetre(pages=_cinq(), pagesTotal=7,
                    provenances=[{"cle": "a.test", "n": 1}], provenancesTotal=1)
    bloc = _bloc(donnees=_donnees(sept=sept))
    assert bloc.count("+ 2 autres") == 1 and "autres" in bloc and "premières" not in bloc


def test_sans_total_du_site_aucune_phrase_inventee():
    bloc = _bloc(donnees=_donnees(sept=_fenetre(pages=_cinq())))
    assert "autres" not in bloc and "premières" not in bloc
    bloc = _bloc(donnees=_donnees(sept=_fenetre(pages=_cinq(), pagesTotal="beaucoup")))
    assert "autres" not in bloc


def test_les_jours_ou_le_signal_semble_en_panne():
    d = _donnees(trente=_fenetre(du="2026-10-30", panneSignal=["2026-11-26", "2026-11-27"]))
    bloc = _bloc(donnees=d)
    assert "signal" in bloc and "26/11 et le 27/11" in bloc
    assert "peut-être en panne" not in _bloc()


# ---- Le lien vers /audience ---------------------------------------------

def test_le_lien_vers_audience_sans_la_cle(monkeypatch):
    monkeypatch.setenv("RECO_AUDIENCE_KEY", "fausse-cle-audience-123")
    bloc = _bloc()
    assert 'href="https://unebonnere.co/audience"' in bloc
    assert "s'ouvre depuis ton signet" in bloc
    assert "fausse-cle-audience-123" not in bloc and "cle=" not in bloc


def test_le_lien_suit_site_url(monkeypatch):
    monkeypatch.setenv("SITE_URL", "https://essai.example/un-bon-moment")
    assert 'href="https://essai.example/audience"' in _bloc()


def test_un_site_url_refuse_ne_donne_aucun_lien(monkeypatch):
    monkeypatch.setenv("SITE_URL", "javascript:alert(1)")
    bloc = _bloc()
    assert "href=" not in bloc and "adresse du site refusée" in bloc


# ---- Les états -------------------------------------------------------------

def test_a_jour_donne_l_age_des_donnees():
    bloc = _bloc(age=12 * 60)
    assert 'data-etat="ok"' in bloc and "lu il y a 12 min" in bloc


def test_lu_a_l_instant():
    assert "lu à l'instant" in _bloc(age=20)


@pytest.mark.parametrize(("etat", "detail", "attendu"), [
    ("cle-absente", None, "Clé absente sur venus"),
    ("cle-refusee", "HTTP 404", "Le site répond « introuvable »"),
    ("panne", "TimeoutError", "Site injoignable"),
    ("reponse-illisible", "JSON invalide", "Réponse illisible"),
    ("cache-illisible", None, "distant.json"),
    ("inconnu", None, "Pas encore lu"),
])
def test_chaque_etat_a_son_message_sans_donnees(etat, detail, attendu):
    bloc = _bloc(etat=etat, donnees=None, detail=detail)
    assert f'data-etat="{etat}"' in bloc and attendu in bloc
    assert "bord-chiffre-valeur" not in bloc
    if detail:
        assert detail in bloc


def test_une_cle_refusee_dit_les_trois_causes_possibles():
    """Tour 1, F2 : tout 404 est lu « clé refusée », or le site répond 404 aussi sans la route."""
    bloc = _bloc(etat="cle-refusee", donnees=None, detail="HTTP 404")
    assert "diffère de celle du site" in bloc
    assert "le site n'a pas la clé" in bloc
    assert "pas encore la route" in bloc


def test_la_premiere_lecture_n_est_annoncee_que_si_elle_est_lancee():
    """Tour 1, F4."""
    lancee = {**_audience(etat="inconnu", donnees=None), "relance": True}
    assert "la première lecture est lancée" in bra.bloc_audience(lancee)
    non = bra.bloc_audience(_audience(etat="inconnu", donnees=None))
    assert "n'a pas pu être lancée" in non and "première lecture" not in non


def test_le_cache_illisible_donne_le_vrai_chemin_echappe(monkeypatch, tmp_path):
    """Tour 1, F7 : le chemin que lit `bord_distant`, pas un chemin fixe."""
    monkeypatch.setenv("RECO_BORD_DIR", str(tmp_path / "a&b<i>"))
    bloc = _bloc(etat="cache-illisible", donnees=None)
    assert html.escape(str(tmp_path / "a&b<i>" / "distant.json")) in bloc
    assert "<i>" not in bloc and "tools/output/bord" not in bloc


@pytest.mark.parametrize("champ", ["bascule", "panneSignal"])
def test_les_dates_de_bascule_et_de_panne_sont_verifiees_avant_d_entrer_dans_la_page(champ):
    """Tour 1, F1 : une valeur qui n'est pas une date n'entre jamais dans le HTML."""
    valeur = "3" + CHARGE if champ == "bascule" else [CHARGE]  # « 3… » > du : la note s'affiche
    bloc = _bloc(donnees=_donnees(sept=_fenetre(**{champ: valeur}),
                                  trente=_fenetre(**{champ: valeur})))
    assert "<script>alert" not in bloc and '"><script>' not in bloc
    assert "depuis le ?" in bloc if champ == "bascule" else "le ?" in bloc


def test_un_etat_inconnu_du_rendu_est_echappe():
    bloc = _bloc(etat=CHARGE, donnees=None, detail=CHARGE)
    assert "<script>alert" not in bloc and '"><script>' not in bloc


def test_des_donnees_perimees_restent_affichees_avec_leur_age():
    bloc = _bloc(etat="panne", detail="URLError", age=3 * 3600 + 5 * 60)
    assert "Site injoignable" in bloc and "URLError" in bloc
    assert "données d'il y a 3 h 05" in bloc
    assert re.findall(r'class="bord-chiffre-valeur">([^<]+)<', bloc)[:3] == ["41", "23", "57"]


def test_sans_etat_l_audience_est_inconnue():
    bloc = bra.bloc_audience(None)
    assert 'data-etat="inconnu"' in bloc and "Pas encore lu" in bloc


def test_une_reponse_de_forme_inattendue_ne_casse_pas_la_page(caplog):
    bloc = _bloc(donnees=_donnees(sept=_fenetre(colonnes={"confirmes": "x"})))
    assert "forme inattendue" in bloc
    assert "lecture de l'audience" in caplog.text


def test_deux_fenetres_illisibles_ni_clics_ni_listes():
    bloc = _bloc(donnees=_donnees(sept=None, trente=None, jours=[], erreur=None))
    assert "7 derniers jours : illisible sur le site." in bloc
    assert "30 derniers jours : illisible" in bloc
    assert "Clics pour 100" not in bloc and "Pages les plus vues" not in bloc


def test_un_compte_qui_n_est_pas_un_nombre_s_ecrit_point_d_interrogation():
    bloc = _bloc(donnees=_donnees(sept=_fenetre(pages=[{"cle": "/x", "n": "beaucoup"}])))
    assert "beaucoup" not in bloc and ">?<" in bloc


# ---- Signalements (`bord_rendu_blocs`, tranche 2c) ---------------------------------------------------------

def _sig(n, **kw):
    return [{"id": f"rep-{k}", "recoId": f"ubm-{k}", "categorie": "broken-link",
             "date": f"2026-11-{27 - k:02d}T10:00:00.000Z", **kw} for k in range(n)]


def _aud(enattente=None, etat="ok", sig_etat="lu", age=60):
    return {"etat": etat, "age": age,
            "donnees": {"signalements": {"etat": sig_etat, "enAttente": enattente or []}}}


def test_signalements_reco_categorie_et_date_jamais_plus():
    bloc = bb.bloc_signalements(_aud(_sig(2, nom="Jean Dupont", texte="mon adresse")))
    assert "ubm-0" in bloc and "ubm-1" in bloc
    assert "Lien mort" in bloc and "27/11" in bloc and "26/11" in bloc
    assert "rep-0" not in bloc and "Jean Dupont" not in bloc and "mon adresse" not in bloc
    assert "+ " not in bloc


def test_signalements_coupes_disent_combien_restent():
    bloc = bb.bloc_signalements(_aud(_sig(8)))
    assert bloc.count("<li") == bb.SIGNALEMENTS_MAX
    assert "ubm-0" in bloc and f"ubm-{bb.SIGNALEMENTS_MAX}" not in bloc  # les plus récents
    assert f"+ {8 - bb.SIGNALEMENTS_MAX} autres" in bloc


def _aud_total(envoyes, total):
    """Le site n'envoie que les 5 plus récents, avec le total (revue globale, S4)."""
    aud = _aud(_sig(envoyes))
    aud["donnees"]["signalements"]["total"] = total
    return aud


def test_signalements_coupes_par_le_site_disent_combien_restent_d_apres_le_total():
    bloc = bb.bloc_signalements(_aud_total(5, 8))
    assert bloc.count("<li") == 5 and "+ 3 autres" in bloc


def test_la_ligne_a_faire_compte_le_total_du_site_pas_la_liste_coupee():
    assert ba.lignes_signalements(_aud_total(5, 8)) == ["8 signalements en attente"]


@pytest.mark.parametrize("total", ["beaucoup", True, 2, -1, None])
def test_un_total_absent_ou_faux_se_rabat_sur_la_liste(total):
    """Un cache d'avant S4 n'a pas `total` ; un total qui n'est pas un entier plausible est écarté."""
    aud = _aud_total(5, total)
    assert ba.lignes_signalements(aud) == ["5 signalements en attente"]
    assert "+ " not in bb.bloc_signalements(aud)


def test_signalements_ok_mais_anciens_se_disent_perimes():
    bloc = bb.bloc_signalements(_aud(_sig(1), age=3 * 3600))
    assert "Périmé" in bloc and "données d'il y a 3 h 00" in bloc
    assert "Périmé" not in bb.bloc_signalements(_aud(_sig(1), age=60))


def test_signalements_aucun_en_attente():
    assert "Aucun signalement en attente." in bb.bloc_signalements(_aud([]))


def test_signalements_inconnus_sans_donnees_ou_illisibles_sur_le_site():
    assert "Signalements : inconnu" in bb.bloc_signalements(None)
    assert "Signalements : inconnu" in bb.bloc_signalements({"etat": "panne", "donnees": None})
    assert "Signalements : inconnu" in bb.bloc_signalements(_aud(sig_etat="inconnu"))


def test_signalements_perimes_disent_leur_age():
    bloc = bb.bloc_signalements(_aud(_sig(1), etat="panne", age=2 * 3600))
    assert "ubm-0" in bloc and "données d'il y a 2 h 00" in bloc
    assert "il y a" not in bb.bloc_signalements(_aud(_sig(1)))


def test_signalements_neutralisent_l_injection():
    bloc = bb.bloc_signalements(_aud([{"id": "x", "recoId": CHARGE, "categorie": CHARGE,
                                       "date": CHARGE}]))
    assert "<script>alert" not in bloc and '"><script>' not in bloc
    assert "&lt;script&gt;" in bloc


@pytest.mark.parametrize("sig", [
    {"etat": "lu", "enAttente": "pas une liste"},
    {"etat": "lu", "enAttente": [{"recoId": "x"}, "texte"]},
    ["pas", "un", "objet"],
])
def test_signalements_de_forme_inattendue_restent_inconnus(sig):
    """Tour 1, M3."""
    bloc = bb.bloc_signalements({"etat": "ok", "age": 1, "donnees": {"signalements": sig}})
    assert "Signalements : inconnu" in bloc


def test_des_donnees_ok_de_plus_de_20_min_se_disent_perimees():
    """Revue globale, M2 : un essai réussi mais plus réécrit ne reste pas « À jour »."""
    assert "À jour · lu il y a 20 min" in _bloc(age=20 * 60)
    bloc = _bloc(age=3 * 3600)
    assert "Périmé · lu il y a 3 h 00" in bloc and "À jour" not in bloc
