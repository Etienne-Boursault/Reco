"""Tests du verdict : est-ce bien la bonne personne ? Aucun réseau ici.

Les entités sont construites à la main, telles que Wikidata les a réellement
rendues le 2026-09-27 (relevé dans l'en-tête de `enrich_wikidata_links`). Le test
le plus important est celui du village : il verrouille le seul piège mesuré.
"""
from __future__ import annotations

import pytest

import wikidata_matching as wm

# Relevés réels. Le village porte le même titre d'article que la chanteuse, et
# c'est lui que `fr.wikipedia.org/wiki/Yoa` sert.
FABE = wm.Entite(qid="Q3063503", label="Fabe", natures=("Q5",), frwiki="Fabe",
                 claims={"P31": ("Q5",)})
VILLAGE_INDONESIEN = wm.Entite(
    qid="Q25796185", label="Fabe", natures=("Q12488913",), frwiki="Fabe",
    claims={"P31": ("Q12488913",)})
VILLAGE_YOA = wm.Entite(qid="Q28041053", label="Yoa", natures=("Q486972",),
                        frwiki="Yoa", claims={"P31": ("Q486972",)})
CHANTEUSE_YOA = wm.Entite(
    qid="Q124961805", label="Yoa", natures=("Q5",), frwiki="Yoa (artiste)",
    claims={"P31": ("Q5",), "P1902": ("7d1ctWXfrUvAe804Zld3Gy",)})
SOLANN = wm.Entite(
    qid="Q130304844", label="Solann", natures=("Q5",), frwiki="Solann",
    claims={"P31": ("Q5",), "P2722": ("78965772",), "P2003": ("solann_zla",),
            "P856": ("https://solann.fr/",)})
EFIRA = wm.Entite(
    qid="Q3560737", label="Virginie Efira", natures=("Q5",), frwiki="Virginie Efira",
    claims={"P31": ("Q5",), "P1266": ("97635",), "P345": ("nm1812637",),
            "P2003": ("efira_virginie",)})


def reco(**champs):
    base = {"id": "ubm-1", "title": "Fabe", "types": ["artiste"],
            "status": "validated", "links": []}
    return {**base, **champs}


# ===== le piège mesuré ======================================================
def test_le_village_homonyme_ne_passe_jamais():
    """« Fabe » et « Yoa » nomment aussi des villages : seul P31 les arrête.

    C'est LE cas qui justifie ce garde-fou : le titre d'article est une clé
    exacte, mais une clé exacte vers la mauvaise chose.
    """
    for village in (VILLAGE_INDONESIEN, VILLAGE_YOA):
        titre = village.label
        resolution = wm.verdict(reco(title=titre),
                                [(village, wm.PREUVE_TITRE)])
        assert resolution.liens == ()
        assert resolution.raison == wm.RAISON_TYPE_INCOMPATIBLE


def test_le_rappeur_francais_passe_lui():
    """Même titre, même chemin : c'est la nature qui fait la différence."""
    resolution = wm.verdict(reco(), [(FABE, wm.PREUVE_TITRE)])

    assert resolution.raison == wm.RAISON_OK
    assert [lien.url for lien in resolution.liens] == [
        "https://fr.wikipedia.org/wiki/Fabe"]


# ===== la preuve la plus forte : l'identifiant ===============================
def test_un_identifiant_commun_suffit_a_prouver_lidentite():
    """Deezer 78965772 dans la reco ET dans l'entité : c'est un fait."""
    r = reco(title="Solann", externalIds={"deezer": "https://www.deezer.com/artist/78965772"})

    resolution = wm.verdict(r, [(SOLANN, wm.PREUVE_IDENTIFIANT)])

    assert resolution.raison == wm.RAISON_OK
    assert resolution.preuve == wm.PREUVE_IDENTIFIANT
    assert {lien.source for lien in resolution.liens} == {
        "site-officiel", "instagram", "wikipedia"}


def test_la_preuve_par_identifiant_dispense_de_la_nature():
    """Fiche Wikidata sans P31 : l'identité est acquise, on ne perd pas le lien."""
    sans_nature = wm.Entite(qid="Q1", label="Qui Que Ce Soit", frwiki="Untel",
                            claims={"P2722": ("42",), "P2003": ("untel",)})
    r = reco(title="Rien à voir", externalIds={"deezer": "42"})

    resolution = wm.verdict(r, [(sans_nature, wm.PREUVE_IDENTIFIANT)])

    assert resolution.raison == wm.RAISON_OK


def test_un_identifiant_different_fait_refuser_meme_sur_bon_titre():
    """Deux valeurs sur la même propriété = deux personnes. Refus net."""
    r = reco(title="Solann",
             externalIds={"deezer": "https://www.deezer.com/artist/999999"})

    resolution = wm.verdict(r, [(SOLANN, wm.PREUVE_TITRE)])

    assert resolution.liens == ()
    assert resolution.raison == wm.RAISON_ID_MISMATCH
    assert "P2722" in resolution.detail


# ===== les autres refus =====================================================
def test_deux_entites_distinctes_ne_sont_pas_tranchees():
    resolution = wm.verdict(reco(), [(FABE, wm.PREUVE_TITRE),
                                     (VILLAGE_INDONESIEN, wm.PREUVE_TITRE)])

    assert resolution.raison == wm.RAISON_AMBIGUOUS
    assert "Q3063503" in resolution.detail and "Q25796185" in resolution.detail


def test_un_libelle_qui_ne_correspond_pas_est_refuse():
    """Article trouvé par redirection : le libellé ne nomme pas la reco."""
    autre = wm.Entite(qid="Q9", label="Quelqu'un d'autre", natures=("Q5",),
                      frwiki="Fabe", claims={"P31": ("Q5",)})

    resolution = wm.verdict(reco(), [(autre, wm.PREUVE_TITRE)])

    assert resolution.raison == wm.RAISON_LABEL_MISMATCH


def test_un_alias_suffit_a_reconnaitre_la_personne():
    avec_alias = wm.Entite(qid="Q9", label="Fabien Marsaud", alias=("Fabe",),
                           natures=("Q5",), frwiki="Fabe", claims={"P31": ("Q5",)})

    assert wm.verdict(reco(), [(avec_alias, wm.PREUVE_TITRE)]).raison == wm.RAISON_OK


def test_aucune_entite_nest_pas_une_erreur():
    assert wm.verdict(reco(), []).raison == wm.RAISON_NO_ENTITY


def test_un_type_non_servi_est_ecarte_avant_tout():
    for types in (["lieu"], ["autre"], ["film"], []):
        assert wm.verdict(reco(types=types),
                          [(FABE, wm.PREUVE_IDENTIFIANT)]).raison == \
            wm.RAISON_TYPE_UNSUPPORTED


def test_un_groupe_et_un_duo_sont_admis():
    """Bigflo & Oli ne porte que « duo musical » : refuser serait une perte."""
    for nature in ("Q215380", "Q9212979"):
        groupe = wm.Entite(qid="Q7", label="Fabe", natures=(nature,), frwiki="Fabe",
                           claims={"P31": (nature,)})
        assert wm.verdict(reco(), [(groupe, wm.PREUVE_TITRE)]).raison == wm.RAISON_OK


# ===== ce que l'entité offre, et ce qu'elle n'écrase pas =====================
def test_un_lien_deja_pose_nest_jamais_double():
    r = reco(title="Virginie Efira", links=[
        {"kind": "social", "ethics": "neutral", "label": "Instagram",
         "url": "https://www.instagram.com/efira_virginie/"}])

    resolution = wm.verdict(r, [(EFIRA, wm.PREUVE_TITRE)])

    sources = {lien.source for lien in resolution.liens}
    assert "instagram" not in sources
    assert sources == {"allocine", "imdb", "wikipedia"}


def test_une_entite_sans_rien_de_neuf_le_dit():
    r = reco(links=[{"kind": "info", "ethics": "indie", "label": "Wikipédia",
                     "url": "https://fr.wikipedia.org/wiki/Fabe"}])

    assert wm.verdict(r, [(FABE, wm.PREUVE_TITRE)]).raison == wm.RAISON_NO_NEW_LINK


def test_les_url_suivent_le_schema_de_chaque_site():
    resolution = wm.verdict(reco(title="Virginie Efira"),
                            [(EFIRA, wm.PREUVE_TITRE)])
    urls = {lien.source: lien.url for lien in resolution.liens}

    assert urls["allocine"] == (
        "https://www.allocine.fr/personne/fichepersonne_gen_cpersonne=97635.html")
    assert urls["imdb"] == "https://www.imdb.com/name/nm1812637/"
    assert urls["instagram"] == "https://www.instagram.com/efira_virginie/"


@pytest.mark.parametrize("valeur,attendu", [
    ("nm0037625", "https://www.imdb.com/name/nm0037625/"),
    ("tt12262116", "https://www.imdb.com/title/tt12262116/"),
    ("zz1234", None),      # préfixe inconnu : on ne devine pas
])
def test_imdb_distingue_personne_et_oeuvre(valeur, attendu):
    assert wm._url_imdb(valeur) == attendu


def test_un_site_officiel_qui_nest_pas_une_url_est_ignore():
    bancal = wm.Entite(qid="Q9", label="Fabe", natures=("Q5",), frwiki="Fabe",
                       claims={"P31": ("Q5",), "P856": ("pas-une-url",)})

    sources = {lien.source
               for lien in wm.verdict(reco(), [(bancal, wm.PREUVE_TITRE)]).liens}
    assert "site-officiel" not in sources


def test_une_fiche_allocine_non_numerique_est_ignoree():
    assert wm._url_allocine("abc") is None


@pytest.mark.parametrize("titre,attendu", [
    ("Solann", "Solann"),
    ("Ben Mazué", "Ben_Mazu%C3%A9"),
    # Le corpus garde parenthèses, apostrophes, points et virgules en clair.
    ("Yoa (artiste)", "Yoa_(artiste)"),
    ("Le Monde à l'Envers (chaîne YouTube)",
     "Le_Monde_%C3%A0_l'Envers_(cha%C3%AEne_YouTube)"),
    ("Mr. et Mrs. Smith (série télévisée, 2024)",
     "Mr._et_Mrs._Smith_(s%C3%A9rie_t%C3%A9l%C3%A9vis%C3%A9e,_2024)"),
])
def test_wikipedia_encode_les_accents_et_seulement_eux(titre, attendu):
    """Les trois derniers cas sont des URL réelles du corpus, à l'identique."""
    assert wm.url_wikipedia(titre) == f"https://fr.wikipedia.org/wiki/{attendu}"


# ===== les identifiants que la reco porte déjà ==============================
@pytest.mark.parametrize("reco_partielle,attendu", [
    ({"externalIds": {"deezer": "https://www.deezer.com/artist/2691"}},
     {"P2722": "2691"}),
    ({"externalIds": {"deezer": "13674"}}, {"P2722": "13674"}),
    ({"links": [{"url": "https://www.deezer.com/fr/artist/7768"}]},
     {"P2722": "7768"}),
    ({"links": [{"url": "https://open.spotify.com/artist/73BDzWqbf1grbgQ8xYn2ou"}]},
     {"P1902": "73BDzWqbf1grbgQ8xYn2ou"}),
    ({"links": [{"url": "https://open.spotify.com/intl-fr/artist/4Fp"}]},
     {"P1902": "4Fp"}),
    # Un album n'identifie pas une personne : seule la page ARTISTE compte.
    ({"links": [{"url": "https://www.deezer.com/album/989085991"}]}, {}),
    ({"externalIds": {"deezer": "https://www.deezer.com/track/42"}}, {}),
    ({}, {}),
])
def test_les_identifiants_portes_sont_lus_des_deux_gisements(reco_partielle, attendu):
    assert wm.identifiants_portes(reco(**reco_partielle)) == attendu


def test_hote_ignore_le_www_et_la_casse():
    assert wm.hote("https://WWW.Imdb.com/name/nm1/") == "imdb.com"
    assert wm.hote("https://fr.wikipedia.org/wiki/X") == "fr.wikipedia.org"
