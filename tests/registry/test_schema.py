"""Tests du validateur de schema `reco-registry.json` (Python).

Mirroir des tests vitest côté TS (`tests/registry/test_types.test.ts`).
"""
from __future__ import annotations

import copy

import pytest

from meta.validator import (
    REGISTRY_SCHEMA_VERSION,
    RegistryValidationError,
    validate_registry,
)


VALID_DOC: dict = {
    "schemaVersion": 1,
    "siteUrl": "https://un-bon-moment.example.com",
    "podcast": {
        "title": "Un Bon Moment",
        "tagline": "Les recos de Kyan & Navo",
        "rssUrl": "https://feeds.acast.com/public/shows/xyz",
        "hosts": ["Kyan Khojandi", "Navo"],
        "since": "2018-09-01",
        "language": "fr",
    },
    "stats": {
        "itemsCount": 2651,
        "mentionsCount": 2866,
        "episodesCount": 104,
        "guestsCount": 224,
        "lastUpdatedAt": "2026-06-12T00:00:00Z",
    },
    "meta": {
        "generator": "Reco/0.3.0",
        "generatedAt": "2026-06-12T07:45:00Z",
        "manifesto": "https://un-bon-moment.example.com/manifeste",
    },
    "endpoints": {
        "ogImage": "/og/default.png",
        "sitemap": "/sitemap-index.xml",
        "search": "/search.json",
    },
}


def test_schema_version_is_one() -> None:
    assert REGISTRY_SCHEMA_VERSION == 1


def test_valid_document_passes() -> None:
    out = validate_registry(copy.deepcopy(VALID_DOC))
    assert out["podcast"]["title"] == "Un Bon Moment"
    assert out["stats"]["mentionsCount"] == 2866


def test_endpoints_default_to_empty_dict() -> None:
    doc = copy.deepcopy(VALID_DOC)
    del doc["endpoints"]
    out = validate_registry(doc)
    assert out["endpoints"] == {}


def test_endpoints_none_becomes_empty() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["endpoints"] = None
    out = validate_registry(doc)
    assert out["endpoints"] == {}


def test_rejects_wrong_schema_version() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["schemaVersion"] = 2
    with pytest.raises(RegistryValidationError) as exc:
        validate_registry(doc)
    assert "schemaVersion" in str(exc.value)


def test_rejects_non_https_site_url() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["siteUrl"] = "http://insecure.example"
    with pytest.raises(RegistryValidationError) as exc:
        validate_registry(doc)
    assert "HTTPS" in str(exc.value)


def test_rejects_invalid_language() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["podcast"]["language"] = "fra"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_negative_counts() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["stats"]["itemsCount"] = -1
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_non_iso_generated_at() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["meta"]["generatedAt"] = "hier"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_bad_since_format() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["podcast"]["since"] = "2018"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_non_dict_root() -> None:
    with pytest.raises(RegistryValidationError):
        validate_registry("nope")


def test_rejects_missing_podcast() -> None:
    doc = copy.deepcopy(VALID_DOC)
    del doc["podcast"]
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_non_int_count() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["stats"]["mentionsCount"] = "ten"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_bool_as_int() -> None:
    """`True` est un int Python — on filtre quand même (faux positif)."""
    doc = copy.deepcopy(VALID_DOC)
    doc["stats"]["itemsCount"] = True
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_non_list_hosts() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["podcast"]["hosts"] = "Kyan"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_empty_title() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["podcast"]["title"] = "   "
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_accepts_iso_with_offset() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["meta"]["generatedAt"] = "2026-06-12T07:45:00+02:00"
    out = validate_registry(doc)
    assert out["meta"]["generatedAt"].endswith("+02:00")


def test_accepts_iso_with_microseconds() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["stats"]["lastUpdatedAt"] = "2026-06-12T00:00:00.123456Z"
    validate_registry(doc)  # no raise


def test_rejects_non_http_rss_url() -> None:
    """Couvre _check_url chemin string mais ni http ni https."""
    doc = copy.deepcopy(VALID_DOC)
    doc["podcast"]["rssUrl"] = "ftp://feeds.example/x"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_non_str_generator() -> None:
    """Couvre _check_str (chemin non-string)."""
    doc = copy.deepcopy(VALID_DOC)
    doc["meta"]["generator"] = 42
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_non_str_manifesto() -> None:
    """Couvre _check_url (valeur non-string passe par _check_str, return)."""
    doc = copy.deepcopy(VALID_DOC)
    doc["meta"]["manifesto"] = 42
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_non_str_endpoint() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["endpoints"]["ogImage"] = 42
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_non_dict_stats() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["stats"] = []
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_non_dict_meta() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["meta"] = "nope"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_non_dict_endpoints() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["endpoints"] = "x"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_podcasts_non_list() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["podcasts"] = "nope"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_podcasts_non_object_entry() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["podcasts"] = ["not-a-dict"]
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_strict_rejects_unknown_root_key() -> None:
    """H24-2 — `.strict()` côté Python : clé inconnue à la racine refusée."""
    doc = copy.deepcopy(VALID_DOC)
    doc["extra"] = 1
    with pytest.raises(RegistryValidationError) as exc:
        validate_registry(doc)
    assert "extra" in str(exc.value)


def test_strict_rejects_unknown_podcast_key() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["podcast"]["secret"] = "x"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_strict_rejects_unknown_stats_key() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["stats"]["bonus"] = 0
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_strict_rejects_unknown_endpoints_key() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["endpoints"]["custom"] = "/x"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_title_too_long() -> None:
    """M24-6 — title borné à 200 caractères."""
    doc = copy.deepcopy(VALID_DOC)
    doc["podcast"]["title"] = "a" * 201
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_too_many_hosts() -> None:
    """M24-5 — hosts borné à 64."""
    doc = copy.deepcopy(VALID_DOC)
    doc["podcast"]["hosts"] = [f"H{i}" for i in range(65)]
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_host_too_long() -> None:
    """M24-5 — chaque host borné à 200."""
    doc = copy.deepcopy(VALID_DOC)
    doc["podcast"]["hosts"] = ["x" * 201]
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_accepts_endpoint_relative_path() -> None:
    """M24-7 — chemin /... accepté."""
    doc = copy.deepcopy(VALID_DOC)
    doc["endpoints"]["ogImage"] = "/og/custom.png"
    validate_registry(doc)


def test_accepts_endpoint_https_url() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["endpoints"]["ogImage"] = "https://cdn.example/x.png"
    validate_registry(doc)


def test_rejects_endpoint_http() -> None:
    """M24-7 — pas de http en clair."""
    doc = copy.deepcopy(VALID_DOC)
    doc["endpoints"]["ogImage"] = "http://insecure/x"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_rejects_iso_seconds_60() -> None:
    """L24-21 — heures/minutes/secondes bornées."""
    doc = copy.deepcopy(VALID_DOC)
    doc["meta"]["generatedAt"] = "2026-06-12T07:45:60Z"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_accepts_optional_podcasts_array() -> None:
    """R-P1-05 — `podcasts` réservé multi-source (forward-compat)."""
    doc = copy.deepcopy(VALID_DOC)
    doc["podcasts"] = [
        {"title": "Second", "hosts": [], "language": "fr"},
    ]
    out = validate_registry(doc)
    assert out["podcasts"][0]["title"] == "Second"


def test_rejects_podcasts_with_invalid_entry() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["podcasts"] = [{"title": "ok", "language": "xx", "hosts": []}]
    # `xx` est valide (2 lettres). On force une erreur réelle :
    doc["podcasts"][0]["language"] = "english"
    with pytest.raises(RegistryValidationError):
        validate_registry(doc)


def test_error_collects_multiple_issues() -> None:
    doc = copy.deepcopy(VALID_DOC)
    doc["siteUrl"] = "http://x"
    doc["podcast"]["language"] = "fra"
    with pytest.raises(RegistryValidationError) as exc:
        validate_registry(doc)
    assert len(exc.value.errors) >= 2
