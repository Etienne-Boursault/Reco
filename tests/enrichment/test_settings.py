"""Tests enrichment.settings (P3.5-B / ADR 0023)."""
from __future__ import annotations

from datetime import timedelta
from types import MappingProxyType

import pytest

from enrichment.settings import (
    DEFAULT_OLDER_THAN,
    DEFAULT_PROVIDER_FILTER,
    RefreshEnrichmentSettings,
)


class TestDefaults:
    def test_default_values(self) -> None:
        s = RefreshEnrichmentSettings()
        assert s.older_than == DEFAULT_OLDER_THAN
        assert s.provider_filter == DEFAULT_PROVIDER_FILTER
        assert dict(s.ttl_per_provider) == {}
        assert s.prioritize_suspect is False


class TestValidation:
    def test_negative_older_than_rejected(self) -> None:
        with pytest.raises(ValueError, match="older_than"):
            RefreshEnrichmentSettings(older_than=timedelta(days=-1))

    def test_provider_filter_invalid(self) -> None:
        with pytest.raises(ValueError, match="provider_filter"):
            RefreshEnrichmentSettings(provider_filter="invalid")

    def test_provider_filter_accepts_aliases(self) -> None:
        assert (
            RefreshEnrichmentSettings(provider_filter="musicbrainz").provider_filter
            == "musicbrainz"
        )
        assert RefreshEnrichmentSettings(provider_filter="tmdb").provider_filter == "tmdb"

    def test_ttl_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="ttl_per_provider"):
            RefreshEnrichmentSettings(ttl_per_provider={"tmdb": -1})

    def test_ttl_non_mapping_rejected(self) -> None:
        with pytest.raises(ValueError, match="ttl_per_provider"):
            RefreshEnrichmentSettings(ttl_per_provider=[("tmdb", 30)])  # type: ignore[arg-type]

    def test_ttl_coerced_to_mappingproxy(self) -> None:
        s = RefreshEnrichmentSettings(ttl_per_provider={"tmdb": 30, "music": 180})
        assert isinstance(s.ttl_per_provider, MappingProxyType)
        assert s.ttl_per_provider["tmdb"] == 30

    def test_prioritize_suspect_non_bool_rejected(self) -> None:
        with pytest.raises(ValueError, match="prioritize_suspect"):
            RefreshEnrichmentSettings(prioritize_suspect="yes")  # type: ignore[arg-type]

    def test_older_than_str_coerced(self) -> None:
        s = RefreshEnrichmentSettings(older_than="30d")  # type: ignore[arg-type]
        assert s.older_than == timedelta(days=30)


class TestFromSourceExtra:
    def test_none_extra_defaults(self) -> None:
        assert (
            RefreshEnrichmentSettings.from_source_extra(None)
            == RefreshEnrichmentSettings()
        )

    def test_missing_key_defaults(self) -> None:
        s = RefreshEnrichmentSettings.from_source_extra({"other": {"x": 1}})
        assert s == RefreshEnrichmentSettings()

    def test_payload_used(self) -> None:
        s = RefreshEnrichmentSettings.from_source_extra(
            {"refresh_enrichment": {"provider_filter": "tmdb"}}
        )
        assert s.provider_filter == "tmdb"

    def test_payload_str_older_than_coerced(self) -> None:
        s = RefreshEnrichmentSettings.from_source_extra(
            {"refresh_enrichment": {"older_than": "180d"}}
        )
        assert s.older_than == timedelta(days=180)

    def test_overrides_win(self) -> None:
        s = RefreshEnrichmentSettings.from_source_extra(
            {"refresh_enrichment": {"provider_filter": "tmdb"}},
            overrides={"provider_filter": "music"},
        )
        assert s.provider_filter == "music"

    def test_overrides_none_ignored(self) -> None:
        s = RefreshEnrichmentSettings.from_source_extra(
            {"refresh_enrichment": {"provider_filter": "tmdb"}},
            overrides={"provider_filter": None},
        )
        assert s.provider_filter == "tmdb"

    def test_ttl_via_payload(self) -> None:
        s = RefreshEnrichmentSettings.from_source_extra(
            {"refresh_enrichment": {"ttl_per_provider": {"tmdb": 90, "music": 180}}}
        )
        assert s.ttl_per_provider["tmdb"] == 90
        assert s.ttl_per_provider["music"] == 180

    def test_unknown_key_ignored(self) -> None:
        s = RefreshEnrichmentSettings.from_source_extra(
            {"refresh_enrichment": {"future_param": "x"}}
        )
        assert s == RefreshEnrichmentSettings()


class TestFrozen:
    def test_immutable(self) -> None:
        s = RefreshEnrichmentSettings()
        with pytest.raises((AttributeError, TypeError)):
            s.provider_filter = "tmdb"  # type: ignore[misc]
