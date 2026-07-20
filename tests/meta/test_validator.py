"""Tests validateur registry (Python).

Couvre :
- B-HIGH-5 — borne URL 2048.
- B-MED-8 — strptime stricte ISO dates.
- B-MED-9 — rssUrl HTTPS.
- B-NIT-2 — messages français.
- Tous les chemins de validation pour pousser la coverage à 100%.
"""
from __future__ import annotations

import pytest

from meta.validator import (
    REGISTRY_SCHEMA_VERSION,
    RegistryValidationError,
    validate_registry,
)


def _valid() -> dict:
    return {
        "schemaVersion": 1,
        "siteUrl": "https://x.example",
        "podcast": {"title": "X", "hosts": [], "language": "fr"},
        "stats": {
            "itemsCount": 1,
            "mentionsCount": 1,
            "episodesCount": 1,
            "guestsCount": 1,
            "lastUpdatedAt": "2026-06-12T00:00:00Z",
        },
        "meta": {"generator": "Reco/0.3.0", "generatedAt": "2026-06-12T00:00:00Z"},
        "endpoints": {},
    }


def test_valid_passes() -> None:
    out = validate_registry(_valid())
    assert out["siteUrl"] == "https://x.example"


def test_not_dict_raises() -> None:
    with pytest.raises(RegistryValidationError):
        validate_registry([1, 2, 3])


def test_unknown_root_key_raises() -> None:
    bad = _valid()
    bad["surprise"] = 1
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_wrong_schema_version_raises() -> None:
    bad = _valid()
    bad["schemaVersion"] = 99
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_site_url_not_https_raises() -> None:
    bad = _valid()
    bad["siteUrl"] = "http://x"
    with pytest.raises(RegistryValidationError) as ei:
        validate_registry(bad)
    assert "HTTPS" in str(ei.value)


def test_site_url_too_long_raises() -> None:
    """B-HIGH-5 — URL > 2048 → erreur de longueur."""
    bad = _valid()
    bad["siteUrl"] = "https://" + ("a" * 2050) + ".example"
    with pytest.raises(RegistryValidationError) as ei:
        validate_registry(bad)
    assert "2048" in str(ei.value)


def test_site_url_not_string_raises() -> None:
    bad = _valid()
    bad["siteUrl"] = 42
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_site_url_empty_raises() -> None:
    bad = _valid()
    bad["siteUrl"] = "   "
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_podcast_not_dict_raises() -> None:
    bad = _valid()
    bad["podcast"] = "x"
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_podcast_bad_language_raises() -> None:
    bad = _valid()
    bad["podcast"]["language"] = "FR"  # uppercase rejeté
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_podcast_missing_language_raises() -> None:
    bad = _valid()
    del bad["podcast"]["language"]
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_podcast_tagline_too_long_raises() -> None:
    bad = _valid()
    bad["podcast"]["tagline"] = "x" * 501
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_podcast_tagline_none_ignored() -> None:
    ok = _valid()
    ok["podcast"]["tagline"] = None
    out = validate_registry(ok)
    assert out["podcast"]["tagline"] is None


def test_podcast_tagline_ok() -> None:
    ok = _valid()
    ok["podcast"]["tagline"] = "Slogan"
    validate_registry(ok)


def test_podcast_rss_url_http_raises() -> None:
    """B-MED-9 — rssUrl en HTTP → rejeté."""
    bad = _valid()
    bad["podcast"]["rssUrl"] = "http://feed.example/rss"
    with pytest.raises(RegistryValidationError) as ei:
        validate_registry(bad)
    assert "HTTPS" in str(ei.value)


def test_podcast_rss_url_https_ok() -> None:
    ok = _valid()
    ok["podcast"]["rssUrl"] = "https://feed.example/rss"
    validate_registry(ok)


def test_podcast_rss_url_none_ignored() -> None:
    ok = _valid()
    ok["podcast"]["rssUrl"] = None
    validate_registry(ok)


def test_podcast_since_invalid_format_raises() -> None:
    bad = _valid()
    bad["podcast"]["since"] = "2026/01/01"
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_podcast_since_impossible_date_raises() -> None:
    """B-MED-8 — strptime rejette 2026-02-31."""
    bad = _valid()
    bad["podcast"]["since"] = "2026-02-31"
    with pytest.raises(RegistryValidationError) as ei:
        validate_registry(bad)
    assert "invalide" in str(ei.value)


def test_podcast_since_month_13_raises() -> None:
    bad = _valid()
    bad["podcast"]["since"] = "2026-13-01"
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_podcast_since_valid_ok() -> None:
    ok = _valid()
    ok["podcast"]["since"] = "2026-02-28"
    validate_registry(ok)


def test_podcast_since_none_ignored() -> None:
    ok = _valid()
    ok["podcast"]["since"] = None
    validate_registry(ok)


def test_podcast_hosts_not_list_raises() -> None:
    bad = _valid()
    bad["podcast"]["hosts"] = "alice"
    with pytest.raises(RegistryValidationError) as ei:
        validate_registry(bad)
    # B-NIT-2 — message en français.
    assert "liste" in str(ei.value).lower()


def test_podcast_hosts_too_many_raises() -> None:
    bad = _valid()
    bad["podcast"]["hosts"] = [f"h{i}" for i in range(65)]
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_podcast_host_too_long_raises() -> None:
    bad = _valid()
    bad["podcast"]["hosts"] = ["x" * 201]
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_podcasts_array_optional_present() -> None:
    ok = _valid()
    ok["podcasts"] = [
        {"title": "Y", "hosts": [], "language": "fr"},
    ]
    validate_registry(ok)


def test_podcasts_not_list_raises() -> None:
    bad = _valid()
    bad["podcasts"] = "x"
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_podcasts_entry_not_dict_raises() -> None:
    bad = _valid()
    bad["podcasts"] = ["not-a-dict"]
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_podcasts_none_ignored() -> None:
    ok = _valid()
    ok["podcasts"] = None
    validate_registry(ok)


def test_stats_not_dict_raises() -> None:
    bad = _valid()
    bad["stats"] = "x"
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_stats_count_negative_raises() -> None:
    bad = _valid()
    bad["stats"]["itemsCount"] = -1
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_stats_count_bool_rejected() -> None:
    """Les bool sont des int en Python → on doit les rejeter explicitement."""
    bad = _valid()
    bad["stats"]["itemsCount"] = True
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_stats_last_updated_at_bad_raises() -> None:
    bad = _valid()
    bad["stats"]["lastUpdatedAt"] = "not-a-date"
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_stats_last_updated_at_impossible_raises() -> None:
    """B-MED-8 — `2026-02-30T...` rejeté."""
    bad = _valid()
    bad["stats"]["lastUpdatedAt"] = "2026-02-30T00:00:00Z"
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_meta_not_dict_raises() -> None:
    bad = _valid()
    bad["meta"] = "x"
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_meta_generator_too_long_raises() -> None:
    bad = _valid()
    bad["meta"]["generator"] = "x" * 101
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_meta_manifesto_url_ok() -> None:
    ok = _valid()
    ok["meta"]["manifesto"] = "https://example.com/manifesto"
    validate_registry(ok)


def test_meta_manifesto_not_url_raises() -> None:
    bad = _valid()
    bad["meta"]["manifesto"] = "ftp://bad"
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_meta_manifesto_none_ignored() -> None:
    ok = _valid()
    ok["meta"]["manifesto"] = None
    validate_registry(ok)


def test_endpoints_default_applied() -> None:
    ok = _valid()
    ok["endpoints"] = None
    out = validate_registry(ok)
    assert out["endpoints"] == {}


def test_endpoints_not_dict_raises() -> None:
    bad = _valid()
    bad["endpoints"] = "x"
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_endpoints_ok_relative_path() -> None:
    ok = _valid()
    ok["endpoints"] = {"sitemap": "/sitemap.xml"}
    validate_registry(ok)


def test_endpoints_ok_https_url() -> None:
    ok = _valid()
    ok["endpoints"] = {"ogImage": "https://x.example/og.png"}
    validate_registry(ok)


def test_endpoints_bad_value_raises() -> None:
    bad = _valid()
    bad["endpoints"] = {"sitemap": "ftp://nope"}
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_endpoints_not_string_raises() -> None:
    bad = _valid()
    bad["endpoints"] = {"sitemap": 42}
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_endpoints_none_value_ignored() -> None:
    ok = _valid()
    ok["endpoints"] = {"sitemap": None}
    validate_registry(ok)


def test_endpoints_unknown_key_raises() -> None:
    bad = _valid()
    bad["endpoints"] = {"surprise": "/x"}
    with pytest.raises(RegistryValidationError):
        validate_registry(bad)


def test_schema_version_constant() -> None:
    assert REGISTRY_SCHEMA_VERSION == 1


def test_endpoints_absent_defaulted() -> None:
    ok = _valid()
    del ok["endpoints"]
    out = validate_registry(ok)
    assert out["endpoints"] == {}
