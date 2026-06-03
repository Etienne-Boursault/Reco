"""review_guests.py — Gestion des invités d'un épisode (panel + mutations).

Extrait de `review_server.py` pour rester sous 500 lignes par fichier et
isoler la logique métier de la couche transport HTTP. Tout est en fonctions
pures : pas de dépendance au Handler.
"""
from __future__ import annotations

import html
import re
import urllib.parse
from pathlib import Path
from typing import Callable

from common import (
    find_episode_by_guid, log, read_json, write_json_if_changed,
)

# Placeholders à ne jamais proposer comme invité (et à nettoyer du JSON
# quand on les rencontre via le panneau « Invités »).
GUEST_PLACEHOLDERS: frozenset[str] = frozenset({
    "intervenant non spécifié",
    "intervenants non spécifiés",
    "invité non spécifié",
    "invités non spécifiés",
    "non spécifié",
})

# Séparateurs trouvés dans un champ recommendedBy multi-noms ("Kyan & Navo").
_NAME_SPLIT = re.compile(r"\s*(?:&|,| et )\s*")

# Guid valide : ASCII printable « safe », longueur raisonnable.
_GUID_RE = re.compile(r"^[A-Za-z0-9_.:\-]{1,128}$")


def is_placeholder(name: str) -> bool:
    """Vrai si `name` matche un libellé fourre-tout ('non spécifié', …)."""
    return name.strip().casefold() in GUEST_PLACEHOLDERS


def split_names(s: str) -> list[str]:
    """Découpe une chaîne multi-noms (& / virgule / ' et ') en liste.

    USAGE : à appliquer sur des CHAMPS DE NOMS (recommendedBy, ep.guests),
    PAS sur des titres d'œuvre — le séparateur ' et ' tolère des faux
    positifs (ex. titre « Une étoile et la lune » serait scindé à tort).
    """
    return [n.strip() for n in _NAME_SPLIT.split(s or "") if n.strip()]


def collect_guests(
    ep: dict, recs: list[dict], hosts: list[str],
) -> list[str]:
    """Invités distincts de l'épisode (hors hosts et placeholders).

    Union de `ep.guests` (ajouts manuels) et des `recommendedBy` des recos.
    Préserve l'ordre de première occurrence — important pour que la
    saisie utilisateur reste prévisible dans le panel.
    """
    host_keys = {h.casefold() for h in hosts}
    seen: dict[str, str] = {}
    sources: list[str] = list(ep.get("guests") or [])
    for r in recs:
        rb = r.get("recommendedBy", "")
        if rb:
            sources.extend(split_names(rb))
    for n in sources:
        key = n.casefold()
        if key in host_keys or is_placeholder(n) or key in seen:
            continue
        seen[key] = n
    return list(seen.values())


def render_guests_panel(
    guid: str, ep: dict, recs: list[dict], hosts: list[str],
) -> str:
    """Panneau « Invités de l'épisode » : rename / suppression en masse.

    Chaque ligne pré-remplie avec le nom courant ; soumission met à jour
    toutes les recos de l'épisode (côté serveur via /rename-guest).
    """
    guests = collect_guests(ep, recs, hosts)
    guid_q = html.escape(guid)
    rows = "".join(
        f'<form class="guest-row" method="post" action="/rename-guest">'
        f'<input type="hidden" name="guid" value="{guid_q}">'
        f'<input type="hidden" name="old" value="{html.escape(g)}">'
        f'<input type="text" name="new" value="{html.escape(g)}" '
        f'aria-label="Renommer {html.escape(g)}">'
        f'<button type="submit" title="Renommer dans toutes les recos">✓</button>'
        f'<button type="submit" name="action" value="delete" class="discard" '
        f'title="Retirer de toutes les recos">✕</button>'
        f'</form>'
        for g in guests
    )
    add_form = (
        f'<form class="guest-row" method="post" action="/rename-guest">'
        f'<input type="hidden" name="guid" value="{guid_q}">'
        f'<input type="hidden" name="action" value="add">'
        f'<input type="text" name="new" value="" placeholder="+ ajouter un invité…" '
        f'aria-label="Ajouter un invité">'
        f'<button type="submit" title="Ajouter à l\'épisode">+</button>'
        f'</form>'
    )
    label = f"Invités de l'épisode ({len(guests)})" if guests else "Invités de l'épisode"
    return (
        f'<details class="guests" open><summary>{label}</summary>'
        f'<div class="guest-list">{rows}{add_form}</div></details>'
    )


def apply_guest_action(
    source_id: str,
    ep_path: Path,
    guid: str,
    action: str,
    old: str,
    new: str,
    *,
    load_groups: Callable[[str], tuple[dict, dict, dict[str, list[dict]]]],
    reco_path: Callable[[str, str], Path | None],
    invalidate_cache: Callable[[str], None],
) -> tuple[str, str]:
    """Mute l'épisode + ses recos selon l'action. Retourne (flash, kind).

    Actions :
      - 'add'    : ajoute `new` à `ep.guests` (refusé si placeholder ou hôte)
      - 'delete' : retire `old` partout (ep.guests + recommendedBy des recos)
      - autres   : renomme `old` → `new` partout

    Les callbacks `load_groups` / `reco_path` / `invalidate_cache` sont
    injectés pour éviter une dépendance circulaire avec review_server.
    """
    ep = read_json(ep_path)
    guests = list(ep.get("guests") or [])
    hosts = list((load_groups(source_id)[0]).get("hosts", []))

    if action == "add":
        if not new or is_placeholder(new):
            return "Nom vide ou non valide.", "warning"
        if any(h.casefold() == new.casefold() for h in hosts):
            return (
                f"« {new} » est un hôte du podcast, pas un invité.",
                "warning",
            )
        if any(g.casefold() == new.casefold() for g in guests):
            return f"« {new} » est déjà dans les invités.", "info"
        guests.append(new)
        ep["guests"] = guests
        write_json_if_changed(ep_path, ep)
        log.info("Invité ajouté à %s : %s", guid, new)
        return f"Invité « {new} » ajouté.", "success"

    if not old:
        return "Action invalide.", "error"

    replacement = "" if action == "delete" else new
    # 1) Mute ep.guests
    new_guests: list[str] = []
    for g in guests:
        if g.casefold() == old.casefold():
            if replacement and not any(
                replacement.casefold() == x.casefold() for x in new_guests
            ):
                new_guests.append(replacement)
        else:
            new_guests.append(g)
    ep["guests"] = new_guests
    write_json_if_changed(ep_path, ep)
    # 2) Mute les recos
    _source, _episodes, groups = load_groups(source_id)
    recs = groups.get(guid, [])
    changed = 0
    for r in recs:
        names = split_names(r.get("recommendedBy", ""))
        if not any(n.casefold() == old.casefold() for n in names):
            continue
        updated: list[str] = []
        for n in names:
            if n.casefold() == old.casefold():
                if replacement and not any(
                    replacement.casefold() == x.casefold() for x in updated
                ):
                    updated.append(replacement)
            else:
                updated.append(n)
        # NOTE shallow copy : on écrit JSON sur disque ; le cache local sera
        # rechargé au prochain _load_groups (cf. invalidate_cache plus bas).
        r2 = dict(r)
        if updated:
            r2["recommendedBy"] = " & ".join(updated)
        else:
            r2.pop("recommendedBy", None)
        p = reco_path(source_id, r.get("id", ""))
        if p and write_json_if_changed(p, r2):
            changed += 1
    invalidate_cache(source_id)
    verb = "retiré" if action == "delete" else "renommé"
    log.info("Guest %s [%s → %s] sur %s : %d reco(s)",
             verb, old, replacement or "(retiré)", guid, changed)
    if changed:
        flash = (f"Invité {verb} sur {changed} reco"
                 + ("s" if changed > 1 else "") + ".")
        return flash, "success"
    return f"Invité {verb} de l'épisode.", "success"


def handle_rename_guest(
    source_id: str,
    data: dict,
    *,
    load_groups: Callable[[str], tuple[dict, dict, dict[str, list[dict]]]],
    reco_path: Callable[[str, str], Path | None],
    invalidate_cache: Callable[[str], None],
) -> str:
    """Entrée principale POST /rename-guest. Retourne l'URL de redirection (Location).

    Garde-fous : guid manquant ou invalide → `/`. Epoch JSON introuvable → `/`.
    """
    guid = (data.get("guid") or [""])[0]
    old = (data.get("old") or [""])[0].strip()
    new = (data.get("new") or [""])[0].strip()
    action = (data.get("action") or [""])[0]
    if not guid or not _GUID_RE.match(guid):
        return "/"
    try:
        ep_path = find_episode_by_guid(source_id, guid)
    except FileNotFoundError:
        return "/"
    flash, kind = apply_guest_action(
        source_id, ep_path, guid, action, old, new,
        load_groups=load_groups,
        reco_path=reco_path,
        invalidate_cache=invalidate_cache,
    )
    return (f"/ep?guid={urllib.parse.quote(guid)}"
            f"&flash={urllib.parse.quote(flash)}&kind={kind}")
