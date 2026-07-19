"""review_render_page.py — Pages HTML du review_server (index, épisode).

Extrait de review_render.py (M4 CR cumulative — limite 500 lignes) :
review_render garde les CARTES (`_reco_card` et ses helpers) + le cache
`_load_groups` ; ce module assemble les PAGES complètes qui les consomment.

Convention d'accès : les helpers partagés sont résolus VIA le module
`review_render` (`_rr.xxx`) et non importés par nom — les tests monkeypatchent
`review_render._parse_guests`, `review_render._load_groups`, etc., et doivent
continuer d'atteindre le code des pages. `review_render` réexporte les noms de
ce module en lazy (PEP 562) pour la rétro-compat des consommateurs existants.
"""
from __future__ import annotations

import functools
import html
import urllib.parse

import review_render as _rr

__all__ = [
    "render_episode",
    "render_index",
]


def _ep_nav_link(side: str, guid: str | None) -> str:
    """Flèche prev/next ou placeholder désactivé (pour garder l'alignement)."""
    arrow = "←" if side == "prev" else "→"
    label = "Épisode précédent" if side == "prev" else "Épisode suivant"
    cls = f"eph-arrow eph-arrow-{side}"
    if guid:
        href = f"/ep?guid={urllib.parse.quote(guid)}"
        return (f'<a class="{cls}" href="{href}" title="{label}" '
                f'aria-label="{label}">{arrow}</a>')
    return f'<span class="{cls} disabled" aria-hidden="true">{arrow}</span>'


def _ep_header(
    ep: dict, recs: list[dict],
    *, prev_guid: str | None = None, next_guid: str | None = None,
) -> str:
    """En-tête d'épisode : numéro, titre, durées, compteur, navigation."""
    season, num = ep.get("season"), ep.get("number")
    ep_num = f"S{season}·E{num}" if season and num else (f"#{num}" if num else "")
    badge = f'<b class="epnum">{ep_num}</b> ' if ep_num else ""
    # Story 3 — le titre RSS (français) prime : la chaîne YouTube publie
    # parfois sous des titres de format anglais (« A Good Time with… »,
    # cf. épisodes 40/48/50/S5E25). Le youtubeTitle reste consultable en
    # tooltip quand il diffère (utile pour vérifier le match YT).
    rss_title = ep.get("title") or ""
    yt_title = ep.get("youtubeTitle") or ""
    title = html.escape(rss_title or yt_title or "?")
    tooltip = (f' title="YouTube : {html.escape(yt_title)}"'
               if rss_title and yt_title and yt_title != rss_title else "")
    yt = _rr._safe_url(ep.get("youtubeUrl"))  # #5 : XSS guard sur href.
    # L1 CR — le tooltip survit même sans lien YouTube (rendu via <span>).
    if yt:
        title_html = (f'<a href="{html.escape(yt)}" target="_blank"{tooltip}>'
                      f'{title}</a>')
    elif tooltip:
        title_html = f'<span{tooltip}>{title}</span>'
    else:
        title_html = title
    # #23 + #39 : `youtubeDuration` peut être string → cast via _safe_int.
    # 0 (sentinel default) traité comme None : "?" affiché plutôt qu'un 0:00:00
    # trompeur quand le champ est absent.
    from review_render_common import _safe_int  # noqa: PLC0415
    ad_i: int | None = _safe_int(ep.get("audioDuration"), 0) or None
    vd_i: int | None = _safe_int(ep.get("youtubeDuration"), 0) or None
    dur = ""
    if ad_i or vd_i:
        diff = f" Δ{vd_i - ad_i:+d}s" if (ad_i and vd_i) else ""
        warn = ' style="color:#e08a8a"' if (ad_i and vd_i and abs(vd_i - ad_i) > 300) else ""
        dur = (f'<span class="dur"{warn}>🎧 {_rr._fmt(ad_i) if ad_i else "?"} · '
               f'▶ {_rr._fmt(vd_i) if vd_i else "?"}{diff}</span>')
    n_draft = sum(1 for r in recs if r.get("status", "draft") == "draft")
    tm = ep.get("transcriptModel") or ""
    tm_html = (f' <span class="tmodel" title="Modèle Whisper utilisé">📝 {html.escape(tm)}</span>'
               if tm else "")
    prev_a = _ep_nav_link("prev", prev_guid)
    next_a = _ep_nav_link("next", next_guid)
    return (f'<div class="eph-row">{prev_a}'
            f'<h2 class="eph">{badge}{title_html} '
            f'<span class="cnt">{len(recs)} recos · {n_draft} à valider</span> '
            f'{dur}{tm_html}</h2>'
            f'{next_a}</div>')


def _render_index(source_id: str) -> str:
    """Page d'accueil : galerie de miniatures, tous les épisodes."""
    source, episodes, groups = _rr._load_groups(source_id)

    def _key(guid: str):
        ep = episodes.get(guid, {})
        return (ep.get("season") or 0, ep.get("number") or 9999)

    thumbs = []
    todo = 0
    for guid in sorted(episodes.keys(), key=_key):
        ep = episodes.get(guid, {})
        recs = groups.get(guid, [])
        n_draft = sum(1 for r in recs if r.get("status", "draft") == "draft")
        todo += n_draft
        season, num = ep.get("season"), ep.get("number")
        ep_num = f"S{season}·E{num}" if season and num else (f"#{num}" if num else "?")
        vid = _rr._yt_id(ep.get("youtubeUrl", ""))
        style = f'style="background-image:url(https://i.ytimg.com/vi/{vid}/mqdefault.jpg)"' if vid else ""
        cls = "thumb"
        if not recs:
            cls += " empty"
        elif n_draft == 0:
            cls += " done"
        href = f"/ep?guid={urllib.parse.quote(guid)}"
        count_label = f"{n_draft} à valider" if recs else "0 reco"
        thumbs.append(
            f'<a class="{cls}" href="{href}" {style}>'
            f'<span class="tbadge">{ep_num}</span>'
            f'<span class="tcount">{count_label}</span></a>'
        )

    inner = (f'<div class="gallery">{"".join(thumbs)}</div>' if thumbs
             else "<p>Aucune reco — lance l’extraction d’abord.</p>")
    n_with = sum(1 for g in episodes if g in groups)
    # Lien vers la file des doutes agent (si non vide). Import différé :
    # review_doubts importe review_render (anti-cycle).
    # L2 — `count_doubts` refait un `_load_groups` : c'est un 2ᵉ *scan mémoire*
    # (pas d'I/O — le cache mtime `_GROUPS_CACHE` sert la même structure déjà
    # chargée ci-dessus). Fusionner le comptage dans la boucle des miniatures
    # coûterait un couplage avec la logique de sectionnement de review_doubts
    # (importée en différé pour l'anti-cycle) : non rentable ici.
    from review_doubts import count_doubts  # noqa: PLC0415
    n_doubts = count_doubts(source_id)
    doubts_link = (f' · <a class="doubts-link" href="/doutes">🤖 Doutes '
                   f'agent : <b>{n_doubts}</b></a>' if n_doubts else "")
    subtitle = (f"<b>{todo}</b> recos à valider · {len(episodes)} épisodes ({n_with} avec recos). "
                f"Clique une miniature.{doubts_link}")
    return _rr._shell(source.get("title", source_id), subtitle, inner)


def _render_with_clusters(
    recs: list[dict], ep: dict, hosts: list[str], source_id: str,
    edit_id: str | None, parsed: list[str] | None = None,
) -> str:
    """Rendu de la liste des recos, en regroupant les doublons en clusters.

    L3 — `parsed` (invités parsés du titre, calculé une fois par
    `_render_episode`) est propagé à chaque `_reco_card`.
    """
    from reco_dedup import cluster_recos  # noqa: PLC0415
    if edit_id:
        return "".join(
            _rr._reco_card(r, ep, hosts, source_id, edit_id, siblings=recs,
                           parsed=parsed)
            for r in recs
        )
    clusters = cluster_recos(recs)
    clustered_ids: set[str] = set()
    cluster_by_first_id: dict[str, object] = {}
    for c in clusters:
        ids = [m.get("id", "") for m in c.members]
        for i in ids:
            clustered_ids.add(i)
        if ids:
            cluster_by_first_id[ids[0]] = c

    out: list[str] = []
    rendered_clusters: set[str] = set()
    for r in recs:
        rid = r.get("id", "")
        if rid in clustered_ids:
            c = cluster_by_first_id.get(rid)
            if c is not None and c.canonical_id not in rendered_clusters:
                cluster_member_ids = {m.get("id", "") for m in c.members}
                other_recos = _rr._other_episode_recos_for_cluster(
                    recs, cluster_member_ids,
                )
                out.append(_rr._dedup_cluster_card(
                    c, ep, source_id, hosts, other_recos=other_recos,
                ))
                rendered_clusters.add(c.canonical_id)
            continue
        out.append(_rr._reco_card(r, ep, hosts, source_id, edit_id,
                                  siblings=recs, parsed=parsed))
    return "".join(out)


def _has_undoable_merge(source_id: str) -> bool:
    """True si au moins un backup avec manifest matching cette source existe.

    #24/#15 review — Cache invalidé via (mtime_ns, size) de BACKUP_DIR.
    Merge/undo touche le dossier (mkdir/rmtree) → la mtime bouge ; on
    ajoute `st_size` (nombre d'entrées * taille) pour réduire encore
    les faux positifs sur les FS à granularité mtime grossière.
    """
    from reco_dedup import BACKUP_DIR  # noqa: PLC0415
    if not BACKUP_DIR.exists():
        return False
    st = BACKUP_DIR.stat()
    return _has_undoable_merge_cached(source_id, st.st_mtime_ns, st.st_size)


@functools.lru_cache(maxsize=32)
def _has_undoable_merge_cached(source_id: str, _mtime_ns: int,
                               _size: int) -> bool:
    """Lookup réel — clé inclut (mtime_ns, size) pour auto-invalidation."""
    from reco_dedup import BACKUP_DIR  # noqa: PLC0415
    import json as _json  # noqa: PLC0415
    for d in BACKUP_DIR.iterdir():
        if not d.is_dir():
            continue
        manifest_path = d / "manifest.json"
        if not manifest_path.exists():
            continue
        try:
            m = _json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if m.get("source_id") == source_id:
            return True
    return False


# #27 — Markup statique du wrapper iframe YouTube : indépendant de l'épisode,
# extrait en constante pour la lisibilité de `_render_episode`.
# `hidden` au chargement : pas d'iframe vide flottante à l'arrivée — le JS
# (setupPlayerToggle) retire la classe au premier clic sur un timecode.
_PLAYER_WRAP_HTML = (
    '<div class="player-wrap hidden" data-player-wrap>'
    '<div class="player-drag-handle" data-player-drag '
    'title="Glisser pour déplacer">⠿</div>'
    '<button type="button" class="player-close" data-player-close '
    'title="Fermer le lecteur" aria-label="Fermer le lecteur">✕</button>'
    '<iframe name="ytplayer" class="player" title="Lecteur YouTube" '
    'allowfullscreen></iframe>'
    '</div>'
)


def _render_merge_bar(guid: str) -> str:
    """#27 — Markup de la barre de fusion (top-of-page sticky, hidden par défaut).

    JS toggle `hidden` quand l'utilisateur·rice coche ≥ 2 cartes.
    """
    guid_q = html.escape(guid)
    return (
        '<div class="merge-bar" data-merge-bar hidden>'
        '<form method="post" action="/merge-recos">'
        f'<input type="hidden" name="guid" value="{guid_q}">'
        '<input type="hidden" name="cluster_ids" data-merge-ids value="">'
        '<input type="hidden" name="action" value="pick">'
        '<span class="merge-count" data-merge-count>0 recos sélectionnées</span>'
        '<button type="submit" class="primary">Fusionner</button>'
        '<button type="button" data-merge-clear>Tout déselectionner</button>'
        '</form></div>'
    )


def _render_episode(
    source_id: str, guid: str, edit_id: str | None = None,
    *, flash: str | None = None, flash_kind: str = "info",
) -> str:
    """Page d'un épisode : son en-tête + ses recos à relire."""
    source, episodes, groups = _rr._load_groups(source_id)
    hosts = source.get("hosts", [])
    ep = episodes.get(guid)
    recs = groups.get(guid, [])
    back = '<a class="back" href="/">← tous les épisodes</a>'
    if _has_undoable_merge(source_id):
        undo_form = (
            f'<form method="post" action="/undo-merge" class="undo-merge-form" '
            f'style="display:inline-block; margin-left:1em;">'
            f'<input type="hidden" name="guid" value="{html.escape(guid)}">'
            f'<button type="submit" class="btn-undo-merge" '
            f'title="Restaure le dernier merge enregistré">'
            f'↶ Annuler la dernière fusion</button></form>'
        )
        back = back + undo_form
    if not ep:
        return _rr._shell(source.get("title", source_id), "Épisode introuvable.", back)

    def _key(g: str):
        e = episodes.get(g, {})
        return (e.get("season") or 0, e.get("number") or 9999)
    ordered = sorted(episodes.keys(), key=_key)
    idx = ordered.index(guid) if guid in ordered else -1
    prev_guid = ordered[idx - 1] if idx > 0 else None
    next_guid = ordered[idx + 1] if 0 <= idx < len(ordered) - 1 else None
    # Passe le parsing du titre en fallback pour les épisodes pas encore
    # migrés (avant exécution de tools/migrate_guests_parsed.py).
    parsed_guests = (ep.get("guestsParsed")
                     or _rr._parse_guests(ep.get("title", ""), hosts))
    guests_panel = _rr._render_guests_panel(
        guid, ep, recs, hosts, parsed=parsed_guests,
    )
    # L3 — propage `parsed_guests` (calculé une fois ci-dessus) aux cartes pour
    # éviter que chaque `_reco_card` reparse le titre de l'épisode.
    cards = _render_with_clusters(
        recs, ep, hosts, source_id, edit_id, parsed=parsed_guests,
    )
    add_reco_btn = (
        '<li class="row add-reco-row">'
        '<form method="post" action="/add-reco" class="add-reco-form">'
        f'<input type="hidden" name="guid" value="{html.escape(guid)}">'
        '<button type="submit" class="btn-add-reco" '
        'title="Créer une reco manuelle pour cet épisode">'
        '+ Ajouter une reco manuellement</button></form></li>'
    )
    cards = cards + add_reco_btn
    banner = _rr._flash_banner(flash, flash_kind)
    inner = (f'{back}{banner}{_PLAYER_WRAP_HTML}{_render_merge_bar(guid)}'
             f'<section class="ep">'
             f'{_ep_header(ep, recs, prev_guid=prev_guid, next_guid=next_guid)}'
             f'{guests_panel}<ul>{cards}</ul></section>')
    return _rr._shell(source.get("title", source_id), "Relecture d'un épisode.", inner)


# ---- API publique (#15) — alias sans underscore pour les consommateurs externes
render_episode = _render_episode
render_index = _render_index
