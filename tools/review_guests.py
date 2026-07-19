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
    *, parsed: list[str] | None = None,
) -> list[str]:
    """Invités distincts de l'épisode (hors hosts, placeholders, exclus).

    Union de :
      - `ep.guests` (ajouts manuels positifs)
      - `ep.guestsParsed` (snapshot du parsing du titre, persisté)
      - `parsed` (optionnel : parsing à la volée — utilisé en fallback
        SEULEMENT quand `guestsParsed` est absent/vide, pour ne pas
        double-alimenter la liste sur les épisodes déjà migrés)
      - les noms cités dans `recommendedBy` des recos.

    Retrait : `ep.guestsExcluded` (autorité ultime, comparaison casefold).
    Filtre : hosts, placeholders. Préserve l'ordre de 1ère occurrence.
    """
    host_keys = {h.casefold() for h in hosts}
    excluded_keys = {n.casefold() for n in (ep.get("guestsExcluded") or [])}
    seen: dict[str, str] = {}
    sources: list[str] = list(ep.get("guests") or [])
    sources.extend(ep.get("guestsParsed") or [])
    # `parsed` n'est qu'un fallback : ignoré si le snapshot `guestsParsed` est
    # présent (sinon les mêmes noms seraient ajoutés deux fois — cf. N2).
    if parsed and not ep.get("guestsParsed"):
        sources.extend(parsed)
    for r in recs:
        rb = r.get("recommendedBy", "")
        if rb:
            sources.extend(split_names(rb))
    for n in sources:
        key = n.casefold()
        if (key in host_keys or key in excluded_keys
                or is_placeholder(n) or key in seen):
            continue
        seen[key] = n
    return list(seen.values())


def render_guests_panel(
    guid: str, ep: dict, recs: list[dict], hosts: list[str],
    *, parsed: list[str] | None = None,
) -> str:
    """Panneau « Invités de l'épisode » : rename / exclusion persistante.

    Chaque ligne pré-remplie avec le nom courant ; soumission met à jour
    toutes les recos de l'épisode (côté serveur via /rename-guest). Le
    bouton ✕ utilise `action=exclude` → persiste dans `guestsExcluded`
    pour que le nom ne réapparaisse plus via le parsing du titre.
    """
    guests = collect_guests(ep, recs, hosts, parsed=parsed)
    guid_q = html.escape(guid)
    rows = "".join(
        f'<form class="guest-row" method="post" action="/rename-guest">'
        f'<input type="hidden" name="guid" value="{guid_q}">'
        f'<input type="hidden" name="old" value="{html.escape(g)}">'
        f'<input type="text" name="new" value="{html.escape(g)}" '
        f'aria-label="Renommer {html.escape(g)}">'
        f'<button type="submit" title="Renommer dans toutes les recos">✓</button>'
        f'<button type="submit" name="action" value="exclude" class="discard" '
        f'title="Retirer (et ne plus jamais proposer ce nom)">✕</button>'
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


def _exclude_add(ep: dict, name: str) -> bool:
    """Ajoute `name` à `ep.guestsExcluded` (sans doublon casefold).

    Retourne True si la liste a été modifiée. `guestsExcluded` est l'autorité
    ultime consultée par `collect_guests` : un nom qui y figure ne réapparaît
    plus, même s'il revient du parsing du titre (guestsParsed).
    """
    excluded = list(ep.get("guestsExcluded") or [])
    if any(x.casefold() == name.casefold() for x in excluded):
        return False
    excluded.append(name)
    ep["guestsExcluded"] = excluded
    return True


def _exclude_remove(ep: dict, name: str) -> bool:
    """Retire `name` de `ep.guestsExcluded` (comparaison casefold).

    Retourne True si la liste a été modifiée (réhabilitation effective).
    """
    excluded = list(ep.get("guestsExcluded") or [])
    kept = [x for x in excluded if x.casefold() != name.casefold()]
    if kept == excluded:
        return False
    ep["guestsExcluded"] = kept
    return True


def _reconcile_parsed_rename(
    ep: dict, old: str, replacement: str, new_guests: list[str],
) -> None:
    """Réconcilie le renommage/retrait d'un invité issu de `ep.guestsParsed`.

    Quand `old` provient du snapshot du parsing du titre (guestsParsed) et non
    de `ep.guests`, la mutation de `ep.guests` ne l'atteint pas et
    `collect_guests` le referait réapparaître via l'union guests+guestsParsed.
    On corrige `new_guests` (modifié en place) et `ep.guestsExcluded` :

      - renommage réel / retrait (casefold différent) : masque `old` via
        guestsExcluded (autorité ultime) ;
      - renommage pur-casse (« Seb » → « SEB », casefold identique) : n'exclut
        PAS `old` — l'exclusion casefold masquerait aussi la nouvelle casse —
        et se contente d'insérer la nouvelle casse (elle passe en tête de
        `collect_guests` et l'emporte sur l'ancienne issue de guestsParsed) ;
      - noop strict (`old == new` exact) : ne fait rien.

    Le remplacement est ajouté à `new_guests` s'il n'y figure pas (casefold).
    """
    if replacement == old:  # noop strict : ✓ sans édition → rien à faire
        return
    parsed = ep.get("guestsParsed") or []
    if not any(p.casefold() == old.casefold() for p in parsed):
        return
    if replacement.casefold() != old.casefold():
        _exclude_add(ep, old)
    if replacement and not any(
        replacement.casefold() == g.casefold() for g in new_guests
    ):
        new_guests.append(replacement)


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
      - 'add'     : ajoute `new` à `ep.guests` (refusé si vide, placeholder ou
                    hôte ; réhabilite un nom précédemment exclu).
      - 'delete'  : retire `old` partout (ep.guests + recommendedBy des recos).
                    Si `old` vient de `ep.guestsParsed`, il est aussi masqué via
                    `ep.guestsExcluded` (sinon il réapparaîtrait au render).
      - 'exclude' : comme 'delete', mais mémorise TOUJOURS `old` dans
                    `ep.guestsExcluded` — c'est le ✕ du panneau : « ne plus
                    jamais proposer ce nom », même s'il revient du parsing du
                    titre.
      - autres    : renomme `old` → `new` partout (`new` validé comme pour
                    'add' : refusé si vide, placeholder ou hôte).

    Garde-fou hôte : `old` ne peut être ni renommé ni retiré s'il matche un
    hôte du podcast (defense in depth contre un POST forgé — sinon des
    `recommendedBy` validés seraient silencieusement cassés).

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
        # Réhabilitation : si le nom était exclu, on le retire de
        # `guestsExcluded` avant l'ajout (permet de revenir sur un ✕).
        rehabilitated = _exclude_remove(ep, new)
        if any(g.casefold() == new.casefold() for g in guests):
            if rehabilitated:
                write_json_if_changed(ep_path, ep)
                return f"« {new} » réhabilité.", "success"
            return f"« {new} » est déjà dans les invités.", "info"
        guests.append(new)
        ep["guests"] = guests
        write_json_if_changed(ep_path, ep)
        log.info("Invité ajouté à %s : %s", guid, new)
        return f"Invité « {new} » ajouté.", "success"

    if not old:
        return "Action invalide.", "error"

    # Garde-fou hôte (cf. docstring) : jamais renommer/retirer un hôte.
    if any(h.casefold() == old.casefold() for h in hosts):
        return (
            f"« {old} » est un hôte du podcast : action refusée.",
            "warning",
        )

    # ✕ du panneau : mémorise le retrait dans guestsExcluded puis nettoie comme
    # un delete. Un SEUL write JSON de l'épisode en aval (cf. `ep["guests"] =
    # …`), plus de double écriture (N1).
    was_exclude = action == "exclude"
    if was_exclude:
        _exclude_add(ep, old)
        action = "delete"

    # Renommage : valide `new` comme pour 'add' (symétrie). Delete/exclude ont
    # un `new` vide légitime → validation uniquement hors delete.
    if action != "delete":
        if not new or is_placeholder(new):
            return "Nom vide ou non valide.", "warning"
        if any(h.casefold() == new.casefold() for h in hosts):
            return (
                f"« {new} » est un hôte du podcast, pas un invité.",
                "warning",
            )

    replacement = "" if action == "delete" else new
    # Réhabilitation : renommer/éditer vers un nom exclu le retire de
    # guestsExcluded (sinon il redisparaîtrait au prochain render).
    if replacement:
        _exclude_remove(ep, replacement)
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
    # `old` issu de guestsParsed (pas de ep.guests) : masque/insère au besoin.
    _reconcile_parsed_rename(ep, old, replacement, new_guests)
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
    else:
        flash = f"Invité {verb} de l'épisode."
    # N3 : le ✕ persiste le retrait → on le dit explicitement dans le flash.
    if was_exclude:
        flash += " Il ne sera plus proposé."
    return flash, "success"


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
