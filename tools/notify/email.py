"""notify.email — sender SMTP plain-text.

Config via env (lue côté CLI) : SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS,
SMTP_FROM, SMTP_TO. STARTTLS si port 587, SSL implicite si 465.

Implémentation minimale : pas de templating HTML, pas de retry — l'email
est une option secondaire (Discord est le canal principal recommandé).
"""
from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from common import log


@dataclass(frozen=True, slots=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    sender: str
    recipient: str
    use_ssl: bool = False
    starttls: bool = True
    timeout: float = 15.0


class SmtpSender:
    """Envoie un email plain-text. Payload attendu : `{"subject": ..., "body": ...}`.

    Injecter `smtp_factory` en test pour éviter tout I/O réel (cf.
    `tests/notify/test_smtp.py`).
    """

    name = "email"

    def __init__(self, config: SmtpConfig, *, smtp_factory=None) -> None:
        self._config = config
        # Default factory : `smtplib.SMTP_SSL` si SSL implicite, sinon
        # `smtplib.SMTP`. Toujours surchargeable pour les tests.
        self._smtp_factory = smtp_factory

    def _open(self):
        if self._smtp_factory is not None:
            return self._smtp_factory(self._config.host, self._config.port)
        if self._config.use_ssl:
            return smtplib.SMTP_SSL(
                self._config.host,
                self._config.port,
                timeout=self._config.timeout,
            )
        return smtplib.SMTP(
            self._config.host,
            self._config.port,
            timeout=self._config.timeout,
        )

    def send(self, payload: dict) -> bool:
        subject = str(payload.get("subject", "Reco — nouvel épisode"))
        body = str(payload.get("body", ""))
        msg = EmailMessage()
        msg["From"] = self._config.sender
        msg["To"] = self._config.recipient
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            with self._open() as client:
                if self._config.starttls and not self._config.use_ssl:
                    try:
                        client.starttls()
                    except smtplib.SMTPException:
                        # Serveur sans TLS (ex: MailHog en dev) : on continue.
                        pass
                if self._config.user:
                    client.login(self._config.user, self._config.password)
                client.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            log.warning("SMTP send a échoué : %s", exc)
            return False
        return True
