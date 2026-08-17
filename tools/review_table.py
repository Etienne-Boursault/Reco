"""review_table.py — Page /tableau : tableau de pilotage des recos actives.

Une passe de curation ne se fait pas carte par carte : il faut voir les ~1200
recos actives d'un coup, les trier sous plusieurs angles, et poser au fil de
l'eau un commentaire et une coche de validation. C'est ce que rend cette page —
dans le SERVEUR DE RELECTURE, jamais dans le site public : un outil de curation
interne n'a rien à faire dans un build qu'on publie.

Le tri est fait CÔTÉ CLIENT (`review_client_table.js`) : 1200 lignes, c'est du
DOM raisonnable, et un tri sans rechargement ne fait pas perdre le commentaire
en cours de frappe. Chaque `<tr>` porte donc ses clés de tri pré-calculées en
`data-k-*` (normalisées ici, une fois, plutôt que 1200 fois dans le navigateur).

Le commentaire et la coche vivent dans un sidecar (cf. `review_curation`), pas
dans les JSON de recos. La colonne « Types » affiche, quand la passe de
reclassement a produit son fichier, la proposition à côté du type courant, avec
une coche pour l'accepter (POST /accept-type).
"""
from __future__ import annotations

import html
import urllib.parse

from common import normalize_text
from review_curation import load_curation, load_type_proposals
from review_edit import RECO_TYPES, TYPE_EMOJIS, TYPE_LABELS
from review_render import _PLAYER_WRAP_HTML, _load_groups
from review_render_common import (
    _flash_banner,
    _safe_int,
    _safe_url,
    _shell,
    _ts_seconds,
    _yt_timecode_link,
)
from review_search_links import search_links

__all__ = ["build_rows", "render_table_page"]

#: Colonnes : (clé de tri, libellé, tri numérique, infobulle).
#: L'ordre fait foi pour l'en-tête ET pour les cellules.
_COLUMNS: tuple[tuple[str, str, bool, str], ...] = (
    ("title", "Titre", False, ""),
    ("artist", "Artiste", False, ""),
    ("episode", "Épisode", False,
     "Tri chronologique : date de l’épisode, puis timecode"),
    # Colonne de RÉÉCOUTE (2026-08-15). Le passage est ce qui tranche une
    # curation : le titre seul ne dit pas si la reco est sérieuse, ironique,
    # ou si l'invité parle d'autre chose. Le lecteur s'ouvre sur place plutôt
    # que d'obliger à rouvrir l'épisode et à y retrouver le moment.
    ("timecode", "⏱", True, "Cliquer pour réécouter le passage"),
    ("by", "Qui recommande", False, ""),
    ("types", "Types", False, ""),
    ("links", "Liens", True,
     "Tri par nombre de liens POSÉS — les recherches 🔍 ne comptent pas"),
    ("comment", "Commentaire", False, ""),
    # EN DERNIER (2026-08-15, retour utilisateur). La coche marque « je l'ai
    # regardée » : on la pose APRÈS avoir lu la ligne, pas avant. Sa place
    # naturelle est donc au bout, à côté du commentaire qu'on vient d'écrire.
    ("check", "✔", True,
     ("Marque de passe de curation : « je l’ai regardée ». Enregistrée à côté "
      "du corpus (tools/output/curation/), elle ne modifie AUCUNE reco et "
      "n’apparaît pas sur le site.")),
)

#: Éthique d'un lien telle que posée par le pipeline. Sert de suffixe de classe
#: CSS : les liens `avoid` (Amazon, Bolloré…) restent visibles mais signalés.
_ETHICS: frozenset[str] = frozenset({"indie", "neutral", "avoid"})

#: Date de repli pour un épisode sans date : le pousse en FIN de tri
#: chronologique plutôt qu'au début (où il masquerait les vrais anciens).
_NO_DATE = "9999-99-99"


# ---- Collecte ---------------------------------------------------------------
def _ep_label(ep: dict) -> str:
    """« S1·E3 — Titre », « #7 — Titre », « Titre », ou le guid en dernier repli."""
    title = str(ep.get("title") or "").strip()
    if not title:
        return str(ep.get("guid") or "?")
    season, number = ep.get("season"), ep.get("number")
    if season and number:
        return f"S{season}·E{number} — {title}"
    if number:
        return f"#{number} — {title}"
    return title


def _chrono_key(ep: dict, reco: dict) -> str:
    """Clé de tri chronologique, comparable en simple ordre lexicographique.

    Champs zéro-padés pour que la comparaison de chaînes côté client donne le
    même ordre qu'une comparaison numérique — pas besoin de parser en JS.
    """
    date = str(ep.get("date") or _NO_DATE)
    secs = _ts_seconds(reco.get("timestamp")) or 0
    return (f"{date}|{_safe_int(ep.get('season')):03d}"
            f"|{_safe_int(ep.get('number')):04d}|{secs:07d}")


def _host_of(url: str) -> str:
    """Nom d'hôte d'une URL, ou l'URL entière si elle n'en a pas.

    Découpage manuel (et non `urlparse`) : `urlparse(...).hostname` lève
    ValueError sur certaines URLs mal formées, et on est ici sur un chemin
    d'affichage qui ne doit jamais casser le rendu.
    """
    host = url.split("//", 1)[-1].split("/", 1)[0]
    return host or url


def _row_links(raw) -> list[dict]:
    """Liens affichables : http(s) uniquement, label et éthique normalisés.

    Le filtre `_safe_url` est la garde qui compte : un `javascript:` ou un
    `file://` glissé dans une donnée éditable ne doit pas devenir un lien
    cliquable dans un outil interne (le dépôt a un précédent de `file://`).
    """
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for link in raw:
        if not isinstance(link, dict):
            continue
        url = _safe_url(link.get("url"))
        if not url:
            continue
        ethics = link.get("ethics")
        out.append({
            "url": url,
            "label": str(link.get("label") or "").strip() or _host_of(url),
            "ethics": ethics if ethics in _ETHICS else "",
        })
    return out


def _proposal_for(reco_id: str, current: list[str],
                  proposals: dict[str, dict]) -> dict | None:
    """Proposition de reclassement retenue pour une reco, ou None.

    Écartée si elle propose un type hors vocabulaire (on ne veut pas qu'une
    coche écrive n'importe quoi dans le JSON) ou si elle ne change rien.

    `dropped` matérialise ce que le remplacement RETIRE : la proposition est un
    remplacement complet de `types`, et 159 des 178 cas consistent justement à
    enlever `autre`. Sans cette information, « → Lieu » se lit comme un ajout,
    donc l'inverse de ce qui est proposé.
    """
    prop = proposals.get(reco_id)
    if not prop:
        return None
    types = [t for t in prop.get("types", []) if t in RECO_TYPES]
    if not types or set(types) == set(current):
        return None
    return {
        "types": types,
        "dropped": [t for t in current if t not in types],
        "reason": prop.get("reason", ""),
        "confidence": prop.get("confidence", ""),
        "arbitrage": prop.get("arbitrage", ""),
    }


def build_rows(source_id: str) -> tuple[dict, list[dict]]:
    """(source, lignes) — une ligne par reco ACTIVE, prête à rendre.

    Les recos `discarded` sont hors sujet ici : la page sert à piloter ce qui
    part sur le site, pas à revisiter ce qui a déjà été écarté (c'est le rôle
    de /doutes et /doublons).
    """
    source, episodes, groups = _load_groups(source_id)
    curation = load_curation(source_id)
    proposals = load_type_proposals()
    rows: list[dict] = []
    for guid, recos in groups.items():
        ep = episodes.get(guid) or {"guid": guid}
        for r in recos:
            if r.get("status") == "discarded":
                continue
            rid = r.get("id", "")
            note = curation.get(rid) or {}
            types = list(r.get("types") or [])
            title = str(r.get("title") or "")
            artist = str(r.get("creator") or "")
            links = _row_links(r.get("links"))
            rows.append({
                "id": rid,
                "title": title,
                "artist": artist,
                "by": str(r.get("recommendedBy") or ""),
                "ep_guid": guid,
                "ep_label": _ep_label(ep),
                "timestamp": str(r.get("timestamp") or ""),
                # Lien de timecode PRÊT À RENDRE, construit par le même
                # helper que la page d'épisode : il gère le décalage d'intro
                # entre l'horodatage Acast et la position YouTube, et bascule
                # sur l'audio quand la vidéo n'est pas intégrable. Le
                # reproduire ici aurait fatalement divergé.
                "tc_html": _yt_timecode_link(r, ep),
                "tc_secs": _ts_seconds(r.get("timestamp")),
                "chrono": _chrono_key(ep, r),
                "types": types,
                "proposal": _proposal_for(rid, types, proposals),
                "links": links,
                # Recherches pré-remplies : outil de curation INTERNE, jamais
                # écrit dans les JSON de recos (cf. review_search_links).
                "search": search_links(title, artist, types, links),
                "comment": str(note.get("comment") or ""),
                "checked": bool(note.get("checked")),
            })
    rows.sort(key=lambda row: row["chrono"])
    return source, rows


# ---- Rendu ------------------------------------------------------------------
def _types_html(types: list[str]) -> str:
    """Badges emoji + libellé pour les types courants d'une reco."""
    return "".join(
        f'<span class="tbl-type">{TYPE_EMOJIS.get(t, "✨")} '
        f'{html.escape(TYPE_LABELS.get(t, t))}</span>'
        for t in types)


def _proposal_html(row: dict) -> str:
    """Proposition de reclassement + coche « accepter » (ou rien).

    Formulée comme un REMPLACEMENT (« Remplacer par … · retire … ») : c'est ce
    que la coche fait vraiment. Un « ⚖ » signale les cas que la passe a marqués
    comme demandant un arbitrage éditorial, un « ≈ » ceux tirés d'une inférence
    plutôt que d'un signal certain — on ne coche pas ceux-là mécaniquement.
    """
    prop = row["proposal"]
    if not prop:
        return ""
    labels = ", ".join(TYPE_LABELS.get(t, t) for t in prop["types"])
    dropped = ", ".join(TYPE_LABELS.get(t, t) for t in prop["dropped"])
    drop_html = (f' <span class="tbl-prop-drop">· retire {html.escape(dropped)}</span>'
                 if dropped else "")
    marker = ""
    classes = "tbl-prop"
    if prop["arbitrage"]:
        marker, classes = "⚖ ", "tbl-prop tbl-prop-arb"
    elif prop["confidence"] and prop["confidence"] != "certain":
        marker, classes = "≈ ", "tbl-prop tbl-prop-weak"
    tip = " — ".join(t for t in (prop["reason"], prop["arbitrage"]) if t)
    hint = f' title="{html.escape(tip)}"' if tip else ""
    return (
        f'<label class="{classes}"{hint}>'
        f'<input type="checkbox" class="tbl-accept" '
        f'data-id="{html.escape(row["id"])}" '
        f'data-types="{html.escape(",".join(prop["types"]))}"> '
        f'{marker}Remplacer par : {html.escape(labels)}{drop_html}</label>'
    )


def _links_html(links: list[dict]) -> str:
    """Liens cliquables : nouvel onglet, `noopener noreferrer`, http(s) seuls."""
    return "".join(
        f'<a class="tbl-link tbl-link-{link["ethics"] or "none"}" '
        f'href="{html.escape(link["url"])}" target="_blank" '
        f'rel="noopener noreferrer">{html.escape(link["label"])}</a>'
        for link in links)


def _search_html(searches: list[dict]) -> str:
    """Recherches pré-remplies, repliées derrière un 🔍 par ligne.

    REPLIÉES à dessein : 1200 lignes × ~3,4 puces = ~4100 ancres de plus.
    Dépliées, elles noieraient les VRAIS liens — qui sont l'information de la
    colonne — et tripleraient la surface à mettre en page. `<details>` fait ça
    sans une ligne de JavaScript, et le navigateur ne met en page ni ne peint
    le contenu replié.

    VISUELLEMENT DISTINCTES des liens posés (trait pointillé, 🔍, teinte
    sourde) : un lien posé DÉSIGNE l'œuvre, celui-ci désigne une recherche
    qui reste à faire. Confondre les deux, c'est reposter une URL de
    recherche comme si c'était la fiche.
    """
    if not searches:
        return ""
    chips = "".join(
        f'<a class="tbl-search-link" href="{html.escape(s["url"])}"'
        f' target="_blank" rel="noopener noreferrer"'
        f' title="{html.escape(s["hint"])}">🔍 {html.escape(s["label"])}</a>'
        for s in searches)
    return (
        f'<details class="tbl-search"><summary class="tbl-search-open"'
        f' title="Recherches pré-remplies sur les plateformes qui manquent'
        f' encore — à finir à la main">🔍 {len(searches)}</summary>'
        f'<span class="tbl-search-list">{chips}</span></details>'
    )


def _row_html(row: dict) -> str:
    """Une ligne du tableau, avec ses clés de tri pré-calculées.

    TOUS les liens de la ligne ouvrent un nouvel onglet, y compris les deux
    liens INTERNES (titre → fiche d'édition, épisode). Le tableau porte un état
    que la navigation détruirait : le filtre d'épisode, l'ordre de tri en
    cours, et surtout le commentaire en train d'être saisi — non encore envoyé
    au sidecar. Revenir en arrière rendrait la page dans son état initial.
    Corriger une reco depuis le tableau doit être un aller sans retour à payer.

    `rel="noopener"` sans `noreferrer` : la cible est le même serveur, on lui
    laisse le référent (utile aux journaux) mais jamais l'accès à
    `window.opener`.
    """
    rid = html.escape(row["id"])
    ep_href = f"/ep?guid={urllib.parse.quote(row['ep_guid'])}"
    edit_href = f"{ep_href}&edit={urllib.parse.quote(row['id'])}"
    type_labels = " ".join(TYPE_LABELS.get(t, t) for t in row["types"])
    # Recos sans timecode POUSSÉES EN FIN de tri, dans les deux sens : trier
    # par timecode sert à parcourir un épisode dans l'ordre, pas à collecter
    # d'abord ce qui n'en a pas.
    tc_key = row["tc_secs"] if row["tc_secs"] is not None else 10**9
    return (
        f'<tr class="tbl-row" data-id="{rid}"'
        f' data-k-check="{"1" if row["checked"] else "0"}"'
        f' data-k-title="{html.escape(normalize_text(row["title"]))}"'
        f' data-k-artist="{html.escape(normalize_text(row["artist"]))}"'
        f' data-k-episode="{html.escape(row["chrono"])}"'
        f' data-k-by="{html.escape(normalize_text(row["by"]))}"'
        f' data-k-types="{html.escape(normalize_text(type_labels))}"'
        f' data-k-links="{len(row["links"])}"'
        f' data-k-timecode="{tc_key}"'
        f' data-k-comment="{html.escape(normalize_text(row["comment"]))}"'
        # Guid de l'épisode : ce sur quoi le filtre s'appuie. Distinct de
        # `data-k-episode`, qui est une clé de TRI chronologique (date +
        # timecode) et ne désigne donc pas un épisode de façon stable.
        f' data-ep="{html.escape(row["ep_guid"])}">'
        f'<td class="tbl-c-title"><a href="{html.escape(edit_href)}"'
        f' target="_blank" rel="noopener"'
        f' title="Ouvrir la fiche dans l’épisode (nouvel onglet)">'
        f'{html.escape(row["title"])}</a></td>'
        f'<td class="tbl-c-artist">{html.escape(row["artist"])}</td>'
        f'<td class="tbl-c-episode"><a href="{html.escape(ep_href)}"'
        f' target="_blank" rel="noopener"'
        f' title="Ouvrir l’épisode (nouvel onglet)">'
        f'{html.escape(row["ep_label"])}</a></td>'
        # `tc_html` vient de `_yt_timecode_link` : déjà échappé, et c'est le
        # SEUL fragment non ré-échappé de la ligne. Il ne doit jamais recevoir
        # de saisie libre — il ne contient qu'une URL d'embed et un timecode.
        f'<td class="tbl-c-timecode">{row["tc_html"]}</td>'
        f'<td class="tbl-c-by">{html.escape(row["by"])}</td>'
        f'<td class="tbl-c-types">{_types_html(row["types"])}'
        f'{_proposal_html(row)}</td>'
        f'<td class="tbl-c-links">{_links_html(row["links"])}'
        f'{_search_html(row["search"])}</td>'
        f'<td class="tbl-c-comment"><textarea class="tbl-comment"'
        f' data-id="{rid}" rows="2" aria-label="Commentaire de curation"'
        f'>{html.escape(row["comment"])}</textarea></td>'
        f'<td class="tbl-c-check"><input type="checkbox" class="tbl-check"'
        f' data-id="{rid}" aria-label="Marquer cette reco comme regardée"'
        f'{" checked" if row["checked"] else ""}></td>'
        f'</tr>'
    )


def _filter_html(rows: list[dict]) -> str:
    """Barre de filtre : une liste déroulante des épisodes.

    Liste déroulante et non champ de recherche : les épisodes sont une liste
    FERMÉE et connue au rendu, et leurs titres se ressemblent trop pour qu'une
    saisie libre soit fiable. Le compteur par épisode donne en prime la taille
    de ce qui reste à traiter.

    Ordre chronologique, hérité de `build_rows` — la passe de curation se fait
    épisode par épisode, dans l'ordre de diffusion, pas par ordre alphabétique
    de titres qui commencent presque tous pareil.
    """
    vus: dict[str, tuple[str, int]] = {}
    for row in rows:
        guid = row["ep_guid"]
        label, n = vus.get(guid, (row["ep_label"], 0))
        vus[guid] = (label, n + 1)
    options = "".join(
        f'<option value="{html.escape(guid)}">{html.escape(label)}'
        f' ({n})</option>'
        for guid, (label, n) in vus.items())
    return (
        f'<div class="tbl-bar">'
        f'<label class="tbl-bar-lbl" for="tbl-filter-ep">Épisode</label>'
        f'<select id="tbl-filter-ep" class="tbl-filter">'
        f'<option value="">Tous ({len(rows)} recos, {len(vus)} épisodes)</option>'
        f'{options}</select>'
        f'<button type="button" id="tbl-filter-clear" class="tbl-bar-btn"'
        f' hidden>✕ tout afficher</button>'
        f'<span id="tbl-filter-count" class="tbl-bar-count"></span>'
        f'</div>'
    )


def _header_html() -> str:
    """Ligne d'en-tête : bouton de tri + poignée de redimensionnement.

    La poignée est un ÉLÉMENT À PART, frère du bouton et non son enfant : un
    `mousedown` dessus ne doit jamais atteindre le bouton de tri, sans quoi
    chaque redimensionnement trierait la colonne en prime. Elle est focalisable
    et porte `role="separator"` — la largeur se règle aussi aux flèches du
    clavier, comme le reste de cette page se pilote sans souris.

    La dernière colonne en a une aussi : le tableau défile horizontalement
    (`overflow-x:auto`), donc son bord droit est atteignable.
    """
    cells = []
    for key, label, numeric, hint in _COLUMNS:
        title = f' title="{html.escape(hint)}"' if hint else ""
        aria = f"Redimensionner la colonne {label}" if label.strip() else \
            "Redimensionner la première colonne"
        cells.append(
            f'<th class="tbl-h tbl-h-{key}" data-sort-key="{key}"'
            f' data-sort-numeric="{"1" if numeric else "0"}"'
            f' aria-sort="none"{title}>'
            f'<button type="button" class="tbl-sort">{html.escape(label)}'
            f'<span class="tbl-arrow" aria-hidden="true"></span></button>'
            f'<span class="tbl-resize" role="separator" aria-orientation="vertical"'
            f' tabindex="0" data-resize-key="{key}"'
            f' title="Glisser pour redimensionner · double-clic pour réinitialiser"'
            f' aria-label="{html.escape(aria)}"></span></th>')
    return f'<thead><tr>{"".join(cells)}</tr></thead>'


def render_table_page(source_id: str, flash: str | None = None,
                      flash_kind: str = "info") -> str:
    """Page complète /tableau."""
    source, rows = build_rows(source_id)
    banner = _flash_banner(flash, flash_kind)
    back = ('<a class="back" href="/">← tous les épisodes</a> · '
            '<a class="back" href="/doutes">🤖 Doutes agent</a>')
    if not rows:
        return _shell(source.get("title", source_id),
                      "Tableau de pilotage.",
                      f"{banner}{back}<p>Aucune reco active à piloter.</p>")
    n_checked = sum(1 for r in rows if r["checked"])
    n_comments = sum(1 for r in rows if r["comment"])
    subtitle = (f"{len(rows)} recos actives · {n_checked} validées · "
                f"{n_comments} commentées. Clique un en-tête pour trier ; "
                f"commentaire et coche sont enregistrés au fil de l’eau.")
    body = "".join(_row_html(r) for r in rows)
    # Le défilement horizontal appartient au CONTENEUR, pas à la table.
    # La table portait `display:block; overflow-x:auto` — ce qui confinait bien
    # le défilement, mais au prix d'un effet de bord invisible : `table-layout`
    # ne s'applique qu'à un élément `display:table`. Sur un bloc, les rangées
    # sont enveloppées dans une table anonyme que la propriété n'atteint pas,
    # et les largeurs posées sur les colonnes redeviennent de simples
    # suggestions. Un `<div>` scrollable rend la table à sa vraie nature.
    # Lecteur AVANT le tableau, et surtout HORS de `reco-table-scroll` :
    # l'encart vidéo est positionné en fixe, mais un ancêtre défilant en ferait
    # son référentiel — il partirait sur le côté avec les colonnes. La barre
    # audio, elle, est collée en bas de fenêtre pour la même raison.
    inner = (f'{banner}{back}{_PLAYER_WRAP_HTML}{_filter_html(rows)}'
             f'<div class="reco-table-scroll">'
             f'<table class="reco-table" id="reco-table">'
             f'{_header_html()}<tbody>{body}</tbody></table></div>')
    return _shell(source.get("title", source_id), subtitle, inner)
