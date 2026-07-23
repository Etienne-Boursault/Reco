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

from review_edit import render_edit_form
from review_render import (
    _PLAYER_WRAP_HTML,
    _load_groups,
    _reco_candidates,
    _reco_checkboxes,
    _reco_quote_block,
)
from review_render_common import _flash_banner, _shell, _yt_timecode_link_parts

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
    # Décision humaine déjà prise via /save → la reco quitte la file, quels que
    # soient les flags / la confiance restants. Sinon une reco validée mais
    # encore flaggée réapparaît dans /doutes (retour utilisateur 2026-07-21).
    if ar.get("reviewedByHuman"):
        return None
    if ar.get("verdict") == "unsure":
        return "pending"
    # Une reco DISCARDED n'est pas un doute ouvert : sa décision (écarter) est
    # prise. Ses flags deviennent sans objet — on ne la met donc PAS en
    # « signalement ». Exception : si sa confiance est faible, elle retombe en
    # `lowconf` ci-dessous (re-contrôle d'un discard limite). Sans ça, les
    # jumelles discardées des clusters de doublons encombraient /doutes (571 sur
    # un-bon-moment au 2026-07-23).
    if ar.get("flags") and reco.get("status") != "discarded":
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


# Libellés HUMAINS des flags agent : l'en-tête « ce qui doit être corrigé »
# doit être explicite, pas un slug (retour utilisateur 2026-07-21).
_FLAG_LABELS: dict[str, str] = {
    "title_suspect": "Titre à vérifier",
    "attribution_suspect": "Attribution à vérifier",
    "duplicate_suspect": "Doublon probable",
    "guest_missing": "Invité manquant",
    "link_suspect": "Lien à vérifier",
    "timestamp_suspect": "Timecode à vérifier",
}
# En-tête de repli quand la reco n'a AUCUN flag (sections pending/recby/lowconf).
_SECTION_HEADINGS: dict[str, str] = {
    "pending": "À trancher (l'agent n'a pas su décider)",
    "recby": "Qui recommande ?",
    "lowconf": "Confiance faible — à contrôler",
}


def _deslug_flag(flag: str) -> str:
    """Rend lisible un flag hors mapping ('foo_suspect' → 'Foo à vérifier').
    Défensif : un agent LLM peut inventer un flag inconnu."""
    s = str(flag).replace("_suspect", "").replace("_", " ").strip()
    if not s:
        return "À vérifier"
    return f"{s[:1].upper()}{s[1:]} à vérifier"


def _issue_heading(key: str, reco: dict) -> str:
    """En-tête explicite du doute : les libellés de flags s'il y en a (plus
    précis que la section), sinon le libellé de la section."""
    flags = (reco.get("agentReview") or {}).get("flags") or []
    if flags:
        labels = dict.fromkeys(_FLAG_LABELS.get(f, _deslug_flag(f)) for f in flags)
        return " · ".join(labels)
    return _SECTION_HEADINGS.get(key, "À vérifier")


def _sig_meta(ar: dict) -> str:
    """Ligne méta discrète : 🤖 verdict · conf (+ raison si une note occupe
    déjà la ligne « correction »). Préserve verdict/confiance à l'écran."""
    bits: list[str] = []
    if ar.get("verdict"):
        bits.append(f'🤖 {html.escape(str(ar["verdict"]))}')
    if ar.get("confidence") is not None:
        bits.append(f'conf {html.escape(str(ar["confidence"]))}')
    reason, note = ar.get("reason"), ar.get("note")
    if note and reason and reason != note:
        bits.append(html.escape(str(reason)))
    return " · ".join(bits)


def _sig_fix(key: str, ar: dict) -> tuple[str, str]:
    """(label, texte HTML échappé) du bloc « ce qui doit être corrigé ».

    Priorité : la note de l'agent (souvent la correction concrète) > la raison >
    une invite propre à la section. Pour recby, la correction EST le choix du
    prescripteur (cases à cocher juste en dessous)."""
    if key == "recby":
        return ("Qui recommande cette œuvre ?",
                "Coche le host ou l'invité qui la recommande, puis valide.")
    if ar.get("note"):
        return ("Correction suggérée (agent)", html.escape(str(ar["note"])))
    if ar.get("reason"):
        return ("À vérifier", html.escape(str(ar["reason"])))
    hint = {
        "pending": "Valide, mets en citation, marque « leur œuvre » ou écarte.",
        "lowconf": "Contrôle rapide, puis valide ou corrige.",
        "flagged": "Vérifie le signalement, puis corrige ou valide.",
    }.get(key, "À vérifier.")
    return ("À vérifier", hint)


def _signalement_card(key: str, ep: dict, r: dict, hosts: list[str],
                      source_id: str, siblings: list[dict],
                      edit_id: str | None) -> str:
    """Bloc « signalement en avant » d'UN doute (refonte 2026-07-21).

    Encadré compact qui met CE QUI DOIT ÊTRE CORRIGÉ en avant : en-tête explicite
    (type de problème), reco actuelle, correction suggérée par l'agent, puis les
    actions (✎ Corriger / ✓ OK tel quel / ✕ Écarter). Remplace l'ancienne carte
    complète (lecteur + contexte) jugée trop lourde à scanner.

    Reste un `<li class="row" data-reco-id>` porteur du form /save : l'AJAX
    (removeCard) et l'édition inline continuent de fonctionner tels quels.
    `edit_id == id` → on rend le formulaire d'édition inline à la place.
    """
    rid = r.get("id", "")
    if edit_id and rid == edit_id:
        return render_edit_form(r, ep, siblings, hosts, "/doutes")

    ar = r.get("agentReview") or {}
    rid_esc = html.escape(rid)
    edit_href = (f'/doutes?ep={urllib.parse.quote(ep.get("guid", ""))}'
                 f'&edit={urllib.parse.quote(rid)}')
    heading = html.escape(_issue_heading(key, r))
    meta = _sig_meta(ar)
    fix_label, fix_txt = _sig_fix(key, ar)

    # Reco actuelle : titre + créateur + « Reco de » + lien timecode + citation.
    tcl = _yt_timecode_link_parts(r, ep)
    creator = (f' <i>· {html.escape(str(r["creator"]))}</i>'
               if r.get("creator") else "")
    recby = str(r.get("recommendedBy") or "").strip()
    recby_html = (f' <span class="sig-recby">Reco de {html.escape(recby)}</span>'
                  if recby else "")

    # Cases « qui recommande » PRÉ-COCHÉES avec le recommendedBy courant : sans
    # elles, « OK tel quel » (validate) écraserait l'attribution existante (le
    # save reconstruit recommendedBy à partir des cases `who` soumises).
    boxes = _reco_checkboxes(
        _reco_candidates(r, ep, hosts, siblings), r.get("recommendedBy", ""),
    )
    other_input = '<input type="text" name="other" placeholder="autre nom…" value="">'
    if key == "recby":
        # Le choix du prescripteur EST la correction → cases ouvertes, en avant.
        who_html = f'<div class="sig-who sig-who-recby">{boxes}{other_input}</div>'
    else:
        # Repliées : présentes dans le DOM (valider préserve le recommendedBy
        # déjà coché) mais discrètes — fidèle à l'aperçu « 3 boutons ».
        who_html = (
            '<details class="sig-who-toggle"><summary>👤 Qui recommande ? '
            f'(facultatif)</summary><div class="sig-who">{boxes}{other_input}'
            '</div></details>'
        )
    ok_label = "✓ Valider" if key == "recby" else "✓ OK tel quel"
    # L'agent était incertain (pending) → on garde les qualifications Citation /
    # Leur œuvre. Les autres sections restent au trio Corriger / OK / Écarter.
    extra = (
        '<button type="submit" name="action" value="citation" class="citation-btn"'
        ' title="Œuvre évoquée mais pas recommandée">📝 Citation</button>'
        '<button type="submit" name="action" value="guest-work" class="guestwork-btn"'
        ' title="Auto-promo d\'un·e invité·e ou d\'un host">⭐ Leur œuvre</button>'
    ) if key == "pending" else ""
    human = ar.get("humanCorrection")
    human_html = (f' <span class="sig-human">✔ {html.escape(str(human))}</span>'
                  if human else "")
    meta_html = f'<span class="sig-meta">{meta}</span>' if meta else ""

    return f"""
    <li class="row sig sig-{html.escape(key)}" data-reco-id="{rid_esc}">
      <div class="sig-head">🚩 {heading}{meta_html}</div>
      <div class="sig-current"><span class="sig-label">Reco actuelle :</span>
        <b>{html.escape(str(r.get("title", "") or "(sans titre)"))}</b>{creator}{recby_html} {tcl.html}
        {_reco_quote_block(r)}
      </div>
      <div class="sig-fix"><span class="sig-fix-label">💡 {html.escape(fix_label)} :</span>
        <span class="sig-fix-txt">{fix_txt}</span>{human_html}
      </div>
      <form method="post" action="/save" class="sig-actions">
        <input type="hidden" name="id" value="{rid_esc}">
        {who_html}
        <div class="sig-btns">
          <a class="btn-edit" href="{edit_href}">✎ Corriger</a>
          <button type="submit" name="action" value="validate" class="sig-ok">{ok_label}</button>
          {extra}
          <button type="submit" name="action" value="discard" class="discard sig-ecarter">✕ Écarter</button>
        </div>
      </form>
    </li>"""


def _render_type_section(
    key: str, label: str, desc: str,
    items: list[tuple[dict, dict]], hosts: list[str],
    source_id: str, groups: dict[str, list[dict]],
    edit_id: str | None,
) -> str:
    """Bloc d'UN type de doute : en-tête (libellé + compte + description) puis un
    « signalement en avant » compact par reco. `items` = [(episode, reco), …]
    (tous du même épisode dans la vue épisode ; déjà triés chronologiquement par
    `_load_groups`). Refonte 2026-07-21 : encadré signalement au lieu de la carte
    complète."""
    out = [
        f'<section class="doubt-section doubt-type doubt-type-{html.escape(key)}">'
        f'<h2 class="doubt-type-h">{html.escape(label)} '
        f'<span class="cnt">{len(items)}</span></h2>'
        f'<p class="doubt-type-desc">{html.escape(desc)}</p><ul>'
    ]
    for ep, r in items:
        out.append(_signalement_card(
            key, ep, r, hosts, source_id,
            groups.get(ep.get("guid", ""), []), edit_id,
        ))
    out.append("</ul></section>")
    return "".join(out)


def collect_doubts_by_episode(
    source_id: str,
) -> tuple[dict, dict, dict, dict[str, dict]]:
    """Doutes regroupés PAR ÉPISODE (refonte perf 2026-07-21).

    Renvoie (source, episodes, groups, per_ep) où per_ep =
    {guid: {"ep": episode, "sections": {clé: [reco,…]}, "total": n}} pour les
    seuls épisodes ayant au moins un doute. La page /doutes chargeait TOUTES
    les cartes d'un coup (~6 Mo, navigateur à genoux) ; on sert désormais un
    index léger puis un épisode à la fois."""
    source, episodes, groups = _load_groups(source_id)
    per_ep: dict[str, dict] = {}
    for guid, recos in groups.items():
        ep = episodes.get(guid, {"guid": guid, "title": guid})
        secs: dict[str, list[dict]] = {}
        for r in recos:
            key = _section_for(r)
            if key is not None:
                secs.setdefault(key, []).append(r)
        if secs:
            per_ep[guid] = {"ep": ep, "sections": secs,
                            "total": sum(len(v) for v in secs.values())}
    return source, episodes, groups, per_ep


def _ep_sort_key(ep: dict):
    """Tri des épisodes du plus RÉCENT au plus ancien (date desc), comme la
    chaîne YouTube. Repli sur (saison, numéro) si une date manque."""
    return (str(ep.get("date") or ""),
            ep.get("season") or 0, ep.get("number") or 0)


def _render_index(source: dict, per_ep: dict[str, dict], source_id: str,
                  flash: str | None, flash_kind: str) -> str:
    """Index léger : la liste des épisodes à revoir (aucune carte ni lecteur)."""
    banner = _flash_banner(flash, flash_kind)
    back = '<a class="back" href="/">← tous les épisodes</a>'
    total = sum(d["total"] for d in per_ep.values())
    if total == 0:
        inner = f"{banner}{back}<p>Aucun doute en attente — tout est validé. 🎉</p>"
        return _shell(source.get("title", source_id),
                      "File de validation des doutes agent.", inner)

    rows = sorted(per_ep.values(), key=lambda d: _ep_sort_key(d["ep"]),
                  reverse=True)
    lis = []
    for d in rows:
        ep = d["ep"]
        href = f"/doutes?ep={urllib.parse.quote(ep.get('guid', ''))}"
        badges = " ".join(
            f'<span class="doubt-mini doubt-mini-{html.escape(k)}">'
            f'{html.escape(_SECTION_LABELS[k])} {len(d["sections"][k])}</span>'
            for k, _l, _dd in _SECTIONS if d["sections"].get(k)
        )
        lis.append(
            f'<li class="doubt-ep-row"><a class="doubt-ep-link" href="{href}">'
            f'<span class="doubt-ep-total">{d["total"]}</span> '
            f'<span class="doubt-ep-name">{html.escape(_ep_label(ep))}</span>'
            f'</a> <span class="doubt-mini-wrap">{badges}</span></li>'
        )
    inner = (
        f'{banner}{back}'
        f'<p class="doubt-summary"><b>{total}</b> reco(s) à revoir sur '
        f'<b>{len(per_ep)}</b> épisode(s) — choisis un épisode.</p>'
        f'<ul class="doubt-ep-list">{"".join(lis)}</ul>'
    )
    return _shell(source.get("title", source_id),
                  f"{total} reco(s) à revoir, {len(per_ep)} épisode(s).", inner)


def _render_episode(source: dict, guid: str, per_ep: dict[str, dict],
                    hosts: list[str], source_id: str,
                    groups: dict[str, list[dict]], edit_id: str | None,
                    flash: str | None, flash_kind: str) -> str:
    """Vue d'UN épisode : ses doutes groupés par type, avec cartes + lecteur."""
    banner = _flash_banner(flash, flash_kind)
    back = '<a class="back" href="/doutes">← liste des épisodes à revoir</a>'
    d = per_ep.get(guid)
    if d is None:
        inner = (f"{banner}{back}<p>Aucun doute sur cet épisode — "
                 "tout est traité. 🎉</p>")
        return _shell(source.get("title", source_id),
                      "File de validation des doutes agent.", inner)
    ep = d["ep"]
    nav = " · ".join(
        f'<a href="#sec-{html.escape(key)}">'
        f'{html.escape(_SECTION_LABELS[key])} ({len(d["sections"][key])})</a>'
        for key, _t, _dd in _SECTIONS if d["sections"].get(key)
    )
    # Le titre YouTube (souvent un format anglais) reste consultable en tooltip
    # quand il diffère du RSS — le per-item ep-tag ayant disparu (refonte 07-21).
    rss_t, yt_t = ep.get("title") or "", ep.get("youtubeTitle") or ""
    tip = (f' title="YouTube : {html.escape(yt_t)}"'
           if rss_t and yt_t and yt_t != rss_t else "")
    # M2 — wrap player inline (liens timecode ciblent target="ytplayer").
    body = [
        banner, back,
        f'<h1 class="doubt-ep-title"{tip}>{html.escape(_ep_label(ep))}</h1>',
        f'<p class="doubt-summary"><b>{d["total"]}</b> reco(s) à revoir — {nav}</p>',
        _PLAYER_WRAP_HTML,
    ]
    for key, label, desc in _SECTIONS:
        items = d["sections"].get(key)
        if not items:
            continue
        body.append(
            f'<a id="sec-{html.escape(key)}" class="anchor"></a>'
            + _render_type_section(key, label, desc, [(ep, r) for r in items],
                                   hosts, source_id, groups, edit_id)
        )
    return _shell(source.get("title", source_id),
                  f'{d["total"]} reco(s) — {_ep_label(ep)}', "".join(body))


def render_doubts(source_id: str, ep: str | None = None,
                  edit_id: str | None = None,
                  flash: str | None = None, flash_kind: str = "info") -> str:
    """Page /doutes. Sans `ep` → index des épisodes à revoir (léger). Avec
    `ep=<guid>` → les doutes de ce seul épisode (cartes + lecteur).

    Refonte perf 2026-07-21 : l'ancienne page unique rendait toutes les cartes
    d'un coup (~6 Mo). `edit_id`/`flash`/`flash_kind` : cf. #M3 (retour inline
    après save + bannière sans-JS)."""
    source, _episodes, groups, per_ep = collect_doubts_by_episode(source_id)
    if ep:
        return _render_episode(source, ep, per_ep, source.get("hosts", []),
                               source_id, groups, edit_id, flash, flash_kind)
    return _render_index(source, per_ep, source_id, flash, flash_kind)
