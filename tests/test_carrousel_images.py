"""Tests de tools/carrousel_images.py : l'image de chaque page du carrousel, sans réseau."""
from __future__ import annotations

import pytest

import carrousel_images as ci


class FauxWeb:
    """Réponses préparées, par adresse ; note les adresses demandées."""

    def __init__(self, json=None, html=None, avatars=None, invalides=()):
        self._json, self._html, self._avatars = json or {}, html or {}, avatars or {}
        self.invalides = set(invalides)
        self.demandes: list[str] = []

    def json(self, url, **params):
        self.demandes.append(url)
        return self._json.get(url, {})

    def html(self, url):
        self.demandes.append(url)
        page = self._html.get(url, "")
        return page if isinstance(page, tuple) else (url, page)

    def image_valide(self, url):
        return url not in self.invalides

    def avatar_youtube(self, url):
        self.demandes.append(url)
        return self._avatars.get(url)


def lien(url, kind="streaming", label="x"):
    return {"url": url, "kind": kind, "label": label}


# ===== Films et séries : l'affiche TMDB, dans la langue originale ============
TMDB = "https://api.themoviedb.org/3/movie/38"


def test_film_prend_l_affiche_dans_la_langue_originale():
    web = FauxWeb(json={
        TMDB: {"original_language": "en"},
        TMDB + "/images": {"posters": [{"iso_639_1": "fr", "file_path": "/fr.jpg"},
                                       {"iso_639_1": "en", "file_path": "/en.jpg"}]},
    })
    reco = {"types": ["film"], "externalIds": {"tmdb": "38", "tmdbType": "movie"}}
    assert ci.source({}, reco, web, "cle") == "https://image.tmdb.org/t/p/w780/en.jpg"


def test_serie_sans_affiche_originale_prend_la_premiere():
    base = "https://api.themoviedb.org/3/tv/7"
    web = FauxWeb(json={base: {"original_language": "ko"},
                        base + "/images": {"posters": [{"iso_639_1": "fr", "file_path": "/fr.jpg"}]}})
    item = {"types": ["serie"], "externalIds": {"tmdb": 7, "tmdbType": "tv"}}
    assert ci.source(item, {"types": ["serie"]}, web, "cle") == "https://image.tmdb.org/t/p/w780/fr.jpg"


def test_film_sans_cle_ni_affiche_ne_donne_rien():
    reco = {"types": ["film"], "externalIds": {"tmdb": "38", "tmdbType": "movie"}}
    assert ci.source({}, reco, FauxWeb(), None) is None
    assert ci.source({}, reco, FauxWeb(json={TMDB + "/images": {"posters": []}}), "cle") is None


# ===== Musique =================================================================
def test_album_prend_la_pochette_deezer():
    web = FauxWeb(json={"https://api.deezer.com/album/42": {"cover_xl": "https://cdn/42.jpg"}})
    reco = {"types": ["album"], "links": [lien("https://www.deezer.com/album/42")]}
    assert ci.source({}, reco, web, None) == "https://cdn/42.jpg"


def test_album_sans_deezer_prend_la_pochette_apple_agrandie():
    web = FauxWeb(json={"https://itunes.apple.com/lookup": {"results": [
        {"artworkUrl100": "https://is1/x/100x100bb.jpg"}]}})
    reco = {"types": ["album"], "links": [lien("https://music.apple.com/fr/album/graou/1794232869?uo=4")]}
    assert ci.source({}, reco, web, None) == "https://is1/x/1000x1000bb.jpg"


def test_artiste_prend_sa_photo_deezer_sauf_la_photo_par_defaut():
    reco = {"types": ["artiste"], "links": [lien("https://www.deezer.com/artist/9")]}
    web = FauxWeb(json={"https://api.deezer.com/artist/9": {"picture_xl": "https://cdn/artist/abc/1000.jpg"}})
    assert ci.source({}, reco, web, None) == "https://cdn/artist/abc/1000.jpg"
    vide = FauxWeb(json={"https://api.deezer.com/artist/9": {"picture_xl": "https://cdn/images/artist//1000.jpg"}})
    assert ci.source({}, reco, vide, None) is None


def test_podcast_prend_la_vignette_apple_agrandie():
    web = FauxWeb(json={"https://itunes.apple.com/lookup": {"results": [
        {"artworkUrl600": "https://is1/p/600x600bb.jpg"}]}})
    reco = {"types": ["podcast"], "links": [
        lien("https://podcasts.apple.com/fr/podcast/menteuse-menteuse/id1534412600?i=1000790049064")]}
    assert ci.source({}, reco, web, None) == "https://is1/p/1200x1200bb.jpg"


# ===== Chaîne, livre, site officiel ===========================================
def test_chaine_youtube_prend_l_avatar():
    url = "https://www.youtube.com/@nardwuar"
    reco = {"types": ["chaine"], "links": [lien(url, "official")]}
    assert ci.source({}, reco, FauxWeb(avatars={url: "https://yt3/avatar"}), None) == "https://yt3/avatar"


def test_livre_prend_l_image_wikipedia():
    web = FauxWeb(json={"https://fr.wikipedia.org/api/rest_v1/page/summary/Max_et_Lili":
                        {"originalimage": {"source": "https://upload/maxlili.jpg"}}})
    reco = {"types": ["bd"], "links": [lien("https://fr.wikipedia.org/wiki/Max_et_Lili", "info")]}
    assert ci.source({}, reco, web, None) == "https://upload/maxlili.jpg"


def test_sinon_l_image_de_partage_du_site_officiel():
    url = "https://le-zenith.com/shows/Miki-21173"
    page = '<meta property="og:image" content="https://le-zenith.com/a.jpg?x=1&amp;y=2">'
    reco = {"types": ["spectacle"], "links": [lien("https://billet/x", "buy"), lien(url, "official")]}
    assert ci.source({}, reco, FauxWeb(html={url: page}), None) == "https://le-zenith.com/a.jpg?x=1&y=2"


def test_aucune_source_ne_donne_rien_et_ne_casse_pas_sur_une_erreur():
    class Panne(FauxWeb):
        def json(self, url, **params):
            raise OSError("réseau coupé")

    reco = {"types": ["album"], "links": [lien("https://www.deezer.com/album/42")]}
    assert ci.source({}, reco, Panne(), None) is None
    assert ci.source({}, {"types": ["autre"]}, FauxWeb(), None) is None


# ===== La mise en scène, d'après le type et les proportions ===================
def test_mise_en_scene():
    assert ci.mise_en_scene("Film", []) == "sans"
    assert ci.mise_en_scene("Album", [(1000, 1000), (1000, 1000)]) == "double"
    assert ci.mise_en_scene("Film", [(780, 1170)]) == "affiche"
    assert ci.mise_en_scene("Album", [(1000, 1000)]) == "carre"
    assert ci.mise_en_scene("Artiste", [(1000, 1000)]) == "rond"
    assert ci.mise_en_scene("Chaîne YouTube", [(800, 800)]) == "rond"
    assert ci.mise_en_scene("Application", [(192, 192)]) == "tuile"
    assert ci.mise_en_scene("Spectacle", [(1280, 720)]) == "photo"
    assert ci.mise_en_scene("BD", [(720, 480)]) == "cadre"


def test_credits_nomment_les_sources_des_images():
    urls = ["https://image.tmdb.org/t/p/w780/a.jpg", "https://cdn-images.dzcdn.net/x.jpg",
            "https://i.ytimg.com/vi/x/maxresdefault.jpg", "https://le-zenith.com/a.jpg",
            "https://image.tmdb.org/t/p/w780/b.jpg"]
    assert ci.credits(urls) == "Images : affiches TMDB, pochettes Deezer, YouTube, sites des œuvres"
    assert ci.credits([]) == ""


def test_une_source_presente_mais_vide_ne_donne_rien():
    vide = FauxWeb()
    assert ci.source({}, {"types": ["album"], "links": [
        lien("https://music.apple.com/fr/album/graou/1794232869")]}, vide, None) is None
    assert ci.source({}, {"types": ["album"], "links": [lien("https://exemple.org/album")]}, vide, None) is None
    assert ci.source({}, {"types": ["artiste"], "links": [lien("https://exemple.org/x")]}, vide, None) is None
    assert ci.source({}, {"types": ["podcast"], "links": [
        lien("https://podcasts.apple.com/fr/podcast/x/id1")]}, vide, None) is None
    assert ci.source({}, {"types": ["podcast"]}, vide, None) is None
    assert ci.source({}, {"types": ["chaine"]}, vide, None) is None
    assert ci.source({}, {"types": ["livre"]}, vide, None) is None
    assert ci.source({}, {"types": ["spectacle"], "links": [
        lien("https://exemple.org/", "official")]}, vide, None) is None


def test_site_sans_image_de_partage_donne_son_icone_d_application():
    url = "https://www.wiki-masters.com/"
    page = ('<meta charset="utf-8"><meta name="description" content="Cartes">'
            '<link rel="icon" href="/favicon.ico"><link rel="apple-touch-icon" href="/apple-touch-icon.png" sizes="180x180">')
    reco = {"types": ["application"], "links": [lien(url, "official")]}
    assert ci.source({}, reco, FauxWeb(html={url: page}), None) == "https://www.wiki-masters.com/apple-touch-icon.png"


# ===== Revue de la PR #204 ====================================================
def test_la_cle_tmdb_ne_sort_jamais_dans_les_journaux(caplog):
    class Panne(FauxWeb):
        def json(self, url, **params):
            raise OSError("404 Client Error for url: https://api.themoviedb.org/3/movie/600?api_key=SECRET&x=1")

    reco = {"id": "ubm-1", "types": ["film"], "externalIds": {"tmdb": "600", "tmdbType": "movie"}}
    assert ci.source({}, reco, Panne(), "SECRET") is None
    assert "SECRET" not in caplog.text and "api_key=…" in caplog.text


def test_une_erreur_de_reponse_d_une_source_ne_bloque_pas():
    class Panne(FauxWeb):
        def avatar_youtube(self, url):
            raise LookupError("unknown encoding: utf8mb4")

    reco = {"types": ["chaine"], "links": [lien("https://www.youtube.com/@x")]}
    assert ci.source({}, reco, Panne(), None) is None


def test_image_de_partage_quel_que_soit_l_ordre_des_attributs():
    url = "https://site.fr/spectacle"
    reco = {"types": ["spectacle"], "links": [lien(url, "official")]}
    for page, attendu in (
        ('<meta content="/img/a.jpg" property="og:image">', "https://site.fr/img/a.jpg"),
        ("<meta property='og:image' content='https://cdn/b.jpg'>", "https://cdn/b.jpg"),
        ('<meta name="og:image" content="//cdn/c.jpg">', "https://cdn/c.jpg"),
    ):
        assert ci.source({}, reco, FauxWeb(html={url: page}), None) == attendu


def test_wikipedia_donne_une_vignette_agrandie_plutot_que_l_original():
    base = "https://fr.wikipedia.org/api/rest_v1/page/summary/"
    reco = {"types": ["livre"], "links": [lien("https://fr.wikipedia.org/wiki/Logo", "info")]}
    web = FauxWeb(json={base + "Logo": {
        "thumbnail": {"source": "https://upload/thumb/a/ab/Logo.svg/330px-Logo.svg.png"},
        "originalimage": {"source": "https://upload/a/ab/Logo.svg"}}})
    # Sans largeur connue, la vignette telle quelle : Wikimedia refuse d'agrandir (400).
    assert ci.source({}, reco, web, None) == "https://upload/thumb/a/ab/Logo.svg/330px-Logo.svg.png"


def test_affiche_de_repli_francaise_puis_sans_texte():
    reco = {"types": ["film"], "externalIds": {"tmdb": "38", "tmdbType": "movie"}}
    for affiches, attendu in (
        ([{"iso_639_1": "de", "file_path": "/de.jpg"}, {"iso_639_1": "fr", "file_path": "/fr.jpg"}], "/fr.jpg"),
        ([{"iso_639_1": "ru", "file_path": "/ru.jpg"}, {"iso_639_1": None, "file_path": "/nu.jpg"}], "/nu.jpg"),
        ([{"iso_639_1": "ru", "file_path": "/ru.jpg"}], "/ru.jpg"),
    ):
        web = FauxWeb(json={TMDB: {"original_language": "cn"}, TMDB + "/images": {"posters": affiches}})
        assert ci.source({}, reco, web, "cle") == "https://image.tmdb.org/t/p/w780" + attendu


def test_pochette_deezer_par_defaut_cede_la_place_a_apple():
    web = FauxWeb(json={"https://api.deezer.com/album/42": {"cover_xl": "https://cdn/images/cover//1000.jpg"},
                        "https://itunes.apple.com/lookup": {"results": [{"artworkUrl100": "https://is1/100x100bb.jpg"}]}})
    reco = {"types": ["album"], "links": [lien("https://www.deezer.com/album/42"),
                                          lien("https://music.apple.com/fr/album/x/7")]}
    assert ci.source({}, reco, web, None) == "https://is1/1000x1000bb.jpg"


def test_toutes_les_formes_d_adresse_de_chaine_youtube():
    for url, attendu in (("https://youtube.com/@x", "https://www.youtube.com/@x"),
                         ("http://m.youtube.com/c/Nom", "https://www.youtube.com/c/Nom"),
                         ("https://www.youtube.com/user/Ancien", "https://www.youtube.com/user/Ancien")):
        web = FauxWeb(avatars={attendu: "https://yt3/a"})
        assert ci.source({}, {"types": ["chaine"], "links": [lien(url)]}, web, None) == "https://yt3/a"


def test_livre_sans_wikipedia_prend_l_image_de_la_librairie():
    url = "https://www.placedeslibraires.fr/livre/9782"
    reco = {"types": ["livre"], "links": [lien(url, "buy")]}
    page = '<meta property="og:image" content="https://www.placedeslibraires.fr/couv.jpg">'
    assert ci.source({}, reco, FauxWeb(html={url: page}), None) == "https://www.placedeslibraires.fr/couv.jpg"


def test_couverture_suit_l_adresse_youtube_de_l_episode():
    assert ci.couverture({"guid": "abc", "youtubeUrl": "https://www.youtube.com/watch?v=aBc-12_xYz9"}) == \
        "https://i.ytimg.com/vi/aBc-12_xYz9/maxresdefault.jpg"
    assert ci.couverture({"guid": "abc", "youtubeUrl": "https://youtu.be/aBc-12_xYz9?t=3"}) == \
        "https://i.ytimg.com/vi/aBc-12_xYz9/maxresdefault.jpg"
    assert ci.couverture({"guid": "yt-rwlXWp7Lrhg"}) == "https://i.ytimg.com/vi/rwlXWp7Lrhg/maxresdefault.jpg"
    assert ci.couverture({"guid": "acast-1"}) is None


# ===== Deuxième tour de revue de la PR #204 ===================================
WIKI = "https://fr.wikipedia.org/api/rest_v1/page/summary/"
LIVRE = {"types": ["livre"], "links": [lien("https://fr.wikipedia.org/wiki/X", "info")]}


def test_wikipedia_n_agrandit_jamais_au_dela_de_l_original():
    vignette = {"source": "https://upload/thumb/a/ab/X.jpg/330px-X.jpg"}
    petit = FauxWeb(json={WIKI + "X": {"thumbnail": vignette,
                                       "originalimage": {"source": "https://upload/a/ab/X.jpg", "width": 600}}})
    assert ci.source({}, LIVRE, petit, None) == "https://upload/a/ab/X.jpg"
    svg = FauxWeb(json={WIKI + "X": {"thumbnail": {"source": "https://upload/thumb/a/ab/X.svg/330px-X.svg.png"},
                                     "originalimage": {"source": "https://upload/a/ab/X.svg", "width": 600}}})
    assert ci.source({}, LIVRE, svg, None) == "https://upload/thumb/a/ab/X.svg/330px-X.svg.png"
    grand = FauxWeb(json={WIKI + "X": {"thumbnail": vignette,
                                       "originalimage": {"source": "https://upload/a/ab/X.jpg", "width": 4000}}})
    assert ci.source({}, LIVRE, grand, None) == "https://upload/thumb/a/ab/X.jpg/960px-X.jpg"


def test_une_image_refusee_fait_passer_a_la_source_suivante():
    url = "https://www.placedeslibraires.fr/livre/1"
    reco = {"types": ["livre"], "links": [lien("https://fr.wikipedia.org/wiki/X", "info"), lien(url, "buy")]}
    web = FauxWeb(json={WIKI + "X": {"originalimage": {"source": "https://upload/X.svg", "width": 500}}},
                  html={url: '<meta property="og:image" content="https://pdl/couv.jpg">'},
                  invalides={"https://upload/X.svg"})
    assert ci.source({}, reco, web, None) == "https://pdl/couv.jpg"


def test_une_image_relative_se_resout_sur_l_adresse_finale_apres_redirection():
    url = "http://ancien-site.fr"
    page = ("https://www.nouveau.fr/fr/", '<meta property="og:image" content="/img/partage.jpg">')
    reco = {"types": ["spectacle"], "links": [lien(url, "official")]}
    assert ci.source({}, reco, FauxWeb(html={url: page}), None) == "https://www.nouveau.fr/img/partage.jpg"


def test_les_types_de_la_fiche_priment_sur_ceux_de_la_reco():
    web = FauxWeb(json={"https://api.deezer.com/album/42": {"cover_xl": "https://cdn/42.jpg"}})
    reco = {"types": ["musique"], "links": [lien("https://www.deezer.com/album/42")]}
    assert ci.source({"types": ["album"]}, reco, web, None) == "https://cdn/42.jpg"


def test_un_titre_prend_la_pochette_de_son_album():
    web = FauxWeb(json={"https://api.deezer.com/track/7": {"album": {"cover_xl": "https://cdn/album7.jpg"}}})
    reco = {"types": ["musique"], "links": [lien("https://www.deezer.com/fr/track/7")]}
    assert ci.source({}, reco, web, None) == "https://cdn/album7.jpg"


def test_les_avatars_youtube_ggpht_sont_credites_youtube():
    assert ci.credits(["https://yt3.ggpht.com/a"]) == "Images : YouTube"


def test_une_erreur_de_programmation_n_est_pas_masquee():
    class Bug(FauxWeb):
        def json(self, url, **params):
            raise TypeError("argument manquant")

    reco = {"types": ["album"], "links": [lien("https://www.deezer.com/album/42")]}
    with pytest.raises(TypeError):
        ci.source({}, reco, Bug(), None)


def test_une_page_de_recherche_de_librairie_n_est_pas_une_fiche_de_livre():
    """Son image de partage est le logo du site, pas la couverture (Max et Lili, S6-E09)."""
    recherche = "https://www.placedeslibraires.fr/listeliv.php?base=allbooks&mots_recherche=max%20et%20lili"
    reco = {"types": ["bd"], "links": [lien(recherche, "buy")]}
    web = FauxWeb(html={recherche: '<meta property="og:image" content="https://pdl/logo.png">'})
    assert ci.source({}, reco, web, None) is None


def test_l_extension_de_l_original_se_lit_sans_les_parametres_de_suivi():
    """Wikipédia ajoute « ?utm_source=… » à l'adresse de l'original (Max et Lili, S6-E09)."""
    original = "https://upload/0/08/Max_et_Lili.jpg?utm_source=fr.wikipedia.org&utm_campaign=api"
    web = FauxWeb(json={WIKI + "X": {"thumbnail": {"source": "https://thumb/0/08/M.jpg/330px-M.jpg"},
                                     "originalimage": {"source": original, "width": 720}}})
    assert ci.source({}, LIVRE, web, None) == original


# ===== Troisième tour de revue de la PR #204 ==================================
def test_sans_type_tmdb_pas_d_affiche_et_jamais_un_couple_croise():
    """Les identifiants des films et des séries se chevauchent : sans type, l'affiche serait d'une autre œuvre."""
    web = FauxWeb(json={TMDB: {"original_language": "en"},
                        TMDB + "/images": {"posters": [{"iso_639_1": "en", "file_path": "/film.jpg"}]}})
    assert ci.source({}, {"types": ["serie"], "externalIds": {"tmdb": "38"}}, web, "cle") is None
    croise = ci.source({"externalIds": {"tmdb": "99", "tmdbType": "tv"}},
                       {"types": ["serie"], "externalIds": {"tmdb": "38"}}, web, "cle")
    assert croise is None and not any("/tv/38" in d for d in web.demandes)


def test_une_reponse_d_api_de_forme_inattendue_ne_bloque_pas():
    class Liste(FauxWeb):
        def json(self, url, **params):
            return []
    reco = {"types": ["album"], "links": [lien("https://www.deezer.com/album/42")]}
    assert ci.source({}, reco, Liste(), None) is None
    sans_chemin = FauxWeb(json={TMDB: {"original_language": "en"},
                                TMDB + "/images": {"posters": [{"iso_639_1": "en", "file_path": None}]}})
    film = {"types": ["film"], "externalIds": {"tmdb": "38", "tmdbType": "movie"}}
    assert ci.source({}, film, sans_chemin, "cle") is None


def test_icone_et_image_de_partage_sous_leurs_autres_noms():
    url = "https://vieux-cms.fr/"
    reco = {"types": ["spectacle"], "links": [lien(url, "official")]}
    for page, attendu in (
        ('<link rel="Apple-Touch-Icon-Precomposed" href="/icone.png">', "https://vieux-cms.fr/icone.png"),
        ('<link rel="icon apple-touch-icon" href="/i.png">', "https://vieux-cms.fr/i.png"),
        ('<meta property="og:image:secure_url" content="https://cdn/s.jpg">', "https://cdn/s.jpg"),
    ):
        assert ci.source({}, reco, FauxWeb(html={url: page}), None) == attendu


def test_seuls_les_domaines_youtube_sont_credites_youtube():
    assert ci.credits(["https://blogger.googleusercontent.com/img/a.jpg"]) == "Images : sites des œuvres"
    assert ci.credits(["https://yt3.googleusercontent.com/a"]) == "Images : YouTube"


def test_une_pochette_carree_reste_carree_et_une_photo_d_artiste_est_ronde():
    assert ci.mise_en_scene("Musique", [(1000, 1000)], ["https://cdn-images.dzcdn.net/images/cover/x.jpg"]) == "carre"
    assert ci.mise_en_scene("Musique", [(1000, 1000)], ["https://cdn-images.dzcdn.net/images/artist/x.jpg"]) == "rond"
    assert ci.mise_en_scene("Artiste", [(1000, 1000)]) == "rond"


def test_couverture_des_adresses_live_shorts_et_embed():
    for forme in ("live", "shorts", "embed"):
        ep = {"guid": "abc", "youtubeUrl": f"https://www.youtube.com/{forme}/aBc-12_xYz9"}
        assert ci.couverture(ep) == "https://i.ytimg.com/vi/aBc-12_xYz9/maxresdefault.jpg"


# ===== Quatrième tour de revue de la PR #204 ==================================
def test_une_fiche_de_livre_dont_le_titre_contient_recherche_n_est_pas_une_recherche():
    url = "https://www.placedeslibraires.fr/livre/9782070360/a-la-recherche-du-temps-perdu"
    reco = {"types": ["livre"], "links": [lien(url, "buy")]}
    web = FauxWeb(html={url: '<meta property="og:image" content="https://pdl/proust.jpg">'})
    assert ci.source({}, reco, web, None) == "https://pdl/proust.jpg"
    for recherche in ("https://site.fr/recherche?q=x", "https://site.fr/search/x", "https://site.fr/p?query=x"):
        reco = {"types": ["livre"], "links": [lien(recherche, "buy")]}
        assert ci.source({}, reco, FauxWeb(html={recherche: '<meta property="og:image" content="/l.png">'}),
                         None) is None


def test_un_pseudo_youtube_encode_garde_ses_caracteres():
    web = FauxWeb(avatars={"https://www.youtube.com/@caf%C3%A9": "https://yt3/cafe"})
    reco = {"types": ["chaine"], "links": [lien("https://www.youtube.com/@caf%C3%A9")]}
    assert ci.source({}, reco, web, None) == "https://yt3/cafe"


def test_un_titre_wikipedia_avec_une_barre_est_encode():
    reco = {"types": ["livre"], "links": [lien("https://fr.wikipedia.org/wiki/AC/DC", "info")]}
    web = FauxWeb(json={WIKI + "AC%2FDC": {"originalimage": {"source": "https://upload/acdc.jpg", "width": 500}}})
    assert ci.source({}, reco, web, None) == "https://upload/acdc.jpg"


def test_un_lien_apple_music_court_donne_la_pochette():
    web = FauxWeb(json={"https://itunes.apple.com/lookup": {"results": [{"artworkUrl100": "https://is1/100x100bb.jpg"}]}})
    reco = {"types": ["album"], "links": [lien("https://music.apple.com/fr/album/1440857781")]}
    assert ci.source({}, reco, web, None) == "https://is1/1000x1000bb.jpg"


# ===== Cinquième tour de revue de la PR #204 ==================================
def test_deezer_en_panne_laisse_sa_chance_a_apple_music():
    class DeezerEnPanne(FauxWeb):
        def json(self, url, **params):
            if "deezer" in url:
                raise OSError("délai dépassé")
            return {"results": [{"artworkUrl100": "https://is1/100x100bb.jpg"}]}

    reco = {"types": ["album"], "links": [lien("https://www.deezer.com/album/42"),
                                          lien("https://music.apple.com/fr/album/x/7")]}
    assert ci.source({}, reco, DeezerEnPanne(), None) == "https://is1/1000x1000bb.jpg"


def test_une_photo_d_artiste_deezer_n_est_pas_une_pochette():
    assert ci.credits(["https://cdn-images.dzcdn.net/images/artist/a/1000.jpg"]) == "Images : photos Deezer"
