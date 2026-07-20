"""notify.discord — sender vers un webhook Discord.

Sécurité : la webhook URL est secrète. On l'accepte en argument constructeur
(en pratique, lue depuis env `RECO_DISCORD_WEBHOOK` côté CLI). On ne logue
JAMAIS l'URL — seulement le host (`discord.com`) en cas d'erreur.
"""
from __future__ import annotations

from urllib.parse import urlparse

from common import log


class DiscordWebhookSender:
    """POST le payload JSON sur la webhook URL fournie.

    Attribut `name="discord"` pour le routing depuis le CLI.
    """

    name = "discord"

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout: float = 10.0,
        session=None,
    ) -> None:
        if not webhook_url:
            raise ValueError(
                "DiscordWebhookSender : webhook_url vide — vérifie la "
                "variable d'environnement RECO_DISCORD_WEBHOOK.",
            )
        self._url = webhook_url
        self._timeout = timeout
        self._session = session  # injecté en test ; sinon `requests` global.

    def _post(self, payload: dict):
        if self._session is not None:
            return self._session.post(self._url, json=payload, timeout=self._timeout)
        import requests  # noqa: PLC0415 — import paresseux.

        return requests.post(self._url, json=payload, timeout=self._timeout)

    def send(self, payload: dict) -> bool:
        try:
            resp = self._post(payload)
        except Exception as exc:  # noqa: BLE001 — best-effort, ne casse pas le poll
            host = urlparse(self._url).hostname or "discord"
            log.warning("Discord webhook %s a échoué : %s", host, exc)
            return False
        ok = bool(getattr(resp, "ok", False))
        if not ok:
            status = getattr(resp, "status_code", "?")
            log.warning("Discord webhook a renvoyé status=%s", status)
        return ok
