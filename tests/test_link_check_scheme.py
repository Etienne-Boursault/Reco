"""`link_check` ne doit ouvrir que des URLs http(s).

Les URLs verifiees viennent des DONNEES du site (`customLinks`,
`watchProviders`), pas de constantes. Sans filtre, un `file:///etc/passwd`
glisse dans une reco serait ouvert par `urllib.request.urlopen`, qui gere ce
schema — le contenu remonterait dans le rapport de verification.

Le filtre n'est pas seulement une garde de securite, c'est une mise en
COHERENCE : la carte du site n'affiche deja que des liens http(s) (via
`isSafeUrl`, cf. `src/data/merchants.ts`). Un verificateur qui ouvre ce que la
page refuse d'afficher verifie autre chose que ce qui est publie.
"""
from __future__ import annotations

import pytest

import link_check


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "file://C:/Windows/win.ini",
    "ftp://example.invalid/secret.txt",
    "data:text/html,<script>alert(1)</script>",
    "javascript:alert(1)",
    "gopher://example.invalid/",
])
def test_les_schemas_non_http_sont_refuses_sans_ouverture(url, monkeypatch):
    """Refus AVANT toute ouverture : `urlopen` ne doit jamais etre atteint."""
    def _interdit(*a, **kw):  # pragma: no cover - ne doit jamais s'executer
        raise AssertionError(f"urlopen ne doit pas etre appele pour {url!r}")

    monkeypatch.setattr(link_check.urllib.request, "urlopen", _interdit)
    out = link_check.fetch_via_urllib(url, timeout=1.0)
    assert out.status is None
    assert "schema" in out.error.lower() or "sch" in out.error.lower()


@pytest.mark.parametrize("url", ["http://exemple.test/a", "https://exemple.test/a"])
def test_http_et_https_restent_acceptes(url, monkeypatch):
    """Le filtre ne doit pas refuser ce que le site publie reellement."""
    appels: list[str] = []

    class _Resp:
        status = 200
        headers = type("H", (), {"get_content_charset": lambda self: "utf-8"})()

        def read(self, _n):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _urlopen(req, **kw):
        appels.append(req.full_url)
        return _Resp()

    monkeypatch.setattr(link_check.urllib.request, "urlopen", _urlopen)
    out = link_check.fetch_via_urllib(url, timeout=1.0)
    assert out.status == 200
    assert appels == [url]


def test_une_url_sans_schema_est_refusee(monkeypatch):
    def _interdit(*a, **kw):  # pragma: no cover
        raise AssertionError("urlopen ne doit pas etre appele")

    monkeypatch.setattr(link_check.urllib.request, "urlopen", _interdit)
    assert link_check.fetch_via_urllib("exemple.test/a", timeout=1.0).status is None


def test_le_refus_est_un_echec_de_verification_pas_un_lien_mort():
    """Un schema refuse n'est pas la preuve que la ressource n'existe pas.

    `status=None` fait retomber l'interpretation sur « unknown », donc le lien
    n'est pas declare mort a tort — il est signale comme non verifiable.
    """
    out = link_check.fetch_via_urllib("file:///etc/passwd", timeout=1.0)
    assert out.status is None and out.error
