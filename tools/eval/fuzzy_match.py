"""Match approximatif entre une reco attendue (golden) et une reco extraite.

Fonctions pures, sans état, faciles à tester unitairement.

Stratégie :
  1. Normalisation : NFKC + casefold + suppression diacritiques + retrait
     ponctuation Unicode (catégories P*) + collapse espaces.
  2. ``difflib.SequenceMatcher`` sur les titres normalisés.
  3. Bonus/malus créateur (paramétré via ``EvalConfig``).

Le score créateur ne tire pas le score titre vers le bas s'il est absent
(``None``) : on ne pénalise pas l'incomplétude des golden sets.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Final

from tools.eval.types import (
    DEFAULT_CREATOR_BOOST,
    DEFAULT_CREATOR_BOOST_THRESHOLD,
    DEFAULT_CREATOR_PENALTY,
    DEFAULT_CREATOR_PENALTY_THRESHOLD,
    EvalConfig,
)

__all__ = ["fuzzy_match_score", "normalize_text"]


_WS_RE: Final[re.Pattern[str]] = re.compile(r"\s+")


def normalize_text(text: str | None) -> str:
    """Normalise pour comparaison : NFKC + casefold + sans diacritiques
    + sans ponctuation Unicode + espaces compactés.

    Retourne ``""`` si ``text`` est ``None``, vide, ou ne contient que
    de la ponctuation/whitespace.
    """
    if not text:
        return ""
    # NFKC : unifie compatibilité (« œ » → « œ » conservé, demi-largeur → pleine)
    normalized = unicodedata.normalize("NFKC", text)
    # Décompose pour virer les diacritiques (catégorie Mn).
    decomposed = unicodedata.normalize("NFKD", normalized)
    # casefold : lowercase étendu (ß → ss, etc.) — plus robuste que .lower().
    folded = decomposed.casefold()
    out_chars: list[str] = []
    for ch in folded:
        cat = unicodedata.category(ch)
        if cat.startswith("M"):           # marques de combinaison (diacritiques)
            continue
        if cat.startswith("P") or cat.startswith("S"):  # ponctuation / symboles
            out_chars.append(" ")
            continue
        out_chars.append(ch)
    collapsed = _WS_RE.sub(" ", "".join(out_chars)).strip()
    return collapsed


def _string_similarity(a: str, b: str) -> float:
    """Similarité Ratcliff/Obershelp ∈ [0, 1]. Suppose ``a`` et ``b`` non vides."""
    return SequenceMatcher(None, a, b).ratio()


def fuzzy_match_score(
    a_title: str,
    a_creator: str | None,
    b_title: str,
    b_creator: str | None,
    *,
    config: EvalConfig | None = None,
) -> float:
    """Score de similarité ∈ [0, 1] entre deux recos.

    Args:
        a_title, b_title: titres des recos à comparer.
        a_creator, b_creator: créateurs (optionnels).
        config: configuration injectée. Si ``None``, valeurs par défaut.

    Returns:
        Score ∈ [0, 1]. 0 si les deux titres se normalisent en vide.
    """
    cfg = config or EvalConfig()
    title_a = normalize_text(a_title)
    title_b = normalize_text(b_title)
    if not title_a and not title_b:
        return 0.0
    title_score = _string_similarity(title_a, title_b)

    norm_a_creator = normalize_text(a_creator)
    norm_b_creator = normalize_text(b_creator)
    if norm_a_creator and norm_b_creator:
        creator_score = _string_similarity(norm_a_creator, norm_b_creator)
        if creator_score >= cfg.creator_boost_threshold:
            title_score = min(
                1.0, title_score + cfg.creator_boost * creator_score,
            )
        elif creator_score < cfg.creator_penalty_threshold:
            title_score = max(0.0, title_score - cfg.creator_penalty)

    return title_score


# --- Réexports pour rétrocompat — éviter cycles d'import -------------------
_ = (DEFAULT_CREATOR_BOOST, DEFAULT_CREATOR_BOOST_THRESHOLD,
     DEFAULT_CREATOR_PENALTY, DEFAULT_CREATOR_PENALTY_THRESHOLD)
