"""notify.ports — Protocol `NotificationSender` pour DI.

Tous les canaux (Discord, Slack, email, console-dev) doivent l'implémenter
pour être interchangeables côté CLI `poll_rss.py`.
"""
from __future__ import annotations

from typing import Protocol


class NotificationSender(Protocol):
    """Envoie un message structuré sur un canal.

    Renvoie True si l'envoi est jugé réussi (status 2xx pour HTTP,
    pas d'exception pour SMTP). Les implémentations DOIVENT logger
    leurs erreurs mais NE PAS lever (un canal en panne ne doit pas
    interrompre le poll des autres sources).
    """

    name: str

    def send(self, payload: dict) -> bool:
        ...
