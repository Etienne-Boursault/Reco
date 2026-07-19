"""review_doubts.py — Page /doutes : file de validation des incertitudes agent.

Regroupe en une page unique tout ce que les agents de review ont signalé comme
incertain, pour que la relecture humaine se fasse en un seul passage :

  1. `pending`  — verdicts `unsure` (la reco est restée en draft) ;
  2. `flagged`  — recos porteuses de `agentReview.flags` (titre suspect,
                  lien à vérifier, …) quel que soit leur statut ;
  3. `recby`    — recos VALIDÉES par l'agent mais sans `recommendedBy`
                  (attribution du locuteur impossible sans diarization) ;
  4. `lowconf`  — verdicts appliqués avec confiance < LOW_CONFIDENCE.

Chaque reco n'apparaît que dans UNE section (priorité : pending > flagged >
recby > lowconf). Les cartes réutilisent `_reco_card` : les boutons
Valider / Citation / Pas une reco fonctionnent directement depuis la page.
Depuis M3, un POST /save initié ici redirige vers /doutes (avec flash) et non
vers l'épisode : la promesse « un seul passage » est désormais tenue — on
enchaîne les doutes sans être éjecté vers /ep à chaque validation.

Module séparé de review_render.py pour rester sous la limite des 500 lignes.
"""
from __future__ import annotations

import html
import urllib.parse

from review_render import _PLAYER_WRAP_HTML, _load_groups, _reco_card
from review_render_common import _flash_banner, _shell

# Sous ce seuil, un verdict appliqué est considéré « à vérifier ».
LOW_CONFIDENCE = 0.7

# (clé, étiquette, description) — l'ordre est celui des PRIORITÉS (un doute ne
# porte qu'une étiquette) ET l'ordre d'affichage des sections. Depuis le retour
# utilisateur 2026-07-19, l'affichage est groupé PAR TYPE d'info à valider
# (chaque reco reste étiquetée avec son épisode).
_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("pending", "À trancher (verdict en attente)",
     "L'agent n'a pas su décider — à toi de Valider, mettre en Citation, "
     "marquer « Leur œuvre » ou écarter."),
    ("flagged", "Signalements à vérifier",
     "Titre suspect, lien incertain, invité manquant, doublon, timecode… "
     "— vérifie puis corrige/valide."),
    ("recby", "Qui recommande ? (« Reco de » à compléter)",
     "Reco validée mais sans prescripteur (transcript non diarizé) — "
     "coche le host ou l'invité qui la recommande, puis Valider."),
    ("lowconf", "Faible confiance",
     f"Verdict appliqué avec confiance < {LOW_CONFIDENCE} — contrôle rapide."),
)
_SECTION_LABELS = {key: label for key, label, _d in _SECTIONS}


def _section_for(reco: dict) -> str | None:
    """Section (unique) où ranger une reco — None si rien à revoir."""
    ar = reco.get("agentReview")
    if not ar:
        return None
    if ar.get("verdict") == "unsure":
        return "pending"
    if ar.get("flags"):
        return "flagged"
    # « Reco de » à compléter : recos validées sans prescripteur. Une œuvre
    # d'invité (guestWork) est aussi une reco (kind=reco) → même traitement.
    is_reco_like = reco.get("kind", "reco") == "reco" or bool(reco.get("guestWork"))
    if (reco.get("status") == "validated"
            and is_reco_like
            # m5 (revue 2026-07-19) : str(...) défensif — un recommendedBy en
            # liste (donnée agent malformée) planterait sinon .strip() → et
            # _section_for tourne pour CHAQUE reco de l'index ET de /doutes.
            and not str(reco.get("recommendedBy") or "").strip()):
        return "recby"
    # Coercion défensive : un agent LLM peut écrire "0.8" (chaîne) au lieu de
    # 0.8 → sans ça, le `<` plante TOUTE la page /doutes (pas de try/except sur
    # la route). Cf. revue M1 / incident confidence textuelle 2026-07-18.
    conf = ar.get("confidence")
    try:
        conf = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf = None
    if conf is not None and conf < LOW_CONFIDENCE:
        return "lowconf"
    return None


def collect_doubts(source_id: str) -> dict[str, list[tuple[dict, dict]]]:
    """Toutes les recos à revoir, par section : {clé: [(episode, reco), …]}."""
    _source, episodes, groups = _load_groups(source_id)
    sections: dict[str, list[tuple[dict, dict]]] = {
        key: [] for key, _t, _d in _SECTIONS
    }
    for guid, recos in groups.items():
        ep = episodes.get(guid, {"guid": guid, "title": guid})
        for r in recos:
            key = _section_for(r)
            if key is not None:
                sections[key].append((ep, r))
    return sections


def count_doubts(source_id: str) -> int:
    """Nombre total de recos à revoir (pour le lien de l'index).

    L2 — compte directement via `_section_for` sans matérialiser les tuples
    (ep, reco) de `collect_doubts` : le lien d'index n'a besoin que du total,
    pas de la structure sectionnée. `_load_groups` est caché (mtime) → l'appel
    est O(recos) en mémoire, sans I/O disque supplémentaire.
    """
    _source, _episodes, groups = _load_groups(source_id)
    return sum(
        1
        for recos in groups.values()
        for r in recos
        if _section_for(r) is not None
    )


def _ep_label(ep: dict) -> str:
    season, num = ep.get("season"), ep.get("number")
    badge = f"S{season}·E{num} — " if season and num else ""
    return f'{badge}{ep.get("title", ep.get("guid", "?"))}'


def _agent_block(reco: dict) -> str:
    """Bloc contexte agent (verdict, confiance, raison, flags, correction)."""
    ar = reco.get("agentReview") or {}
    conf = ar.get("confidence")
    conf_html = f" (conf {html.escape(str(conf))})" if conf is not None else ""
    parts = [
        f'<b>🤖 {html.escape(str(ar.get("verdict", "?")))}</b>{conf_html}',
    ]
    if ar.get("reason"):
        parts.append(html.escape(str(ar["reason"])))
    if ar.get("flags"):
        flags = ", ".join(html.escape(str(f)) for f in ar["flags"])
        parts.append(f'<span class="doubt-flags">🚩 {flags}</span>')
    if ar.get("note"):
        parts.append(html.escape(str(ar["note"])))
    if ar.get("humanCorrection"):
        parts.append(
            f'<span class="doubt-human">✔ {html.escape(str(ar["humanCorrection"]))}</span>'
        )
    return f'<div class="agent-review">{" · ".join(parts)}</div>'


def _render_type_section(
    key: str, label: str, desc: str,
    items: list[tuple[dict, dict]], hosts: list[str],
    source_id: str, groups: dict[str, list[dict]],
    edit_id: str | None,
) -> str:
    """Bloc d'UN type de doute : en-tête explicite (libellé + action + compte)
    puis toutes ses recos, CHACUNE étiquetée avec son épisode. `items` =
    [(episode, reco), …]. Les recos sont triées par épisode (saison/numéro)."""
    items_sorted = sorted(
        items,
        key=lambda er: (er[0].get("season") or 0, er[0].get("number") or 9999),
    )
    out = [
        f'<section class="doubt-section doubt-type doubt-type-{html.escape(key)}">'
        f'<h2 class="doubt-type-h">{html.escape(label)} '
        f'<span class="cnt">{len(items)}</span></h2>'
        f'<p class="doubt-type-desc">{html.escape(desc)}</p><ul>'
    ]
    for ep, r in items_sorted:
        guid = ep.get("guid", "")
        ep_href = f"/ep?guid={urllib.parse.quote(guid)}"
        # Symétrie avec _ep_header : le titre YouTube (souvent un format
        # anglais) reste consultable en tooltip quand il diffère du RSS.
        rss_t, yt_t = ep.get("title") or "", ep.get("youtubeTitle") or ""
        tip = (f' title="YouTube : {html.escape(yt_t)}"'
               if rss_t and yt_t and yt_t != rss_t else "")
        # L1 — le bloc agent doit être un <li> (pas un <div> enfant direct de
        # <ul>) : <li class="doubt-note"> avec l'étiquette épisode + le contexte
        # agent, juste avant la carte (elle-même un <li>), frères dans le <ul>.
        out.append(
            f'<li class="doubt-note">'
            f'<a class="doubt-ep-tag" href="{ep_href}"{tip}>'
            f'{html.escape(_ep_label(ep))}</a> {_agent_block(r)}</li>'
        )
        out.append(_reco_card(
            r, ep, hosts, source_id, edit_id=edit_id,
            siblings=groups.get(guid, []), edit_origin="/doutes",
        ))
    out.append("</ul></section>")
    return "".join(out)


def render_doubts(source_id: str, edit_id: str | None = None,
                  flash: str | None = None, flash_kind: str = "info") -> str:
    """Page /doutes complète — groupée PAR TYPE d'info à valider (verdict en
    attente, signalements, « Reco de » à compléter, faible confiance), chaque
    reco étiquetée avec son épisode. `edit_id` (facultatif) : rend le
    formulaire d'édition inline pour cette reco — le save y ramène (#M3).

    rev-render m3 (revue 2026-07-19) : `flash`/`flash_kind` rendent une bannière
    en tête de page. Sans ça, un POST /save initié depuis /doutes redirige vers
    `/doutes?flash=…` (#M3) mais le message était PERDU pour un client sans JS
    (le toast est injecté côté JS uniquement)."""
    source, episodes, groups = _load_groups(source_id)
    hosts = source.get("hosts", [])
    sections = collect_doubts(source_id)
    total = sum(len(v) for v in sections.values())

    banner = _flash_banner(flash, flash_kind)
    back = '<a class="back" href="/">← tous les épisodes</a>'
    if total == 0:
        inner = f"{banner}{back}<p>Aucun doute en attente — tout est validé. 🎉</p>"
        return _shell(source.get("title", source_id),
                      "File de validation des doutes agent.", inner)

    # Sommaire cliquable : total + compte par type (ancre vers chaque section).
    nav = " · ".join(
        f'<a href="#sec-{html.escape(key)}">'
        f'{html.escape(_SECTION_LABELS[key])} ({len(sections[key])})</a>'
        for key, _t, _d in _SECTIONS if sections[key]
    )
    # M2 — wrap player inline : les cartes réutilisent `_reco_card`, dont les
    # liens timecode ciblent `target="ytplayer"`. Sans cet iframe nommé dans
    # la page, le navigateur ouvrirait un onglet à chaque clic.
    body = [
        banner,
        back,
        f'<p class="doubt-summary"><b>{total}</b> reco(s) à revoir — {nav}</p>',
        _PLAYER_WRAP_HTML,
    ]
    # Une section par TYPE, dans l'ordre de priorité de _SECTIONS.
    for key, label, desc in _SECTIONS:
        items = sections.get(key) or []
        if not items:
            continue
        body.append(
            f'<a id="sec-{html.escape(key)}" class="anchor"></a>'
            + _render_type_section(key, label, desc, items, hosts,
                                   source_id, groups, edit_id)
        )
    subtitle = f"{total} reco(s) à revoir, groupées par type d'action."
    return _shell(source.get("title", source_id), subtitle, "".join(body))
