"""Tests de `tools.stats.aggregator` (miroir Python de l'agrégation TS).

Le but n'est pas de retester les invariants exhaustivement (le module TS
les couvre côté front), mais d'**ancrer la parité** : à entrée équivalente,
le snapshot Python doit reproduire les mêmes counts, tris, et clés.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from stats import STATS_SCHEMA_VERSION, build_snapshot
from stats.aggregator import (
    _month_key,
    _slugify,
    compute_global_counts,
    compute_monthly_episodes,
    compute_top_guests,
    compute_top_works,
    compute_type_distribution,
    public_mentions,
)


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def sources():
    return [
        {"id": "ubm", "hosts": ["Kyan"]},
        {"id": "autre", "hosts": []},
    ]


@pytest.fixture
def episodes():
    return [
        {"sourceId": "ubm", "date": "2024-01-15T00:00:00Z"},
        {"sourceId": "ubm", "date": "2024-01-25T00:00:00Z"},
        {"sourceId": "ubm", "date": "2024-02-10T00:00:00Z"},
        {"sourceId": "autre", "date": "2024-02-20T00:00:00Z"},
        {"sourceId": "ubm", "date": None},  # ignoré pour monthly
    ]


@pytest.fixture
def items():
    return [
        {"id": "parasite", "title": "Parasite", "types": ["film"]},
        {"id": "dune", "title": "Dune", "types": ["film", "livre"]},
        {"id": "sapiens", "title": "Sapiens", "types": ["livre"]},
        {"id": "orphan", "title": "Orphan", "types": ["film"]},
    ]


@pytest.fixture
def mentions():
    return [
        {"itemId": "parasite", "recommendedBy": "Alice", "status": "validated",
         "sourceRef": {"sourceId": "ubm"}},
        {"itemId": "parasite", "recommendedBy": "Bob", "status": "validated",
         "sourceRef": {"sourceId": "ubm"}},
        {"itemId": "parasite", "recommendedBy": "Alice", "status": "discarded",
         "sourceRef": {"sourceId": "ubm"}},  # exclu
        {"itemId": "dune", "recommendedBy": "Alice", "status": "validated",
         "sourceRef": {"sourceId": "ubm"}},
        {"itemId": "sapiens", "recommendedBy": "Kyan", "status": "validated",
         "sourceRef": {"sourceId": "ubm"}},  # host exclu de guests
        {"itemId": "sapiens", "recommendedBy": "Bob", "status": "validated",
         "sourceRef": {"sourceId": "autre"}},
        {"itemId": "sapiens", "recommendedBy": None, "status": "validated",
         "sourceRef": {"sourceId": "autre"}},
    ]


# --- Tests ------------------------------------------------------------------


def test_public_mentions_excludes_discarded(mentions):
    assert len(public_mentions(mentions)) == 6


def test_slugify_handles_diacritics_and_empty():
    assert _slugify("Mary-Léa Dupont") == "mary-lea-dupont"
    assert _slugify("") == "x"
    assert _slugify("---") == "x"


def test_month_key_variants():
    assert _month_key("2024-01-15T00:00:00Z") == "2024-01"
    assert _month_key(datetime(2024, 3, 1, tzinfo=timezone.utc)) == "2024-03"
    assert _month_key(None) is None
    assert _month_key("pas une date") is None
    # Type inattendu → None (couvre la branche `dt is None`).
    assert _month_key(12345) is None
    assert _month_key([]) is None


def test_global_counts(sources, episodes, mentions, items):
    g = compute_global_counts(
        sources=sources, episodes=episodes, mentions=mentions, items=items
    )
    assert g.podcastsCount == 2
    assert g.episodesCount == 5
    assert g.recommendationsCount == 6
    assert g.uniqueWorksCount == 3  # orphan exclu
    assert g.uniqueGuestsCount == 2  # Alice + Bob (Kyan host, null ignoré)


def test_global_counts_empty():
    g = compute_global_counts(sources=[], episodes=[], mentions=[], items=[])
    assert g.podcastsCount == 0
    assert g.recommendationsCount == 0


def test_global_counts_rejects_negative():
    from stats.models import GlobalCounts
    with pytest.raises(ValueError):
        GlobalCounts(podcastsCount=-1)


def test_top_guests_sort_and_limit(sources, mentions):
    top = compute_top_guests(mentions, sources, limit=10)
    # Alice = 2, Bob = 2 → tri alpha → Alice avant Bob
    assert top[0].name == "Alice"
    assert top[0].count == 2
    assert top[0].slug == "alice"
    assert top[1].name == "Bob"
    top1 = compute_top_guests(mentions, sources, limit=1)
    assert len(top1) == 1


def test_top_works_sort_and_orphan_ignored(items, mentions):
    top = compute_top_works(items, mentions, limit=10)
    # sapiens = 3 mentions publiques (Kyan, Bob, null) → top1
    assert top[0].id == "sapiens"
    assert top[0].mentionsCount == 3
    assert top[0].type == "livre"
    # ajout d'une mention orpheline → ignorée
    extra = mentions + [
        {"itemId": "ghost", "status": "validated",
         "sourceRef": {"sourceId": "ubm"}},
    ]
    ids = [w.id for w in compute_top_works(items, extra, limit=10)]
    assert "ghost" not in ids


def test_type_distribution(items, mentions):
    d = compute_type_distribution(items, mentions)
    # parasite=film, dune=film, sapiens=livre → film:2, livre:1
    assert d == {"film": 2, "livre": 1}


def test_monthly_episodes_sorted(episodes):
    buckets = compute_monthly_episodes(episodes)
    assert [b.month for b in buckets] == ["2024-01", "2024-02"]
    assert [b.count for b in buckets] == [2, 2]


def test_monthly_episodes_fills_gaps_R_P3_30():
    """R-P3-30 : trous remplis avec count=0 entre min et max."""
    buckets = compute_monthly_episodes(
        [
            {"sourceId": "x", "date": "2024-01-01T00:00:00Z"},
            {"sourceId": "x", "date": "2024-04-01T00:00:00Z"},
        ]
    )
    months = [b.month for b in buckets]
    assert months == ["2024-01", "2024-02", "2024-03", "2024-04"]
    assert [b.count for b in buckets] == [1, 0, 0, 1]


def test_monthly_episodes_empty_returns_empty():
    assert compute_monthly_episodes([]) == []
    # Dates invalides → ignorées → vide.
    assert compute_monthly_episodes([{"sourceId": "x", "date": "pas une date"}]) == []


def test_monthly_episodes_crosses_year_boundary_R_P3_30():
    """Couvre la branche `mo > 12 → mo=1 ; y+=1` (lignes 239-240)."""
    buckets = compute_monthly_episodes(
        [
            {"sourceId": "x", "date": "2024-11-01T00:00:00Z"},
            {"sourceId": "x", "date": "2025-02-01T00:00:00Z"},
        ]
    )
    months = [b.month for b in buckets]
    assert months == ["2024-11", "2024-12", "2025-01", "2025-02"]


def test_month_key_handles_naive_datetime_via_utc():
    """Couvre les branches tz-naive / tz-aware (lignes 77, 79)."""
    naive = datetime(2024, 5, 12)  # pas de tzinfo
    assert _month_key(naive) == "2024-05"
    # tz non-UTC → converti en UTC, mois peut shifter mais ici 12:00 PT reste
    # le même jour en UTC.
    aware = datetime(2024, 5, 12, 12, 0, tzinfo=timezone.utc)
    assert _month_key(aware) == "2024-05"


def test_unique_slug_handles_triple_collision():
    """Couvre la boucle `while ...-n in used` (ligne 162)."""
    from stats.aggregator import _unique_slug
    used: set[str] = set()
    assert _unique_slug("Alice", used) == "alice"
    assert _unique_slug("alice", used) == "alice-2"
    assert _unique_slug("ALICE", used) == "alice-3"


def test_type_distribution_sort_count_desc_then_alpha_L26_27():
    items = [
        {"id": "a", "title": "A", "types": ["zeta"]},
        {"id": "b", "title": "B", "types": ["alpha"]},
        {"id": "c", "title": "C", "types": ["alpha"]},
        {"id": "d", "title": "D", "types": ["beta"]},
    ]
    mentions = [
        {"itemId": k, "status": "validated", "sourceRef": {"sourceId": "s"}}
        for k in ("a", "b", "c", "d")
    ]
    d = compute_type_distribution(items, mentions)
    # alpha:2, beta:1, zeta:1 — tri secondaire alpha.
    assert list(d.keys()) == ["alpha", "beta", "zeta"]


def test_build_snapshot_full(sources, episodes, mentions, items):
    snap = build_snapshot(
        sources=sources,
        episodes=episodes,
        mentions=mentions,
        items=items,
        generated_at="2026-06-12T00:00:00Z",
    )
    assert snap.schemaVersion == STATS_SCHEMA_VERSION
    assert snap.generatedAt == "2026-06-12T00:00:00Z"
    assert snap.global_.podcastsCount == 2
    payload = snap.to_dict()
    # Parité TS : `global` (pas `global_`).
    assert payload["global"]["podcastsCount"] == 2
    assert "perSource" in payload
    assert payload["perSource"]["ubm"]["episodesCount"] == 4
    assert all(isinstance(b["month"], str) for b in payload["monthlyEpisodes"])


def test_build_snapshot_filtered_by_source(sources, episodes, mentions, items):
    snap = build_snapshot(
        sources=sources,
        episodes=episodes,
        mentions=mentions,
        items=items,
        source_id="ubm",
        generated_at="x",
    )
    assert snap.global_.podcastsCount == 1
    assert snap.global_.episodesCount == 4
    assert list(snap.perSource.keys()) == ["ubm"]


def test_build_snapshot_default_generated_at_iso(sources, episodes, mentions, items):
    snap = build_snapshot(
        sources=sources, episodes=episodes, mentions=mentions, items=items
    )
    # ISO 8601 UTC : `YYYY-MM-DDTHH:MM:SSZ`
    assert snap.generatedAt.endswith("Z")
    assert len(snap.generatedAt) == 20
