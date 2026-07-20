"""notify.slack — sender vers un webhook Slack incoming-webhook.

Symétrique de `notify.discord`. Pas requis pour la roadmap mais livré
pour ne pas avoir à toucher au CLI quand un utilisateur self-host activera
Slack.
"""
from __future__ import annotations

from urllib.parse import urlparse

from common import log


class SlackWebhookSender:
    name = "slack"

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: float = 10.0,
        session=None,
    ) -> None:
        if not webhook_url:
            raise ValueError(
                "SlackWebhookSender : webhook_url vide — vérifie la "
                "variable d'environnement RECO_SLACK_WEBHOOK.",
            )
        self._url = webhook_url
        self._timeout = timeout
        self._session = session

    def _post(self, payload: dict):
        if self._session is not None:
            return self._session.post(self._url, json=payload, timeout=self._timeout)
        import requests  # noqa: PLC0415

        return requests.post(self._url, json=payload, timeout=self._timeout)

    def send(self, payload: dict) -> bool:
        try:
            resp = self._post(payload)
        except Exception as exc:  # noqa: BLE001
            host = urlparse(self._url).hostname or "slack"
            log.warning("Slack webhook %s a échoué : %s", host, exc)
            return False
        ok = bool(getattr(resp, "ok", False))
        if not ok:
            log.warning(
                "Slack webhook a renvoyé status=%s",
                getattr(resp, "status_code", "?"),
            )
        return ok
