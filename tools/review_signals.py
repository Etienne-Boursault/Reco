"""review_signals.py — Ce qui mérite un second regard sur une reco.

L'encadré « À vérifier » de la page de relecture : au lieu de relire chaque
carte en entier, on montre d'abord ce qui cloche probablement. Chaque signal
vient d'une erreur réellement rencontrée en relecture :

- attribution réduite au prénom (« Carla » pour Carla de Coignac) — le
  transcript n'est pas diarisé, l'extracteur n'a que ce que les gens disent ;
- recommandeur ni animateur ni invité de l'épisode ;
- créateur qui est l'invité lui-même, sans être marqué « leur œuvre » ;
- numéro différent entre le titre et la citation (« Bref » contre « la
  saison 2 de Bref ») ;
- citation absente, minutage absent ou au-delà de la fin de l'épisode.

Fonctions pures, sans I/O : la page les appelle pour chaque carte.
"""
from __future__ import annotations

import html
import re
from typing import NamedTuple

# `episode_people` est ré-exporté (tests, appelants historiques) : le repérage
# des personnes de l'épisode et du prénom seul vit dans review_guests, partagé
# avec `collect_guests` (review_guests ne peut pas importer ce module : cycle).
from review_guests import episode_people, split_names
from review_guests import fold_name as _fold
from review_guests import partial_match as _partial_match
from review_render_common import _safe_int, _ts_seconds


class Signal(NamedTuple):
    """Un point à vérifier.

    `fix_from` / `fix_to` : correction d'attribution applicable en un clic
    (décocher l'un, cocher l'autre dans « Qui recommande ? »). Vides quand la
    correction demande un jugement.
    """
    kind: str
    message: str
    fix_from: str = ""
    fix_to: str = ""


# « saison 2 », « tome III », « vol. 4 », « partie 2 », « chapitre 1 ».
_NUMBERED = re.compile(
    r"\b(saison|tome|vol(?:ume|\.)?|partie|chapitre|episode|épisode)\s+"
    r"(\d+|[ivx]+)\b",
    re.IGNORECASE,
)
_BARE_NUMBER = re.compile(r"\b(\d+|[ivxIVX]+)\b")
_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7,
          "viii": 8, "ix": 9, "x": 10}


def _as_int(token: str) -> int | None:
    token = token.lower()
    if token.isdigit():
        return int(token)
    return _ROMAN.get(token)


def _numbers(text: str) -> dict[str, set[int]]:
    """Numéros de saison/tome/… cités dans un texte, par mot-clé."""
    found: dict[str, set[int]] = {}
    for word, num in _NUMBERED.findall(text or ""):
        n = _as_int(num)
        if n is None:
            continue
        key = _fold(word).rstrip(".")
        key = {"vol": "volume", "episode": "épisode"}.get(key, key)
        found.setdefault(key, set()).add(n)
    return found


def _who_signals(r: dict, people: list[str]) -> list[Signal]:
    known = {_fold(p) for p in people}
    out: list[Signal] = []
    for name in split_names(r.get("recommendedBy", "")):
        if _fold(name) in known:
            continue
        full = _partial_match(name, people)
        if full:
            out.append(Signal(
                "who-partial",
                f"« {name} » : sans doute {full}.",
                fix_from=name, fix_to=full,
            ))
        else:
            out.append(Signal(
                "who-unknown",
                f"« {name} » n'est ni animateur ni invité de l'épisode.",
            ))
    return out


def _creator_signal(r: dict, people: list[str]) -> list[Signal]:
    if r.get("guestWork") or r.get("kind") == "citation":
        return []
    creator = _fold(r.get("creator", ""))
    if not creator:
        return []
    for p in people:
        # Mot entier : « Seb » ne doit pas désigner « Sébastien Tellier ».
        if _fold(p) and re.search(rf"(?<!\w){re.escape(_fold(p))}(?!\w)", creator):
            return [Signal(
                "creator-is-guest",
                f"L'œuvre est de {p}, présent dans l'épisode : « Leur œuvre » ?",
            )]
    return []


def _number_signal(r: dict) -> list[Signal]:
    in_quote = _numbers(r.get("quote", ""))
    if not in_quote:
        return []
    title = r.get("title", "")
    in_title = _numbers(title)
    # « Étincelle 2 » : le numéro nu dans le titre suffit.
    bare = {n for t in _BARE_NUMBER.findall(title)
            if (n := _as_int(t)) is not None}
    for word, nums in in_quote.items():
        if (in_title.get(word, set()) | bare) & nums:
            continue
        n = min(nums)
        label = f"{word} {n}"
        if word in in_title:
            have = ", ".join(str(x) for x in sorted(in_title[word]))
            msg = f"La citation parle de {label}, le titre de {word} {have}."
        else:
            msg = f"La citation parle de {label}, le titre n'en dit rien."
        return [Signal("number-mismatch", msg)]
    return []


def _timing_signals(r: dict, ep: dict) -> list[Signal]:
    secs = _ts_seconds(r.get("timestamp"))
    if secs is None:
        return [Signal("no-timestamp", "Pas de minutage : impossible de réécouter.")]
    durations = [d for d in (_safe_int(ep.get("audioDuration"), 0),
                             _safe_int(ep.get("youtubeDuration"), 0)) if d]
    if durations and secs > max(durations):
        return [Signal("timestamp-out",
                       "Le minutage dépasse la fin de l'épisode.")]
    return []


def render_signals(signals: list[Signal]) -> str:
    """Encadré « À vérifier » d'une carte ("" quand il n'y a rien à signaler).

    Une correction d'attribution sûre devient un bouton : le client décoche
    `fix_from` et coche `fix_to` dans « Qui recommande ? ». Rien n'est
    enregistré avant la décision (Valider, etc.).
    """
    if not signals:
        return ""
    items = []
    for s in signals:
        fix = ""
        if s.fix_to:
            fix = (f' <button type="button" class="verif-fix" '
                   f'data-fix-from="{html.escape(s.fix_from)}" '
                   f'data-fix-to="{html.escape(s.fix_to)}">'
                   f'Corriger en {html.escape(s.fix_to)}</button>')
        elif s.kind == "creator-is-guest":
            fix = (' <button type="button" class="verif-fix" '
                   'data-fix-action="guest-work">Marquer « Leur œuvre »</button>')
        items.append(f'<li class="verif-{s.kind}">{html.escape(s.message)}{fix}</li>')
    return (f'<div class="verif" role="note"><b class="verif-h">À vérifier</b>'
            f'<ul>{"".join(items)}</ul></div>')


def reco_signals(r: dict, ep: dict, hosts: list[str],
                 parsed: list[str] | None = None) -> list[Signal]:
    """Liste ordonnée des points à vérifier pour une reco (vide si rien)."""
    if r.get("status") == "discarded":
        return []
    people = episode_people(ep, hosts, parsed)
    out: list[Signal] = []
    out += _who_signals(r, people)
    out += _creator_signal(r, people)
    out += _number_signal(r)
    if not (r.get("quote") or "").strip():
        out.append(Signal("no-quote", "Pas de citation : écoute le passage."))
    out += _timing_signals(r, ep)
    return out
