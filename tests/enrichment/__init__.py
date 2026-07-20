# `tests/enrichment/` doit rester un dossier de tests, PAS un package shadow
# de `tools/enrichment`. Quand pytest découvre ce __init__.py avec
# `pythonpath=["tools","tests"]`, le nom `enrichment` pointe sur CE module.
# On rebranche dynamiquement vers le vrai package `tools/enrichment/`.
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

_REAL = Path(__file__).resolve().parents[2] / "tools" / "enrichment" / "__init__.py"
_spec = importlib.util.spec_from_file_location(
    "enrichment", _REAL, submodule_search_locations=[str(_REAL.parent)]
)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules["enrichment"] = _mod
_spec.loader.exec_module(_mod)
# Recharge les sous-modules à la demande via la machinerie standard.
