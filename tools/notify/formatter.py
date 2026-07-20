"""notify.formatter — construction de payloads par canal.

Mutualise la troncature (256 / 4096 chars Discord, etc.) et l'échappement
markdown pour ne pas laisser un titre exotique casser le rendu d'un canal.
"""
from __future__ import annotations

from dataclasses import dataclass

DISCORD_EMBED_TITLE_LIMIT = 256
DISCORD_EMBED_DESCRIPTION_LIMIT = 4096

# Couleur accent par défaut (turquoise — ADR 0030 design tokens).
DISCORD_DEFAULT_COLOR = 0x5EEAD4

# Caractères markdown Discord à neutraliser pour éviter du formatage non voulu.
# Ne s'applique qu'au TITRE qui est une chaîne plain-text côté embed ; on
# laisse la description telle quelle car Discord supporte le markdown
# (souhaitable pour les italiques / liens du summary RSS).
_MARKDOWN_SPECIAL = "\\*_`~|>"


def escape_discord_markdown(text: str) -> str:
    """Échappe les caractères markdown Discord en plain-text.

    Utilisé pour les TITRES d'embed (rendu plain). Ne pas appliquer au
    `description` qui doit conserver son rendu markdown éventuel.
    """
    out = []
    for ch in text:
        if ch in _MARKDOWN_SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def truncate(text: str, limit: int, *, ellipsis: str = "…") -> str:
    """Tronque proprement à `limit` caractères, suffixe `ellipsis` si coupé.

    `limit<=0` renvoie une chaîne vide. `len(ellipsis) > limit` renvoie
    `text[:limit]` sans suffixe (le suffixe ne tiendrait pas).
    """
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    if len(ellipsis) >= limit:
        return text[:limit]
    return text[: limit - len(ellipsis)] + ellipsis


@dataclass(frozen=True, slots=True)
class NewEpisodeMessage:
    """Données minimales pour formater une notification multi-canal."""

    feed_title: str
    episode_title: str
    episode_url: str
    published_at: str
    source_id: str = ""


def build_discord_embed(
    msg: NewEpisodeMessage,
    *,
    color: int = DISCORD_DEFAULT_COLOR,
) -> dict:
    """Construit le payload Discord (webhook) pour un nouvel épisode.

    Le wrapper `{"embeds": [...]}` est attendu par l'API Discord ; on
    retourne directement la structure complète prête à `requests.post`.
    """
    title = truncate(
        f"🎙️ Nouvel épisode — {escape_discord_markdown(msg.feed_title)}",
        DISCORD_EMBED_TITLE_LIMIT,
    )
    description = truncate(msg.episode_title, DISCORD_EMBED_DESCRIPTION_LIMIT)
    embed: dict = {
        "title": title,
        "description": description,
        "color": color,
        "footer": {"text": "Reco poll RSS"},
    }
    if msg.episode_url:
        embed["url"] = msg.episode_url
    if msg.published_at:
        embed["timestamp"] = msg.published_at
    return {"embeds": [embed]}


def build_slack_blocks(msg: NewEpisodeMessage) -> dict:
    """Construit un payload Slack Block Kit minimal.

    Format documenté : https://api.slack.com/block-kit. On reste sur
    deux blocs (header + section) ; suffisant pour transmettre
    titre/lien/date sans dépendre de la richesse Discord.
    """
    header_text = truncate(f"🎙️ Nouvel épisode — {msg.feed_title}", 150)
    body_lines = [f"*{msg.episode_title}*"]
    if msg.episode_url:
        body_lines.append(f"<{msg.episode_url}|Écouter l'épisode>")
    if msg.published_at:
        body_lines.append(f"_Publié : {msg.published_at}_")
    return {
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": header_text}},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(body_lines)},
            },
        ],
    }


def build_plain_text(msg: NewEpisodeMessage) -> str:
    """Construit un message texte pur (email, log, fallback)."""
    lines = [
        f"Nouvel épisode — {msg.feed_title}",
        "",
        msg.episode_title,
    ]
    if msg.episode_url:
        lines += ["", f"Lien : {msg.episode_url}"]
    if msg.published_at:
        lines += [f"Publié : {msg.published_at}"]
    return "\n".join(lines)
