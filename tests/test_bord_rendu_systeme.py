"""Tests de `tools/bord_rendu_systeme.py` : « Santé et versions » et « Coûts et modèles ».

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 6, § 9 et § 14, tranche 3d-1).

Le rendu est pur : chaque test lui donne l'état de `bord_github.lire()` et de
`bord_systeme.lire()` en dictionnaires (formes des notes 3a et 3b du journal),
sans disque ni réseau. Le fuseau est forcé à UTC.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

import bord_distant
import bord_rendu as br
import bord_rendu_blocs as bb
import bord_rendu_systeme as brs

CHARGE = '"><script>alert(1)</script>'
JS = "javascript:alert(1)"
MAINTENANT = datetime(2026, 11, 29, 10, 51, tzinfo=UTC)
RUN = "https://github.com/Etienne-Boursault/Reco/actions/runs/42"


@pytest.fixture(autouse=True)
def _utc(monkeypatch):
    monkeypatch.setattr(bb, "_fuseau", lambda: UTC)


def _course(conclusion="success", adresse=RUN, date="2026-11-28T08:04:00Z"):
    return {"conclusion": conclusion, "date": date, "adresse": adresse}


def _github(etat="ok", donnees="defaut", age=180, detail=None, relance=False):
    if donnees == "defaut":
        donnees = {"depot": "Etienne-Boursault/Reco", "ouvertes": None, "fusionnees": None,
                   "ci": _course(), "deploiement": _course(date="2026-11-28T08:30:00Z")}
    return {"source": "github", "etat": etat, "libelle": etat, "detail": detail,
            "donnees": donnees, "lu": "2026-11-28T09:30:00+00:00" if donnees else None,
            "essai": None, "age": age if donnees else None, "relance": relance}


def _cout(known="1.750000", inconnus=0):
    return {"known": {"USD": known} if known is not None else None,
            "unknownCostCalls": inconnus, "pricingCoverage": 1.0}


def _fenetre(appels=12, cout=None, par_modele=None):
    return {"appels": appels, "cout": cout or _cout(),
            "par_modele": par_modele if par_modele is not None
            else {"claude-opus-5": _cout("1.250000"), "claude-sonnet-5": _cout("0.500000")}}


def _systeme(**kw):
    s = {"couts": {"semaine": _fenetre(), "precedente": _fenetre(appels=3, cout=_cout("0.300000"),
                                                                par_modele={})},
         "modeles": {"extraction": {"nom": "claude-opus-5", "source": "mesure",
                                    "date": "2026-11-27T09:00:00+00:00"},
                     "secours": {"nom": "claude-sonnet-5", "source": "env"}},
         "image": "reco-atelier:2026-11-14-pillow13"}
    s.update(kw)
    return s


# ---- Santé et versions : les états --------------------------------------

def test_etat_ok_montre_la_ci_le_deploiement_et_l_age():
    bloc = brs.bloc_sante(_github(), _systeme())
    assert 'data-etat="ok"' in bloc and "À jour · lu il y a 3 min" in bloc
    assert "CI de main" in bloc and "Dernier déploiement" in bloc
    assert 'data-conclusion="ok"' in bloc and "réussie" in bloc
    assert "28/11 08 h 04" in bloc and "28/11 08 h 30" in bloc
    assert f'href="{RUN}"' in bloc


@pytest.mark.parametrize("etat,attendu", [
    ("panne", "GitHub injoignable"),
    ("limite", "limite de débit"),
    ("reponse-illisible", "Réponse illisible de GitHub"),
    ("cache-illisible", "cache de GitHub est illisible"),
    ("inconnu", "GitHub : pas encore lu"),
    ("etat-surprise", "etat-surprise"),
])
def test_chaque_etat_a_son_message(etat, attendu):
    bloc = brs.bloc_sante(_github(etat=etat, donnees=None), _systeme())
    assert attendu in bloc and f'data-etat="{etat}"' in bloc
    # Sans donnée, la CI et le déploiement sont inconnus, jamais « verts ».
    assert bloc.count("inconnu") >= 2 and "réussie" not in bloc
    assert "À jour" not in bloc


def test_inconnu_dit_si_la_lecture_est_lancee():
    assert "la première lecture est lancée" in brs.bloc_sante(
        _github("inconnu", None, relance=True), _systeme())
    assert "n'a pas pu être lancée" in brs.bloc_sante(
        _github("inconnu", None, relance=False), _systeme())


def test_des_donnees_gardees_apres_une_panne_restent_avec_leur_age():
    bloc = brs.bloc_sante(_github("panne", age=7200, detail="HTTP 403"), _systeme())
    assert "GitHub injoignable (HTTP 403)" in bloc
    assert "Ce sont les données d'il y a 2 h 00" in bloc
    assert "réussie" in bloc and "À jour" not in bloc


def test_des_donnees_trop_vieilles_ne_sont_plus_dites_a_jour():
    """Tour 1, F9 : au-delà de 2 fois la fraîcheur de la source, « Périmé », pas « À jour »."""
    limite = int(2 * bord_distant.FRAICHEUR.total_seconds())
    assert "À jour · lu il y a 20 min" in brs.bloc_sante(_github(age=limite), _systeme())
    bloc = brs.bloc_sante(_github(age=limite + 1), _systeme())
    assert "Périmé · lu il y a 20 min" in bloc and "À jour" not in bloc
    assert 'data-etat="ok"' in bloc


def test_une_panne_de_la_ci_ou_du_deploiement_est_dite_et_echappee():
    """Tour 1, lot A : `pannes` dit pourquoi un bloc est inconnu."""
    donnees = {"ci": None, "deploiement": None, "jeton": None,
               "pannes": {"ci": {"etat": "panne", "detail": "HTTP 500"},
                          "deploiement": {"etat": "limite", "detail": CHARGE}}}
    bloc = brs.bloc_sante(_github(donnees=donnees), _systeme())
    assert "inconnu (panne : HTTP 500)" in bloc
    assert "<script>alert" not in bloc and "&quot;&gt;&lt;script&gt;" in bloc
    sans_detail = {"ci": None, "deploiement": None, "pannes": {"ci": {"etat": "limite"}}}
    assert "inconnu (panne : limite)" in brs.bloc_sante(_github(donnees=sans_detail), _systeme())
    for pannes in (None, "texte", {"ci": "texte"}, {}):
        bloc = brs.bloc_sante(_github(donnees={"ci": None, "deploiement": None,
                                               "pannes": pannes}), _systeme())
        assert "panne :" not in bloc


def test_un_jeton_refuse_est_dit():
    donnees = {"ci": _course(), "deploiement": None, "jeton": "refuse"}
    assert "Jeton GitHub refusé : lecture anonyme." in brs.bloc_sante(
        _github(donnees=donnees), _systeme())
    for jeton in (None, "autre"):
        assert "Jeton" not in brs.bloc_sante(
            _github(donnees={"ci": None, "deploiement": None, "jeton": jeton}), _systeme())


def test_aucun_bloc_github_se_lit_inconnu():
    for github in (None, _github(donnees={"depot": "x", "ci": None, "deploiement": None})):
        bloc = brs.bloc_sante(github, _systeme())
        assert "CI de main" in bloc and "réussie" not in bloc and "verte" not in bloc
        assert bloc.count("inconnu") >= 2


def test_une_course_de_forme_inattendue_est_inconnue():
    donnees = {"ci": "texte", "deploiement": ["x"]}
    assert "réussie" not in brs.bloc_sante(_github(donnees=donnees), _systeme())


@pytest.mark.parametrize("conclusion,cle,texte", [
    ("success", "ok", "réussie"), ("failure", "echec", "échec"),
    ("cancelled", "annule", "annulée"), ("timed_out", "autre", "autre : timed_out")])
def test_conclusions(conclusion, cle, texte):
    bloc = brs.bloc_sante(_github(donnees={"ci": _course(conclusion), "deploiement": None}),
                          _systeme())
    assert f'data-conclusion="{cle}"' in bloc and texte in bloc


def test_conclusion_piegee_echappee():
    bloc = brs.bloc_sante(_github(donnees={"ci": _course(CHARGE), "deploiement": None}),
                          _systeme())
    assert "<script>alert" not in bloc and '"><script>' not in bloc


def test_date_illisible_ou_absente_est_dite():
    donnees = {"ci": _course(date="pas une date"), "deploiement": _course(date=None)}
    bloc = brs.bloc_sante(_github(donnees=donnees), _systeme())
    assert bloc.count("date inconnue") == 2


# ---- Les liens (F21) -------------------------------------------------------

@pytest.mark.parametrize("adresse", [
    JS, "http://github.com/x", "https://github.com.evil.test/x", "https://evil.test/github.com/",
    "https://github.com\\@evil.test/x", "https://evil.com\\@github.com/x",
    "https://evil.com@github.com/x", "https://github.com:443@evil.test/x", "", None, 42, CHARGE])
def test_un_lien_qui_n_est_pas_github_devient_du_texte(adresse):
    bloc = brs.bloc_sante(_github(donnees={"ci": _course(adresse=adresse), "deploiement": None}),
                          _systeme())
    assert "<a " not in bloc and "href=" not in bloc
    assert "<script>alert" not in bloc and '"><script>' not in bloc


def test_le_texte_de_l_adresse_refusee_est_echappe_et_coupe():
    adresse = "https://evil.test/" + CHARGE + "x" * 300
    bloc = brs.bloc_sante(_github(donnees={"ci": _course(adresse=adresse), "deploiement": None}),
                          _systeme())
    assert "&lt;script&gt;" in bloc and "x" * 200 not in bloc


# ---- L'image ---------------------------------------------------------------

def test_image_selon_compose():
    bloc = brs.bloc_sante(_github(), _systeme())
    assert "reco-atelier:2026-11-14-pillow13" in bloc and "selon compose.yml" in bloc


def test_image_inconnue_ou_systeme_absent():
    assert "Image de la chaîne : inconnue" in brs.bloc_sante(_github(), _systeme(image=None))
    assert "Image de la chaîne : inconnue" in brs.bloc_sante(_github(), None)


def test_image_piegee_echappee():
    bloc = brs.bloc_sante(_github(), _systeme(image=CHARGE))
    assert "<script>alert" not in bloc


# ---- Coûts -----------------------------------------------------------------

def test_couts_des_deux_semaines_avec_detail_par_modele():
    bloc = brs.bloc_couts(_systeme())
    assert "7 derniers jours" in bloc and "7 jours d'avant" in bloc
    assert "1,75 $" in bloc and "12 appels" in bloc
    assert "0,30 $" in bloc and "3 appels" in bloc
    assert bloc.index("claude-opus-5") < bloc.index("claude-sonnet-5")  # le plus cher d'abord
    assert "1,25 $" in bloc and "0,50 $" in bloc


def test_un_cout_inconnu_ne_s_affiche_jamais_zero():
    sem = _fenetre(appels=4, cout=_cout(None, inconnus=4), par_modele={"m": _cout(None, 4)})
    bloc = brs.bloc_couts(_systeme(couts={"semaine": sem, "precedente": None}))
    assert "0 $" not in bloc and "0,00" not in bloc
    assert "inconnu" in bloc
    assert "7 jours d'avant : inconnu" in bloc  # fenêtre None


def test_un_cout_minimum_s_affiche_au_moins():
    sem = _fenetre(cout=_cout("1.750000", inconnus=2), par_modele={"m": _cout("1.0", 1)})
    bloc = brs.bloc_couts(_systeme(couts={"semaine": sem, "precedente": None}))
    assert "au moins 1,75 $" in bloc and "2 appels sans coût connu" in bloc
    assert "au moins 1,00 $" in bloc and "1 appel sans coût connu" in bloc


def test_aucun_appel_est_une_mesure():
    sem = _fenetre(appels=0, cout=_cout(None, 0), par_modele={})
    bloc = brs.bloc_couts(_systeme(couts={"semaine": sem, "precedente": None}))
    assert "aucun appel" in bloc


def test_un_petit_montant_n_est_pas_arrondi_a_zero():
    sem = _fenetre(cout=_cout("0.003000"), par_modele={})
    assert "0,0030 $" in brs.bloc_couts(_systeme(couts={"semaine": sem, "precedente": None}))


def test_plusieurs_devises_et_devise_inconnue():
    cout = {"known": {"USD": "1.0", "EUR": "2.5", "CHF": "pas un nombre"},
            "unknownCostCalls": 0, "pricingCoverage": 1.0}
    bloc = brs.bloc_couts(_systeme(couts={"semaine": _fenetre(cout=cout, par_modele={}),
                                          "precedente": None}))
    assert "1,00 $" in bloc and "2,50 EUR" in bloc and "CHF ?" in bloc


def test_couts_absents_ou_de_forme_inattendue_sont_inconnus():
    for systeme in (None, _systeme(couts=None), _systeme(couts={"semaine": "x", "precedente": []}),
                    _systeme(couts={"semaine": {"appels": "?", "cout": 5, "par_modele": 3},
                                    "precedente": None})):
        bloc = brs.bloc_couts(systeme)
        assert "7 derniers jours : inconnu" in bloc and "$" not in bloc


def test_la_liste_des_modeles_est_coupee_et_le_dit():
    modeles = {f"m{i}": _cout(f"{i}.0") for i in range(1, 8)}
    sem = _fenetre(par_modele=modeles)
    bloc = brs.bloc_couts(_systeme(couts={"semaine": sem, "precedente": None}))
    assert bloc.count('<li') == 5 and "+ 2 autres" in bloc
    assert "m7" in bloc and "m3" in bloc and "m2<" not in bloc  # les plus chers restent


def test_cinq_modeles_ne_sont_pas_coupes():
    sem = _fenetre(par_modele={f"m{i}": _cout("1.0") for i in range(5)})
    assert "autres" not in brs.bloc_couts(_systeme(couts={"semaine": sem, "precedente": None}))


def test_un_modele_au_cout_inconnu_vient_apres_les_autres():
    sem = _fenetre(par_modele={"a": _cout(None, 3), "b": _cout("0.1")})
    bloc = brs.bloc_couts(_systeme(couts={"semaine": sem, "precedente": None}))
    assert bloc.index(">b<") < bloc.index(">a<")


def test_un_nom_de_modele_piege_est_echappe():
    sem = _fenetre(par_modele={CHARGE: _cout()})
    bloc = brs.bloc_couts(_systeme(couts={"semaine": sem, "precedente": None}))
    assert "<script>alert" not in bloc and "&lt;script&gt;" in bloc


# ---- Modèles ---------------------------------------------------------------

def test_modele_mesure_et_secours():
    bloc = brs.bloc_couts(_systeme())
    assert "Extraction : claude-opus-5" in bloc and "mesuré le 27/11" in bloc
    assert "Secours : claude-sonnet-5" in bloc and ".env au démarrage" in bloc


def test_modele_de_l_environnement_et_secours_coupe():
    modeles = {"extraction": {"nom": "claude-haiku-5", "source": "env", "date": None},
               "secours": {"nom": None, "source": "env"}}
    bloc = brs.bloc_couts(_systeme(modeles=modeles))
    assert "Extraction : claude-haiku-5 (.env au démarrage)" in bloc
    assert "Secours : aucun" in bloc


def test_mesure_sans_date_lisible():
    modeles = {"extraction": {"nom": "m", "source": "mesure", "date": "n'importe quoi"},
               "secours": {"nom": "s", "source": "env"}}
    assert "mesuré, date inconnue" in brs.bloc_couts(_systeme(modeles=modeles))


def test_modeles_absents_ou_de_forme_inattendue_sont_inconnus():
    for modeles in (None, "x", {"extraction": None, "secours": 3}):
        bloc = brs.bloc_couts(_systeme(modeles=modeles))
        assert "Extraction : inconnu" in bloc and "Secours : inconnu" in bloc
    assert "Extraction : inconnu" in brs.bloc_couts(None)


def test_noms_de_modeles_pieges_echappes():
    modeles = {"extraction": {"nom": CHARGE, "source": "env", "date": None},
               "secours": {"nom": CHARGE, "source": "env"}}
    bloc = brs.bloc_couts(_systeme(modeles=modeles))
    assert "<script>alert" not in bloc and '"><script>' not in bloc


# ---- Dans la page ------------------------------------------------------------

def _page(**kw):
    chaine = {"episode": None, "etapes": [], "passages": [], "erreurs": [], "etat_lu": True}
    args = {"titre": "Un Bon Moment", "afaire": [], "chaine": chaine,
            "recents": [], "coches": {}, "maintenant": MAINTENANT}
    args.update(kw)
    return br.rendre_bord(**args)


def _colonne(page, cle):
    return page.split(f'id="bord-{cle}"', 1)[1].split("</section>", 1)[0]


def _sans_balise_active(page):
    assert "<script>alert" not in page and 'href="javascript:' not in page
    assert '"><script>' not in page


def test_le_systeme_montre_la_sante_et_les_couts_sans_donnees_comme_inconnus():
    systeme = _colonne(_page(), "systeme")
    assert "Santé et versions" in systeme and "Coûts et modèles" in systeme
    assert "GitHub : pas encore lu" in systeme and "Image de la chaîne : inconnue" in systeme
    assert "7 derniers jours : inconnu" in systeme and "Extraction : inconnu" in systeme
    assert "Santé et versions</span><p class=\"bord-mut\">en attente" not in systeme


def test_le_systeme_rend_les_donnees_de_github_et_de_la_chaine():
    github = {"etat": "ok", "donnees": {"ci": {"conclusion": "failure", "date": "2026-11-29T08:00:00Z",
                                                "adresse": "https://github.com/a/b/actions/runs/1"},
                                        "deploiement": None}, "age": 60}
    systeme = {"couts": {"semaine": None, "precedente": None},
               "modeles": {"extraction": {"nom": "claude-x", "source": "env", "date": None},
                           "secours": {"nom": None, "source": "env"}},
               "image": "reco-atelier:1"}
    colonne = _colonne(_page(github=github, systeme=systeme), "systeme")
    assert 'data-conclusion="echec"' in colonne and "reco-atelier:1" in colonne
    assert "Extraction : claude-x" in colonne


def test_les_donnees_du_systeme_piegees_ne_cassent_pas_la_page():
    github = {"etat": CHARGE, "donnees": {"ci": {"conclusion": CHARGE, "adresse": JS},
                                          "deploiement": None}}
    systeme = {"couts": None, "modeles": None, "image": CHARGE}
    _sans_balise_active(_page(github=github, systeme=systeme))


def test_une_adresse_illisible_devient_du_texte():
    donnees = {"ci": _course(adresse="https://[pas-une-ip/x"), "deploiement": None}
    assert "<a " not in brs.bloc_sante(_github(donnees=donnees), _systeme())
