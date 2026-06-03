"""
review_edit.py — Édition inline + ré-enrichissement (helpers de review_server).

Externalisé pour garder `review_server.py` sous la barre des 500 lignes.
"""
from __future__ import annotations

import html
import os
import urllib.parse
from pathlib import Path

from common import log, read_json, write_json_if_changed
from review_links import AUTO_PLATFORMS_BY_TYPE, auto_url, auto_urls_for

# Types de reco autorisés (mirror de domain.RecoType — gardé synchronisé).
RECO_TYPES: tuple[str, ...] = (
    "film", "serie", "livre", "bd",
    "musique", "album", "podcast", "jeu",
    "spectacle", "lieu", "artiste", "video", "autre",
)


# Emoji par type, miroir de src/utils/recoTypes.ts (TYPE_EMOJIS).
TYPE_EMOJIS: dict[str, str] = {
    "film": "🎬", "serie": "📺", "livre": "📖", "bd": "💭",
    "musique": "🎵", "album": "💿", "podcast": "🎙️", "jeu": "🎮",
    "spectacle": "🎭", "lieu": "📍", "artiste": "🎤",
    "video": "📹", "autre": "✨",
}

# Libellés humains par type, miroir de src/utils/recoTypes.ts (TYPE_LABELS).
TYPE_LABELS: dict[str, str] = {
    "film": "Film", "serie": "Série", "livre": "Livre", "bd": "BD",
    "musique": "Musique", "album": "Album", "podcast": "Podcast", "jeu": "Jeu",
    "spectacle": "Spectacle", "lieu": "Lieu", "artiste": "Artiste",
    "video": "Vidéo", "autre": "Autre",
}


def render_type_badges(types: list[str]) -> str:
    """HTML des badges emoji pour une liste de types (title= = libellé)."""
    parts = []
    for t in types:
        emoji = TYPE_EMOJIS.get(t, "✨")
        label = TYPE_LABELS.get(t, t)
        parts.append(
            f'<span class="type-emoji" title="{html.escape(label)}" '
            f'aria-label="{html.escape(label)}">{emoji}</span>'
        )
    return "".join(parts)

# Champs `externalIds` exposés dans le formulaire d'édition inline.
EXT_FIELDS: tuple[str, ...] = (
    "tmdb", "imdb", "isbn", "musicbrainz",
    "youtube", "instagram", "website",
    "justwatch", "deezer", "spotify",
)


def is_reenrichable(reco: dict) -> bool:
    """True si la reco a un type que TMDB ou Music sait traiter."""
    types = reco.get("types") or []
    return any(t in ("film", "serie", "musique", "album", "artiste") for t in types)


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

    def _row(p: str) -> str:
        auto = auto_urls.get(p) or auto_url(p, r)
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


def render_edit_form(
    r: dict,
    ep: dict,
    siblings: list[dict] | None = None,
    hosts: list[str] | None = None,
) -> str:
    """HTML du formulaire d'édition inline pour une reco.

    `siblings` : les autres recos du même épisode — sert à proposer leurs
    créateurs et leurs `recommendedBy` déjà saisis dans les datalists.
    `hosts`    : hôtes du podcast (Kyan, Navo…) — ajoutés à la datalist
    « Reco de » pour qu'ils soient toujours proposés.
    """
    reco_id = r.get("id", "")
    guid = ep.get("guid", "")
    title = html.escape(r.get("title", ""))
    creator = html.escape(r.get("creator", "") or "")
    recommended_by = html.escape(r.get("recommendedBy", "") or "")
    current_types = set(r.get("types") or [])
    siblings = siblings or []
    hosts = hosts or []

    creators, creators_id, creators_dl = _render_creators_datalist(siblings, reco_id)
    recommenders, rec_id, rec_dl = _render_recommenders_datalist(siblings, hosts, reco_id)
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
    cancel = f'/ep?guid={urllib.parse.quote(guid)}'
    return f"""
    <li class="row editing">
      <form class="edit-form" method="post" action="/edit">
        <input type="hidden" name="id" value="{html.escape(reco_id)}">
        <label class="ext"><span>Titre</span>
          <input type="text" name="title" value="{title}" autofocus required></label>
        <label class="ext"><span>Créateur</span>
          <input type="text" name="creator" value="{creator}"
            placeholder="auteur·rice, réalisateur·rice, artiste…"
            {f'list="{creators_id}"' if creators else ''}>
          {creators_dl}</label>
        <label class="ext"><span>Reco de</span>
          <input type="text" name="recommendedBy" value="{recommended_by}"
            placeholder="Kyan, Navo, ou nom de l'invité·e…"
            {f'list="{rec_id}"' if recommenders else ''}>
          {rec_dl}</label>
        <div class="types-box">{type_boxes}</div>
        {details_block}
        <div class="edit-actions">
          <a class="back" href="{html.escape(cancel)}">Annuler</a>
          <button type="submit">Sauvegarder</button>
        </div>
      </form>
    </li>"""


def apply_edit(path: Path, data: dict) -> tuple[bool, str]:
    """Applique POST /edit : valide, mute le JSON, écrit.

    Retourne (ok, guid) — ok=False si validation rejette.
    """
    title = (data.get("title") or [""])[0].strip()
    creator = (data.get("creator") or [""])[0].strip()
    recommended_by = (data.get("recommendedBy") or [""])[0].strip()
    types_raw = data.get("types") or []
    types = list(dict.fromkeys(t for t in types_raw if t in RECO_TYPES))
    if not title:
        log.warning("Edit refusé : titre vide")
        return False, ""
    if not types:
        log.warning("Edit refusé : types vides ou inconnus (raw=%s)", types_raw)
        return False, ""
    reco = read_json(path)
    guid = reco.get("episodeGuid", "")
    reco["title"] = title
    if creator:
        reco["creator"] = creator
    elif "creator" in reco:
        del reco["creator"]
    if recommended_by:
        reco["recommendedBy"] = recommended_by
    elif "recommendedBy" in reco:
        del reco["recommendedBy"]
    reco["types"] = types
    ext = dict(reco.get("externalIds") or {})
    for k in EXT_FIELDS:
        field = f"ext_{k}"
        if field in data:
            val = (data.get(field) or [""])[0].strip()
            if val:
                ext[k] = val
            elif k in ext:
                del ext[k]
    if ext:
        reco["externalIds"] = ext
    elif "externalIds" in reco:
        del reco["externalIds"]
    new_providers: list[dict] = []
    indices = sorted({
        int(k.split("_")[-1]) for k in data
        if k.startswith("wp_label_") and k.split("_")[-1].isdigit()
    })
    for i in indices:
        label = (data.get(f"wp_label_{i}") or [""])[0].strip()
        url = (data.get(f"wp_url_{i}") or [""])[0].strip()
        if not (label and url):
            continue
        # L10 : refuse les URLs non-https (form HTML utilisateur).
        if not url.startswith("https://"):
            log.warning("watchProvider ignoré : URL non-https (%s)", url)
            continue
        new_providers.append({"label": label, "url": url})
    if new_providers:
        reco["watchProviders"] = new_providers
    elif "watchProviders" in reco:
        del reco["watchProviders"]
    # --- customLinks : libellé vide ou URL vide → ligne ignorée. ---
    cl_indices = sorted({
        int(k.split("_")[-1]) for k in data
        if k.startswith("cl_label_") and k.split("_")[-1].isdigit()
    })
    new_links: list[dict] = []
    for i in cl_indices:
        label = (data.get(f"cl_label_{i}") or [""])[0].strip()
        url = (data.get(f"cl_url_{i}") or [""])[0].strip()
        logo = (data.get(f"cl_logo_{i}") or [""])[0].strip()
        if not label or not url:
            continue
        entry: dict = {"label": label, "url": url}
        if logo:
            entry["logoUrl"] = logo
        new_links.append(entry)
    if new_links:
        reco["customLinks"] = new_links
    elif "customLinks" in reco:
        del reco["customLinks"]
    # --- linkOverrides : map label → URL. Vide = pas d'override. ---
    # Contrat : seuls les labels présents dans AUTO_PLATFORMS_BY_TYPE (miroir
    # de merchants.ts) sont acceptés. Tout autre `lo_<label>` est ignoré
    # silencieusement (log.warning). Labels = ASCII + espace + '.'.
    known_labels: set[str] = {
        label for labels in AUTO_PLATFORMS_BY_TYPE.values() for label in labels
    }
    new_overrides: dict[str, str] = {}
    for key, vals in data.items():
        if not key.startswith("lo_"):
            continue
        label = key[3:]
        url = (vals[0] if vals else "").strip()
        if not url:
            continue
        if label not in known_labels:
            log.warning("Override ignoré : label inconnu « %s »", label)
            continue
        new_overrides[label] = url
    if new_overrides:
        reco["linkOverrides"] = new_overrides
    elif "linkOverrides" in reco:
        del reco["linkOverrides"]
    write_json_if_changed(path, reco)
    return True, guid


def _kind_for(statuses: list[str]) -> str:
    """Détermine le 'kind' du flash à partir des statuts collectés.

    Ordre de priorité (pire au mieux) : error > not_found > ok > info.
    """
    if "error" in statuses:
        return "error"
    if "not_found" in statuses:
        return "warning"
    if "ok" in statuses:
        return "success"
    return "info"


def apply_reenrich(path: Path, reco_id: str) -> tuple[str, str, str]:
    """Applique POST /reenrich : appelle les enrichers applicables, écrit.

    Retourne (guid, summary, kind) :
      - guid     : pour la redirection PRG
      - summary  : ex. "TMDB : trouvé · Music : non trouvé" (lisible UI)
      - kind     : 'success' | 'warning' | 'error' | 'info' (pour styler le flash)

    Tolère les exceptions des APIs externes (loggue, statut 'error' dans le
    flash, mais ne lève pas).
    """
    reco = read_json(path)
    guid = reco.get("episodeGuid", "")
    # Imports paresseux groupés : évite de charger requests/tmdb au démarrage
    # du serveur (gain de ~150ms à l'import). On les fait tous au même endroit
    # pour la lisibilité, plus de re-import dans la closure _error_message.
    import requests  # noqa: PLC0415
    import enrich_music  # noqa: PLC0415
    import enrich_tmdb  # noqa: PLC0415
    from enrich_tmdb import TMDBAPIError  # noqa: PLC0415

    title = reco.get("title", "?")
    statuses: list[str] = []
    parts: list[str] = []

    def _error_message(name: str, exc: Exception) -> str:
        """Message UI pour une exception remontée par un enricher."""
        if isinstance(exc, TMDBAPIError):
            code = exc.status_code
            if code == 401:
                return f"{name} : clé API invalide"
            if code == 429:
                return f"{name} : rate-limit (HTTP 429)"
            if code is not None:
                return f"{name} : erreur API (HTTP {code})"
            # Erreur réseau (timeout, DNS) — pas de code HTTP.
            return f"{name} : erreur réseau ({exc.__class__.__name__})"
        return f"{name} : erreur ({exc.__class__.__name__})"

    def _run(name: str, fn):
        """Lance un enricher, collecte status + texte humain pour le flash."""
        try:
            fn()
            status = reco.pop("_enrich_status", None) or "ok"
            log.info("Ré-enrichi (%s) %s : %s", name, reco_id, status)
            statuses.append(status)
            if status == "ok":
                parts.append(f"{name} : « {title} » trouvée")
            else:
                parts.append(f"{name} : « {title} » non trouvée")
        except Exception as exc:  # noqa: BLE001
            reco.pop("_enrich_status", None)
            log.warning("Ré-enrich %s %s a échoué : %s", name, reco_id, exc)
            statuses.append("error")
            parts.append(_error_message(name, exc))

    session = requests.Session()
    try:
        if enrich_tmdb.is_targetable(reco):
            _run("TMDB", lambda: enrich_tmdb.enrich_one(
                reco, session=session,
                api_key=os.environ.get("TMDB_API_KEY"),
                force=True,
            ))
        if enrich_music.is_targetable(reco):
            _run("Music", lambda: enrich_music.enrich_one(
                reco, session=session,
                spotify_token=None, force=True,
            ))
    finally:
        session.close()
    reco.pop("_enrich_status", None)
    write_json_if_changed(path, reco)

    if not parts:
        return guid, "Aucun enricher applicable pour ces types.", "info"
    return guid, " · ".join(parts), _kind_for(statuses)
