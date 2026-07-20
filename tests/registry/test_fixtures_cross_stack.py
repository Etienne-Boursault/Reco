"""R-P2-06 — Fixtures golden cross-stack (côté Python).

Mêmes JSON consommés que `tests/registry/test_fixtures_cross_stack.test.ts`.
Garantit la parité de comportement entre les deux validateurs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from meta.validator import RegistryValidationError, validate_registry

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "registry"


@pytest.mark.parametrize(
    "path",
    sorted((FIXTURES_ROOT / "valid").glob("*.json")),
    ids=lambda p: p.name,
)
def test_valid_fixture(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    validate_registry(raw)


@pytest.mark.parametrize(
    "path",
    sorted((FIXTURES_ROOT / "invalid").glob("*.json")),
    ids=lambda p: p.name,
)
def test_invalid_fixture(path: Path) -> None:
    raw = json.loads(path.read_text(encoding="utf-8"))
    with pytest.raises(RegistryValidationError):
        validate_registry(raw)
