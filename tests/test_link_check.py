"""Tests de tools/link_check.py.

Chaque cas de `classify` encode un comportement de plateforme réellement
observé le 2026-07-20, pas une supposition. Les commentaires disent lequel :
si un test casse un jour, c'est que la plateforme a changé, pas que le test
était arbitraire.
"""
from __future__ import annotations

import ssl
import urllib.error

import pytest

from link_check import (
    FetchOutcome,
    ProbeResult,
    _make_ssl_context,
    classify,
    fetch_via_urllib,
    host_in,
    page_title,
    verify_url,
)

OPAQUE = frozenset({"netflix.com", "deezer.com"})


# ---------------------------------------------------------------------------
# host_in
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("url", "expected"), [
    ("https://netflix.com/title/1", True),
    ("https://www.netflix.com/title/1", True),      # sous-domaine
    ("https://FR.NETFLIX.COM/x", True),             # casse ignorée
    ("https://notnetflix.com/x", False),            # pas de faux positif
    ("https://netflix.com.evil.tld/x", False),      # suffixe ≠ domaine
    ("https://example.org/x", False),
])
def test_host_in_matche_domaine_et_sous_domaines(url, expected):
    assert host_in(url, OPAQUE) is expected


def test_host_in_sur_url_illisible():
    assert host_in("https://[bad", OPAQUE) is False


def test_host_in_sans_host():
    assert host_in("file:///etc/passwd", OPAQUE) is False


# ---------------------------------------------------------------------------
# page_title
# ---------------------------------------------------------------------------
def test_page_title_extrait_et_denormalise_les_espaces():
    assert page_title("<html><title>  Serge\n  Le Mytho </title>") == "Serge Le Mytho"


def test_page_title_retire_le_suffixe_de_marque():
    assert page_title("<title>Serge Le Mytho - YouTube</title>") == "Serge Le Mytho"
    assert page_title("<title>Black Swan | Disney+</title>") == "Black Swan"


def test_page_title_decode_les_entites_html():
    assert page_title("<title>Ol&#39;Kainry &amp; co</title>") == "Ol'Kainry & co"


def test_page_title_gere_les_attributs_sur_la_balise():
    assert page_title('<title data-x="1">Titre</title>') == "Titre"


def test_page_title_absent_renvoie_vide():
    # Signature d'une page morte servie en 200 : c'est ce que YouTube renvoie
    # pour un ID de playlist inventé.
    assert page_title("<html><body>rien</body></html>") == ""


# ---------------------------------------------------------------------------
# classify — le cœur de la politique
# ---------------------------------------------------------------------------
def test_classify_page_vivante_avec_titre():
    res = classify("https://ex.fr/a", FetchOutcome(200, "<title>Une œuvre</title>"))
    assert res == ProbeResult("alive", "HTTP 200", "Une œuvre")
    assert res.accepted is True


def test_classify_200_sans_titre_est_mort():
    # YouTube répond 200 à n'importe quel ID de playlist bien formé, garbage
    # compris ; seule l'absence de <title> distingue la coquille vide.
    res = classify("https://www.youtube.com/playlist?list=PLZZZ", FetchOutcome(200, "<html></html>"))
    assert res.verdict == "dead"
    assert "sans titre" in res.detail
    assert res.accepted is False


@pytest.mark.parametrize("code", [404, 410])
def test_classify_404_est_mort_sur_host_normal(code):
    res = classify("https://www.allocine.fr/film/999", FetchOutcome(code))
    assert res == ProbeResult("dead", f"HTTP {code}", "")


@pytest.mark.parametrize("url", [
    "https://www.netflix.com/title/80013561",
    "https://www.deezer.com/us/album/182457842",
])
def test_classify_404_sur_host_opaque_est_non_concluant(url):
    # Netflix et Deezer renvoient 404 même sur un ID RÉEL : leur 404 ne porte
    # aucune information, on ne peut pas s'en servir pour rejeter.
    res = classify(url, FetchOutcome(404))
    assert res.verdict == "unknown"
    assert "opaque" in res.detail
    assert res.accepted is True


def test_classify_404_disney_reste_mort():
    # Disney+ discrimine (vrai UUID → 200, bidon → 404) : il est volontairement
    # hors de OPAQUE_404_HOSTS. C'est ce qui a démasqué l'URL Black Swan restée
    # à l'ancien schéma /movies/<slug>/<id>.
    res = classify("https://www.disneyplus.com/fr-fr/movies/x/BIDON", FetchOutcome(404))
    assert res.verdict == "dead"


@pytest.mark.parametrize("code", [401, 403, 405, 406, 429, 500, 502, 503, 504])
def test_classify_codes_non_concluants_laissent_passer(code):
    # Anti-bot, quota, panne : jamais une preuve d'absence. Les rejeter
    # écarterait Fnac Spectacles (403), Paramount+ (406), Qobuz (503)…
    res = classify("https://www.fnacspectacles.com/a", FetchOutcome(code))
    assert res.verdict == "unknown"
    assert "non concluant" in res.detail


def test_classify_code_4xx_inconnu_est_non_concluant():
    res = classify("https://ex.fr/a", FetchOutcome(418))
    assert res == ProbeResult("unknown", "HTTP 418", "")


def test_classify_erreur_reseau_est_non_concluante():
    # TLS, DNS, timeout : jamais une preuve d'absence. Un magasin de
    # certificats périmé faisait échouer fr.wikipedia.org.
    res = classify("https://fr.wikipedia.org/wiki/X",
                   FetchOutcome(None, error="certificate has expired"))
    assert res.verdict == "unknown"
    assert "certificate has expired" in res.detail
    assert res.accepted is True


def test_classify_3xx_avec_titre_est_vivant():
    res = classify("https://ex.fr/a", FetchOutcome(304, "<title>T</title>"))
    assert res.verdict == "alive"


# ---------------------------------------------------------------------------
# verify_url — cache et injection
# ---------------------------------------------------------------------------
def test_verify_url_utilise_le_fetcher_injecte():
    res = verify_url("https://ex.fr/a",
                     fetcher=lambda u, t: FetchOutcome(200, "<title>OK</title>"))
    assert res.title == "OK"


def test_verify_url_met_en_cache_et_ne_resonde_pas():
    appels: list[str] = []

    def fetcher(url: str, timeout: float) -> FetchOutcome:
        appels.append(url)
        return FetchOutcome(200, "<title>T</title>")

    cache: dict[str, ProbeResult] = {}
    first = verify_url("https://ex.fr/a", cache=cache, fetcher=fetcher)
    second = verify_url("https://ex.fr/a", cache=cache, fetcher=fetcher)
    assert first == second
    assert appels == ["https://ex.fr/a"]  # une seule requête


def test_verify_url_sans_cache_resonde():
    appels: list[str] = []

    def fetcher(url: str, timeout: float) -> FetchOutcome:
        appels.append(url)
        return FetchOutcome(200, "<title>T</title>")

    verify_url("https://ex.fr/a", fetcher=fetcher)
    verify_url("https://ex.fr/a", fetcher=fetcher)
    assert len(appels) == 2


def test_verify_url_transmet_le_timeout():
    recu: list[float] = []
    verify_url("https://ex.fr/a", timeout=3.5,
               fetcher=lambda u, t: recu.append(t) or FetchOutcome(200, "<title>T</title>"))
    assert recu == [3.5]


# ---------------------------------------------------------------------------
# fetch_via_urllib — transport, avec urlopen simulé (aucun réseau)
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, status: int, body: bytes, charset: str | None = "utf-8"):
        self.status = status
        self._body = body
        self._pos = 0
        self.headers = self  # get_content_charset() servi par cet objet
        self._charset = charset

    def get_content_charset(self):
        return self._charset

    def read(self, size: int) -> bytes:
        chunk = self._body[self._pos:self._pos + size]
        self._pos += len(chunk)
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, factory):
    monkeypatch.setattr("link_check.urllib.request.urlopen",
                        lambda req, timeout=None, context=None: factory(req))


def test_fetch_via_urllib_lit_le_corps(monkeypatch):
    _patch_urlopen(monkeypatch,
                   lambda req: _FakeResponse(200, b"<title>Bonjour</title>"))
    outcome = fetch_via_urllib("https://ex.fr/a", 5.0)
    assert outcome.status == 200
    assert "Bonjour" in outcome.body


def test_fetch_via_urllib_envoie_le_cookie_de_consentement(monkeypatch):
    vus: dict[str, str] = {}

    def factory(req):
        vus.update(req.headers)
        return _FakeResponse(200, b"<title>T</title>")

    _patch_urlopen(monkeypatch, factory)
    fetch_via_urllib("https://www.youtube.com/playlist?list=X", 5.0)
    # urllib capitalise les noms d'en-tête.
    assert vus.get("Cookie") == "SOCS=CAI"


def test_fetch_via_urllib_sarrete_des_le_titre(monkeypatch):
    # Le corps déclare 3 Mo mais le titre est au début : on ne doit pas tout
    # lire. Inversement le titre de YouTube est à ~700 Ko, d'où MAX_BODY_BYTES.
    body = b"<title>Court</title>" + b"x" * 3_000_000
    fake = _FakeResponse(200, body)
    _patch_urlopen(monkeypatch, lambda req: fake)
    outcome = fetch_via_urllib("https://ex.fr/a", 5.0)
    assert "Court" in outcome.body
    assert len(outcome.body) < 200_000  # arrêt précoce


def test_fetch_via_urllib_titre_a_cheval_sur_deux_chunks(monkeypatch):
    # Le marqueur </title> peut chevaucher une frontière de chunk : la sonde
    # recolle les deux derniers morceaux pour ne pas le manquer.
    filler = b"a" * (65_536 - 10)
    fake = _FakeResponse(200, filler + b"<title>Coupe</title>" + b"z" * 100)
    _patch_urlopen(monkeypatch, lambda req: fake)
    assert page_title(fetch_via_urllib("https://ex.fr/a", 5.0).body) == "Coupe"


def test_fetch_via_urllib_respecte_le_plafond(monkeypatch, ):
    # Aucun titre et un corps énorme : on s'arrête au plafond au lieu de
    # rapatrier indéfiniment.
    fake = _FakeResponse(200, b"y" * (MAX := 3_000_000))
    _patch_urlopen(monkeypatch, lambda req: fake)
    outcome = fetch_via_urllib("https://ex.fr/a", 5.0)
    assert 0 < len(outcome.body) <= MAX


def test_fetch_via_urllib_lit_jusqua_la_fin_dun_corps_sans_titre(monkeypatch):
    # Flux épuisé avant tout <title> et bien avant le plafond : la boucle doit
    # sortir sur le chunk vide. C'est la page 200-sans-titre que `classify`
    # déclare morte.
    _patch_urlopen(monkeypatch, lambda req: _FakeResponse(200, b"<html>rien</html>"))
    outcome = fetch_via_urllib("https://ex.fr/a", 5.0)
    assert outcome.body == "<html>rien</html>"
    assert classify("https://ex.fr/a", outcome).verdict == "dead"


def test_fetch_via_urllib_charset_absent_retombe_sur_utf8(monkeypatch):
    _patch_urlopen(monkeypatch,
                   lambda req: _FakeResponse(200, "<title>Œuvre</title>".encode("utf-8"), None))
    assert "Œuvre" in fetch_via_urllib("https://ex.fr/a", 5.0).body


def test_fetch_via_urllib_remonte_le_code_http(monkeypatch):
    def factory(req):
        raise urllib.error.HTTPError("https://ex.fr/a", 403, "Forbidden", {}, None)

    _patch_urlopen(monkeypatch, factory)
    assert fetch_via_urllib("https://ex.fr/a", 5.0) == FetchOutcome(403)


def test_fetch_via_urllib_erreur_reseau_sans_status(monkeypatch):
    def factory(req):
        raise urllib.error.URLError("certificate has expired")

    _patch_urlopen(monkeypatch, factory)
    outcome = fetch_via_urllib("https://ex.fr/a", 5.0)
    assert outcome.status is None
    assert "certificate has expired" in outcome.error


def test_fetch_via_urllib_timeout_sans_status(monkeypatch):
    def factory(req):
        raise TimeoutError("read timed out")

    _patch_urlopen(monkeypatch, factory)
    assert fetch_via_urllib("https://ex.fr/a", 5.0).status is None


def test_fetch_via_urllib_tronque_le_message_derreur(monkeypatch):
    def factory(req):
        raise OSError("z" * 500)

    _patch_urlopen(monkeypatch, factory)
    assert len(fetch_via_urllib("https://ex.fr/a", 5.0).error) == 70


# ---------------------------------------------------------------------------
# contexte TLS
# ---------------------------------------------------------------------------
def test_make_ssl_context_utilise_certifi():
    assert isinstance(_make_ssl_context(), ssl.SSLContext)
