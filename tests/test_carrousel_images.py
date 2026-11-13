"""Tests de tools/carrousel_images.py : l'image de chaque page du carrousel, sans réseau."""
from __future__ import annotations

import carrousel_images as ci


class FauxWeb:
    """Réponses préparées, par adresse ; note les adresses demandées."""

    def __init__(self, json=None, html=None, avatars=None):
        self._json, self._html, self._avatars = json or {}, html or {}, avatars or {}
        self.demandes: list[str] = []

    def json(self, url, **params):
        self.demandes.append(url)
        return self._json.get(url, {})

    def html(self, url):
        self.demandes.append(url)
        return self._html.get(url, "")

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
    reco = {"types": ["film"], "externalIds": {"tmdb": "38"}}
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


# ===== L'accès réel au web, avec une fausse session ===========================
class FausseReponse:
    encoding = "utf-8"

    def __init__(self, donnees=None, texte=""):
        self._donnees, self.text = donnees, texte

    def raise_for_status(self):
        return None

    def json(self):
        return self._donnees

    def iter_content(self, chunk_size):
        yield self.text.encode("utf-8")

    def close(self):
        return None


class FausseSession:
    def __init__(self):
        self.appels = []

    def get(self, url, **kw):
        self.appels.append((url, kw))
        return FausseReponse({"ok": url}, "<html>" + url)


def test_web_reel_lit_json_et_html_avec_les_bons_en_tetes():
    session = FausseSession()
    web = ci.WebReel(session=session)
    assert web.json("https://api/x", id=3) == {"ok": "https://api/x"}
    assert web.html("https://site/y") == "<html>https://site/y"
    assert session.appels[0][1]["params"] == {"id": 3}
    assert "SOCS=CAI" in session.appels[1][1]["headers"]["Cookie"]


def test_web_reel_trouve_l_avatar_youtube(monkeypatch):
    infos = {"thumbnails": [{"id": "banner", "url": "b"}, {"id": "avatar_uncropped", "url": "https://yt3/a"}]}
    assert ci.WebReel(session=FausseSession(), ytdl=lambda url: infos).avatar_youtube("https://youtube/@x") == \
        "https://yt3/a"
    assert ci.WebReel(session=FausseSession(), ytdl=lambda url: {}).avatar_youtube("https://youtube/@x") is None

    import sys
    import types

    class FauxYoutubeDL:
        def __init__(self, options):
            assert options["extract_flat"] is True

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download):
            return infos

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FauxYoutubeDL))
    assert ci.WebReel(session=FausseSession()).avatar_youtube("https://youtube/@x") == "https://yt3/a"


def test_wikipedia_recoit_un_agent_qui_nomme_l_outil():
    """Wikimedia refuse (403) les agents qui imitent un navigateur ; il veut un nom d'outil."""
    session = FausseSession()
    ci.WebReel(session=session).json("https://fr.wikipedia.org/api/rest_v1/page/summary/X")
    assert session.appels[0][1]["headers"]["User-Agent"].startswith("UneBonneReco/")


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

    reco = {"id": "ubm-1", "types": ["film"], "externalIds": {"tmdb": "600"}}
    assert ci.source({}, reco, Panne(), "SECRET") is None
    assert "SECRET" not in caplog.text and "api_key=…" in caplog.text


def test_une_erreur_inattendue_d_une_source_ne_bloque_pas():
    class Panne(FauxWeb):
        def avatar_youtube(self, url):
            raise AttributeError("yt-dlp a changé")

    reco = {"types": ["chaine"], "links": [lien("https://www.youtube.com/@x")]}
    assert ci.source({}, reco, Panne(), None) is None


def test_yt_dlp_en_echec_ne_donne_pas_d_avatar(monkeypatch):
    import sys
    import types

    class ErreurYoutube(Exception):
        pass

    class FauxYoutubeDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download):
            raise ErreurYoutube("This channel does not exist")

    faux = types.SimpleNamespace(YoutubeDL=FauxYoutubeDL, utils=types.SimpleNamespace(YoutubeDLError=ErreurYoutube))
    monkeypatch.setitem(sys.modules, "yt_dlp", faux)
    assert ci.WebReel(session=FausseSession()).avatar_youtube("https://www.youtube.com/@disparue") is None


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
    assert ci.source({}, reco, web, None) == "https://upload/thumb/a/ab/Logo.svg/1000px-Logo.svg.png"


def test_affiche_de_repli_francaise_puis_sans_texte():
    reco = {"types": ["film"], "externalIds": {"tmdb": "38"}}
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


def test_html_ne_lit_que_le_debut_de_la_page():
    class Flux:
        encoding = "utf-8"

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield b"<head>og</head>"
            yield b"x" * ci.TAILLE_PAGE
            raise AssertionError("lu trop loin")

        def close(self):
            self.ferme = True

    class Session:
        def get(self, url, **kw):
            assert kw["stream"] is True
            self.reponse = Flux()
            return self.reponse

    session = Session()
    texte = ci.WebReel(session=session).html("https://site/x")
    assert texte.startswith("<head>og</head>") and session.reponse.ferme
