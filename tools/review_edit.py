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

# Types de reco autorisés (mirror de domain.RecoType — gardé synchronisé).
RECO_TYPES: tuple[str, ...] = (
    "film", "serie", "livre", "bd",
    "musique", "album", "podcast", "jeu",
    "spectacle", "lieu", "artiste", "video", "autre",
)

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


def render_edit_form(r: dict, ep: dict) -> str:
    """HTML du formulaire d'édition inline pour une reco."""
    reco_id = r.get("id", "")
    guid = ep.get("guid", "")
    title = html.escape(r.get("title", ""))
    creator = html.escape(r.get("creator", "") or "")
    current_types = set(r.get("types") or [])
    type_boxes = "".join(
        f'<label><input type="checkbox" name="types" value="{t}"'
        f'{" checked" if t in current_types else ""}> {t}</label>'
        for t in RECO_TYPES
    )
    ext = r.get("externalIds") or {}
    ext_inputs = []
    for k in EXT_FIELDS:
        if k in ext:
            val = html.escape(str(ext[k]))
            ext_inputs.append(
                f'<label class="ext"><span>externalIds.{k}</span>'
                f'<input type="text" name="ext_{k}" value="{val}"></label>'
            )
    providers = r.get("watchProviders") or []
    wp_inputs = []
    for i, p in enumerate(providers):
        label = html.escape(p.get("label", ""))
        url = html.escape(p.get("url", ""))
        wp_inputs.append(
            f'<label class="ext"><span>watchProviders[{label}]</span>'
            f'<input type="hidden" name="wp_label_{i}" value="{label}">'
            f'<input type="text" name="wp_url_{i}" value="{url}"'
            f' placeholder="(vider pour supprimer)"></label>'
        )
    details_block = ""
    if ext_inputs or wp_inputs:
        details_block = (
            '<details><summary>URLs stockées (avancé)</summary>'
            f'{"".join(ext_inputs)}{"".join(wp_inputs)}'
            '</details>'
        )
    cancel = f'/ep?guid={urllib.parse.quote(guid)}'
    return f"""
    <li class="row editing">
      <form class="edit-form" method="post" action="/edit">
        <input type="hidden" name="id" value="{html.escape(reco_id)}">
        <label class="ext"><span>Titre</span>
          <input type="text" name="title" value="{title}" autofocus required></label>
        <label class="ext"><span>Créateur</span>
          <input type="text" name="creator" value="{creator}"
            placeholder="auteur·rice, réalisateur·rice, artiste…"></label>
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
    types_raw = data.get("types") or []
    types = list(dict.fromkeys(t for t in types_raw if t in RECO_TYPES))
    if not title or not types:
        return False, ""
    reco = read_json(path)
    guid = reco.get("episodeGuid", "")
    reco["title"] = title
    if creator:
        reco["creator"] = creator
    elif "creator" in reco:
        del reco["creator"]
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
        if label and url:
            new_providers.append({"label": label, "url": url})
    if new_providers:
        reco["watchProviders"] = new_providers
    elif "watchProviders" in reco:
        del reco["watchProviders"]
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
    # Imports paresseux : évite de charger requests/tmdb au démarrage du serveur.
    import requests  # noqa: PLC0415
    import enrich_music  # noqa: PLC0415
    import enrich_tmdb  # noqa: PLC0415

    title = reco.get("title", "?")
    statuses: list[str] = []
    parts: list[str] = []

    def _error_message(name: str, exc: Exception) -> str:
        """Message UI pour une exception remontée par un enricher."""
        # Import paresseux pour éviter une dépendance cyclique au chargement.
        from enrich_tmdb import TMDBAPIError  # noqa: PLC0415
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
