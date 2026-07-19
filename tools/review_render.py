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

from common import (
    list_episode_files,
    load_source,
    read_json,
    recos_dir_for,
)
from review_edit import is_reenrichable, render_edit_form, render_type_badges
from review_guests import (
    collect_guests as _collect_guests,
    is_placeholder as _is_placeholder,
    render_guests_panel as _render_guests_panel,
    split_names as _split_names,
)

# #11/#12 review — `_other_episode_recos_for_cluster` était importé dans
# `_render_with_clusters` au runtime (hot path) ; on remonte l'import.
from review_render_cluster import (
    _dedup_cluster_card,
    _other_episode_recos_for_cluster,
    render_merge_preview,
    render_pick_canonical,
)

# #H — `_style` / `_shell` viennent de review_render_common (une seule source
# de vérité). Les tests qui patchaient `review_render._CSS_PATH` doivent
# patcher `review_render_common._CSS_PATH` (cf. note dans test_review_server).
from review_render_common import (
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
)

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

    L3 — `parsed` peut être fourni par l'appelant (`_render_episode` le calcule
    UNE fois et le propage à toutes les cartes) pour éviter de reparser le
    titre par carte. `None` = calcul à la volée (compat des appelants isolés :
    /card, /doutes, JSON post).
    """
    # Fallback : si pas de snapshot persisté, on parse à la volée pour ne
    # rien casser sur les épisodes legacy.
    if parsed is None:
        parsed = (ep.get("guestsParsed")
                  or _parse_guests(ep.get("title", ""), hosts))
    # Inclut la reco courante + ses siblings pour conserver le même périmètre
    # qu'avant le refactor. N1 — `siblings` contient DÉJÀ `r` chez tous les
    # appelants (liste complète des recos de l'épisode) : on filtre `r` par id
    # pour ne pas le compter deux fois. (collect_guests dédupe les noms, donc
    # c'était sans conséquence fonctionnelle, mais inutilement redondant.)
    rid = r.get("id")
    all_recs: list[dict] = [r]
    for s in (siblings or []):
        if rid and s.get("id") == rid:
            continue
        all_recs.append(s)
    guests = _collect_guests(ep, all_recs, hosts, parsed=parsed)
    # Hosts d'abord (ordre stable, attendu par les UX existantes), puis
    # invités collectés dédupés contre les hosts (déjà fait par collect_guests).
    return list(hosts) + guests


def _reco_checkboxes(candidates: list[str], current: str) -> str:
    """Cases à cocher des recommendedBy pour une reco.

    M1 — appartenance EXACTE (via `_split_names`) et non par sous-chaîne :
    sinon « Navo » serait coché parce que `recommendedBy` contient « Navon ».
    On matérialise le split une seule fois (hors boucle).
    """
    current_names = _split_names(current)
    return "".join(
        f'<label><input type="checkbox" name="who" value="{html.escape(c)}"'
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
        edit_href = f"/doutes?edit={edit_id_q}"
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
        f'title="Supprimer définitivement (irréversible)">🗑</button>'
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
    """En-tête d'une carte reco : checkbox merge + types + title + actions."""
    status = r.get("status", "draft")
    reco_id_for_select = html.escape(r.get("id", ""))
    # `episodeGuid` propagé dans r pour le bouton edit (peut être absent).
    r_with_guid = r if r.get("episodeGuid") else {**r, "episodeGuid": ep.get("guid", "")}
    actions = _reco_action_buttons(r_with_guid, edit_origin)
    conf_badge = _extractors_badge(r.get("extractors") or [])
    creator_html = (f"<i>· {html.escape(r['creator'])}</i>"
                    if r.get("creator") else "")
    return (
        f'<div class="hd"><label class="merge-select" title="Sélectionner pour fusion manuelle">'
        f'<input type="checkbox" data-merge-select value="{reco_id_for_select}"></label>'
        f'<span class="type">{render_type_badges(r.get("types", []))}</span>'
        f'<b>{html.escape(r.get("title", ""))}</b>'
        f'{creator_html}'
        f'{link}'
        f'{conf_badge}'
        f'{_reco_agent_badge(r)}'
        f'<span class="st">{html.escape(status)}</span>'
        f'{actions}</div>'
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
    tcl = _yt_timecode_link_parts(r, ep)  # #4 : un seul calcul de secs
    header = _reco_header(r, ep, tcl.html, edit_origin)
    ctx_html = _reco_context_block(r, ep, source_id, tcl.secs)
    quote_html = _reco_quote_block(r)
    boxes = _reco_checkboxes(
        _reco_candidates(r, ep, hosts, siblings, parsed=parsed),
        r.get("recommendedBy", ""),
    )
    cls = _reco_row_class(r)
    reco_id_for_select = html.escape(r.get("id", ""))
    return f"""
    <li class="row {cls}" data-reco-id="{reco_id_for_select}">
      {header}
      {ctx_html}
      {quote_html}
      <form method="post" action="/save">
        <input type="hidden" name="id" value="{html.escape(r.get('id',''))}">
        <div class="who">{boxes}
          <input type="text" name="other" placeholder="autre nom…" value="">
          <button type="submit" name="action" value="validate">Valider</button>
          <button type="submit" name="action" value="citation" class="citation-btn" title="Œuvre évoquée mais pas recommandée">📝 Citation</button>
          <button type="submit" name="action" value="guest-work" class="guestwork-btn" title="Auto-promo d'un·e invité·e ou d'un host : reste comptée comme reco, mais présentée à part sur la page épisode">⭐ Leur œuvre</button>
          <button type="submit" name="action" value="discard" class="discard">Pas une reco</button>
        </div>
      </form>
    </li>"""


# ---- Cache _load_groups (#mtime-reload) ------------------------------------
# Le serveur tourne en single-threaded mais peut servir BEAUCOUP de pages
# successives sur les mêmes données. Sans cache, chaque page relit ~80
# épisodes + ~1000 recos depuis le disque (= O(N) syscalls). Avec un cache
# indexé sur (max(mtime_ns), files_signature), on évite tout ré-lit tant
# que le pipeline n'a rien modifié.
#
# Signature = max des `st_mtime_ns` + nombre de fichiers, sur les dossiers
# recos/<src>/ ET episodes/<src>/. Coût : 2*N stats (rapide) au lieu de
# 2*N read+parse JSON.
#
# Bonus : si la signature recos a changé, on invalide aussi
# `_RECO_PATH_CACHE[source_id]` côté review_handler_base — sinon un
# fichier nouvellement créé par le pipeline ne serait pas trouvé.
_GROUPS_CACHE: dict[str, tuple[tuple, tuple]] = {}


def _dir_signature(directory) -> tuple[int, int]:
    """(max_mtime_ns, count) sur les .json d'un dossier — None-safe.

    Renvoie (0, 0) si le dossier n'existe pas. Très peu coûteux : un seul
    listdir + N stats (pas de lecture du contenu).
    """
    if not directory.exists():
        return (0, 0)
    max_mtime = 0
    count = 0
    for p in directory.glob("*.json"):
        try:
            st = p.stat()
        except OSError:
            continue
        if st.st_mtime_ns > max_mtime:
            max_mtime = st.st_mtime_ns
        count += 1
    return (max_mtime, count)


def _load_groups(source_id: str):
    """Renvoie (source, episodes_par_guid, recos_par_guid triés).

    Cache mtime-based : si ni le dossier recos/<src>/ ni episodes/<src>/
    n'ont changé depuis le dernier appel, on retourne le résultat caché.
    Sinon on re-scanne et on invalide aussi `_RECO_PATH_CACHE` côté
    handler_base (un fichier reco créé en arrière-plan par le pipeline
    pourrait sinon rester invisible).
    """
    from common import episodes_dir_for  # noqa: PLC0415 — éviter cycles
    from review_handler_base import _invalidate_reco_path_cache  # noqa: PLC0415

    recos_dir = recos_dir_for(source_id)
    episodes_dir = episodes_dir_for(source_id)
    sig = (_dir_signature(recos_dir), _dir_signature(episodes_dir))

    cached = _GROUPS_CACHE.get(source_id)
    if cached is not None and cached[0] == sig:
        return cached[1]

    # Cache miss ou stale → re-scan complet + invalidation cache reco_path
    # (un nouveau fichier reco créé par extract_recos n'apparaît dans
    # `_RECO_PATH_CACHE` qu'après rebuild).
    _invalidate_reco_path_cache(source_id)

    source = load_source(source_id)
    episodes: dict[str, dict] = {}
    for p in list_episode_files(source_id):
        ep = read_json(p)
        episodes[ep["guid"]] = ep
    recos = [read_json(p) for p in sorted(recos_dir.glob("*.json"))]
    groups: dict[str, list[dict]] = {}
    for r in recos:
        groups.setdefault(r.get("episodeGuid", ""), []).append(r)
    for g in groups.values():
        # Tiebreaker : à timestamp identique, plus d'extractors d'abord
        # (confiance plus haute → généralement le canonique d'un cluster).
        g.sort(key=lambda r: (*_order_key(r),
                              -len(r.get("extractors") or [])))
    result = (source, episodes, groups)
    _GROUPS_CACHE[source_id] = (sig, result)
    return result


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
        import review_render_page as _page  # noqa: PLC0415 — lazy, anti-cycle
        return getattr(_page, name)
    raise AttributeError(f"module 'review_render' has no attribute {name!r}")
