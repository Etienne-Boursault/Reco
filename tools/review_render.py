"""review_render.py — Présentation HTML (cartes, index, épisode, shell).

Extrait de review_server.py pour isoler le rendu HTML de la couche transport
HTTP. Les fonctions sont pures : elles consomment des dicts en entrée et
retournent des chaînes HTML. Le serveur reste responsable du routage et des
mutations.

Helpers communs partagés via `review_render_common.py` (anti-cycle).
"""
from __future__ import annotations

import html
import urllib.parse
from pathlib import Path

from common import (
    list_episode_files,
    load_source,
    read_json,
    recos_dir_for,
)
from creator_flags import flag_badge_html
from review_edit import is_reenrichable, render_edit_form, render_type_badges

# Ré-exports pour la rétro-compat des tests : le `noqa` est posé LIGNE PAR
# LIGNE, pas sur le bloc — isort regroupe/sépare ces imports, et un `noqa` de
# bloc se retrouve alors orphelin, laissant `ruff --fix` supprimer les noms
# (constaté le 2026-07-29 : import de `review_server` cassé).
from review_guests import collect_guests as _collect_guests
from review_guests import is_placeholder as _is_placeholder
from review_guests import render_guests_panel as _render_guests_panel  # noqa: F401
from review_guests import split_names as _split_names
from review_render_carte import (
    _reco_agent_badge,
    _status_label,
    render_liens,
)

# #11/#12 review — `_other_episode_recos_for_cluster` était importé dans
# `_render_with_clusters` au runtime (hot path) ; on remonte l'import.
from review_render_cluster import (  # noqa: F401 — ré-exports (cf. ci-dessous)
    _dedup_cluster_card,
    _other_episode_recos_for_cluster,
    render_merge_preview,
    render_pick_canonical,
)

# #H — `_style` / `_shell` viennent de review_render_common (une seule source
# de vérité). Les tests qui patchaient `review_render._CSS_PATH` doivent
# patcher `review_render_common._CSS_PATH` (cf. note dans test_review_server).
#
# Les noms non utilisés ICI sont des RÉ-EXPORTS : `review_server` les réimporte
# depuis ce module (`from review_render import _CLIENT_JS, ...`) pour la
# rétro-compat des tests. Sans le `noqa`, `ruff --fix` les supprime et casse
# l'import de `review_server` — c'est arrivé le 2026-07-29.
from review_render_common import (  # noqa: F401 — ré-exports rétro-compat
    _CLIENT_JS,
    _CSS_PATH,
    _STOP,
    _context_around,
    _embed_url,
    _extractors_badge,
    _flash_banner,
    _fmt,
    _load_transcript,
    _parse_guests,
    _safe_url,
    _shell,
    _strip_french_quotes,
    _style,
    _ts_seconds,
    _yt_id,
    _yt_timecode_link,
    _yt_timecode_link_parts,
    _yt_watch_link,
)
from review_signals import reco_signals, render_signals

# Tri chronologique des cartes (ordre d'apparition dans l'épisode) — facilite
# la détection visuelle de doublons à fusionner. Les discarded sont relégués
# en fin de liste (déjà visuellement atténués par CSS, peu utiles dans le
# scan chronologique). Sentinel `MAX` pour les recos sans timestamp valide.
_NO_TS = 10**9


def _order_key(r: dict) -> tuple[int, int]:
    """Clé de tri : (discarded_bucket, timestamp_secondes).

    - discarded_bucket : 0 pour actifs (draft/validated/citation), 1 pour
      discarded → tous les discarded en fin de liste.
    - timestamp_secondes : ordre chronologique (croissant) ; les recos sans
      timestamp parsable tombent à la fin de leur bucket via `_NO_TS`.
    """
    is_discarded = 1 if r.get("status") == "discarded" else 0
    secs = _ts_seconds(r.get("timestamp"))
    return (is_discarded, secs if secs is not None else _NO_TS)


# ---- Helpers privés à _reco_card (issue #16 décomposition) ------------------
def _reco_candidates(r: dict, ep: dict, hosts: list[str],
                     siblings: list[dict] | None,
                     parsed: list[str] | None = None) -> list[str]:
    """Liste des noms cochables : hosts + invités collectés (source unique).

    Source unique de vérité : `collect_guests` — qui prend en compte
    `ep.guests`, `ep.guestsParsed` (snapshot), `ep.guestsExcluded` (autorité)
    et les `recommendedBy` des recos. On y ajoute un fallback `parsed`
    (parsing du titre à la volée) pour les épisodes pas encore migrés.

    L3 — `parsed` peut venir de l'appelant (`_render_episode` le calcule UNE
    fois) ; `None` = calcul à la volée (/card, /doutes, JSON post).
    """
    # Fallback : si pas de snapshot persisté, on parse à la volée pour ne
    # rien casser sur les épisodes legacy.
    if parsed is None:
        parsed = (ep.get("guestsParsed")
                  or _parse_guests(ep.get("title", ""), hosts))
    # Inclut la reco courante + ses siblings. N1 — `siblings` contient DÉJÀ
    # `r` chez tous les appelants : on filtre `r` par id (pas de doublon).
    rid = r.get("id")
    all_recs = [r] + [s for s in (siblings or []) if not (rid and s.get("id") == rid)]
    guests = _collect_guests(ep, all_recs, hosts, parsed=parsed)
    # Hosts d'abord (ordre stable attendu par l'UX), puis invités collectés.
    candidates = list(hosts) + guests
    # INVARIANT : chaque nom du `recommendedBy` de CETTE reco garde sa case
    # cochée, même un prénom seul écarté par collect_guests (« Jenny » / Jenny
    # Letellier) : « Valider » reconstruit recommendedBy depuis les cases (sinon
    # le nom serait perdu en silence) et « Corriger en … » la décoche.
    # Seuls les placeholders et les exclus restent écartés (nettoyage voulu).
    excluded = {n.casefold() for n in (ep.get("guestsExcluded") or [])}
    for n in _split_names(r.get("recommendedBy", "")):
        if (n not in candidates and not _is_placeholder(n)
                and n.casefold() not in excluded):
            candidates.append(n)
    return candidates


def _reco_checkboxes(candidates: list[str], current: str) -> str:
    """Cases à cocher des recommendedBy pour une reco.

    M1 — appartenance EXACTE (via `_split_names`) et non par sous-chaîne :
    sinon « Navo » serait coché parce que `recommendedBy` contient « Navon ».
    On matérialise le split une seule fois (hors boucle).
    """
    current_names = _split_names(current)
    return "".join(
        f'<label class="who-name"><input type="checkbox" name="who" value="{html.escape(c)}"'
        f'{" checked" if c in current_names else ""}> {html.escape(c)}</label>'
        for c in candidates
    )


def _reco_action_buttons(r: dict, edit_origin: str = "/ep") -> str:
    """Boutons Éditer / Ré-enrichir / Supprimer d'une reco.

    `edit_origin` : page où doit se dérouler l'édition. "/ep" (défaut) ouvre le
    formulaire sur la page épisode ; "/doutes" le rend inline dans la file des
    doutes — ainsi #M3 (Referer == /doutes) ramène à /doutes après le save au
    lieu d'éjecter vers /ep.
    """
    reco_id_esc = html.escape(r.get("id", ""))
    guid_q = urllib.parse.quote(r.get("episodeGuid", ""))
    edit_id_q = urllib.parse.quote(r.get("id", ""))
    if edit_origin == "/doutes":
        # Refonte perf 2026-07-21 : l'édition se fait dans la vue épisode
        # (/doutes?ep=<guid>) — sans le guid on retomberait sur l'index léger,
        # qui ignore `edit`.
        edit_href = f"/doutes?ep={guid_q}&edit={edit_id_q}"
    else:
        edit_href = f"/ep?guid={guid_q}&edit={edit_id_q}"
    edit_btn = f'<a class="btn-edit" href="{edit_href}">✎ Éditer</a>'
    reenrich_btn = (
        f'<form method="post" action="/reenrich" class="reenrich-form">'
        f'<input type="hidden" name="id" value="{reco_id_esc}">'
        f'<button type="submit" class="btn-reenrich">🔄 Ré-enrichir</button>'
        f'</form>'
    ) if is_reenrichable(r) else ""
    delete_btn = (
        f'<form method="post" action="/delete-reco" class="delete-form">'
        f'<input type="hidden" name="id" value="{reco_id_esc}">'
        f'<button type="submit" class="btn-delete" '
        f'onclick="return confirm(\'Supprimer définitivement cette reco ?\')" '
        f'title="Supprimer définitivement (irréversible)">🗑 Supprimer</button>'
        f'</form>'
    )
    return edit_btn + reenrich_btn + delete_btn


def _reco_quote_block(r: dict) -> str:
    """Bloc HTML de la quote (strippée des guillemets français — #12)."""
    quote_raw = r.get("quote")
    if not quote_raw:
        return ""
    cleaned = _strip_french_quotes(quote_raw)
    return f'<p class="q">« {html.escape(cleaned)} »</p>'


def _reco_context_block(r: dict, ep: dict, source_id: str,
                        secs: int | None) -> str:
    """Snippet de transcript autour du timecode de la reco (ou ""))."""
    if secs is None:
        return ""
    ctx = _context_around(_load_transcript(source_id, ep.get("guid", "")), secs)
    if not ctx:
        return ""
    spans = [
        f'<span class="{"ctx-here" if abs(sec - secs) < 3 else "ctx"}">'
        f'{html.escape(txt)}</span>' for sec, txt in ctx
    ]
    return f'<div class="context">{" ".join(spans)}</div>'




def _reco_header(r: dict, ep: dict, link: str, edit_origin: str = "/ep") -> str:
    """En-tête d'une carte reco : types, titre, créateur, écoute, menu ⋯.

    Les actions rares (fusion, édition, ré-enrichissement, suppression)
    vivent dans le menu ⋯ : la carte ne montre d'emblée que ce qui sert à
    décider.
    """
    reco_id_for_select = html.escape(r.get("id", ""))
    # `episodeGuid` propagé dans r pour le bouton edit (peut être absent).
    r_with_guid = r if r.get("episodeGuid") else {**r, "episodeGuid": ep.get("guid", "")}
    actions = _reco_action_buttons(r_with_guid, edit_origin)
    conf_badge = _extractors_badge(r.get("extractors") or [])
    creator_html = (f"<i>· {html.escape(r['creator'])}</i>"
                    f"{flag_badge_html(r.get('creator'))}"
                    if r.get("creator") else "")
    return (
        f'<div class="hd">'
        f'<span class="type">{render_type_badges(r.get("types", []))}</span>'
        f'<b>{html.escape(r.get("title", ""))}</b>'
        f'{creator_html}'
        f'<span class="hd-meta">{link}{conf_badge}{_reco_agent_badge(r)}</span>'
        f'<span class="st">{html.escape(_status_label(r))}</span>'
        f'<details class="more"><summary title="Plus d’actions" '
        f'aria-label="Plus d’actions">⋯</summary><div class="more-panel">'
        f'<label class="merge-select" title="Sélectionner pour fusion manuelle">'
        f'<input type="checkbox" data-merge-select value="{reco_id_for_select}">'
        f' Sélectionner pour fusion</label>'
        f'{actions}</div></details></div>'
    )


def _reco_row_class(r: dict) -> str:
    """Classe CSS de la <li> (validated/discarded + citation/guestwork)."""
    cls = {"validated": "done", "discarded": "discarded"}.get(
        r.get("status", "draft"), "",
    )
    if r.get("kind") == "citation":
        cls = (cls + " citation").strip()
    # Marqueur « œuvre d'invité » — orthogonal à citation (mutuellement
    # exclusifs en pratique : guest-work force kind=reco).
    if r.get("guestWork"):
        cls = (cls + " guestwork").strip()
    return cls




def _reco_card(r: dict, ep: dict, hosts: list, source_id: str,
               edit_id: str | None = None,
               siblings: list[dict] | None = None,
               parsed: list[str] | None = None,
               edit_origin: str = "/ep") -> str:
    """Carte d'une reco : assembleur pur des helpers _reco_* (#16).

    L3 — `parsed` (invités parsés du titre) est optionnel : quand
    `_render_episode` le calcule une fois, il le propage ici pour éviter que
    chaque carte reparse le titre. `None` → calcul à la volée dans
    `_reco_candidates`.
    """
    if edit_id and r.get("id") == edit_id:
        return render_edit_form(r, ep, siblings, hosts, edit_origin)
    if parsed is None:
        parsed = (ep.get("guestsParsed")
                  or _parse_guests(ep.get("title", ""), hosts))
    tcl = _yt_timecode_link_parts(r, ep)  # #4 : un seul calcul de secs
    header = _reco_header(r, ep, tcl.html, edit_origin)
    signals = reco_signals(r, ep, hosts, parsed)
    ctx_html = _reco_context_block(r, ep, source_id, tcl.secs)
    quote_html = _reco_quote_block(r)
    boxes = _reco_checkboxes(
        _reco_candidates(r, ep, hosts, siblings, parsed=parsed),
        r.get("recommendedBy", ""),
    )
    cls = _reco_row_class(r)
    reco_id_for_select = html.escape(r.get("id", ""))
    # Ordre de lecture : quoi (en-tête) → ce qui cloche → ce qui a été dit →
    # qui le dit → la décision. Le texte des boutons de décision porte leur
    # raccourci clavier, la seule aide qu'il faut avoir sous les yeux.
    return f"""
    <li class="row {cls}" data-reco-id="{reco_id_for_select}" data-signals="{len(signals)}">
      {header}
      {render_signals(signals)}
      {quote_html}
      {ctx_html}
      {render_liens(r)}
      <form method="post" action="/save">
        <input type="hidden" name="id" value="{html.escape(r.get('id',''))}">
        <div class="who"><span class="who-label">Qui recommande ?</span>{boxes}
          <input type="text" name="other" placeholder="autre nom…" value="" aria-label="Autre nom">
        </div>
        <div class="decide">
          <button type="submit" name="action" value="validate" class="ok">Valider <kbd>V</kbd></button>
          <button type="submit" name="action" value="citation" class="citation-btn" title="Citation : œuvre évoquée mais pas recommandée">Seulement évoquée <kbd>C</kbd></button>
          <button type="submit" name="action" value="discard" class="discard">Pas une reco <kbd>D</kbd></button>
          <button type="submit" name="action" value="guest-work" class="guestwork-btn" title="Auto-promo d'un·e invité·e ou d'un host : reste comptée comme reco, mais présentée à part sur la page épisode">⭐ Leur œuvre</button>
        </div>
      </form>
    </li>"""


# ---- Cache _load_groups (#mtime-reload) ------------------------------------
# Sans cache, chaque page relirait ~80 épisodes + ~3000 recos. Signature =
# (max `st_mtime_ns`, nombre de fichiers) des dossiers recos/<src>/ ET
# episodes/<src>/ : 2*N stats au lieu de 2*N read+parse JSON.
#
# Entrée : (signature, (source, episodes, groups), fichiers) où `fichiers`
# = {nom → (mtime_ns, reco)} — c'est ce qui permet à `refresh_reco_in_cache`
# de remplacer UNE reco écrite par le serveur sans tout relire.
_GROUPS_CACHE: dict[str, tuple[tuple, tuple, dict]] = {}


def _dir_mtimes(directory) -> dict[str, int]:
    """{nom → st_mtime_ns} des .json d'un dossier ({} s'il n'existe pas)."""
    if not directory.exists():
        return {}
    mtimes: dict[str, int] = {}
    for p in directory.glob("*.json"):
        try:
            mtimes[p.name] = p.stat().st_mtime_ns
        except OSError:
            continue
    return mtimes


def _mtimes_signature(mtimes: dict[str, int]) -> tuple[int, int]:
    return (max(mtimes.values(), default=0), len(mtimes))


def _dir_signature(directory) -> tuple[int, int]:
    """(max_mtime_ns, count) sur les .json d'un dossier — (0, 0) s'il manque."""
    return _mtimes_signature(_dir_mtimes(directory))


def _group_key(r: dict) -> tuple:
    # À timestamp égal, plus d'extractors d'abord (canonique d'un cluster).
    return (*_order_key(r), -len(r.get("extractors") or []))


def _load_groups(source_id: str):
    """Renvoie (source, episodes_par_guid, recos_par_guid triés).

    Cache mtime-based (cf. ci-dessus). Un re-scan reconstruit aussi
    `_RECO_PATH_CACHE` (handler_base) depuis les recos lues : une reco créée
    par le pipeline y devient trouvable sans relire les ~3000 fichiers.
    """
    from common import episodes_dir_for
    from review_handler_base import _RECO_PATH_CACHE, _invalidate_reco_path_cache

    recos_dir = recos_dir_for(source_id)
    mtimes = _dir_mtimes(recos_dir)
    sig = (_mtimes_signature(mtimes),
           _dir_signature(episodes_dir_for(source_id)))

    cached = _GROUPS_CACHE.get(source_id)
    if cached is not None and cached[0] == sig:
        return cached[1]

    # Cache miss ou stale → re-scan complet.
    _invalidate_reco_path_cache(source_id)

    source = load_source(source_id)
    episodes = {ep["guid"]: ep for ep in map(read_json, list_episode_files(source_id))}
    # mtime 0 pour un fichier apparu après le stat : la signature suivante
    # différera de toute façon → nouveau re-scan, jamais d'état faux.
    files = {p.name: (mtimes.get(p.name, 0), read_json(p))
             for p in sorted(recos_dir.glob("*.json"))}
    groups: dict[str, list[dict]] = {}
    for _mtime, r in files.values():
        groups.setdefault(r.get("episodeGuid", ""), []).append(r)
    for g in groups.values():
        g.sort(key=_group_key)
    result = (source, episodes, groups)
    _GROUPS_CACHE[source_id] = (sig, result, files)
    _RECO_PATH_CACHE[source_id] = {r["id"]: recos_dir / name
                                   for name, (_m, r) in files.items()
                                   if r.get("id")}
    return result


def refresh_reco_in_cache(source_id: str, path) -> bool:
    """Met à jour le cache pour la SEULE reco `path` que le serveur vient
    d'écrire, de créer ou de supprimer, au lieu de tout relire (~0,4 s).

    Recompose son ou ses groupes (ancien et nouvel `episodeGuid`) dans
    l'ordre d'un re-scan et enregistre la nouvelle signature. Au moindre
    doute (pas de cache, chemin hors du dossier, fichier illisible, AUTRE
    reco ou épisode changé entre-temps) : invalidation complète, jamais
    d'état faux. Renvoie True si la mise à jour s'est faite en place.
    """
    from common import episodes_dir_for
    from review_handler_base import _RECO_PATH_CACHE, _invalidate_reco_path_cache

    path = Path(path)
    recos_dir = recos_dir_for(source_id)
    cached = _GROUPS_CACHE.get(source_id)
    if cached is None or path.parent != recos_dir:
        _invalidate_reco_path_cache(source_id)
        return False
    (_rsig, ep_sig), (source, episodes, groups), files = cached
    name = path.name
    mtimes = _dir_mtimes(recos_dir)
    others_now = {n: m for n, m in mtimes.items() if n != name}
    others_cached = {n: fm[0] for n, fm in files.items() if n != name}
    try:
        stale = (others_now != others_cached
                 or _dir_signature(episodes_dir_for(source_id)) != ep_sig)
        new = read_json(path) if name in mtimes and not stale else None
    except (OSError, ValueError):
        stale = True
    if stale:
        _invalidate_reco_path_cache(source_id)
        return False
    old = files.pop(name, (0, None))[1]
    if new is not None:
        files[name] = (mtimes[name], new)
    for guid in {r.get("episodeGuid", "") for r in (old, new) if r is not None}:
        # Ordre des fichiers puis tri stable : identique à un re-scan.
        members = sorted((r for n, (_m, r) in sorted(files.items())
                          if r.get("episodeGuid", "") == guid), key=_group_key)
        if members:
            groups[guid] = members
        else:
            groups.pop(guid, None)
    bucket = _RECO_PATH_CACHE.get(source_id)
    if bucket is not None:
        if old is not None and bucket.get(old.get("id")) == path:
            del bucket[old["id"]]
        if new is not None and new.get("id"):
            bucket[new["id"]] = path
    _GROUPS_CACHE[source_id] = ((_mtimes_signature(mtimes), ep_sig),
                                (source, episodes, groups), files)
    return True


def _clear_groups_cache() -> None:
    """Reset hard du cache (utile aux tests + au démarrage du serveur)."""
    _GROUPS_CACHE.clear()


# ---- API publique (#15) — alias sans underscore pour consommateurs externes
render_card_fragment = _reco_card

# ---- Rétro-compat pages (M4 découpe) ----------------------------------------
# Les PAGES (_render_episode, _render_index, _ep_header, …) vivent désormais
# dans `review_render_page.py`. Réexport LAZY (PEP 562) : un import direct
# (`from review_render import _render_episode`) et l'accès attribut
# (`review_render._ep_header`) continuent de fonctionner sans créer de cycle
# à l'import (review_render_page importe ce module ; l'inverse n'est résolu
# qu'au premier accès).
_PAGE_EXPORTS = frozenset({
    "_ep_nav_link", "_ep_header",
    "_render_index", "_render_with_clusters",
    "_has_undoable_merge", "_has_undoable_merge_cached",
    "_PLAYER_WRAP_HTML", "_render_merge_bar", "_render_episode",
    "render_episode", "render_index",
})


def __getattr__(name: str):
    if name in _PAGE_EXPORTS:
        import review_render_page as _page
        return getattr(_page, name)
    raise AttributeError(f"module 'review_render' has no attribute {name!r}")
