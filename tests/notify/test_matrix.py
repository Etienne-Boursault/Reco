"""Tests notify.matrix : sender Matrix avec session mock (zéro HTTP réel)."""
from __future__ import annotations

import pytest

from notify.formatter import NewEpisodeMessage, build_matrix_message
from notify.matrix import MatrixSender


class _FakeResp:
    def __init__(self, *, ok=True, status_code=200):
        self.ok = ok
        self.status_code = status_code


class _FakeSession:
    def __init__(self, resp=None, exc=None):
        self.resp = resp or _FakeResp()
        self.exc = exc
        self.calls = []

    def put(self, url, json, headers, timeout):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        if self.exc is not None:
            raise self.exc
        return self.resp


def test_constructor_rejects_missing_config():
    with pytest.raises(ValueError, match="homeserver/token/room_id requis"):
        MatrixSender("", "tok", "!r:s")
    with pytest.raises(ValueError):
        MatrixSender("https://m.fr", "", "!r:s")
    with pytest.raises(ValueError):
        MatrixSender("https://m.fr", "tok", "")


def test_send_puts_to_room_send_endpoint_with_bearer():
    sess = _FakeSession()
    sender = MatrixSender("https://matrix.exemple.fr/", "s3cr3t", "!abc:exemple.fr", session=sess)
    content = {"msgtype": "m.notice", "body": "hello"}
    assert sender.send(content) is True
    call = sess.calls[0]
    # Room URL-encodé, endpoint client-server v3, txn id après m.room.message/.
    assert call["url"].startswith(
        "https://matrix.exemple.fr/_matrix/client/v3/rooms/%21abc%3Aexemple.fr/send/m.room.message/"
    )
    assert call["headers"]["Authorization"] == "Bearer s3cr3t"
    assert call["json"] == content


def test_send_false_on_non_ok():
    sess = _FakeSession(resp=_FakeResp(ok=False, status_code=403))
    sender = MatrixSender("https://m.fr", "t", "!r:s", session=sess)
    assert sender.send({"body": "x"}) is False


def test_send_false_on_exception():
    sess = _FakeSession(exc=ConnectionError("dns"))
    sender = MatrixSender("https://m.fr", "t", "!r:s", session=sess)
    assert sender.send({"body": "x"}) is False


def test_send_does_not_log_token(caplog):
    sess = _FakeSession(exc=ConnectionError("boom"))
    sender = MatrixSender("https://m.fr", "SUPERSECRETTOKEN", "!r:s", session=sess)
    sender.send({"body": "x"})
    logs = " ".join(r.getMessage() for r in caplog.records)
    assert "SUPERSECRETTOKEN" not in logs


def test_build_matrix_message_shape_and_escaping():
    msg = NewEpisodeMessage(
        feed_title="Un Bon <Moment>",
        episode_title="S5·E21 & co",
        episode_url="https://exemple.fr/ep?a=1&b=2",
        published_at="2026-07-28",
        source_id="un-bon-moment",
    )
    content = build_matrix_message(msg)
    assert content["msgtype"] == "m.notice"
    assert content["format"] == "org.matrix.custom.html"
    # Texte pur en fallback.
    assert "S5·E21 & co" in content["body"]
    # HTML échappé (pas de balise injectée par un titre exotique).
    fb = content["formatted_body"]
    assert "&lt;Moment&gt;" in fb
    assert "S5·E21 &amp; co" in fb
    assert '<a href="https://exemple.fr/ep?a=1&amp;b=2">' in fb


def test_uses_requests_when_no_session_injected(monkeypatch):
    """Sans session injectée, l'envoi importe `requests` à la volée. On
    remplace le module dans `sys.modules` : aucune requête ne part."""
    import sys
    from types import SimpleNamespace

    captured = {}

    def _put(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return SimpleNamespace(ok=True, status_code=204, text="")

    monkeypatch.setitem(sys.modules, "requests",
                        SimpleNamespace(put=_put))
    sender = MatrixSender("https://matrix.exemple.fr", "tok", "!salon:exemple.fr")

    assert sender.send({"body": "coucou", "msgtype": "m.text"}) is True
    assert captured["url"].startswith("https://matrix.exemple.fr/")
