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
    for typ, attentes in lf.FAMILLES_ATTENDUES.items():
        for alternatives in attentes:
            assert alternatives, f"{typ} porte une attente vide"
            for f in alternatives:
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


def test_les_familles_de_CHEMINS_existent_dans_la_table():
    """Un hôte peut n'exister QUE dans `_CHEMINS` — `apple.com` sert trop de
    choses pour qu'une famille unique ne mente pas, et seul le chemin d'un
    produit le qualifie. En revanche la famille nommée doit exister, sans quoi
    on créerait un manque que rien ne peut combler."""
    fournies = set(lf.HOTES.values())
    for cle, regles in lf._CHEMINS.items():
        assert regles, cle
        for _, fam in regles:
            assert fam in fournies, f"{cle} produit « {fam} », inconnue ailleurs"


def test_un_hote_generique_hors_de_SON_chemin_n_a_aucune_famille():
    """C'est la contrepartie : `apple.com` ne doit rien qualifier en dehors de
    la page produit qui l'a fait entrer."""
    assert lf.famille("https://www.apple.com/fr/apple-fitness-plus/") == "application"
    assert lf.famille("https://www.apple.com/fr/iphone/") is None
    assert lf.famille("https://www.linkedin.com/learning/courses") == "application"
    assert lf.famille("https://www.linkedin.com/in/quelquun/") is None


# ---------------------------------------------------------------------------
# Spotify et Deezer diffusent DEUX choses
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("url", "attendu"), [
    ("https://open.spotify.com/show/4rOoJ6Egrf8K2IrywzwOMk", "podcast"),
    ("https://open.spotify.com/episode/abc", "podcast"),
    ("https://open.spotify.com/album/123", "ecoute"),
    ("https://open.spotify.com/artist/123", "ecoute"),
    ("https://www.deezer.com/show/1002058731", "podcast"),
    ("https://www.deezer.com/album/70", "ecoute"),
])
def test_le_chemin_separe_le_podcast_de_la_musique(url, attendu):
    """Ranger ces hôtes entièrement du côté « écoute » signalait comme
    dépourvues de podcast trente-quatre recos qui en portaient un : le lien
    était là, l'audit ne savait pas le lire."""
    assert lf.famille(url) == attendu


def test_la_locale_intercalee_par_spotify_ne_masque_pas_le_chemin():
    """Spotify insère parfois `/intl-fr/` : exiger le fragment en tête du
    chemin aurait raté vingt-sept liens du corpus."""
    assert lf.famille("https://open.spotify.com/intl-fr/show/abc") == "podcast"
    assert lf.famille("https://open.spotify.com/intl-fr/album/abc") == "ecoute"


@pytest.mark.parametrize("url", [
    "https://www.arteradio.com/serie/l_ecole_c_est_de_la_merde",
    "https://www.binge.audio/podcast/x",
    "https://podcasts.audiomeans.fr/le-precepteur-144bb12e80d6",
    "https://podcastaddict.com/podcast/x/5977186",
    "https://lavoixdanstatete.com/podcast/les-gens-qui-doutent/",
])
def test_les_plateformes_de_podcast_du_corpus_sont_reconnues(url):
    assert lf.famille(url) == "podcast"


def test_un_site_PERSONNEL_ne_couvre_pas_la_famille_podcast():
    """`joerogan.com` dit où trouver la personne, pas où écouter l'émission.
    L'y ranger ferait disparaître un manque réel du décompte."""
    assert lf.famille("https://www.joerogan.com/") is None
    assert lf.famille("https://billburr.com/") is None


# ---------------------------------------------------------------------------
# Un spectacle attend « un moyen d'y accéder », pas forcément un billet
# ---------------------------------------------------------------------------
def test_un_spectacle_FILME_ne_manque_pas_de_billetterie():
    """« Baby J », « Foresti Party », « L'autre c'est moi » sont finis : il n'y
    a aucune place à vendre, et ce qu'on peut en proposer au lecteur EST la
    captation. Dix-sept recos étaient signalées pour un manque que rien ne
    pouvait combler."""
    liens = [_lien("https://www.netflix.com/fr/title/81619082")]
    assert lf.familles_manquantes(["spectacle"], liens) == set()


def test_un_spectacle_qui_TOURNE_est_couvert_par_sa_billetterie():
    liens = [_lien("https://www.billetreduc.com/x/evt.htm")]
    assert lf.familles_manquantes(["spectacle"], liens) == set()


def test_un_spectacle_SANS_billet_NI_captation_reste_signale():
    """Et le manque est nommé « billetterie » : c'est ce qu'on ira chercher en
    premier pour un spectacle."""
    liens = [_lien("https://www.instagram.com/cabaretsaccage/")]
    assert lf.familles_manquantes(["spectacle"], liens) == {"billetterie"}


def test_un_album_du_spectacle_ne_remplace_PAS_le_spectacle():
    """Un disque n'est pas une captation, et une page d'artiste encore moins :
    accepter l'écoute éteindrait le signalement sur des recos qui méritent un
    vrai lien."""
    liens = [_lien("https://www.deezer.com/album/90157712")]
    assert lf.familles_manquantes(["spectacle"], liens) == {"billetterie"}


def test_infoconcert_est_une_billetterie_pas_un_service_d_ecoute():
    """Le site liste les dates de tournée et renvoie vers la vente."""
    assert lf.famille("https://www.infoconcert.com/artiste/pomme-139757/concerts") == "billetterie"


@pytest.mark.parametrize("url", [
    "https://darksmile.tv/produit/vends-2-pieces-a-beyrouth/",
    "https://vod.blanchegardin.com/spectacle/3/il-faut-que-je",
])
def test_les_boutiques_de_captation_repondent_a_ou_le_voir(url):
    assert lf.famille(url) == "visionnage"


def test_un_film_veut_toujours_SES_DEUX_attentes():
    """Le passage aux alternatives ne doit pas relâcher les autres types : un
    film sans fiche manque toujours d'une fiche, même s'il est visionnable."""
    liens = [_lien("https://www.netflix.com/fr/title/1")]
    assert lf.familles_manquantes(["film"], liens) == {"fiche"}


# ---------------------------------------------------------------------------
# Une playlist YouTube EST l'œuvre
# ---------------------------------------------------------------------------
def test_une_playlist_youtube_est_un_moyen_de_voir():
    """Onze séries web du corpus — Groom, Pitch, Serge, Le Trône des Frogz —
    se regardent là et nulle part ailleurs, et étaient signalées « sans moyen
    de voir »."""
    url = "https://www.youtube.com/playlist?list=PL-CQtpSbsGq"
    assert lf.famille(url) == "visionnage"
    assert lf.familles_manquantes(["serie"], [_lien(url),
                                              _lien("https://www.imdb.com/title/tt1/")]) == set()


def test_une_video_ISOLEE_reste_de_la_video():
    """La distinction est délibérée : une vidéo seule peut être une
    bande-annonce ou un extrait, une playlist ne l'est jamais. Confondre les
    deux ferait passer un teaser pour l'œuvre."""
    assert lf.famille("https://www.youtube.com/watch?v=abc") == "video"


def test_une_chaine_reste_couverte_par_sa_playlist():
    """La règle ne doit pas déshabiller `chaine`, qui attend `video` : une
    chaîne dont le seul lien serait une playlist ne doit pas devenir
    découverte."""
    liens = [_lien("https://www.youtube.com/@UneChaine"),
             _lien("https://www.youtube.com/playlist?list=PL1")]
    assert lf.familles_manquantes(["chaine"], liens) == set()


# ---------------------------------------------------------------------------
# Un jeu mobile s'obtient sur un store
# ---------------------------------------------------------------------------
def test_une_fiche_App_Store_repond_a_ou_avoir_le_JEU():
    """« Make More Views » porte sa fiche App Store : c'est exactement où
    l'obtenir, et la reco était pourtant signalée « sans lien de jeu »."""
    liens = [_lien("https://apps.apple.com/fr/app/make-more-views/id1438348967")]
    assert lf.familles_manquantes(["jeu"], liens) == set()


def test_un_jeu_PHYSIQUE_s_achete_chez_son_editeur():
    """Les Éditions du Trésor vendent leurs chasses au trésor à leur
    catalogue : c'est bien « où l'avoir »."""
    liens = [_lien("https://www.editionsdutresor.com/catalogue/lor-de-sipan")]
    assert lf.familles_manquantes(["jeu"], liens) == set()


@pytest.mark.parametrize(("types", "liens_url", "attendu"), [
    (["application"], "https://store.steampowered.com/app/1", {"application"}),
    (["livre"], "https://store.steampowered.com/app/1", {"libraire"}),
])
def test_les_alternatives_ne_valent_que_dans_UN_sens(types, liens_url, attendu):
    """Ni une application ni un livre ne sont un jeu. Rendre l'alternative
    symétrique ferait qu'une boutique de jeux éteindrait le manque d'une
    application — et un manque éteint ne se rallume jamais."""
    assert lf.familles_manquantes(types, [_lien(liens_url)]) == attendu


@pytest.mark.parametrize(("url", "attendu"), [
    ("https://archive.org/details/humblebragartoff0000witt", "libraire"),
    ("https://boutique.so/en-en/collections/magazines-society", "libraire"),
])
def test_les_deux_libraires_qui_manquaient(url, attendu):
    """`archive.org` prête l'ouvrage — souvent le seul recours pour un livre
    épuisé ; `boutique.so` est la boutique de So Press, qui édite Society."""
    assert lf.famille(url) == attendu


# ---------------------------------------------------------------------------
# Le `kind` dit ce que l'hôte ne peut pas savoir
# ---------------------------------------------------------------------------
def _lien_kind(url, kind):
    return {"url": url, "label": "L", "kind": kind}


def test_une_video_marquee_streaming_EST_un_moyen_de_voir():
    """Le corpus distingue déjà, à la main, le lien qui mène à l'ŒUVRE de
    celui qui mène à son auteur : « Film complet », « Minuit 01 à 07 » portent
    `streaming`, une simple chaîne porte `official`."""
    liens = [_lien_kind("https://www.youtube.com/watch?v=abc", "streaming")]
    assert lf.familles_presentes(liens) == {"video", "visionnage"}


def test_une_video_marquee_official_reste_une_simple_video():
    """C'est la moitié qui protège : sans marqueur, une vidéo isolée peut être
    une bande-annonce, et la compter comme un visionnage éteindrait un vrai
    manque."""
    liens = [_lien_kind("https://www.youtube.com/watch?v=abc", "official")]
    assert lf.familles_presentes(liens) == {"video"}


def test_la_promotion_n_ENLEVE_pas_la_famille_d_origine():
    """Une reco `chaine` attend `video` : si la promotion remplaçait au lieu
    d'ajouter, le même lien la laisserait découverte."""
    liens = [_lien_kind("https://www.youtube.com/watch?v=abc", "streaming")]
    assert lf.familles_manquantes(["chaine"], liens) == set()
    assert lf.familles_manquantes(["film"], liens) == {"fiche"}


def test_le_kind_ne_promeut_pas_n_importe_quelle_famille():
    """`streaming` sur un libraire ne fait pas de lui un moyen de voir."""
    liens = [_lien_kind("https://www.mollat.com/livres/x", "streaming")]
    assert lf.familles_presentes(liens) == {"libraire"}


def test_un_lien_sans_kind_ne_leve_pas():
    assert lf.familles_presentes([{"url": "https://www.youtube.com/watch?v=a",
                                   "label": "L"}]) == {"video"}


def test_les_promotions_visent_des_familles_connues():
    fournies = set(lf.HOTES.values())
    for (depart, _), arrivee in lf._PROMOTIONS.items():
        assert depart in fournies, depart
        assert arrivee in fournies, arrivee


def test_un_article_de_presse_specialisee_est_une_fiche():
    """Un article consacré à une émission la DÉCRIT — c'est la fonction d'une
    fiche. Pour « Exocet », émission web du milieu des années 2000, c'est le
    seul document existant."""
    assert lf.famille("https://podcastmagazine.fr/patrick-baud-exocet/") == "fiche"
