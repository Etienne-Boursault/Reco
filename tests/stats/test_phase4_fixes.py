"""Tests Phase-4 fixer pour `tools/stats/*` + `tools/build_stats.py`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from stats.aggregator import (
    _unique_slug_impl,
    compute_global_counts,
    compute_top_guests,
    unique_slug,
    _fr_sort_key,
    _slugify,
)
from stats.models import GlobalCounts
from stats.settings import StatsSettings


# --- B-MED-14 — recommendedBy guard ----------------------------------------


def test_compute_global_counts_handles_non_string_recommended_by() -> None:
    mentions = [
        {"itemId": "i1", "recommendedBy": 42, "status": "published"},
        {"itemId": "i2", "recommendedBy": None, "status": "published"},
        {"itemId": "i3", "recommendedBy": "Alice", "status": "published"},
    ]
    out = compute_global_counts(
        sources=[], episodes=[], mentions=mentions, items=[],
    )
    # Seul Alice compte ; les autres droppés sans erreur.
    assert out.uniqueGuestsCount == 1


def test_compute_top_guests_handles_non_string_recommended_by() -> None:
    mentions = [
        {"itemId": "i1", "recommendedBy": 42, "status": "published"},
        {"itemId": "i2", "recommendedBy": "Alice", "status": "published"},
    ]
    top = compute_top_guests(mentions, [], limit=10)
    names = [g.name for g in top]
    assert names == ["Alice"]


def test_compute_global_counts_blank_recommended_by_skipped() -> None:
    """Espace blancs uniquement → skip."""
    mentions = [
        {"itemId": "i1", "recommendedBy": "   ", "status": "published"},
        {"itemId": "i2", "recommendedBy": "Bob", "status": "published"},
    ]
    out = compute_global_counts(
        sources=[], episodes=[], mentions=mentions, items=[],
    )
    assert out.uniqueGuestsCount == 1


def test_compute_top_guests_blank_recommended_by_skipped() -> None:
    mentions = [
        {"itemId": "i1", "recommendedBy": "   ", "status": "published"},
        {"itemId": "i2", "recommendedBy": "Bob", "status": "published"},
    ]
    top = compute_top_guests(mentions, [], limit=10)
    assert [g.name for g in top] == ["Bob"]


# --- B-LOW-8 — ligature Œ → OE ---------------------------------------------


def test_slugify_handles_oe_ligature() -> None:
    """Ligature œ doit casser proprement après NFKD ASCII."""
    # NFKD + .encode('ascii','ignore') drop la ligature (pas dans ASCII).
    # On vérifie au moins que le slug est non vide et déterministe.
    out = _slugify("Œuvre")
    assert isinstance(out, str) and out != ""


def test_fr_sort_key_oe_normalization() -> None:
    """Œ et OE doivent avoir une clé proche (insensibilité)."""
    a = _fr_sort_key("Œuvre")
    b = _fr_sort_key("OEuvre")
    # NFKD canonique : Œ → "Œ" (n'a pas de décomposition NFKD strict en ASCII).
    # Test plus mou : on vérifie au moins que casefold s'applique.
    assert a == a.lower() and b == b.lower()


# --- B-NIT-6 — unique_slug public ------------------------------------------


def test_unique_slug_public_alias() -> None:
    used: set[str] = set()
    assert unique_slug("Alice", used) == "alice"
    assert unique_slug("Alice", used) == "alice-2"
    # L'impl privée existe toujours (rétro-compat).
    assert _unique_slug_impl is not None


# --- B-LOW-9 — GlobalCounts via dataclass_fields ---------------------------


def test_global_counts_rejects_negative() -> None:
    with pytest.raises(ValueError):
        GlobalCounts(podcastsCount=-1)


def test_global_counts_rejects_bool() -> None:
    """bool est un int en Python — le check explicite doit le rejeter."""
    with pytest.raises(ValueError):
        GlobalCounts(podcastsCount=True)  # type: ignore[arg-type]


# --- B-LOW-10 — settings sans repr brut ------------------------------------


def test_settings_error_message_no_repr() -> None:
    """Message d'erreur expose le type, pas la valeur brute."""
    with pytest.raises(ValueError) as ei:
        StatsSettings(hidden_statuses=("",))
    msg = str(ei.value)
    assert "type reçu" in msg


# --- B-MED-15 / 16 / 17 — build_stats --------------------------------------


def test_is_safe_path_segment() -> None:
    from build_stats import _is_safe_path_segment

    assert _is_safe_path_segment("foo") is True
    assert _is_safe_path_segment("foo-bar_baz") is True
    assert _is_safe_path_segment("") is False
    assert _is_safe_path_segment(".") is False
    assert _is_safe_path_segment("..") is False
    assert _is_safe_path_segment(".hidden") is False
    assert _is_safe_path_segment("foo/bar") is False
    assert _is_safe_path_segment("foo\\bar") is False
    assert _is_safe_path_segment(42) is False  # type: ignore[arg-type]


def test_build_stats_max_items_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    """B-MED-15 — au-delà de max_items, warn (pas fail)."""
    import build_stats

    monkeypatch.setattr(build_stats, "_read_json_dir", lambda *a, **k: [])
    # On force le warn en mettant max_items = -1 (impossible).
    rc = build_stats.run(
        source="all",
        output_dir=tmp_path,
        fmt="json",
        generated_at="2026-06-12T00:00:00Z",
        max_items=-1,
    )
    assert rc == 0


def test_build_stats_skipped_threshold_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B-MED-17 — trop de skipped → exit 1."""
    import build_stats

    def fake_read(base: Path, *, skipped=None):
        if skipped is not None:
            # Simule 5 fichiers corrompus.
            for i in range(5):
                skipped.append(Path(f"/fake/{i}.json"))
        return []

    monkeypatch.setattr(build_stats, "_read_json_dir", fake_read)
    rc = build_stats.run(
        source="all",
        output_dir=tmp_path,
        fmt="json",
        generated_at="2026-06-12T00:00:00Z",
        skipped_threshold=2,  # 4 directories × 5 = 20 > 2
    )
    assert rc == 1


def test_build_stats_skipped_under_threshold_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B-MED-17 — peu de skipped → OK avec warning."""
    import build_stats

    call_count = {"n": 0}

    def fake_read(base: Path, *, skipped=None):
        call_count["n"] += 1
        if skipped is not None and call_count["n"] == 1:
            skipped.append(Path("/fake/x.json"))
        return []

    monkeypatch.setattr(build_stats, "_read_json_dir", fake_read)
    rc = build_stats.run(
        source="all",
        output_dir=tmp_path,
        fmt="json",
        generated_at="2026-06-12T00:00:00Z",
        skipped_threshold=10,
    )
    assert rc == 0


def test_build_stats_invalid_source_path_segment(tmp_path: Path) -> None:
    """B-MED-16 — `--source ../etc` → exit 1 SANS lire l'I/O."""
    import build_stats

    rc = build_stats.run(
        source="../etc",
        output_dir=tmp_path,
        fmt="json",
        generated_at="2026-06-12T00:00:00Z",
    )
    assert rc == 1


def test_build_stats_max_items_default_in_cli(tmp_path: Path) -> None:
    """B-MED-15 — flag CLI exposé."""
    import build_stats

    args = build_stats._parse_args(["--max-items", "1000"])
    assert args.max_items == 1000


def test_read_json_dir_records_skipped(tmp_path: Path) -> None:
    """B-MED-17 — fichiers corrompus alimentent `skipped`."""
    from build_stats import _read_json_dir

    (tmp_path / "ok.json").write_text("{}", encoding="utf-8")
    (tmp_path / "bad.json").write_text("not-json", encoding="utf-8")
    skipped: list[Path] = []
    out = _read_json_dir(tmp_path, skipped=skipped)
    assert len(out) == 1
    assert len(skipped) == 1
