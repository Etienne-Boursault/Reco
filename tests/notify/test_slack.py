"""Tests notify.slack : symétrique de Discord (mock session)."""
from __future__ import annotations

import pytest

from notify.slack import SlackWebhookSender


class _Resp:
    def __init__(self, ok=True, status_code=200):
        self.ok = ok
        self.status_code = status_code


class _Sess:
    def __init__(self, resp=None, exc=None):
        self.resp = resp or _Resp()
        self.exc = exc
        self.calls = []

    def post(self, url, json, timeout):  # noqa: A002
        self.calls.append((url, json, timeout))
        if self.exc:
            raise self.exc
        return self.resp


def test_empty_url_rejected():
    with pytest.raises(ValueError):
        SlackWebhookSender("")


def test_send_ok():
    sess = _Sess()
    sender = SlackWebhookSender("https://hooks.slack.com/services/X", session=sess)
    assert sender.send({"blocks": []}) is True


def test_send_non_ok_status():
    sess = _Sess(resp=_Resp(ok=False, status_code=500))
    sender = SlackWebhookSender("https://hooks.slack.com/services/X", session=sess)
    assert sender.send({"blocks": []}) is False


def test_send_network_error():
    sess = _Sess(exc=RuntimeError("nope"))
    sender = SlackWebhookSender("https://hooks.slack.com/services/X", session=sess)
    assert sender.send({"blocks": []}) is False
