"""review_edit_form.py — Rendu du formulaire d'édition inline d'une reco.

Extrait de review_edit.py (M4 CR cumulative — limite 500 lignes) :
review_edit garde les constantes partagées (RECO_TYPES, TYPE_EMOJIS…) et les
MUTATIONS (apply_edit, apply_reenrich) ; ce module porte le RENDU du form.

Convention d'accès : les helpers sont résolus via les modules d'origine pour
préserver les monkeypatchs des tests ; `review_edit` réexporte les noms de ce
module en lazy (PEP 562) pour la rétro-compat des consommateurs existants.
"""
from __future__ import annotations

import html
import urllib.parse

from review_edit import EXT_FIELDS, RECO_TYPES, TYPE_EMOJIS, TYPE_LABELS  # noqa: F401
from review_links import AUTO_PLATFORMS_BY_TYPE, auto_url, auto_urls_for


def _dedup_ci(values) -> list[str]:
    """Déduplique en ignorant la casse, garde la 1ʳᵉ occurrence, trie."""
    seen: dict[str, str] = {}
    for v in values:
        v = (v or "").strip()
        if not v:
            continue
        key = v.casefold()
        if key not in seen:
            seen[key] = v
    return sorted(seen.values(), key=str.casefold)


def _render_creators_datalist(
    siblings: list[dict], reco_id: str,
) -> tuple[list[str], str, str]:
    """Datalist des créateurs des autres recos de l'épisode."""
    creators = _dedup_ci(
        s.get("creator") for s in siblings if s.get("id") != reco_id
    )
    dl_id = f"creators-{html.escape(reco_id)}"
    dl_html = (
        f'<datalist id="{dl_id}">'
        + "".join(f'<option value="{html.escape(c)}">' for c in creators)
        + "</datalist>"
    ) if creators else ""
    return creators, dl_id, dl_html


def _render_recommenders_datalist(
    siblings: list[dict], hosts: list[str], reco_id: str,
) -> tuple[list[str], str, str]:
    """Datalist « Reco de » : hosts en tête (ordre métier) puis autres."""
    others = _dedup_ci(s.get("recommendedBy") for s in siblings)
    host_keys = {h.casefold() for h in hosts}
    others = [o for o in others if o.casefold() not in host_keys]
    # `hosts` peut contenir des doublons (casse) → dédup en gardant l'ordre.
    hosts_seen: set[str] = set()
    hosts_ordered: list[str] = []
    for h in hosts:
        k = h.casefold()
        if k not in hosts_seen:
            hosts_seen.add(k)
            hosts_ordered.append(h)
    recommenders = [*hosts_ordered, *others]
    dl_id = f"recby-{html.escape(reco_id)}"
    dl_html = (
        f'<datalist id="{dl_id}">'
        + "".join(f'<option value="{html.escape(c)}">' for c in recommenders)
        + "</datalist>"
    ) if recommenders else ""
    return recommenders, dl_id, dl_html


def _render_type_boxes(current_types: set[str]) -> str:
    """Checkboxes pour chaque RECO_TYPE, cochées selon `current_types`."""
    return "".join(
        f'<label title="{html.escape(TYPE_LABELS.get(t, t))}">'
        f'<input type="checkbox" name="types" value="{t}"'
        f'{" checked" if t in current_types else ""}> '
        f'{TYPE_EMOJIS.get(t, "✨")} {html.escape(TYPE_LABELS.get(t, t))}</label>'
        for t in RECO_TYPES
    )


def _render_ext_inputs(ext: dict) -> list[str]:
    """Inputs `ext_<k>` pour chaque externalId présent."""
    out: list[str] = []
    for k in EXT_FIELDS:
        if k in ext:
            val = html.escape(str(ext[k]))
            out.append(
                f'<label class="ext"><span>externalIds.{k}</span>'
                f'<input type="text" name="ext_{k}" value="{val}"></label>'
            )
    return out


def _render_wp_inputs(providers: list[dict]) -> list[str]:
    """Inputs `wp_label_<i>` + `wp_url_<i>` pour chaque watchProvider."""
    out: list[str] = []
    for i, p in enumerate(providers):
        label = html.escape(p.get("label", ""))
        url = html.escape(p.get("url", ""))
        out.append(
            f'<label class="ext"><span>watchProviders[{label}]</span>'
            f'<input type="hidden" name="wp_label_{i}" value="{label}">'
            f'<input type="text" name="wp_url_{i}" value="{url}"'
            f' placeholder="(vider pour supprimer)"></label>'
        )
    return out


def _render_custom_links_section(custom: list[dict]) -> str:
    """Block <details> pour les customLinks + une ligne vide pour ajouter."""
    cl_rows: list[str] = []
    for i, link in enumerate([*custom, {"label": "", "url": "", "logoUrl": ""}]):
        lbl = html.escape(link.get("label", ""))
        url = html.escape(link.get("url", ""))
        logo = html.escape(link.get("logoUrl", "") or "")
        cl_rows.append(
            f'<div class="custom-link">'
            f'<input type="text" name="cl_label_{i}" value="{lbl}" '
            f'placeholder="Nom (ex. FNAC)">'
            f'<input type="url" name="cl_url_{i}" value="{url}" '
            f'placeholder="URL (https://…)">'
            f'<input type="url" name="cl_logo_{i}" value="{logo}" '
            f'placeholder="URL du logo (optionnel)">'
            f'</div>'
        )
    return (
        '<details><summary>Liens manuels (ajouts)</summary>'
        '<p class="hint">Liens ajoutés en plus des liens automatiques. La '
        'dernière ligne vide sert à en ajouter un nouveau. Vide le nom pour '
        'supprimer. Logo vide → favicon auto-détectée.</p>'
        '<div class="custom-links">' + "".join(cl_rows) + '</div>'
        '</details>'
    )


def _render_overrides_section(r: dict) -> str:
    """Block <details> pour les `linkOverrides` (URL exacte par plateforme)."""
    overrides = r.get("linkOverrides") or {}
    # `auto_urls_for` calque la résolution TS : Spotify/Deezer reçoivent le bon
    # suffixe selon le type courant (podcast → /shows ou /podcast).
    auto_urls = auto_urls_for(r)
    platform_labels: list[str] = []
    for t in r.get("types") or []:
        for p in AUTO_PLATFORMS_BY_TYPE.get(t, ()):
            if p not in platform_labels:
                platform_labels.append(p)
    # Labels présents dans les overrides mais hors miroir (M9 : type changé
    # après coup, label déprécié) → on les affiche quand même pour permettre
    # à l'utilisateur de les éditer/supprimer.
    for k in overrides:
        if k not in platform_labels:
            platform_labels.append(k)
    if not platform_labels:
        return ""

    # C1 (revue 2026-07-19) : le lien auto vient d'externalIds (website/deezer/
    # spotify/justwatch), potentiellement hostile (javascript:) → passer par
    # _safe_url avant le href. html.escape n'échappe PAS le schéma. Import local
    # pour éviter un cycle avec review_render_common (cf. _parse_guests plus bas).
    from review_render_common import _safe_url  # noqa: PLC0415

    def _row(p: str) -> str:
        auto = _safe_url(auto_urls.get(p) or auto_url(p, r))
        label_html = (
            f'<a class="ov-label" href="{html.escape(auto)}" target="_blank" '
            f'rel="noopener noreferrer" title="Ouvrir le lien auto-généré dans '
            f'un nouvel onglet">{html.escape(p)} ↗</a>'
        ) if auto else f'<span class="ov-label">{html.escape(p)}</span>'
        return (
            f'<div class="custom-link override">{label_html}'
            f'<input type="url" name="lo_{html.escape(p)}" '
            f'value="{html.escape(overrides.get(p, ""))}" '
            f'placeholder="Laisser vide = lien auto conservé">'
            f'</div>'
        )

    rows = "".join(_row(p) for p in platform_labels)
    return (
        '<details><summary>Modifier un lien automatique</summary>'
        '<p class="hint">Saisis ici l\'URL exacte d\'une fiche pour remplacer '
        'le lien de recherche auto-généré sur cette plateforme. Vide → on '
        'garde le lien auto.</p>'
        f'<div class="custom-links">{rows}</div>'
        '</details>'
    )


def _collect_recby_candidates(
    siblings: list[dict], ep: dict, hosts: list[str],
) -> list[str]:
    """Construit la liste de candidats pour le `<select name=recommendedBy>`.

    Hosts en tête (ordre saisi, dédup casse), puis invités de l'épisode.

    #3 — On délègue au SSOT `collect_guests` (comme les checkboxes de carte
    dans `review_render._reco_candidates`) : il unifie `ep.guests`,
    `ep.guestsParsed` (snapshot des épisodes migrés), le parsing du titre en
    fallback (épisodes legacy) et les `recommendedBy` des recos sœurs, tout
    en retirant `ep.guestsExcluded` (autorité) et les placeholders. Sans
    cette délégation, un épisode migré (invités seulement dans
    `guestsParsed`) n'exposait aucun invité dans le dropdown « Reco de ».
    """
    from review_guests import collect_guests, is_placeholder  # noqa: PLC0415
    from review_render_common import _parse_guests  # noqa: PLC0415

    # Fallback parsing du titre pour les épisodes pas encore migrés (aligné
    # sur `_reco_candidates`).
    parsed = (ep.get("guestsParsed")
              or _parse_guests(ep.get("title", ""), hosts))
    guests = collect_guests(ep, siblings, hosts, parsed=parsed)

    out: list[str] = []
    seen: set[str] = set()

    def _push(name: str) -> None:
        n = (name or "").strip()
        if not n or is_placeholder(n):
            return
        k = n.casefold()
        if k in seen:
            return
        seen.add(k)
        out.append(n)

    # Hosts d'abord (ordre stable attendu par l'UX), puis invités collectés
    # (déjà dédupés contre les hosts par collect_guests).
    for h in hosts:
        _push(h)
    for g in guests:
        _push(g)
    return out


def _render_recap(r: dict, ep: dict) -> str:
    """Bloc read-only en tête du form : timecode cliquable, quote, reco-de.

    Le calcul d'offset YT reproduit exactement celui de `_reco_card` dans
    `review_render.py` : si la reco a été extraite d'un transcript Acast,
    on additionne (youtubeDuration - audioDuration) pour compenser l'intro
    YouTube absente du flux Acast.
    """
    # Import différé pour éviter une dépendance circulaire avec review_render.
    from review_render import _embed_url, _fmt, _ts_seconds  # noqa: PLC0415
    from review_render_common import _safe_url  # noqa: PLC0415

    parts: list[str] = []
    secs = _ts_seconds(r.get("timestamp"))
    # m8/m9 (revue 2026-07-19) : parité avec `_yt_timecode_link_parts` — passer
    # youtubeUrl par `_safe_url` avant de dériver l'embed (convergence des gardes
    # d'URL rendues). `_embed_url` neutralise déjà via extraction d'ID, mais on
    # garde la garde explicite ici comme partout ailleurs côté rendu.
    yt = _safe_url(ep.get("youtubeUrl"))
    reco_src = r.get("transcriptSource") or "acast"
    if reco_src == "acast":
        # M1 (revue 2026-07-19) : _safe_int comme _reco_card — youtubeDuration
        # peut arriver en chaîne ("3700") ; sinon "3700" - 3600 lève TypeError et
        # rend le formulaire (GET /ep?edit ou /doutes?edit) inaccessible (500).
        from review_render_common import _safe_int  # noqa: PLC0415
        yt_offset = max(
            0, _safe_int(ep.get("youtubeDuration")) - _safe_int(ep.get("audioDuration"))
        )
    else:
        yt_offset = 0
    if yt and secs is not None:
        tv = max(0, secs + yt_offset)
        parts.append(
            f'<a class="tc" target="ytplayer" '
            f'href="{html.escape(_embed_url(yt, tv))}">'
            f'▶ {_fmt(secs)}</a>'
        )
    elif r.get("timestamp"):
        parts.append(
            f'<span class="tc off">⏱ {html.escape(r.get("timestamp", ""))}</span>'
        )
    recby = r.get("recommendedBy") or ""
    if recby:
        parts.append(
            f'<span class="recap-recby">Reco de : '
            f'<b>{html.escape(recby)}</b></span>'
        )
    head = " ".join(parts)
    quote = r.get("quote") or ""
    quote_html = (
        f'<blockquote class="recap-quote">« {html.escape(quote)} »</blockquote>'
        if quote else ""
    )
    if not head and not quote_html:
        return ""
    return f'<div class="edit-recap">{head}{quote_html}</div>'


def _render_recby_select(
    candidates: list[str], current: str, reco_id: str,
) -> str:
    """Dropdown `<select name=recommendedBy>` + champ libre.

    Si la valeur courante n'est pas dans la liste (ou contient des
    séparateurs « & », « , »), on l'ajoute en tête pour ne PAS la perdre
    silencieusement en pré-cochant l'option neutre.
    """
    options: list[str] = [f'<option value="">(personne)</option>']
    current_clean = (current or "").strip()
    # Si la valeur courante n'est dans aucun candidat, on l'ajoute en tête
    # pour qu'elle reste sélectionnée (sinon disparait en silence).
    pool: list[str] = list(candidates)
    if current_clean and not any(
        current_clean.casefold() == c.casefold() for c in candidates
    ):
        pool.insert(0, current_clean)
    for c in pool:
        sel = " selected" if c.casefold() == current_clean.casefold() else ""
        options.append(
            f'<option value="{html.escape(c)}"{sel}>{html.escape(c)}</option>'
        )
    select_html = (
        f'<label class="ext"><span>Reco de</span>'
        f'<select name="recommendedBy">{"".join(options)}</select></label>'
    )
    other_html = (
        f'<label class="ext"><span>… ou autre (hors liste)</span>'
        f'<input type="text" name="recommendedByOther" value="" '
        f'placeholder="nom de l\'invité·e ou autre"></label>'
    )
    return select_html + other_html


def render_edit_form(
    r: dict,
    ep: dict,
    siblings: list[dict] | None = None,
    hosts: list[str] | None = None,
    edit_origin: str = "/ep",
) -> str:
    """HTML du formulaire d'édition inline pour une reco.

    `siblings` : les autres recos du même épisode — sert à proposer leurs
    créateurs et leurs `recommendedBy` déjà saisis dans les datalists.
    `hosts`    : hôtes du podcast (Kyan, Navo…) — ajoutés en tête du
    dropdown « Reco de » pour qu'ils soient toujours proposés.
    """
    reco_id = r.get("id", "")
    guid = ep.get("guid", "")
    title = html.escape(r.get("title", ""))
    creator = html.escape(r.get("creator", "") or "")
    recommended_by_raw = r.get("recommendedBy", "") or ""
    current_types = set(r.get("types") or [])
    siblings = siblings or []
    hosts = hosts or []

    creators, creators_id, creators_dl = _render_creators_datalist(siblings, reco_id)
    recby_candidates = _collect_recby_candidates(siblings, ep, hosts)
    recby_block = _render_recby_select(recby_candidates, recommended_by_raw, reco_id)
    recap_block = _render_recap(r, ep)
    type_boxes = _render_type_boxes(current_types)
    ext_inputs = _render_ext_inputs(r.get("externalIds") or {})
    wp_inputs = _render_wp_inputs(r.get("watchProviders") or [])
    cl_block = _render_custom_links_section(r.get("customLinks") or [])
    ov_block = _render_overrides_section(r)
    details_block = ""
    if ext_inputs or wp_inputs:
        details_block = (
            '<details><summary>URLs stockées (avancé)</summary>'
            f'{"".join(ext_inputs)}{"".join(wp_inputs)}'
            '</details>'
        )
    details_block = ov_block + cl_block + details_block
    # M2 (revue 2026-07-19) : rester dans la file quand on édite depuis /doutes
    # (le save y retourne déjà via #M3 ; sans ça l'Annuler éjecte vers /ep).
    cancel = (f'/doutes?ep={urllib.parse.quote(guid)}' if edit_origin == "/doutes"
              else f'/ep?guid={urllib.parse.quote(guid)}')
    # Mode « artiste seul » : on remplace l'étiquette « Titre » par « Nom »
    # et on masque le champ Créateur — pour un artiste, le nom EST le titre.
    is_artist_only = (
        len(current_types) == 1 and "artiste" in current_types
    )
    title_label = "Nom" if is_artist_only else "Titre"
    creator_hidden = ' style="display:none"' if is_artist_only else ''
    # Type (Reco/Citation/Leur œuvre/Pas une reco) — UNIQUEMENT en édition depuis
    # /doutes : « Sauvegarder » applique alors le type choisi (la route /edit lit
    # `action`). Sans ça, corriger un titre ne permettait pas de classer la reco
    # en même temps (retour utilisateur 2026-07-24). Défaut = type actuel.
    type_radio_block = ""
    if edit_origin == "/doutes":
        cur_kind = "guest-work" if r.get("guestWork") else r.get("kind", "reco")
        default_action = (cur_kind if cur_kind in ("citation", "guest-work")
                          else "validate")
        _opts = (("validate", "⭐ Reco"), ("citation", "📝 Citation"),
                 ("guest-work", "🎭 Leur œuvre"), ("discard", "✕ Pas une reco"))
        _radios = "".join(
            f'<label class="sig-radio sig-radio-{v}"><input type="radio" '
            f'name="action" value="{v}"{" checked" if v == default_action else ""}> '
            f'{lbl}</label>' for v, lbl in _opts)
        type_radio_block = ('<fieldset class="sig-type"><legend>Type :</legend>'
                            f'{_radios}</fieldset>')
    return f"""
    <li class="row editing">
      {recap_block}
      <form class="edit-form" method="post" action="/edit">
        <input type="hidden" name="id" value="{html.escape(reco_id)}">
        <label class="ext"><span data-label="title">{title_label}</span>
          <input type="text" name="title" value="{title}" autofocus required></label>
        <label class="ext" data-label="creator-wrap"{creator_hidden}><span>Créateur</span>
          <input type="text" name="creator" value="{creator}"
            placeholder="auteur·rice, réalisateur·rice, artiste…"
            {f'list="{creators_id}"' if creators else ''}>
          {creators_dl}</label>
        {recby_block}
        <div class="types-box">{type_boxes}</div>
        {details_block}
        {type_radio_block}
        <div class="edit-actions">
          <a class="back" href="{html.escape(cancel)}">Annuler</a>
          <button type="submit">Sauvegarder</button>
        </div>
      </form>
    </li>"""


