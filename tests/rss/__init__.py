# `tests/rss/` ne doit PAS shadowiser `tools/rss/`. Quand pytest découvre
# ce __init__.py avec `pythonpath=["tools","tests"]`, le nom `rss`
# pointerait sur CE module (le dossier de tests) plutôt que sur le vrai
# package `tools/rss/`. On rebranche dynamiquement vers `tools/rss/`.
# Pattern identique à `tests/enrichment/__init__.py`.
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REAL = Path(__file__).resolve().parents[2] / "tools" / "rss" / "__init__.py"
_spec = importlib.util.spec_from_file_location(
    "rss", _REAL, submodule_search_locations=[str(_REAL.parent)],
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules["rss"] = _mod
_spec.loader.exec_module(_mod)
