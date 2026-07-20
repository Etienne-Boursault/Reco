"""Check #1 — Similarité titre item ↔ titres TMDB.

Stratégie :
  1. Normalise les deux titres (NFKC + casefold + map œ/æ/ß + strip
     ponctuation + collapse whitespace).
  2. Calcule un ratio Levenshtein normalisé via :stdlib:`difflib.Sequence
     Matcher` (pas de dépendance externe — `python-Levenshtein` n'est
     pas installé).
  3. **Prend le ratio MAXIMUM sur l'union des titres TMDB** (original_title,
     title, original_name, name) — CR senior H1 : sinon une œuvre publiée
     sous titre FR (`title`) et titre original étranger (`original_title`)
     produit un faux mismatch.
  4. Si ratio max < seuil → suspicion.

Pure — aucune IO.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from domain.item import Item

from .thresholds import DEFAULT_TITLE_THRESHOLD
from .types import Severity, Suspicion, TmdbPayload

_RE_PUNCT = re.compile(r"[^\w\s]", flags=re.UNICODE)
_RE_WS = re.compile(r"\s+")

# CR senior L1 : NFKD perd œ/æ/ß. On les mappe manuellement avant NFKC.
_LIGATURE_MAP: dict[str, str] = {
    "œ": "oe", "Œ": "OE",
    "æ": "ae", "Æ": "AE",
    "ß": "ss",
}


def _normalize(text: str) -> str:
    """Casefold + drop accents + drop ponctuation + collapse whitespace.

    Robuste sur ligatures (`œ`/`æ`/`ß`) via mapping explicite préalable
    (NFKD/NFKC ne les décompose pas).
    """
    for src, dst in _LIGATURE_MAP.items():
        if src in text:
            text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = _RE_PUNCT.sub(" ", text)
    text = _RE_WS.sub(" ", text).strip()
    return text


def _iter_tmdb_titles(tmdb_data: TmdbPayload) -> list[str]:
    """Retourne TOUS les titres TMDB exploitables (CR senior H1).

    Préserve l'ordre déclaratif pour faciliter le debug, mais le caller
    prendra le ratio max sur l'ensemble.
    """
    titles: list[str] = []
    for key in ("original_title", "title", "original_name", "name"):
        val = tmdb_data.get(key)
        if isinstance(val, str) and val.strip():
            titles.append(val.strip())
    return titles


def check_title_similarity(
    item: Item,
    tmdb_data: TmdbPayload,
    threshold: float = DEFAULT_TITLE_THRESHOLD,
) -> Suspicion | None:
    """Renvoie une `Suspicion` si la similarité titre tombe sous `threshold`.

    Args:
        item: Item à auditer.
        tmdb_data: dict brut TMDB (movie ou tv).
        threshold: ratio min ∈ [0,1]. Default :data:`DEFAULT_TITLE_THRESHOLD`.

    Returns:
        ``None`` si proche ou si TMDB n'a pas de titre exploitable.
    """
    tmdb_titles = _iter_tmdb_titles(tmdb_data)
    if not tmdb_titles:
        return None

    a = _normalize(item.title)
    ratios = [
        (SequenceMatcher(None, a, _normalize(t)).ratio(), t)
        for t in tmdb_titles
    ]
    best_ratio, best_title = max(ratios, key=lambda rt: rt[0])
    if best_ratio >= threshold:
        return None
    return Suspicion(
        kind="title_mismatch",
        detail=(
            f"Titre item « {item.title} » diverge de TMDB « {best_title} » "
            f"(ratio max={best_ratio:.2f} < seuil {threshold:.2f}, "
            f"essayés={len(tmdb_titles)} titres)"
        ),
        severity=Severity.WARNING,
        confidence=1.0 - best_ratio,
    )


# Check Protocol metadata (CR archi P0 #1).
check_title_similarity.name = "title_similarity"  # type: ignore[attr-defined]
check_title_similarity.kind = "title_mismatch"  # type: ignore[attr-defined]
check_title_similarity.description = (  # type: ignore[attr-defined]
    "Compare le titre de l'Item à tous les titres TMDB (original/locaux, "
    "movie/tv) et prend le ratio maximum."
)


__all__ = ["check_title_similarity"]
