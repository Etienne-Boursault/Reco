"""Tests notify.discord : sender Discord avec session mock (zéro HTTP réel)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from notify.discord import DiscordWebhookSender


class _FakeResp:
    def __init__(self, *, ok=True, status_code=204):
        self.ok = ok
        self.status_code = status_code


class _FakeSession:
    def __init__(self, resp=None, exc=None):
        self.resp = resp or _FakeResp()
        self.exc = exc
        self.calls = []

    def post(self, url, json, timeout):  # noqa: A002 (json mimics requests API)
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.exc is not None:
            raise self.exc
        return self.resp


def test_constructor_rejects_empty_url():
    with pytest.raises(ValueError, match="webhook_url vide"):
        DiscordWebhookSender("")


def test_send_posts_payload_to_webhook():
    sess = _FakeSession()
    sender = DiscordWebhookSender(
        "https://discord.com/api/webhooks/123/abc", session=sess,
    )
    assert sender.send({"embeds": [{"title": "T"}]}) is True
    assert sess.calls[0]["url"] == "https://discord.com/api/webhooks/123/abc"
    assert sess.calls[0]["json"] == {"embeds": [{"title": "T"}]}


def test_send_returns_false_on_non_ok_status():
    sess = _FakeSession(resp=_FakeResp(ok=False, status_code=429))
    sender = DiscordWebhookSender("https://discord.com/api/webhooks/1/x", session=sess)
    assert sender.send({"embeds": []}) is False


def test_send_returns_false_on_network_exception():
    sess = _FakeSession(exc=ConnectionError("dns fail"))
    sender = DiscordWebhookSender("https://discord.com/api/webhooks/1/x", session=sess)
    assert sender.send({"embeds": []}) is False


def test_send_does_not_log_full_url(caplog):
    sess = _FakeSession(exc=ConnectionError("boom"))
    sender = DiscordWebhookSender(
        "https://discord.com/api/webhooks/SECRET/TOKEN", session=sess,
    )
    sender.send({"embeds": []})
    full_log = " ".join(r.getMessage() for r in caplog.records)
    assert "SECRET" not in full_log
    assert "TOKEN" not in full_log
