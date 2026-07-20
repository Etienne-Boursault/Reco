"""Tests pour ``tools.init.writer`` — génération JSON source Zod-valide."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.init.writer import (
    DEFAULT_THEME_COLORS,
    ValidationError,
    WizardAnswers,
    build_source_config,
    serialize,
    validate_answers,
    write_source,
)


def _ok_answers(**overrides) -> WizardAnswers:
    base = dict(
        slug="mon-podcast",
        title="Mon Podcast",
        rss_url="https://example.com/rss.xml",
        site_url="https://mon-podcast.fr",
        hosts=["Alice", "Bob"],
        reco_prefix="mp",
        accent="#5eead4",
        bg="#0e0e10",
        public_site_url="https://mon-podcast.fr",
        contact_email="hello@mon-podcast.fr",
    )
    base.update(overrides)
    return WizardAnswers(**base)


def test_build_source_config_complete() -> None:
    ans = _ok_answers()
    data = build_source_config(ans)
    assert data["id"] == "mon-podcast"
    assert data["title"] == "Mon Podcast"
    assert data["rssUrl"] == "https://example.com/rss.xml"
    assert data["website"] == "https://mon-podcast.fr"
    assert data["hosts"] == ["Alice", "Bob"]
    assert data["recoPrefix"] == "mp"
    assert data["theme"]["colors"]["accent"] == "#5eead4"
    assert data["theme"]["colors"]["bg"] == "#0e0e10"
    # Surface/text/muted/accentText : defaults injectés
    assert data["theme"]["colors"]["surface"] == DEFAULT_THEME_COLORS["surface"]
    assert data["theme"]["colors"]["text"] == DEFAULT_THEME_COLORS["text"]
    assert data["theme"]["colors"]["muted"] == DEFAULT_THEME_COLORS["muted"]
    assert data["siteColorAccent"] == "#5eead4"  # cohérence pipeline
    assert data["schemaVersion"] == 1


def test_build_source_config_optional_omitted() -> None:
    ans = _ok_answers(site_url="", reco_prefix="", contact_email="")
    data = build_source_config(ans)
    assert "website" not in data
    assert "recoPrefix" not in data
    # Pas de site_url → pas de siteColorAccent non plus (lié au prefixe).
    assert "siteColorAccent" not in data


@pytest.mark.parametrize(
    "field, bad",
    [
        ("slug", "BAD SLUG"),
        ("slug", "-leading"),
        ("title", ""),
        ("rss_url", "not-a-url"),
        ("accent", "fff"),
        ("bg", "#zz0000"),
        ("reco_prefix", "TOO_LONG_PREFIX"),
        ("contact_email", "nope"),
    ],
)
def test_validate_answers_rejects_bad_inputs(field: str, bad: str) -> None:
    ans = _ok_answers(**{field: bad})
    with pytest.raises(ValidationError):
        validate_answers(ans)


def test_serialize_is_deterministic_and_utf8() -> None:
    ans = _ok_answers(title="Café & Cœur")
    text = serialize(build_source_config(ans))
    # Ascii non-échappé (accents bruts) + indent 2 + clés triées.
    assert "Café & Cœur" in text
    assert text.endswith("\n")
    # Idempotence (même contenu → même string).
    assert serialize(build_source_config(ans)) == text


def test_serialize_parses_back_to_same_dict() -> None:
    ans = _ok_answers()
    data = build_source_config(ans)
    assert json.loads(serialize(data)) == data


def test_write_source_writes_file(tmp_path: Path) -> None:
    ans = _ok_answers(slug="demo-test")
    path, text = write_source(ans, tmp_path)
    assert path == tmp_path / "demo-test.json"
    assert path.read_text(encoding="utf-8") == text
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["id"] == "demo-test"


def test_write_source_refuses_existing_without_force(tmp_path: Path) -> None:
    ans = _ok_answers(slug="demo-test")
    write_source(ans, tmp_path)
    with pytest.raises(FileExistsError):
        write_source(ans, tmp_path)


def test_write_source_force_overwrites(tmp_path: Path) -> None:
    ans = _ok_answers(slug="demo-test")
    write_source(ans, tmp_path)
    ans2 = _ok_answers(slug="demo-test", title="V2")
    path, _ = write_source(ans2, tmp_path, force=True)
    assert json.loads(path.read_text(encoding="utf-8"))["title"] == "V2"


def test_write_source_dry_run_no_write(tmp_path: Path) -> None:
    ans = _ok_answers(slug="demo-test")
    path, text = write_source(ans, tmp_path, dry_run=True)
    assert not path.exists()
    assert "demo-test" in text


def test_zod_required_theme_colors_present() -> None:
    """Le schéma Zod exige bg, surface, text, muted, accent (cf. content.config.ts)."""
    ans = _ok_answers()
    colors = build_source_config(ans)["theme"]["colors"]
    for key in ("bg", "surface", "text", "muted", "accent"):
        assert key in colors and colors[key], f"theme.colors.{key} manquant ou vide"
