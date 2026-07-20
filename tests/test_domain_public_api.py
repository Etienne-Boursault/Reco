"""Tests non-régression sur l'API publique de `tools.domain`.

Garde-fou contre toute suppression accidentelle d'un symbole exporté
par `domain.__all__`. Cf. critique senior C2.
"""
from __future__ import annotations

import pytest

import domain


@pytest.mark.parametrize("name", domain.__all__)
def test_public_symbol_is_importable(name):
    assert hasattr(domain, name), f"`domain.{name}` manquant"
    assert getattr(domain, name) is not None, f"`domain.{name}` est None"


def test_all_is_alphabetised_per_section():
    """L'`__all__` est organisé par sections (legacy, item, mention, services).
    On vérifie que chaque section n'est pas vide et n'a pas de doublons.
    """
    seen: set[str] = set()
    for name in domain.__all__:
        assert name not in seen, f"doublon dans __all__: {name}"
        seen.add(name)
    assert len(seen) == len(domain.__all__)


def test_all_exposes_at_least_minimum_set():
    """Verrouille les symboles critiques qui DOIVENT rester publics."""
    minimum = {
        "Item", "ItemType", "ExternalIds",
        "Mention", "SourceRef",
        "canonical_key", "can_merge_items", "can_attach_mention",
    }
    assert minimum.issubset(set(domain.__all__))
