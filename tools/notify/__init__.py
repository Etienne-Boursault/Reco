"""Package `notify` — envoi de notifications structurées (Discord, Slack, email).

Tous les sender exposent un Protocol `NotificationSender` (cf. `ports`)
pour permettre l'injection en test sans HTTP/SMTP réel.

Implémentations :
- `discord.DiscordWebhookSender` — POST JSON sur un webhook Discord (embed).
- `slack.SlackWebhookSender` — POST JSON sur un webhook Slack (Block Kit).
- `email.SmtpSender` — SMTP plain-text (optionnel, configuration env).

Le formatage des messages (titre/description, troncature, échappement)
vit dans `notify.formatter` pour homogénéité multi-canal.
"""
from __future__ import annotations

from .formatter import (
    DISCORD_EMBED_DESCRIPTION_LIMIT,
    DISCORD_EMBED_TITLE_LIMIT,
    NewEpisodeMessage,
    build_discord_embed,
    build_plain_text,
    build_slack_blocks,
)
from .ports import NotificationSender

__all__ = [
    "DISCORD_EMBED_DESCRIPTION_LIMIT",
    "DISCORD_EMBED_TITLE_LIMIT",
    "NewEpisodeMessage",
    "NotificationSender",
    "build_discord_embed",
    "build_plain_text",
    "build_slack_blocks",
]
