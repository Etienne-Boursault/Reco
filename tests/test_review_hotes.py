"""Garde des noms d'hôte du serveur de relecture (tableau de bord, 28/11/2026,
relecture du plan R16 ; faille du rebinding DNS).

Une page piégée par « DNS rebinding » parle au serveur sous SON nom de
domaine : l'`Origin` égale le `Host`, l'anti-CSRF passe. La garde refuse donc
tout `Host` non admis (403), en GET comme en POST, dans les deux modes.

La requête est lue par le vrai `BaseHTTPRequestHandler.handle_one_request`
(octets bruts, sans socket) : c'est `parse_request` qui est éprouvé. Les
routes sont remplacées par une sentinelle. Noms et adresses de documentation
seulement (192.0.2.x, 2001:db8::, exemple.local).
"""
from __future__ import annotations

import io

import pytest

import review_handler_base
from review_handler_base import BaseHandler


class _Sentinel(BaseHandler):
    """Handler minimal : répond 204 et note si la route a été atteinte."""

    def do_GET(self):
        self.reached = True
        self._send(204)

    def do_POST(self):
        self.reached = True
        self.same_origin = self._is_same_origin()
        self._send(204)


class _Server:
    server_address = ("0.0.0.0", 8000)  # noqa: S104 — doublure du mode LAN


def _request(method: str = "GET", host: str | None = "localhost:8000",
             extra: dict[str, str] | None = None,
             client: str = "127.0.0.1") -> _Sentinel:
    lines = [f"{method} / HTTP/1.1"]
    if host is not None:
        lines.append(f"Host: {host}")
    lines += [f"{k}: {v}" for k, v in (extra or {}).items()]
    if method == "POST":
        lines.append("Content-Length: 0")
    raw = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")

    h = _Sentinel.__new__(_Sentinel)  # sans socket : pas de __init__
    h.source_id = "demo"
    h.rfile = io.BytesIO(raw)
    h.wfile = io.BytesIO()
    h.client_address = (client, 12345)
    h.server = _Server()
    h.reached = False
    h.handle_one_request()
    return h


def _status(h: _Sentinel) -> int:
    return int(h.wfile.getvalue().split(b" ", 2)[1])


@pytest.fixture
def lan(monkeypatch):
    monkeypatch.setattr(review_handler_base, "ALLOW_LAN", True)
    monkeypatch.delenv("RECO_REVIEW_URL", raising=False)
    monkeypatch.delenv("RECO_REVIEW_HOTES", raising=False)


@pytest.fixture
def strict(monkeypatch):
    monkeypatch.setattr(review_handler_base, "ALLOW_LAN", False)
    monkeypatch.delenv("RECO_REVIEW_URL", raising=False)
    monkeypatch.delenv("RECO_REVIEW_HOTES", raising=False)


# ---- Admis en mode réseau local ---------------------------------------------
def test_lan_ipv4_literal_admitted(lan):
    h = _request(host="192.0.2.10:8000")
    assert _status(h) == 204 and h.reached


def test_lan_ipv6_literal_in_brackets_admitted(lan):
    h = _request(host="[2001:db8::1]:8000")
    assert _status(h) == 204 and h.reached


def test_lan_dot_local_name_admitted(lan):
    h = _request(host="exemple.local:8000")
    assert _status(h) == 204 and h.reached


def test_lan_review_url_host_admitted(lan, monkeypatch):
    monkeypatch.setenv("RECO_REVIEW_URL", "http://revue.exemple.org:8000")
    h = _request(host="revue.exemple.org:8000")
    assert _status(h) == 204 and h.reached


def test_lan_review_url_host_refused_without_env(lan):
    assert _status(_request(host="revue.exemple.org:8000")) == 403


def test_malformed_request_line_refused_before_the_guard(strict):
    # Une ligne de requête invalide est refusée par http.server (400), avant la garde.
    h = _request(method="GET / EN TROP")
    assert _status(h) == 400 and not h.reached


def test_lan_malformed_review_url_admits_nothing_but_lists_still_work(lan, monkeypatch):
    # Une RECO_REVIEW_URL mal formée (crochet non fermé) n'ouvre rien et ne fait pas
    # tomber la garde : les autres noms admis passent toujours.
    monkeypatch.setenv("RECO_REVIEW_URL", "http://[revue.exemple.org:8000")
    monkeypatch.setenv("RECO_REVIEW_HOTES", "un.exemple.org")
    assert _status(_request(host="revue.exemple.org:8000")) == 403
    assert _status(_request(host="un.exemple.org:8000")) == 204


def test_lan_extra_hosts_list_admitted(lan, monkeypatch):
    monkeypatch.setenv("RECO_REVIEW_HOTES", "un.exemple.org, deux.exemple.org:8000")
    assert _status(_request(host="un.exemple.org:8000")) == 204
    assert _status(_request(host="deux.exemple.org")) == 204
    assert _status(_request(host="trois.exemple.org")) == 403


def test_lan_upper_case_admitted(lan):
    assert _status(_request(host="EXEMPLE.Local:8000")) == 204


def test_lan_trailing_dot_admitted(lan):
    assert _status(_request(host="exemple.local.:8000")) == 204


# ---- Admis en mode local strict ---------------------------------------------
@pytest.mark.parametrize("host", ["localhost:8000", "LOCALHOST.", "127.0.0.1:8000",
                                  "[::1]:8000"])
def test_strict_loopback_admitted(strict, host):
    assert _status(_request(host=host)) == 204


@pytest.mark.parametrize("host", ["192.0.2.10:8000", "exemple.local:8000"])
def test_strict_refuses_non_loopback(strict, host):
    """En mode local strict, ni une IP du réseau ni un nom `.local`."""
    assert _status(_request(host=host)) == 403


def test_strict_ignores_review_url(strict, monkeypatch):
    monkeypatch.setenv("RECO_REVIEW_URL", "http://revue.exemple.org:8000")
    assert _status(_request(host="revue.exemple.org:8000")) == 403


# ---- Refusés : nom étranger, Host absent ou mal formé -------------------------
@pytest.mark.parametrize("mode", ["lan", "strict"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_foreign_host_refused(request, mode, method):
    """Le cas du rebinding : un nom de l'attaquant, Origin == Host."""
    request.getfixturevalue(mode)
    h = _request(method, host="piege.exemple.com:8000",
                 extra={"Origin": "http://piege.exemple.com:8000"})
    assert _status(h) == 403
    assert not h.reached


@pytest.mark.parametrize("mode", ["lan", "strict"])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_missing_host_refused(request, mode, method):
    request.getfixturevalue(mode)
    h = _request(method, host=None)
    assert _status(h) == 403
    assert not h.reached


@pytest.mark.parametrize("host", ["[2001:db8::1", "2001:db8::1", "exemple.local:abc",
                                  "piege.exemple.com@exemple.local", ""])
def test_malformed_host_refused(lan, host):
    assert _status(_request(host=host)) == 403


# ---- Anti-CSRF : même analyse du Host -----------------------------------------
def test_lan_post_ipv6_same_origin_accepted(lan):
    """L'ancienne coupe sur le premier `:` refusait tout POST en IPv6."""
    h = _request("POST", host="[2001:db8::1]:8000",
                 extra={"Origin": "http://[2001:db8::1]:8000"}, client="192.0.2.20")
    assert _status(h) == 204
    assert h.same_origin is True


def test_lan_post_trailing_dot_same_origin_accepted(lan):
    h = _request("POST", host="EXEMPLE.local.:8000",
                 extra={"Origin": "http://exemple.local:8000"}, client="192.0.2.20")
    assert h.same_origin is True


def test_lan_post_other_admitted_origin_refused(lan):
    """Deux noms admis mais différents : l'anti-CSRF refuse toujours."""
    h = _request("POST", host="exemple.local:8000",
                 extra={"Origin": "http://192.0.2.10:8000"}, client="192.0.2.20")
    assert h.same_origin is False
