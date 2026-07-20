"""Tests pour la migration placeholder `item.v1_to_v2`.

C'est un no-op de démonstration : la donnée traverse inchangée à
l'exception du champ `schemaVersion` qui passe de 1 à 2. Sert de
template pour les vraies migrations futures.
"""
from __future__ import annotations

import pytest

from migrations.item.v1_to_v2 import V1ToV2Migration


def test_metadata_advertises_v1_to_v2_for_item():
    """Les attributs de classe annoncent correctement la transition."""
    assert V1ToV2Migration.SOURCE_VERSION == 1
    assert V1ToV2Migration.TARGET_VERSION == 2
    assert V1ToV2Migration.ENTITY == "item"


def test_v1_data_is_unchanged_passing_through_v2():
    """Migrer v1 → v2 préserve la donnée (no-op placeholder)."""
    mig = V1ToV2Migration()
    src = {
        "id": "abc123",
        "schemaVersion": 1,
        "title": "Foo",
        "types": ["film"],
        "creator": "Quelqu'un",
    }
    out = mig.migrate_one(src)
    # Le champ schemaVersion est bumpé, le reste est strictement préservé.
    assert out["schemaVersion"] == 2
    for key in ("id", "title", "types", "creator"):
        assert out[key] == src[key]


def test_schema_version_bumped_to_2():
    """Même si l'entrée n'a pas de `schemaVersion`, la sortie le pose à 2."""
    mig = V1ToV2Migration()
    out = mig.migrate_one({"id": "x", "title": "T", "types": ["livre"]})
    assert out["schemaVersion"] == 2


def test_migrate_one_returns_a_new_dict_not_mutating_input():
    """Pureté : `migrate_one` ne mute pas le dict en entrée."""
    mig = V1ToV2Migration()
    src = {"id": "x", "title": "T", "types": ["film"], "schemaVersion": 1}
    snap = dict(src)
    _ = mig.migrate_one(src)
    assert src == snap, "migrate_one a muté son argument d'entrée"


def test_refuses_input_with_wrong_source_version():
    """Si la donnée n'est pas à v1, on lève (le runner doit chaîner avant)."""
    mig = V1ToV2Migration()
    with pytest.raises(ValueError):
        mig.migrate_one({"id": "x", "title": "T", "types": ["film"], "schemaVersion": 2})


def test_mention_v1_to_v2_refuses_wrong_source_version():
    """Idem pour le placeholder Mention."""
    from migrations.mention.v1_to_v2 import V1ToV2Migration as MentionMig
    mig = MentionMig()
    assert mig.ENTITY == "mention"
    with pytest.raises(ValueError):
        mig.migrate_one({"schemaVersion": 5})
    out = mig.migrate_one({"id": "m1", "schemaVersion": 1})
    assert out["schemaVersion"] == 2


def test_source_v1_to_v2_refuses_wrong_source_version():
    """Idem pour le placeholder Source."""
    from migrations.source.v1_to_v2 import V1ToV2Migration as SourceMig
    mig = SourceMig()
    assert mig.ENTITY == "source"
    with pytest.raises(ValueError):
        mig.migrate_one({"schemaVersion": 5})
    out = mig.migrate_one({"id": "s1", "schemaVersion": 1})
    assert out["schemaVersion"] == 2
