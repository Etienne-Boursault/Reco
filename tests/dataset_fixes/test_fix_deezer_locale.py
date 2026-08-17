"""Tests de `tools/fix_deezer_locale.py` — suppression du segment de locale.

L'invariant le plus important : l'identifiant numérique ne bouge jamais. Une
locale retirée mais un id altéré produirait un lien plausible et faux — bien
pire qu'un lien resté localisé.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import fix_deezer_locale as fdl


@pytest.fixture
def recos_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "src" / "content" / "recos"
    root.mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", root)
    monkeypatch.setattr(df, "RECOS_DIR", root)
    return root


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


# ===== strip_locale ========================================================
@pytest.mark.parametrize("section", ["album", "track", "artist", "show"])
@pytest.mark.parametrize("locale", ["us", "en", "fr", "de"])
def test_strip_locale_on_every_verified_section(section: str, locale: str):
    url = f"https://www.deezer.com/{locale}/{section}/262200072"
    assert fdl.strip_locale(url) == f"https://www.deezer.com/{section}/262200072"


def test_strip_locale_preserves_id_query_and_fragment():
    """Tout ce qui suit la section est recopié à l'octet près."""
    url = "https://www.deezer.com/us/album/262200072?utm=x#frag"
    assert fdl.strip_locale(url) == "https://www.deezer.com/album/262200072?utm=x#frag"


def test_strip_locale_returns_none_when_already_canonical():
    assert fdl.strip_locale("https://www.deezer.com/album/262200072") is None


def test_strip_locale_ignores_unknown_section():
    """Une section jamais vérifiée en HTTP n'est pas réécrite."""
    assert fdl.strip_locale("https://www.deezer.com/fr/playlist/123") is None


def test_strip_locale_ignores_foreign_host():
    assert fdl.strip_locale("https://www.spotify.com/us/album/1") is None


def test_strip_locale_accepts_http_and_bare_host():
    assert fdl.strip_locale("http://deezer.com/us/track/1") == "http://deezer.com/track/1"


def test_strip_locale_rejects_three_letter_segment():
    assert fdl.strip_locale("https://www.deezer.com/usa/album/1") is None


# ===== unverified_section ==================================================
def test_unverified_section_names_the_section():
    assert fdl.unverified_section("https://www.deezer.com/fr/playlist/1") == "playlist"


def test_unverified_section_none_for_verified_and_for_canonical():
    assert fdl.unverified_section("https://www.deezer.com/us/album/1") is None
    assert fdl.unverified_section("https://www.deezer.com/album/1") is None


def test_unverified_section_none_for_foreign_url():
    assert fdl.unverified_section("https://example.org/fr/album/1") is None


# ===== _iter_url_slots =====================================================
def test_iter_url_slots_finds_every_container():
    reco = {
        "links": [{"url": "https://a"}],
        "customLinks": [{"url": "https://b"}],
        "watchProviders": [{"url": "https://c"}],
        "linkOverrides": {"Deezer": "https://d"},
        "externalIds": {"deezer": "https://e"},
    }
    labels = [slot[0] for slot in fdl._iter_url_slots(reco)]
    assert labels == ["links[0].url", "customLinks[0].url", "watchProviders[0].url",
                      "linkOverrides['Deezer']", "externalIds.deezer"]


def test_iter_url_slots_tolerates_malformed_shapes():
    reco = {
        "links": "pas une liste",
        "customLinks": [None, {"url": 42}, {"pas_url": "x"}],
        "linkOverrides": {"A": 7},
        "externalIds": {"deezer": 3},
    }
    assert fdl._iter_url_slots(reco) == []


def test_iter_url_slots_on_empty_reco():
    assert fdl._iter_url_slots({}) == []


def test_iter_url_slots_ignores_non_dict_external_ids():
    assert fdl._iter_url_slots({"externalIds": "x", "linkOverrides": "y"}) == []


# ===== transform ===========================================================
def test_transform_rewrites_every_container():
    reco = {
        "id": "ubm-1",
        "links": [{"url": "https://www.deezer.com/us/album/262200072"}],
        "linkOverrides": {"Deezer": "https://www.deezer.com/fr/artist/259"},
        "externalIds": {"deezer": "https://www.deezer.com/en/track/7"},
    }
    changes = fdl.transform(reco)
    assert len(changes) == 3
    assert reco["links"][0]["url"] == "https://www.deezer.com/album/262200072"
    assert reco["linkOverrides"]["Deezer"] == "https://www.deezer.com/artist/259"
    assert reco["externalIds"]["deezer"] == "https://www.deezer.com/track/7"


def test_transform_leaves_canonical_urls_untouched():
    reco = {"id": "ubm-1", "links": [{"url": "https://www.deezer.com/album/1"}]}
    assert fdl.transform(reco) == []


def test_transform_warns_and_skips_unverified_section(caplog):
    reco = {"id": "ubm-1", "links": [{"url": "https://www.deezer.com/fr/playlist/9"}]}
    with caplog.at_level("WARNING"):
        assert fdl.transform(reco) == []
    assert "section Deezer non vérifiée" in caplog.text
    assert reco["links"][0]["url"] == "https://www.deezer.com/fr/playlist/9"


def test_transform_ignores_non_deezer_links():
    reco = {"id": "ubm-1", "links": [{"url": "https://open.spotify.com/us/album/1"}]}
    assert fdl.transform(reco) == []


# ===== CLI =================================================================
def test_main_dry_run_leaves_files_untouched(recos_root: Path, tmp_path: Path):
    path = _write(recos_root / "s" / "a.json",
                  {"id": "a", "links": [{"url": "https://www.deezer.com/us/album/9"}]})
    before = path.read_text(encoding="utf-8")
    report = tmp_path / "r.json"
    assert fdl.main(["--json", str(report)]) == 0
    assert path.read_text(encoding="utf-8") == before
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["applied"] is False and data["files"] == 1
    assert data["verified_sections"] == list(fdl.VERIFIED_SECTIONS)


def test_main_apply_writes_and_touches_only_the_url(recos_root: Path):
    """Après écriture, seule la ligne de l'URL diffère — le reste est identique."""
    original = {"id": "a", "title": "Œuvre à accents",
                "links": [{"label": "Deezer", "url": "https://www.deezer.com/us/album/9"}]}
    path = _write(recos_root / "s" / "a.json", original)
    before_lines = path.read_text(encoding="utf-8").splitlines()
    assert fdl.main(["--apply"]) == 0
    after_lines = path.read_text(encoding="utf-8").splitlines()
    differing = [(b, a) for b, a in zip(before_lines, after_lines, strict=True) if b != a]
    assert len(differing) == 1
    assert "deezer.com/us/album/9" in differing[0][0]
    assert "deezer.com/album/9" in differing[0][1]


def test_build_parser_defaults_to_dry_run():
    assert fdl.build_parser().parse_args([]).apply is False
