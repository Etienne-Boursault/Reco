# Symétrique à `tests/rss/__init__.py` — rebranche `notify` vers le vrai
# package `tools/notify/` pour ne pas shadowiser.
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REAL = Path(__file__).resolve().parents[2] / "tools" / "notify" / "__init__.py"
_spec = importlib.util.spec_from_file_location(
    "notify", _REAL, submodule_search_locations=[str(_REAL.parent)],
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules["notify"] = _mod
_spec.loader.exec_module(_mod)
