"""Tests de l'agrégateur méta (Python)."""
from __future__ import annotations

from meta.aggregator import (
    aggregate_entries,
    dedupe_by_slug,
    slug_from_site_url,
)


def _reg(site_url: str = "https://a.example", *, title: str = "A", mentions: int = 0) -> dict:
    return {
        "schemaVersion": 1,
        "siteUrl": site_url,
        "podcast": {"title": title, "hosts": [], "language": "fr"},
        "stats": {
            "itemsCount": 10,
            "mentionsCount": mentions,
            "episodesCount": 5,
            "guestsCount": 2,
            "lastUpdatedAt": "2026-06-12T00:00:00Z",
        },
        "meta": {
            "generator": "Reco/0.3.0",
            "generatedAt": "2026-06-12T00:00:00Z",
        },
        "endpoints": {},
    }


def test_slug_extracts_hostname() -> None:
    assert slug_from_site_url("https://www.Un-Bon-Moment.example.com/") == "un-bon-moment.example.com"


def test_slug_ignores_port() -> None:
    assert slug_from_site_url("https://host.example:8443/x") == "host.example"


def test_slug_fallback_for_invalid_url() -> None:
    assert slug_from_site_url("not a url!") == "not-a-url"


def test_slug_returns_unknown_when_empty() -> None:
    assert slug_from_site_url("!!!") == "unknown"


def test_aggregate_dedupes_by_slug() -> None:
    items = [
        {"sourceUrl": "u1", "registry": _reg("https://x.example", title="First")},
        {"sourceUrl": "u2", "registry": _reg("https://www.x.example", title="Dup")},
    ]
    out = aggregate_entries(items)
    assert len(out["entries"]) == 1
    assert out["entries"][0]["registry"]["podcast"]["title"] == "First"


def test_aggregate_sorts_by_mentions_desc_then_title() -> None:
    items = [
        {"sourceUrl": "u1", "registry": _reg("https://a.example", title="Beta", mentions=10)},
        {"sourceUrl": "u2", "registry": _reg("https://b.example", title="Charlie", mentions=50)},
        {"sourceUrl": "u3", "registry": _reg("https://c.example", title="Alpha", mentions=50)},
    ]
    out = aggregate_entries(items)
    titles = [e["registry"]["podcast"]["title"] for e in out["entries"]]
    assert titles == ["Alpha", "Charlie", "Beta"]


def test_aggregate_totals() -> None:
    items = [
        {"sourceUrl": "u1", "registry": _reg("https://a.example", mentions=20)},
        {"sourceUrl": "u2", "registry": _reg("https://b.example", mentions=30)},
    ]
    out = aggregate_entries(items)
    assert out["totals"] == {
        "podcasts": 2,
        "items": 20,
        "mentions": 50,
        "episodes": 10,
        "guests": 4,
    }


def test_aggregate_empty() -> None:
    out = aggregate_entries([])
    assert out["entries"] == []
    assert out["totals"]["podcasts"] == 0


def test_dedupe_drops_missing_slug() -> None:
    out = dedupe_by_slug([{"slug": "a", "x": 1}, {"x": 2}, {"slug": "b"}])
    assert [e.get("slug") for e in out] == ["a", "b"]


def test_aggregate_schema_version_is_1() -> None:
    out = aggregate_entries([])
    assert out["schemaVersion"] == 1


def test_slug_handles_str_failure() -> None:
    """Fallback ultime si même `str()` lève."""
    class Boom:
        def __str__(self) -> str:
            raise RuntimeError("boom")

    assert slug_from_site_url(Boom()) == "unknown"  # type: ignore[arg-type]


def test_slug_handles_non_string_input() -> None:
    """M24-12 — TypeError absorbé proprement, fallback `unknown`."""
    assert slug_from_site_url(None) == "unknown"  # type: ignore[arg-type]
    assert slug_from_site_url(42) == "42"  # type: ignore[arg-type]


def test_aggregate_sort_is_nfkd_stable() -> None:
    """L24-24 — tri NFKD/casefold : déterministe inter-runtime."""
    items = [
        {"sourceUrl": "u1", "registry": _reg("https://a.example", title="Étoile", mentions=5)},
        {"sourceUrl": "u2", "registry": _reg("https://b.example", title="Apostrophe", mentions=5)},
    ]
    out = aggregate_entries(items)
    titles = [e["registry"]["podcast"]["title"] for e in out["entries"]]
    # 'a' < 'e' (NFKD : 'É' → 'E' + combining, casefold → 'e').
    assert titles == ["Apostrophe", "Étoile"]
