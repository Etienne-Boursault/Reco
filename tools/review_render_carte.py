"""review_render_carte.py — petites pièces d'une carte de reco.

Sorties de `review_render.py`, qui touchait la limite des 500 lignes au moment
d'ajouter le bloc « Liens » : l'état lisible, le badge de l'agent de revue, et
les liens de la reco. Fonctions pures, réexportées par `review_render`.
"""
from __future__ import annotations

import html

from review_render_common import _safe_url


def _status_label(r: dict) -> str:
    """État lisible d'une reco : ce que la relecture en a décidé."""
    status = r.get("status", "draft")
    if status == "discarded":
        return "écartée"
    if status != "validated":
        return "à relire"
    if r.get("kind") == "citation":
        return "évoquée"
    return "leur œuvre" if r.get("guestWork") else "validée"


def _reco_agent_badge(r: dict) -> str:
    """Badge 🤖 discret si la reco a été traitée par un agent de review.

    Le détail complet (raison, flags, correction humaine) vit sur /doutes ;
    ici on n'affiche que verdict + confiance en title= pour ne pas alourdir
    les cartes.
    """
    ar = r.get("agentReview")
    if not ar:
        return ""
    conf = ar.get("confidence")
    tip = f'{ar.get("verdict", "?")}' + (f" · conf {conf}" if conf is not None else "")
    if ar.get("reason"):
        tip += f' — {ar["reason"]}'
    return (f'<span class="agent-badge" title="{html.escape(tip)}" '
            f'aria-label="Traité par agent : {html.escape(str(ar.get("verdict", "?")))}">'
            f'🤖</span>')


def render_liens(r: dict) -> str:
    """Bloc « Liens » : ce que les passes ont trouvé, retirable d'un clic.

    Les liens sont cherchés avant la relecture (`liens_avant_relecture`) : la
    carte les montre pour qu'un lien faux se voie ici, et non après la
    publication. Le ✕ retire le lien ET le note dans `linksRejected`, pour
    qu'aucune passe ne le repose. Un manque se complète par Éditer → liens
    personnalisés.
    """
    rid = html.escape(r.get("id", ""))
    items = []
    for link in r.get("links") or []:
        if not isinstance(link, dict) or not link.get("url"):
            continue
        label = html.escape(str(link.get("label") or link["url"]))
        url = _safe_url(link["url"])
        cible = (f'<a href="{html.escape(url)}" target="_blank" rel="noopener noreferrer"'
                 f' class="lien-{html.escape(str(link.get("ethics") or "neutral"))}">'
                 f'{label} ↗</a>' if url else f'<span>{label}</span>')
        items.append(
            f'<li>{cible}<form method="post" action="/retirer-lien" class="lien-retirer">'
            f'<input type="hidden" name="id" value="{rid}">'
            f'<input type="hidden" name="url" value="{html.escape(link["url"])}">'
            f'<button type="submit" title="Retirer ce lien : il ne reviendra pas" '
            f'aria-label="Retirer le lien {label}">✕</button></form></li>')
    if not items:
        return ('<div class="liens liens-vide"><span class="liens-h">Liens</span>'
                '<span class="liens-rien">aucun pour l’instant</span></div>')
    return (f'<div class="liens"><span class="liens-h">Liens</span>'
            f'<ul>{"".join(items)}</ul></div>')
