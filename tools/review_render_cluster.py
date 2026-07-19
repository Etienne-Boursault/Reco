"""review_render_cluster.py — Rendu HTML des clusters de doublons.

Extrait de review_render.py pour rester sous la limite de 500 LOC (CLAUDE.md)
et isoler la logique de fusion (cluster card, pick canonical, preview).

Dépendances : importe les helpers purs depuis `review_render`
(`_yt_timecode_link`, `_shell`). Aucun cycle : ce module n'est pas réimporté
côté review_render — seul `_render_with_clusters` y vit encore parce qu'il
dispatche aussi vers `_reco_card`.
"""
from __future__ import annotations

import html
import urllib.parse

from review_render_common import (
    _extractors_badge,
    _shell,
    _strip_french_quotes,
    _ts_seconds,
    _yt_timecode_link,
)


def _other_episode_recos_for_cluster(
    ep_recos: list[dict], cluster_ids: set[str],
) -> list[dict]:
    """Retourne les recos de l'épisode candidates pour ajout manuel au cluster.

    Critères :
      - Pas déjà membre du cluster (`id` not in `cluster_ids`).
      - Pas `status=discarded` (faux positif déjà rejeté).
      - Inclut recos ET citations (l'ajout manuel laisse passer ces mix —
        c'est au user de juger).

    Tri ascendant par timestamp (lecture chronologique, recos sans timestamp
    relégués en fin de liste).
    """
    def _ts_key(r: dict) -> tuple[int, int]:
        # None / invalide → (1, 0) pour pousser en fin de liste.
        s = _ts_seconds(r.get("timestamp"))
        return (1, 0) if s is None else (0, s)

    candidates = [
        r for r in ep_recos
        if r.get("id") not in cluster_ids
        and (r.get("status") or "draft") != "discarded"
    ]
    candidates.sort(key=_ts_key)
    return candidates


def _dedup_cluster_card(cluster, ep: dict, source_id: str,
                        hosts: list[str] | None = None,
                        *, other_recos: list[dict] | None = None) -> str:
    """Carte d'un cluster de doublons détectés.

    Affiche un radio par membre (le canonical pré-coché), un aperçu compact
    de chaque version (titre + timecode cliquable + extractors + quote), et
    3 actions : Preview (diff), Merge, Cancel.

    Note : `_reco_card` est volontairement non modifié — on ne mélange pas
    le rendu reco/cluster pour rester relisible.
    """
    members = cluster.members
    guid = ep.get("guid", "")
    cluster_ids = ",".join(m.get("id", "") for m in members)
    sim_pct = int(round(cluster.similarity * 100))
    n = len(members)
    options_html: list[str] = []
    for m in members:
        rid = m.get("id", "")
        checked = " checked" if rid == cluster.canonical_id else ""
        title = html.escape(m.get("title") or "?")
        recby = html.escape(m.get("recommendedBy") or "—")
        extractors_list = m.get("extractors") or []
        extractors = ", ".join(extractors_list) or "—"
        status = html.escape(m.get("status") or "draft")
        is_canonical = (' <span class="canonical-mark">★ par défaut</span>'
                        if rid == cluster.canonical_id else "")
        # Timecode cliquable (lien YT embed avec offset acast) ou span statique.
        tc = _yt_timecode_link(m, ep)
        # Badge extractors (helper centralisé — #3).
        conf_badge = _extractors_badge(extractors_list)
        # Quote (si présente, sans double guillemets — #12).
        quote = m.get("quote")
        quote_html = (
            f'<p class="cluster-quote">« {html.escape(_strip_french_quotes(quote))} »</p>'
            if quote else ""
        )
        options_html.append(
            f'<label class="cluster-option">'
            f'<input type="radio" name="keep_id" value="{html.escape(rid)}"{checked}>'
            f' <b>{title}</b> {tc} {conf_badge}'
            f' <span class="cluster-meta">par {recby} · {html.escape(extractors)} · {status}</span>'
            f'{is_canonical}'
            f'{quote_html}'
            f'</label>'
        )
    header = (
        f'<header class="cluster-header">'
        f'⚠ {n} doublons probables détectés '
        f'(similarité ≥ {sim_pct}%, Δt moyen {cluster.avg_timecode_delta}s)'
        f'</header>'
    )
    # Bloc « + ajouter une autre reco du même épisode » : rendu seulement si
    # other_recos non vide. Le JS client (setupClusterAdd) écoute le change
    # et :
    #   1. injecte l'id supplémentaire dans le hidden `cluster_ids` ;
    #   2. déplace la <li.row> correspondante dans la cluster card ;
    #   3. ajoute un radio keep_id pour la nouvelle reco.
    add_select_html = ""
    if other_recos:
        opts = ['<option value="">+ Ajouter une autre reco du même épisode…</option>']
        for r in other_recos:
            rid = r.get("id", "")
            t = r.get("title") or "?"
            recby = r.get("recommendedBy") or "—"
            ts = r.get("timestamp") or "—"
            label = f"{t} — {recby} ({ts})"
            opts.append(
                f'<option value="{html.escape(rid)}">{html.escape(label)}</option>'
            )
        add_select_html = (
            f'<div class="cluster-add">'
            f'<select class="cluster-add-select" data-cluster-add>'
            f'{"".join(opts)}'
            f'</select>'
            f'</div>'
        )
    return (
        f'<li class="row cluster">{header}'
        f'<form method="post" action="/merge-recos" class="cluster-form">'
        f'<input type="hidden" name="guid" value="{html.escape(guid)}">'
        f'<input type="hidden" name="cluster_ids" value="{html.escape(cluster_ids)}">'
        f'<div class="cluster-options">{"".join(options_html)}</div>'
        f'{add_select_html}'
        f'<div class="cluster-actions">'
        f'<button type="submit" name="action" value="preview">Aperçu du merge</button>'
        f'<button type="submit" name="action" value="merge" class="primary">Fusionner</button>'
        f'<button type="submit" name="action" value="cancel">Annuler ce cluster</button>'
        f'</div></form></li>'
    )


def render_pick_canonical(members: list[dict], guid: str) -> str:
    """Page de choix manuel de la version à garder avant fusion.

    Extrait de `Handler._render_pick_canonical` (SRP : transport HTTP ↔ rendu).
    """
    from reco_dedup import pick_canonical  # noqa: PLC0415
    default_id = pick_canonical(members)
    rows = [
        f'<h2>Fusionner {len(members)} recos — choisis la version à garder</h2>',
        '<p>La sélection par défaut privilégie : validated &gt; YouTube &gt; '
        'plus de LLMs &gt; quote plus longue.</p>',
    ]
    cluster_ids_csv = ",".join(m.get("id", "") for m in members)
    rows.append(
        f'<form method="post" action="/merge-recos">'
        f'<input type="hidden" name="guid" value="{html.escape(guid)}">'
        f'<input type="hidden" name="cluster_ids" value="{html.escape(cluster_ids_csv)}">'
        '<ul class="pick-list">'
    )
    for m in members:
        rid = m.get("id", "")
        title = m.get("title", "")
        ts = m.get("timestamp", "")
        ex = ", ".join(m.get("extractors") or [])
        status = m.get("status", "draft")
        src = m.get("transcriptSource") or "?"
        checked = " checked" if rid == default_id else ""
        mark = " ★" if rid == default_id else ""
        rows.append(
            f'<li><label><input type="radio" name="keep_id" '
            f'value="{html.escape(rid)}"{checked}> '
            f'<code>{html.escape(rid)}</code>{mark} · '
            f'<b>{html.escape(title)}</b> '
            f'<span class="muted">⏱ {html.escape(ts)} · '
            f'status={html.escape(status)} · source={html.escape(src)} · '
            f'extractors={html.escape(ex)}</span></label></li>'
        )
    rows.append(
        '</ul>'
        '<div class="edit-actions">'
        f'<a class="back" href="/ep?guid={urllib.parse.quote(guid)}">Annuler</a>'
        '<button type="submit" name="action" value="preview" class="primary">'
        'Aperçu du merge</button>'
        '</div></form>'
    )
    return _shell("Choix de la version à garder",
                  "Pick avant l'aperçu, puis validation finale.",
                  "".join(rows))


def render_merge_preview(members: list[dict], keep_id: str, guid: str) -> str:
    """Page de prévisualisation d'un merge — diff lisible avant validation.

    Extrait de `Handler._render_merge_preview` (SRP : transport HTTP ↔ rendu).
    """
    # m7 (revue 2026-07-19) : `next(..., None)` + garde. Le flux normal garantit
    # keep_id ∈ members (validé par _handle_merge_recos), mais cette fonction est
    # publique : sans défaut, un keep_id absent lèverait StopIteration (→ 500).
    keep = next((m for m in members if m.get("id") == keep_id), None)
    if keep is None:
        return _shell(
            "Aperçu de fusion", "Version à conserver introuvable.",
            '<p class="flash flash-error">La version à conserver '
            "n'est plus dans le cluster. Reviens en arrière et réessaie.</p>",
        )
    losers = [m for m in members if m.get("id") != keep_id]
    rows: list[str] = []
    rows.append(
        f'<h2>Aperçu de la fusion vers <code>{html.escape(keep_id)}</code></h2>'
    )
    rows.append(
        f'<p><b>{html.escape(keep.get("title", ""))}</b> '
        f'(status={html.escape(keep.get("status") or "draft")}) '
        f'va absorber {len(losers)} version(s) :</p>'
    )
    loser_rows = "".join(
        f'<li><code>{html.escape(l.get("id", ""))}</code> · '
        f'{html.escape(l.get("title", ""))} ⏱ {html.escape(l.get("timestamp") or "")}'
        f'</li>'
        for l in losers
    )
    rows.append(f'<ul>{loser_rows}</ul>')
    rows.append(
        '<p>Les autres champs (extractionHistory, customLinks, externalIds…) '
        'seront unionnés ; les titres alternatifs seront stockés en <code>aliases</code>.</p>'
    )
    cluster_ids_csv = ",".join(m.get("id", "") for m in members)
    rows.append(
        f'<form method="post" action="/merge-recos">'
        f'<input type="hidden" name="guid" value="{html.escape(guid)}">'
        f'<input type="hidden" name="cluster_ids" value="{html.escape(cluster_ids_csv)}">'
        f'<input type="hidden" name="keep_id" value="{html.escape(keep_id)}">'
        f'<button type="submit" name="action" value="merge" class="primary">'
        f'Confirmer la fusion</button> '
        f'<a class="back" href="/ep?guid={urllib.parse.quote(guid)}">Annuler</a>'
        f'</form>'
    )
    return _shell("Aperçu de fusion", "Vérifie avant de valider.",
                  "".join(rows))
