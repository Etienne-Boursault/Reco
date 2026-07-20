"""Tests notify.email : SMTP avec factory mock (zéro I/O réel)."""
from __future__ import annotations

import smtplib

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
