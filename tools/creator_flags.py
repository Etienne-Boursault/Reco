"""creator_flags.py — Signalements « situation de l'artiste » (côté relecture).

Lit le MÊME fichier curé que le site public — ``src/data/creator-flags.json`` —
et expose une recherche par nom de créateur + un rendu HTML de badge ⚠️ pour
l'outil de relecture (/doutes, /ep). Normalisation identique à
``src/data/creatorFlags.ts``.

N'invente RIEN : n'affiche que ce qui est déclaré et sourcé dans le fichier. Le
fichier est curé à la main (cf. ``src/data/creator-flags.README.md``).
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
from pathlib import Path

from common import TOOLS_DIR, log

_FLAGS_PATH: Path = TOOLS_DIR.parent / "src" / "data" / "creator-flags.json"

# Cache indexé sur la mtime : le fichier est curé à la main et change rarement,
# mais on veut que l'édition soit prise en compte sans redémarrer le serveur.
_cache: dict = {"mtime": None, "index": {}}


def _norm(s: str | None) -> str:
    """Minuscules, sans accents ni ponctuation (aligné sur creatorFlags.ts)."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _build_index() -> dict[str, dict]:
    try:
        data = json.loads(_FLAGS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        log.warning("creator-flags.json illisible (%s) — signalements ignorés", exc)
        return {}
    index: dict[str, dict] = {}
    for flag in data.get("flags") or []:
        names = flag.get("names")
        if not isinstance(names, list) or not flag.get("situation") \
                or not flag.get("source"):
            continue
        for name in names:
            key = _norm(name)
            if key and key not in index:  # première déclaration gagne
                index[key] = flag
    return index


def _index() -> dict[str, dict]:
    try:
        mtime = _FLAGS_PATH.stat().st_mtime_ns
    except OSError:
        return {}
    if _cache["mtime"] != mtime:
        _cache["index"] = _build_index()
        _cache["mtime"] = mtime
    return _cache["index"]


def flag_for(creator: str | None) -> dict | None:
    """Signalement pour un créateur, ou None si aucun."""
    if not creator:
        return None
    return _index().get(_norm(creator))


def _safe_http(url: str) -> bool:
    return url.startswith(("https://", "http://"))


def flag_badge_html(creator: str | None) -> str:
    """Badge ⚠️ + bulle (situation + source) pour l'UI de relecture. Chaîne vide
    si le créateur n'est pas signalé. <details> : la source reste cliquable."""
    flag = flag_for(creator)
    if not flag:
        return ""
    sev = flag.get("severity") or "accusation"
    situation = html.escape(str(flag.get("situation", "")))
    source = str(flag.get("source", ""))
    label = ("Créateur condamné — voir la situation"
             if sev == "condamnation"
             else "Créateur mis en cause — voir la situation")
    src_html = ""
    if source and _safe_http(source):
        src_html = (f'<a class="cflag-src" href="{html.escape(source)}" '
                    f'target="_blank" rel="noopener noreferrer">Source ↗</a>')
    return (
        f'<details class="cflag" data-severity="{html.escape(sev)}">'
        f'<summary title="{html.escape(label)}" '
        f'aria-label="{html.escape(label)}">⚠️</summary>'
        f'<div class="cflag-panel"><p class="cflag-sit">{situation}</p>'
        f'{src_html}</div></details>'
    )
