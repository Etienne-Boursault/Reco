"""
review_edit.py — Édition inline + ré-enrichissement (helpers de review_server).

Externalisé pour garder `review_server.py` sous la barre des 500 lignes.
"""
from __future__ import annotations

import html
import os
import re
import urllib.parse
from pathlib import Path

from common import log, read_json, write_json_if_changed
from review_links import AUTO_PLATFORMS_BY_TYPE

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


# m8/m9 (revue 2026-07-19) — schéma d'URL (RFC 3986 : ALPHA *( ALPHA / DIGIT /
# "+" / "-" / "." ) ":"). Sert à distinguer un externalId « URL » d'un ID opaque.
_URL_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.IGNORECASE)


def _is_https_url(url: str) -> bool:
    """True si `url` est une URL https:// (schéma insensible à la casse).

    m8/m9 — politique https-only PRÉSERVÉE : `javascript:`, `http://`, `data:`
    restent refusés ; seule la casse du schéma est tolérée (`HTTPS://x` est une
    URL https légitime qu'un `.startswith("https://")` strict rejetait à tort).
    """
    return url.lower().startswith("https://")


def _ext_value_ok(val: str) -> bool:
    """Valide un externalId à l'écriture (défense en profondeur, m8/m9).

    Un externalId est soit un identifiant opaque (tmdb=42, imdb=tt…, isbn…)
    soit une URL (website, deezer…). S'il PORTE un schéma d'URL, il ne peut
    être qu'`https://` — sinon un `javascript:`/`data:` stocké ici pourrait
    finir en href/src côté site public. Un ID sans schéma passe tel quel.
    """
    if _URL_SCHEME_RE.match(val):
        return _is_https_url(val)
    return True


def is_reenrichable(reco: dict) -> bool:
    """True si la reco a un type que TMDB ou Music sait traiter."""
    types = reco.get("types") or []
    return any(t in ("film", "serie", "musique", "album", "artiste") for t in types)


def apply_edit(path: Path, data: dict) -> tuple[bool, str]:
    """Applique POST /edit : valide, mute le JSON, écrit.

    Retourne (ok, guid) — ok=False si validation rejette.
    """
    title = (data.get("title") or [""])[0].strip()
    creator = (data.get("creator") or [""])[0].strip()
    # F2 : si le champ libre `recommendedByOther` est rempli, il prime sur
    # la valeur sélectionnée dans le dropdown. Permet de saisir un nom hors
    # liste sans repasser par la datalist (qui n'acceptait pas l'arbitraire).
    recommended_by_other = (data.get("recommendedByOther") or [""])[0].strip()
    recommended_by_select = (data.get("recommendedBy") or [""])[0].strip()
    recommended_by = recommended_by_other or recommended_by_select
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
                # m8/m9 (revue 2026-07-19) : garde https:// sur les externalIds
                # qui SONT des URLs (website/deezer/spotify… finissent en href
                # sur le site public). Un ID opaque (tmdb/imdb/isbn) passe.
                if not _ext_value_ok(val):
                    log.warning("externalId %s ignoré : URL non-https (%s)", k, val)
                    continue
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
        # L10 : refuse les URLs non-https (form HTML utilisateur). m8/m9 (revue
        # 2026-07-19) : garde insensible à la casse — `HTTPS://x` est une URL
        # https légitime qu'un `.startswith("https://")` strict rejetait à tort.
        # La politique reste https-only (`javascript:` etc. toujours refusés).
        if not _is_https_url(url):
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
        # m1 (revue 2026-07-19) : refuse les URLs non-https (parité avec les
        # watchProviders ci-dessus). Sans ça un `javascript:` passerait jusqu'au
        # `href` du site public (RecoCard.astro) → XSS. Critique avant la Task 5
        # (des agents écriront des customLinks). m8/m9 : garde casse-insensible.
        if not _is_https_url(url):
            log.warning("customLink ignoré : URL non-https (%s)", url)
            continue
        entry: dict = {"label": label, "url": url}
        # m2 (revue 2026-07-19) : le logo est rendu en <img src> sur le site
        # public → n'accepter qu'un https:// (garde de fond côté RecoCard).
        if logo and _is_https_url(logo):
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
        # m1 (revue 2026-07-19) : même garde https:// que customLinks/watchProviders.
        # m8/m9 : casse-insensible (parité, https-only préservé).
        if not _is_https_url(url):
            log.warning("Override ignoré : URL non-https (%s)", url)
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


# ---- Rétro-compat rendu du form (M4 découpe) ---------------------------------
# Le RENDU du formulaire (render_edit_form + helpers _render_*) vit désormais
# dans `review_edit_form.py`. Réexport LAZY (PEP 562) : imports directs et
# accès attributs continuent de fonctionner sans cycle à l'import.
_FORM_EXPORTS = frozenset({
    "_dedup_ci", "_render_creators_datalist", "_render_recommenders_datalist",
    "_render_type_boxes", "_render_ext_inputs", "_render_wp_inputs",
    "_render_custom_links_section", "_render_overrides_section",
    "_collect_recby_candidates", "_render_recap", "_render_recby_select",
    "render_edit_form",
})


def __getattr__(name: str):
    if name in _FORM_EXPORTS:
        import review_edit_form as _form  # noqa: PLC0415 — lazy, anti-cycle
        return getattr(_form, name)
    raise AttributeError(f"module 'review_edit' has no attribute {name!r}")
