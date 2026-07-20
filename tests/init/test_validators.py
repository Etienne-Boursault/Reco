"""Tests pour ``tools.init.validators``."""
from __future__ import annotations

import pytest

from tools.init.validators import (
    is_valid_email,
    is_valid_hex_color,
    is_valid_reco_prefix,
    is_valid_url,
)


@pytest.mark.parametrize(
    "value, ok",
    [
        ("#ffd23f", True),
        ("#FFD23F", True),
        ("#fff", False),  # 3-char short form refusé (Zod = 6 strict)
        ("ffd23f", False),
        ("#ggghhh", False),
        ("", False),
    ],
)
def test_hex_color(value: str, ok: bool) -> None:
    assert is_valid_hex_color(value) is ok


@pytest.mark.parametrize(
    "value, ok",
    [
        ("https://example.com/rss", True),
        ("http://example.com", True),
        ("HTTPS://EXAMPLE.COM", True),
        ("ftp://example.com", False),
        ("example.com", False),
        ("", False),
    ],
)
def test_url(value: str, ok: bool) -> None:
    assert is_valid_url(value) is ok


@pytest.mark.parametrize(
    "value, ok",
    [
        ("ubm", True),
        ("a1", True),
        ("abcdefgh", True),  # 8 chars max
        ("a", False),         # < 2
        ("abcdefghi", False), # > 8
        ("UBM", False),       # majuscules refusées
        ("u-m", False),       # tirets refusés
        ("", False),
    ],
)
def test_reco_prefix(value: str, ok: bool) -> None:
    assert is_valid_reco_prefix(value) is ok


@pytest.mark.parametrize(
    "value, ok",
    [
        ("a@b.fr", True),
        ("foo+bar@example.co.uk", True),
        ("plainstring", False),
        ("a@b", False),
        ("", False),
    ],
)
def test_email(value: str, ok: bool) -> None:
    assert is_valid_email(value) is ok
