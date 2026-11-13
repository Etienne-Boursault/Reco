"""Tests de tools/carrousel_images.py : l'accès réel au web (WebReel), avec une fausse session."""
from __future__ import annotations

import carrousel_images as ci


class FausseReponse:
    encoding = "utf-8"

    def __init__(self, donnees=None, texte="", url=""):
        self._donnees, self.text, self.url = donnees, texte, url

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
        return FausseReponse({"ok": url}, "<html>" + url, url)


def test_web_reel_lit_json_et_html_avec_les_bons_en_tetes():
    session = FausseSession()
    web = ci.WebReel(session=session)
    assert web.json("https://api/x", id=3) == {"ok": "https://api/x"}
    assert web.html("https://site/y") == ("https://site/y", "<html>https://site/y")
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


def test_html_ne_lit_que_le_debut_de_la_page():
    class Flux:
        encoding = "utf-8"

        def raise_for_status(self):
            return None

        url = "https://site/x"

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
    finale, texte = ci.WebReel(session=session).html("https://site/x")
    assert texte.startswith("<head>og</head>") and session.reponse.ferme and finale == "https://site/x"


def test_web_reel_verifie_qu_une_adresse_rend_bien_une_image():
    class Reponse:
        def __init__(self, statut, genre):
            self.status_code, self.headers = statut, {"content-type": genre}

        def close(self):
            return None

    class Session:
        def __init__(self, statut, genre):
            self.reponse = Reponse(statut, genre)

        def get(self, url, **kw):
            assert kw["stream"] is True
            return self.reponse

    assert ci.WebReel(session=Session(200, "image/jpeg")).image_valide("https://x/a.jpg")
    assert not ci.WebReel(session=Session(200, "image/svg+xml")).image_valide("https://x/a.svg")
    assert not ci.WebReel(session=Session(200, "text/html; charset=utf-8")).image_valide("https://x/a")
    assert not ci.WebReel(session=Session(404, "image/jpeg")).image_valide("https://x/a.jpg")

    class Coupee:
        def get(self, url, **kw):
            raise OSError("connexion refusée")
    assert not ci.WebReel(session=Coupee()).image_valide("https://x/a.jpg")


def test_html_decode_sans_planter_sur_un_encodage_inconnu_ou_absent():
    class Flux:
        url = "https://site/x"

        def __init__(self, encodage, octets):
            self.encoding, self.octets = encodage, octets

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            yield self.octets

        def close(self):
            return None

    class Session:
        def __init__(self, flux):
            self.flux = flux

        def get(self, url, **kw):
            return self.flux

    ete = "<meta content='/affiche-été.jpg'>".encode()
    assert "été" in ci.WebReel(session=Session(Flux("utf8mb4", ete))).html("https://site/x")[1]
    assert "été" in ci.WebReel(session=Session(Flux("ISO-8859-1", ete))).html("https://site/x")[1]
    latin = "<p>été</p>".encode("latin-1")
    assert "été" in ci.WebReel(session=Session(Flux(None, latin))).html("https://site/x")[1]


def test_wikimedia_recoit_l_agent_de_l_outil_partout():
    """upload.wikimedia.org refuse lui aussi un faux navigateur : vérification et téléchargement."""
    assert ci.entetes("https://upload.wikimedia.org/x.jpg")["User-Agent"] == ci.OUTIL
    assert ci.entetes("https://fr.wikipedia.org/api/x")["User-Agent"] == ci.OUTIL
    assert ci.entetes("https://cdn-images.dzcdn.net/x.jpg")["User-Agent"] != ci.OUTIL

    class Reponse:
        status_code, headers = 200, {"content-type": "image/jpeg"}

        def close(self):
            return None

    class Session:
        def get(self, url, **kw):
            self.agent = kw["headers"]["User-Agent"]
            return Reponse()

    session = Session()
    assert ci.WebReel(session=session).image_valide("https://upload.wikimedia.org/x.jpg")
    assert session.agent == ci.OUTIL


# ===== Troisième tour de revue de la PR #204 ==================================
def test_une_session_par_fil():
    """Une requests.Session n'est pas garantie sûre entre fils : chacun la sienne."""
    import threading
    creees = []

    def fabrique():
        creees.append(FausseSession())
        return creees[-1]

    web = ci.WebReel(fabrique=fabrique)
    web.json("https://api/a")
    fil = threading.Thread(target=lambda: web.json("https://api/b"))
    fil.start()
    fil.join()
    web.json("https://api/c")
    assert len(creees) == 2 and len(creees[0].appels) == 2 and len(creees[1].appels) == 1


def test_une_page_coupee_au_milieu_d_un_caractere_reste_en_utf8():
    class Flux:
        url, encoding = "https://site/x", None

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size):
            debut = "<meta content='/affiche-été.jpg'>".encode()
            # La coupure à TAILLE_PAGE tombe entre les deux octets du dernier « é ».
            yield debut + b"x" * (ci.TAILLE_PAGE - len(debut) - 1) + "é".encode()

        def close(self):
            return None

    class Session:
        def get(self, url, **kw):
            return Flux()

    page = ci.WebReel(session=Session()).html("https://site/x")[1]
    assert "affiche-été.jpg" in page and "Ã" not in page


def test_une_page_wikimedia_est_lue_avec_l_agent_de_l_outil():
    session = FausseSession()
    ci.WebReel(session=session).html("https://fr.wikipedia.org/wiki/X")
    assert session.appels[0][1]["headers"]["User-Agent"] == ci.OUTIL


def test_une_image_servie_en_octet_stream_est_acceptee():
    class Reponse:
        status_code, headers = 200, {"content-type": "binary/octet-stream"}

        def close(self):
            return None

    class Session:
        def get(self, url, **kw):
            return Reponse()

    assert ci.WebReel(session=Session()).image_valide("https://s3/x.jpg")
