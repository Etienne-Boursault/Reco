"""Tests audit_core.reporters — escape_md, Reporter Protocol."""
from __future__ import annotations

import pytest

from audit_core.reporters import REPORTERS, Reporter, escape_md


class TestEscapeMd:
    def test_backslash_escaped(self) -> None:
        assert escape_md("a\\b") == "a\\\\b"

    def test_asterisk_escaped(self) -> None:
        assert escape_md("**bold**") == "\\*\\*bold\\*\\*"

    def test_underscore_escaped(self) -> None:
        assert escape_md("a_b") == "a\\_b"

    def test_backtick_escaped(self) -> None:
        assert escape_md("`code`") == "\\`code\\`"

    def test_brackets_escaped(self) -> None:
        assert escape_md("[link]") == "\\[link\\]"

    def test_pipe_escaped(self) -> None:
        assert escape_md("a|b") == "a\\|b"

    def test_newline_to_space(self) -> None:
        assert escape_md("a\nb") == "a b"

    def test_carriage_return_to_space(self) -> None:
        assert escape_md("a\rb") == "a b"

    def test_idempotent_on_safe_chars(self) -> None:
        assert escape_md("hello world 123") == "hello world 123"

    def test_combined(self) -> None:
        # tous les chars en même temps.
        result = escape_md("**a**|b\nc`d`[e]_f_\\g")
        assert "\\*\\*" in result
        assert "\\|" in result
        assert "\n" not in result
        assert "\\`" in result
        assert "\\[" in result
        assert "\\]" in result
        assert "\\_" in result
        assert "\\\\" in result

    def test_non_str_raises_typeerror(self) -> None:
        with pytest.raises(TypeError):
            escape_md(42)  # type: ignore[arg-type]

    def test_backslash_first_avoids_double_escape(self) -> None:
        # invariant : un '*' devient '\*' (PAS '\\*') car '\' est échappé
        # AVANT '*'. C'est le motif standard markdown.
        # En entrée pure d'un '*' isolé, on doit voir '\*' (= "\\*" en repr).
        out = escape_md("*")
        assert out == "\\*"

    def test_existing_backslash_doubled_then_other_chars(self) -> None:
        # '\*' en entrée → '\\\*' (le '\' devient '\\' puis le '*' devient '\*').
        out = escape_md("\\*")
        assert out == "\\\\\\*"


class _GoodReporter:
    format_id = "markdown"

    def render(self, report) -> str:  # noqa: ANN
        return f"# Report {report}"


class _NoFormatId:
    def render(self, report):  # noqa: ANN
        return ""


class TestReporterProtocol:
    def test_conforming(self) -> None:
        assert isinstance(_GoodReporter(), Reporter)

    def test_missing_format_id_rejected(self) -> None:
        assert not isinstance(_NoFormatId(), Reporter)

    def test_registry_empty_by_default(self) -> None:
        # registre vide à l'init — les modules le peuplent.
        assert isinstance(REPORTERS, dict)
