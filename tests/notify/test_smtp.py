"""Tests notify.email : SMTP avec factory mock (zéro I/O réel)."""
from __future__ import annotations

import smtplib

import pytest

from notify.email import SmtpConfig, SmtpSender


class _FakeSmtp:
    """Fake context-manager imitant `smtplib.SMTP`."""

    def __init__(self, *, fail_send: Exception | None = None) -> None:
        self.starttls_called = False
        self.login_args = None
        self.sent_message = None
        self.fail_send = fail_send

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.starttls_called = True

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, msg):
        if self.fail_send is not None:
            raise self.fail_send
        self.sent_message = msg


def _config() -> SmtpConfig:
    return SmtpConfig(
        host="smtp.example.com", port=587,
        user="bot", password="hunter2",
        sender="bot@example.com", recipient="me@example.com",
    )


def test_send_calls_starttls_login_send():
    fake = _FakeSmtp()
    sender = SmtpSender(_config(), smtp_factory=lambda h, p: fake)
    assert sender.send({"subject": "S", "body": "B"}) is True
    assert fake.starttls_called is True
    assert fake.login_args == ("bot", "hunter2")
    assert fake.sent_message["Subject"] == "S"
    assert fake.sent_message["From"] == "bot@example.com"
    assert fake.sent_message["To"] == "me@example.com"


def test_send_skips_login_when_user_empty():
    fake = _FakeSmtp()
    cfg = SmtpConfig(
        host="x", port=587, user="", password="",
        sender="a@b", recipient="c@d",
    )
    sender = SmtpSender(cfg, smtp_factory=lambda h, p: fake)
    assert sender.send({"subject": "S", "body": "B"}) is True
    assert fake.login_args is None


def test_send_returns_false_on_smtp_exception():
    fake = _FakeSmtp(fail_send=smtplib.SMTPException("rejected"))
    sender = SmtpSender(_config(), smtp_factory=lambda h, p: fake)
    assert sender.send({"subject": "S", "body": "B"}) is False


def test_send_returns_false_on_os_error():
    fake = _FakeSmtp(fail_send=OSError("connection reset"))
    sender = SmtpSender(_config(), smtp_factory=lambda h, p: fake)
    assert sender.send({"subject": "S", "body": "B"}) is False


def test_starttls_failure_does_not_abort():
    class _FailStartTls(_FakeSmtp):
        def starttls(self):
            raise smtplib.SMTPException("no TLS")

    fake = _FailStartTls()
    sender = SmtpSender(_config(), smtp_factory=lambda h, p: fake)
    # On continue : MailHog-like dev sans TLS doit marcher.
    assert sender.send({"subject": "S", "body": "B"}) is True


# ===== _open : choix du transport quand aucune factory n'est injectée ======
def _cfg(**overrides) -> SmtpConfig:
    base = dict(
        host="smtp.exemple.fr", port=587, user="", password="",
        sender="bot@exemple.fr", recipient="moi@exemple.fr",
    )
    base.update(overrides)
    return SmtpConfig(**base)


def test_open_uses_smtp_ssl_when_ssl_is_implicit(monkeypatch):
    """`use_ssl` → connexion SSL implicite (port 465), pas de STARTTLS.
    `smtplib` est doublé : aucune connexion réseau n'est ouverte."""
    seen = {}

    def _fake_ssl(host, port, timeout=None):
        seen["ssl"] = (host, port, timeout)
        return "connexion-ssl"

    def _fake_plain(host, port, timeout=None):
        raise AssertionError("SMTP en clair ne doit pas être utilisé ici")

    monkeypatch.setattr(smtplib, "SMTP_SSL", _fake_ssl)
    monkeypatch.setattr(smtplib, "SMTP", _fake_plain)
    sender = SmtpSender(_cfg(port=465, use_ssl=True, timeout=9.0))

    assert sender._open() == "connexion-ssl"
    assert seen["ssl"] == ("smtp.exemple.fr", 465, 9.0)


def test_open_uses_plain_smtp_by_default(monkeypatch):
    seen = {}

    def _fake_plain(host, port, timeout=None):
        seen["plain"] = (host, port, timeout)
        return "connexion-claire"

    def _fake_ssl(host, port, timeout=None):
        raise AssertionError("SSL implicite non demandé")

    monkeypatch.setattr(smtplib, "SMTP", _fake_plain)
    monkeypatch.setattr(smtplib, "SMTP_SSL", _fake_ssl)
    sender = SmtpSender(_cfg(timeout=9.0))

    assert sender._open() == "connexion-claire"
    assert seen["plain"] == ("smtp.exemple.fr", 587, 9.0)


def test_open_prefers_the_injected_factory(monkeypatch):
    """La factory injectée court-circuite `smtplib` — c'est ce qui garantit
    qu'aucun test n'ouvre de vraie connexion."""
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: pytest.fail(
        "la factory injectée doit primer"))
    seen = {}

    sender = SmtpSender(
        _cfg(),
        smtp_factory=lambda host, port: seen.setdefault("args", (host, port)),
    )
    sender._open()

    assert seen["args"] == ("smtp.exemple.fr", 587)


def test_send_skips_starttls_when_ssl_is_already_implicit():
    """SSL implicite : pas de STARTTLS par-dessus (le serveur le refuserait)."""
    fake = _FakeSmtp()
    sender = SmtpSender(_cfg(use_ssl=True, starttls=True),
                        smtp_factory=lambda h, p: fake)

    assert sender.send({"subject": "S", "body": "B"}) is True
    assert fake.starttls_called is False


def test_send_skips_starttls_when_disabled():
    fake = _FakeSmtp()
    sender = SmtpSender(_cfg(starttls=False),
                        smtp_factory=lambda h, p: fake)

    assert sender.send({"subject": "S", "body": "B"}) is True
    assert fake.starttls_called is False
