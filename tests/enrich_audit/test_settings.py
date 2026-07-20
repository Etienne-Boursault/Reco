"""Tests enrich_audit.settings (D-01/V-01, ADR 0019)."""
from __future__ import annotations

import pytest

from enrich_audit.settings import (
    DEFAULT_FILM_MAX_RUNTIME,
    EnrichAuditSettings,
)
from enrich_audit.thresholds import (
    DEFAULT_FILM_MIN_RUNTIME,
    DEFAULT_TITLE_THRESHOLD,
    DEFAULT_YEAR_TOLERANCE,
)


class TestDefaults:
    def test_default_threshold(self) -> None:
        s = EnrichAuditSettings()
        assert s.title_threshold == DEFAULT_TITLE_THRESHOLD
        assert s.year_tolerance == DEFAULT_YEAR_TOLERANCE
        assert s.film_min_runtime == DEFAULT_FILM_MIN_RUNTIME
        assert s.film_max_runtime == DEFAULT_FILM_MAX_RUNTIME


class TestValidation:
    def test_title_threshold_out_of_bounds_raises(self) -> None:
        with pytest.raises(ValueError, match="title_threshold"):
            EnrichAuditSettings(title_threshold=1.5)
        with pytest.raises(ValueError, match="title_threshold"):
            EnrichAuditSettings(title_threshold=-0.1)

    def test_title_threshold_bool_rejected(self) -> None:
        with pytest.raises(ValueError):
            EnrichAuditSettings(title_threshold=True)  # type: ignore[arg-type]

    def test_negative_runtime_rejected(self) -> None:
        with pytest.raises(ValueError):
            EnrichAuditSettings(film_min_runtime=-1)

    def test_film_max_lt_min_rejected(self) -> None:
        with pytest.raises(ValueError, match="film_max_runtime"):
            EnrichAuditSettings(film_min_runtime=100, film_max_runtime=50)

    def test_series_max_lt_min_rejected(self) -> None:
        with pytest.raises(ValueError, match="series_max_runtime"):
            EnrichAuditSettings(series_min_runtime=100, series_max_runtime=50)


class TestFromSourceExtra:
    def test_none_extra_defaults(self) -> None:
        assert EnrichAuditSettings.from_source_extra(None) == EnrichAuditSettings()

    def test_missing_key_defaults(self) -> None:
        s = EnrichAuditSettings.from_source_extra({"other": {"x": 1}})
        assert s == EnrichAuditSettings()

    def test_payload_used(self) -> None:
        s = EnrichAuditSettings.from_source_extra(
            {"enrich_audit": {"title_threshold": 0.9, "year_tolerance": 3}}
        )
        assert s.title_threshold == 0.9
        assert s.year_tolerance == 3

    def test_overrides_win(self) -> None:
        s = EnrichAuditSettings.from_source_extra(
            {"enrich_audit": {"year_tolerance": 3}},
            overrides={"year_tolerance": 5},
        )
        assert s.year_tolerance == 5

    def test_unknown_key_ignored(self) -> None:
        # forward-compat
        s = EnrichAuditSettings.from_source_extra(
            {"enrich_audit": {"future_seuil": 0.42}}
        )
        assert s == EnrichAuditSettings()


class TestFrozen:
    def test_immutable(self) -> None:
        s = EnrichAuditSettings()
        with pytest.raises((AttributeError, TypeError)):
            s.title_threshold = 0.1  # type: ignore[misc]
