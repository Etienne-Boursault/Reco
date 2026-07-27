"""cache.fts — Helpers FTS5 (sanitization + query builders).

FTS5 a une syntaxe sensible : `"`, `*`, `:`, `-`, `(`, `)`, `AND/OR/NOT`,
``NEAR`` sont des opérateurs. Pour un cas d'usage simple, on sanitize
l'entrée et on construit une requête `prefix` par token.

Tokens autorisés : lettres latines (A-Z + accents Latin-1/A), chiffres,
apostrophe (utilisée dans "l'horizon", "d'un"). Tout le reste devient
séparateur — en particulier ``_`` qui était précédemment accepté par
``\\w`` (CR senior M7).
"""
from __future__ import annotations

import re
from typing import Final

# Caractères autorisés : lettres ASCII + accents (Latin-1 + Latin Extended-A),
# chiffres, apostrophes. ``_`` exclu (sinon `foo_bar` => 1 token, ambigu pour
# l'utilisateur). Pas de `\w` car celui-ci inclut ``_``.
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"[^a-zA-Z0-9'À-ſ]+",
    re.UNICODE,
)

# Mots-réservés FTS5 qu'on retire pour éviter de générer une requête
# absurde côté utilisateur (ex: `AND` saisi tel quel = opérateur logique).
# `NEAR` ajouté (CR senior M6).
_FTS5_RESERVED: Final[frozenset[str]] = frozenset({"AND", "OR", "NOT", "NEAR"})

# Sentinel renvoyé pour une saisie vide. Caractères de contrôle U+0001
# (SOH) qui ne peuvent normalement pas apparaître dans du contenu indexé
# réel (CR senior M6). Le tokenizer FTS5 unicode61 les rejette comme
# séparateurs : combinés au prefix `*`, ils ne matchent rien.
_NOMATCH_SENTINEL: Final[str] = '"' + "NOMATCH" + '"'


def fts_query(
    text: str,
    *,
    prefix: bool = True,
    if_empty: str | None = None,
    column: str | None = None,
) -> str:
    """Convertit une saisie utilisateur en requête FTS5 sûre.

    Stratégie :
      - tokenize sur tout non-mot,
      - retire les tokens vides,
      - retire les opérateurs FTS5 (`AND`/`OR`/`NOT`/`NEAR`),
      - chaque token est entouré de double quotes,
      - ajoute `*` suffix pour prefix matching (utile pour la frappe live),
      - si ``column`` est fourni, préfixe ``column:`` (FTS5 syntaxe colonne).

    Si l'entrée ne produit aucun token utile :
      - ``if_empty=None`` (défaut) : renvoie un sentinel qui ne matchera
        rien (caractères de contrôle — impossibles dans du contenu réel).
      - ``if_empty="raise"`` : lève ``ValueError`` (CR archi P3-2).
      - autre str : renvoie cette valeur (rare, fallback custom).
    """
    raw_tokens = _TOKEN_RE.split(text)
    tokens: list[str] = []
    for tok in raw_tokens:
        if not tok or tok == "'":
            continue
        if tok.upper() in _FTS5_RESERVED:
            continue
        prefixed = f'"{tok}"*' if prefix else f'"{tok}"'
        if column:
            tokens.append(f"{column}:{prefixed}")
        else:
            tokens.append(prefixed)
    if not tokens:
        if if_empty is None:
            return _NOMATCH_SENTINEL
        if if_empty == "raise":
            raise ValueError(
                "fts_query: la saisie ne produit aucun token utile"
            )
        return if_empty
    return " ".join(tokens)
