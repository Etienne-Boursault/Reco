"""enrich_audit.thresholds — seuils par défaut du package (CR senior M8).

Source unique de vérité pour les seuils des checks. Importés par les checks
ET par `cli_runner.default_service(...)` (qui les rend injectables CLI —
CR senior H4).

Pourquoi un module dédié ? Avant, les mêmes valeurs vivaient en quatre
endroits (constantes module / signatures par défaut / ADR / tests).
Toute modification demandait 4 modifs synchronisées : recette parfaite
pour les régressions silencieuses.
"""
from __future__ import annotations

from typing import Final

# --- title_similarity_check ------------------------------------------------

#: Ratio Levenshtein normalisé minimum pour considérer deux titres "proches".
#: Calibré sur dataset un-bon-moment + corpus test (cf. `test_corpus_reference`).
DEFAULT_TITLE_THRESHOLD: Final[float] = 0.7

# --- year_mismatch_check ---------------------------------------------------

#: Tolérance ± années entre `Item.year` et TMDB release/first_air_date.
#: 1 an absorbe les sorties multi-pays décalées (US/FR).
DEFAULT_YEAR_TOLERANCE: Final[int] = 1

# --- runtime_coherence_check (CR senior H2/H3) -----------------------------

#: Runtime minimum d'un film (en minutes). En dessous → court probable.
#: Abaissé de 40 à 20 pour réduire les faux positifs court-métrages
#: éditoriaux (Maupassant, Pixar, etc. — CR senior H3).
DEFAULT_FILM_MIN_RUNTIME: Final[int] = 20

#: Runtime maximum d'un épisode de série (en minutes). Au-dessus → TV-movie
#: probable. Abaissé de 240 à 180 (CR senior H2).
DEFAULT_SERIES_EPISODE_MAX_RUNTIME: Final[int] = 180

#: Runtime minimum d'un épisode de série (en minutes). En dessous → cartoon
#: court / sketch matché par erreur comme série (CR senior H2).
DEFAULT_SERIES_EPISODE_MIN_RUNTIME: Final[int] = 8


__all__ = [
    "DEFAULT_FILM_MIN_RUNTIME",
    "DEFAULT_SERIES_EPISODE_MAX_RUNTIME",
    "DEFAULT_SERIES_EPISODE_MIN_RUNTIME",
    "DEFAULT_TITLE_THRESHOLD",
    "DEFAULT_YEAR_TOLERANCE",
]
