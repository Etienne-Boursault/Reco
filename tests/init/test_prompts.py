"""Tests pour ``tools.init.prompts`` — mock stdin/stdout via StringIO."""
from __future__ import annotations

import io

import pytest

from tools.init.prompts import (
    ask_list,
    ask_text,
    ask_yes_no,
    hex_validator,
    suggest_slug,
    url_validator,
)


def _io(input_text: str) -> tuple[io.StringIO, io.StringIO]:
    return io.StringIO(input_text), io.StringIO()


def test_ask_text_simple() -> None:
    stdin, stdout = _io("hello world\n")
    out = ask_text("Nom", stdin=stdin, stdout=stdout)
    assert out == "hello world"
    assert "Nom" in stdout.getvalue()


def test_ask_text_uses_default_on_empty() -> None:
    stdin, stdout = _io("\n")
    out = ask_text("Nom", default="defaut", stdin=stdin, stdout=stdout)
    assert out == "defaut"


def test_ask_text_retries_on_invalid() -> None:
    stdin, stdout = _io("bad\nhttps://ok.com/rss\n")
    out = ask_text(
        "RSS", validator=url_validator,
        error_msg="URL invalide.",
        stdin=stdin, stdout=stdout,
    )
    assert out == "https://ok.com/rss"
    assert "URL invalide." in stdout.getvalue()


def test_ask_text_optional_returns_empty() -> None:
    stdin, stdout = _io("\n")
    out = ask_text("Optionnel", required=False, stdin=stdin, stdout=stdout)
    assert out == ""


def test_ask_text_raises_after_max_attempts() -> None:
    stdin, stdout = _io("a\nb\nc\nd\ne\nf\n")
    with pytest.raises(ValueError, match="Trop de tentatives"):
        ask_text(
            "Couleur", validator=hex_validator,
            stdin=stdin, stdout=stdout, max_attempts=3,
        )


def test_ask_text_eof_raises() -> None:
    stdin, stdout = _io("")
    with pytest.raises(EOFError):
        ask_text("Nom", stdin=stdin, stdout=stdout)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("o\n", True),
        ("oui\n", True),
        ("y\n", True),
        ("yes\n", True),
        ("n\n", False),
        ("non\n", False),
        ("no\n", False),
    ],
)
def test_ask_yes_no(raw: str, expected: bool) -> None:
    stdin, stdout = _io(raw)
    assert ask_yes_no("OK ?", stdin=stdin, stdout=stdout) is expected


def test_ask_yes_no_default_on_empty() -> None:
    stdin, stdout = _io("\n")
    assert ask_yes_no("OK ?", default=True, stdin=stdin, stdout=stdout) is True
    stdin, stdout = _io("\n")
    assert ask_yes_no("OK ?", default=False, stdin=stdin, stdout=stdout) is False


def test_ask_list_csv() -> None:
    stdin, stdout = _io("Kyan, Navo, Eric\n")
    assert ask_list("Hosts", stdin=stdin, stdout=stdout) == ["Kyan", "Navo", "Eric"]


def test_ask_list_one_per_line() -> None:
    stdin, stdout = _io("Kyan\nNavo\n\n")
    assert ask_list("Hosts", stdin=stdin, stdout=stdout) == ["Kyan", "Navo"]


def test_ask_list_empty_first() -> None:
    stdin, stdout = _io("\n")
    assert ask_list("Hosts", stdin=stdin, stdout=stdout) == []


def test_suggest_slug() -> None:
    assert suggest_slug("Un Bon Moment") == "un-bon-moment"
