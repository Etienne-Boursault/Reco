"""review_render_focus.py — Relecture « focus » : une reco à la fois.

La page d'un épisode montre la liste de ses recos à gauche et UNE carte à
droite ; une décision passe à la suivante. Ce module produit les morceaux
propres à cette mise en page :

- la liste (une entrée par reco ou par grappe de doublons) ;
- la barre de progression ;
- l'écran de fin d'épisode (bilan + suite de la chaîne) ;
- l'accueil (à relire d'abord, état de la chaîne, tous les épisodes).

Les cartes elles-mêmes restent dans `review_render._reco_card`.
"""
from __future__ import annotations

import html
import urllib.parse
from typing import Any

from review_guests import split_names
from review_render_common import _fmt, _parse_guests, _ts_seconds, _yt_id
from review_signals import reco_signals

#: États d'une entrée de liste. `pending` regroupe ce qui reste à décider.
PENDING_STATES = frozenset({"draft", "cluster"})

_COUNT_LABELS = (
    ("done", "validée", "validées"),
    ("citation", "seulement évoquée", "seulement évoquées"),
    ("guestwork", "œuvre d'invité", "œuvres d'invités"),
    ("discarded", "écartée", "écartées"),
)


def entry_state(r: dict) -> str:
    """État d'une reco pour la liste : draft, done, citation, guestwork, discarded."""
    status = r.get("status", "draft")
    if status == "discarded":
        return "discarded"
    if status != "validated":
        return "draft"
    if r.get("kind") == "citation":
        return "citation"
    return "guestwork" if r.get("guestWork") else "done"


def reco_entry(r: dict, ep: dict, hosts: list[str],
               parsed: list[str] | None) -> dict[str, Any]:
    """Entrée de liste d'une reco."""
    secs = _ts_seconds(r.get("timestamp"))
    return {
        "id": r.get("id", ""),
        "title": r.get("title") or "?",
        "time": _fmt(secs) if secs is not None else "",
        "who": ", ".join(split_names(r.get("recommendedBy", ""))),
        "state": entry_state(r),
        "signals": len(reco_signals(r, ep, hosts, parsed)),
    }


def cluster_entry(canonical_id: str, members: list[dict]) -> dict[str, Any]:
    """Entrée de liste d'une grappe de doublons (à fusionner ou séparer)."""
    first = members[0] if members else {}
    return {
        "id": canonical_id,
        "title": first.get("title") or "?",
        "time": "",
        "who": f"{len(members)} doublons probables",
        "state": "cluster",
        "signals": 0,
    }


def _list_item(e: dict[str, Any], pos: int) -> str:
    sig = (f'<span class="fx-sig" title="{e["signals"]} point(s) à vérifier">!</span>'
           if e["signals"] and e["state"] in PENDING_STATES else "")
    meta = " · ".join(x for x in (e["time"], e["who"]) if x)
    return (
        f'<li><button type="button" class="fx-item" data-state="{e["state"]}" '
        f'data-fx-target="{html.escape(e["id"])}" data-time="{e["time"]}">'
        f'<span class="fx-dot" aria-hidden="true"></span>'
        f'<span class="fx-num">{pos}</span>'
        f'<span class="fx-txt"><span class="fx-t">{html.escape(e["title"])}</span>'
        f'<span class="fx-m">{html.escape(meta)}</span></span>{sig}</button></li>'
    )


def render_list(entries: list[dict[str, Any]]) -> str:
    """Liste des recos de l'épisode (navigation du mode focus)."""
    total = len(entries)
    items = "".join(_list_item(e, i) for i, e in enumerate(entries, 1))
    return (
        '<nav class="fx-list" data-fx-list aria-label="Recos de l’épisode">'
        '<button type="button" class="fx-list-toggle" data-fx-list-toggle '
        'aria-expanded="false">Reco <span data-fx-pos>1</span> sur '
        f'{total} ▾</button>'
        f'<ol>{items}</ol></nav>'
    )


def _count(entries: list[dict[str, Any]], state: str) -> int:
    return sum(1 for e in entries if e["state"] == state)


def render_progress(entries: list[dict[str, Any]]) -> str:
    """Barre « n sur N traitées »."""
    total = len(entries)
    done = sum(1 for e in entries if e["state"] not in PENDING_STATES)
    pct = round(100 * done / total) if total else 100
    return (
        '<div class="fx-progress" data-fx-progress>'
        f'<span class="fx-progress-txt"><b data-fx-done>{done}</b> sur '
        f'<span data-fx-total>{total}</span> traitées</span>'
        '<span class="fx-bar" aria-hidden="true">'
        f'<span class="fx-bar-fill" data-fx-bar style="width:{pct}%"></span>'
        '</span></div>'
    )


def _ep_label(ep: dict) -> str:
    season, num = ep.get("season"), ep.get("number")
    if season and num:
        return f"S{season}·E{num}"
    return f"#{num}" if num else ""


def render_end(entries: list[dict[str, Any]], ep: dict,
               next_ep: dict | None) -> str:
    """Écran de fin d'épisode : bilan, ce que fait la chaîne, et la suite.

    Rendu dans tous les cas (le client le révèle quand la dernière reco est
    décidée sans recharger la page) ; `hidden` tant qu'il reste à décider.
    """
    pending = any(e["state"] in PENDING_STATES for e in entries)
    counts = "".join(
        f'<li><b data-fx-count="{state}">{_count(entries, state)}</b> '
        f'<span data-one="{one}" data-many="{many}">'
        f'{one if _count(entries, state) <= 1 else many}</span></li>'
        for state, one, many in _COUNT_LABELS
    )
    if str(ep.get("guid", "")).startswith("yt-"):
        chain = ("Au prochain passage, la chaîne pose les liens d’écoute et les "
                 "fiches, écrit les œuvres et les mentions, puis ouvre la PR. "
                 "Un message Matrix te le dira.")
    else:
        chain = "Épisode traité à la main : rien ne part tout seul."
    if next_ep:
        guid_q = urllib.parse.quote(next_ep.get("guid", ""))
        label = " ".join(x for x in (_ep_label(next_ep),
                                     html.escape(next_ep.get("title") or "")) if x)
        go = (f'<a class="fx-end-go" href="/ep?guid={guid_q}">'
              f'Épisode suivant à relire : {label} →</a>')
    else:
        go = '<a class="fx-end-go" href="/">Plus rien à relire · accueil</a>'
    return (
        f'<div class="fx-end" data-fx-end{" hidden" if pending or not entries else ""}>'
        '<p class="fx-end-k">Épisode relu</p>'
        '<h2 class="fx-end-h">Tout est décidé.</h2>'
        f'<ul class="fx-end-counts">{counts}</ul>'
        f'<p class="fx-end-chain">{chain}</p>'
        f'<div class="fx-end-actions">{go}'
        '<button type="button" class="fx-end-again" data-fx-again>'
        'Revoir les recos</button></div></div>'
    )


def next_to_review(ordered: list[str], current: str | None,
                   groups: dict[str, list[dict]]) -> str | None:
    """Premier épisode après `current` (en boucle) qui a encore des brouillons."""
    if not ordered:
        return None
    start = ordered.index(current) + 1 if current in ordered else 0
    for guid in ordered[start:] + ordered[:start]:
        if guid == current:
            continue
        if any(r.get("status", "draft") == "draft" for r in groups.get(guid, [])):
            return guid
    return None


# ---- Accueil ----------------------------------------------------------------
def _todo_card(ep: dict, recs: list[dict], hosts: list[str]) -> str:
    guid = ep.get("guid", "")
    n_draft = sum(1 for r in recs if entry_state(r) == "draft")
    parsed = ep.get("guestsParsed") or _parse_guests(ep.get("title", ""), hosts)
    n_sig = sum(1 for r in recs if entry_state(r) == "draft"
                and reco_signals(r, ep, hosts, parsed))
    treated = len(recs) - n_draft
    pct = round(100 * treated / len(recs)) if recs else 0
    vid = _yt_id(ep.get("youtubeUrl", ""))
    img = (f'<img class="todo-img" alt="" loading="lazy" '
           f'src="https://i.ytimg.com/vi/{html.escape(vid)}/mqdefault.jpg">'
           if vid else '<span class="todo-img"></span>')
    sig = (f' · <span class="todo-sig">{n_sig} à vérifier</span>' if n_sig else "")
    cta = "Reprendre" if treated else "Commencer"
    return (
        f'<a class="todo-card" href="/ep?guid={urllib.parse.quote(guid)}">{img}'
        f'<span class="todo-body"><span class="todo-num">{_ep_label(ep)}</span>'
        f'<span class="todo-title">{html.escape(ep.get("title") or "?")}</span>'
        f'<span class="todo-meta">{n_draft} à relire sur {len(recs)}{sig}</span>'
        f'<span class="fx-bar"><span class="fx-bar-fill" style="width:{pct}%">'
        f'</span></span><span class="todo-cta">{cta} →</span></span></a>'
    )


def render_todo(ordered: list[str], episodes: dict[str, dict],
                groups: dict[str, list[dict]], hosts: list[str]) -> str:
    """Section « À relire » : les épisodes qui ont encore des brouillons."""
    cards = [
        _todo_card(episodes[g], groups.get(g, []), hosts)
        for g in reversed(ordered)
        if any(entry_state(r) == "draft" for r in groups.get(g, []))
    ]
    body = ("".join(cards) if cards else
            '<p class="home-empty">Rien à relire. La chaîne préviendra au '
            'prochain épisode.</p>')
    return (f'<section class="home-sec"><h2 class="home-h">À relire</h2>'
            f'<div class="todo-grid">{body}</div></section>')


def render_chain(state: dict | None, episodes: dict[str, dict],
                 groups: dict[str, list[dict]]) -> str:
    """Section « La chaîne » : où en sont les épisodes automatiques.

    `state` est le fichier d'état de `traiter_nouveaux_episodes` ; None quand
    la chaîne n'a jamais tourné ici (poste de travail) → section omise.
    """
    if state is None:
        return ""
    finalized = set(state.get("finalized") or [])
    published = set(state.get("published") or [])
    relus = [g for g in episodes if g.startswith("yt-") and g not in finalized
             and groups.get(g)
             and all(entry_state(r) != "draft" for r in groups[g])]
    lines = []
    if relus:
        lines.append(f"{len(relus)} épisode(s) relu(s), en attente de finalisation.")
    a_pousser = finalized - published
    if a_pousser:
        lines.append(f"{len(a_pousser)} épisode(s) finalisé(s), en attente de publication.")
    errors = state.get("lastErrors") or {}
    for msg in list(errors.values())[:3]:
        lines.append(str(msg))
    if not lines:
        lines.append("Rien en cours : tout ce qui a été relu est publié.")
    items = "".join(f"<li>{html.escape(x)}</li>" for x in lines)
    return (f'<section class="home-sec"><h2 class="home-h">La chaîne</h2>'
            f'<ul class="chain-list">{items}</ul></section>')


def render_all_episodes(ordered: list[str], episodes: dict[str, dict],
                        groups: dict[str, list[dict]]) -> str:
    """Section « Tous les épisodes » : liste compacte filtrable."""
    rows = []
    for guid in reversed(ordered):
        ep = episodes.get(guid, {})
        recs = groups.get(guid, [])
        n_draft = sum(1 for r in recs if entry_state(r) == "draft")
        if not recs:
            cls, label = "empty", "0 reco"
        elif n_draft:
            cls, label = "todo", f"{n_draft} à relire sur {len(recs)}"
        else:
            cls, label = "done", f"{len(recs)} recos relues"
        rows.append(
            f'<li class="ep-line {cls}" data-ep-row>'
            f'<a href="/ep?guid={urllib.parse.quote(guid)}">'
            f'<span class="ep-line-num">{_ep_label(ep) or "?"}</span>'
            f'<span class="ep-line-title">{html.escape(ep.get("title") or "?")}</span>'
            f'<span class="ep-line-count">{label}</span></a></li>'
        )
    return (
        '<section class="home-sec"><h2 class="home-h">Tous les épisodes</h2>'
        '<input type="search" class="ep-filter" data-ep-filter '
        'placeholder="Chercher un épisode, un invité…" aria-label="Chercher un épisode">'
        f'<ul class="ep-lines">{"".join(rows)}</ul></section>'
    )
