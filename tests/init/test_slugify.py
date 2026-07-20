"""Tests pour ``tools.init.slugify`` — cf. ADR 0038."""
from __future__ import annotations

import pytest

from tools.init.slugify import SLUG_MAX_LEN, is_valid_slug, slugify


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Un Bon Moment", "un-bon-moment"),
        ("Café & Croissants", "cafe-croissants"),
        ("  Trim  Me  ", "trim-me"),
        ("MAJ-uscules_avec_undersc", "maj-uscules-avec-undersc"),
        ("é à ü ñ", "e-a-u-n"),
        ("", "x"),
        ("@@@", "x"),
        ("a", "a"),
    ],
)
def test_slugify_examples(raw: str, expected: str) -> None:
    assert slugify(raw) == expected


def test_slugify_truncates_to_max_len() -> None:
    raw = "a" * (SLUG_MAX_LEN + 50)
    slug = slugify(raw)
    assert len(slug) <= SLUG_MAX_LEN
    assert is_valid_slug(slug)


def test_slugify_never_trailing_dash() -> None:
    assert slugify("hello---") == "hello"
    assert slugify("---hello") == "hello"


@pytest.mark.parametrize(
    "slug, ok",
    [
        ("un-bon-moment", True),
        ("a", True),
        ("a1b2c3", True),
        ("a" * SLUG_MAX_LEN, True),
        ("a" * (SLUG_MAX_LEN + 1), False),
        ("-leading", False),
        ("trailing-", False),
        ("double--dash", False),
        ("UPPER", False),
        ("with space", False),
        ("with_underscore", False),
        ("", False),
    ],
)
def test_is_valid_slug(slug: str, ok: bool) -> None:
    assert is_valid_slug(slug) is ok


def test_slugify_output_is_always_valid() -> None:
    for raw in ["Un Bon Moment", "Café & Croissants", "@@@", "à é ï"]:
        assert is_valid_slug(slugify(raw))
