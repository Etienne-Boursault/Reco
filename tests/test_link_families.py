"""Tests de tools/link_families.py.

Ce module sert à décider OÙ ALLER CHERCHER un lien manquant. Une famille
inventée envoie donc chercher au mauvais endroit, et un lien trouvé là est un
homonyme — c'est-à-dire pire que le manque qu'on croyait combler. La moitié des
tests vérifient qu'il se tait plutôt que de deviner.
"""
from __future__ import annotations

import pytest

import link_families as lf


# ---------------------------------------------------------------------------
# La comparaison en suffixe — ce qui manquait à la première version
# ---------------------------------------------------------------------------
def test_un_sous_domaine_est_reconnu():
    """`cameronwinter.bandcamp.com` EST un compte Bandcamp. Une égalité stricte
    le manquait, et rangeait un musicien parmi les indécidables."""
    assert lf.famille("https://cameronwinter.bandcamp.com/album/heavy-metal") == "ecoute"
    assert lf.famille("https://yann-tiersen.bandcamp.com/") == "ecoute"


def test_wikipedia_est_reconnue_dans_toutes_ses_langues():
    assert lf.famille("https://fr.wikipedia.org/wiki/Ricky_Gervais") == "encyclopedie"
    assert lf.famille("https://en.wikipedia.org/wiki/Coexister") == "encyclopedie"


def test_le_suffixe_le_plus_long_gagne():
    """`music.apple.com` est de l'écoute, `podcasts.apple.com` du podcast :
    un préfixe commun ne doit pas les confondre."""
    assert lf.famille("https://music.apple.com/fr/album/x/1") == "ecoute"
    assert lf.famille("https://podcasts.apple.com/fr/podcast/x/id1") == "podcast"
    assert lf.famille("https://tv.apple.com/fr/show/x") == "visionnage"


@pytest.mark.parametrize(("url", "attendu"), [
    ("https://www.printemps-bourges.com/artiste/zs/", "ecoute"),
    ("https://www.welovecomedy.fr/artistes/julie-albertine", "billetterie"),
    ("https://allary-editions.fr/livre/x", "libraire"),
    ("https://www.instagram.com/emy_bng/", "reseau"),
    ("https://www.allocine.fr/film/fichefilm_gen_cfilm=6608.html", "fiche"),
    ("https://www.netflix.com/fr/title/80189653", "visionnage"),
    ("https://store.steampowered.com/app/1", "jeu"),
    ("https://apps.apple.com/fr/app/daylio/id1", "application"),
])
def test_les_hotes_qui_manquaient_au_premier_tri(url, attendu):
    """Ces hôtes disent clairement de quoi il s'agit, et le premier tri les
    ignorait tous — d'où sa catégorie « indécis » démesurée."""
    assert lf.famille(url) == attendu


# ---------------------------------------------------------------------------
# Ce que le module REFUSE de deviner
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("url", [
    "https://site-personnel-inconnu.fr/une/page",
    "https://exemple.com/",
    "",
    None,
])
def test_un_hote_inconnu_reste_sans_famille(url):
    """Mieux vaut une famille absente qu'une famille inventée : c'est sur elle
    qu'on décidera d'aller chercher."""
    assert lf.famille(url) is None


def test_une_url_illisible_ne_leve_pas():
    """`urlparse` lève sur un IPv6 malformé. Une URL de travers ne doit pas
    faire tomber tout un audit."""
    assert lf.famille("https://[::1") is None
    assert lf.hote_de("https://[::1") == ""


# ---------------------------------------------------------------------------
# Familles présentes et manquantes
# ---------------------------------------------------------------------------
def _lien(url):
    return {"url": url, "label": "L"}


def test_familles_presentes_dedoublonne():
    liens = [_lien("https://www.deezer.com/artist/1"),
             _lien("https://open.spotify.com/artist/2")]
    assert lf.familles_presentes(liens) == {"ecoute"}


def test_familles_presentes_ignore_les_entrees_mal_formees():
    """Le corpus contient de la donnée héritée : elle ne doit pas faire tomber
    l'audit."""
    assert lf.familles_presentes([_lien("https://www.deezer.com/artist/1"),
                                  "hérité", None]) == {"ecoute"}


def test_un_film_veut_une_fiche_ET_un_visionnage():
    manque = lf.familles_manquantes(
        ["film"], [_lien("https://www.imdb.com/title/tt1/")])
    assert manque == {"visionnage"}


def test_un_film_complet_ne_manque_de_rien():
    liens = [_lien("https://www.imdb.com/title/tt1/"),
             _lien("https://www.netflix.com/fr/title/1")]
    assert lf.familles_manquantes(["film"], liens) == set()


def test_un_livre_veut_un_libraire():
    assert lf.familles_manquantes(["livre"], []) == {"libraire"}


def test_un_spectacle_veut_une_billetterie():
    assert lf.familles_manquantes(["spectacle"], []) == {"billetterie"}


def test_le_type_artiste_n_attend_RIEN():
    """Le cœur du module. `artiste` couvre aussi bien un chanteur qu'un
    humoriste : réclamer un lien d'écoute pour tous produirait des homonymes.
    C'est la même raison qui rend `artiste` opt-in dans `enrich_music_links`."""
    assert lf.familles_manquantes(["artiste"], []) == set()


def test_un_type_inconnu_n_attend_rien():
    assert lf.familles_manquantes(["type-invente"], []) == set()


def test_une_reco_MULTI_TYPES_cumule_les_attentes():
    manque = lf.familles_manquantes(["film", "livre"], [])
    assert manque == {"fiche", "visionnage", "libraire"}


def test_un_reseau_social_ne_comble_AUCUNE_attente():
    """Un compte Instagram ne remplace ni une billetterie ni un libraire : il
    dit où suivre la personne, pas où voir l'œuvre."""
    liens = [_lien("https://www.instagram.com/quelquun/")]
    assert lf.familles_manquantes(["spectacle"], liens) == {"billetterie"}


def test_aucun_lien_du_tout():
    assert lf.familles_manquantes(["film"], None) == {"fiche", "visionnage"}


# ---------------------------------------------------------------------------
# Cohérence de la table
# ---------------------------------------------------------------------------
def test_toutes_les_familles_attendues_existent_dans_la_table():
    """Réclamer une famille qu'aucun hôte ne peut fournir rendrait le manque
    inextinguible : la reco resterait signalée à jamais."""
    fournies = set(lf.HOTES.values())
    for typ, attendues in lf.FAMILLES_ATTENDUES.items():
        for f in attendues:
            assert f in fournies, f"{typ} attend « {f} », qu'aucun hôte ne fournit"


def test_aucun_hote_ne_porte_le_prefixe_www():
    """`hote_de` le retire déjà : le laisser dans la table le rendrait
    inatteignable."""
    for cle in lf.HOTES:
        assert not cle.startswith("www."), cle


# ---------------------------------------------------------------------------
# Quand l'hôte ne suffit pas : le chemin tranche
# ---------------------------------------------------------------------------
def test_la_page_de_visionnage_TMDB_n_est_pas_une_fiche():
    """`themoviedb.org` sert les deux. Les confondre rendait l'audit aveugle à
    ce que la passe de visionnage venait elle-même de poser : 125 recos
    pourvues restaient comptées « sans visionnage »."""
    assert lf.famille("https://www.themoviedb.org/movie/424277-annette/watch?locale=FR") == "visionnage"
    assert lf.famille("https://www.themoviedb.org/movie/424277") == "fiche"


def test_un_film_avec_fiche_ET_page_de_visionnage_TMDB_ne_manque_de_rien():
    liens = [_lien("https://www.themoviedb.org/movie/1"),
             _lien("https://www.themoviedb.org/movie/1-x/watch?locale=FR")]
    assert lf.familles_manquantes(["film"], liens) == set()


def test_le_chemin_ne_s_applique_qu_a_son_hote():
    """Un `/watch` ailleurs ne doit pas devenir un visionnage par accident."""
    assert lf.famille("https://www.youtube.com/watch?v=abc") == "video"


def test_tous_les_hotes_a_chemin_sont_dans_la_table_principale():
    """Un hôte listé dans `_CHEMINS` mais absent de `HOTES` n'aurait aucune
    famille par défaut — son cas hors-chemin tomberait silencieusement."""
    for cle in lf._CHEMINS:
        assert cle in lf.HOTES, cle
