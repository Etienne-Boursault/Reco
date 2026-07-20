"""Tests audit_core.cli_runner — RunOptionsBase, utcnow_iso."""
from __future__ import annotations

import re

import pytest

from audit_core.cli_runner import RunOptionsBase, utcnow_iso


class TestUtcnowIso:
    def test_iso_format(self) -> None:
        s = utcnow_iso()
        # 2026-06-10T12:34:56Z
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", s)

    def test_two_calls_monotonic(self) -> None:
        a = utcnow_iso()
        b = utcnow_iso()
        assert a <= b  # str comparison ISO ⇔ chronological


class TestRunOptionsBase:
    def test_minimal_defaults(self) -> None:
        opts = RunOptionsBase[None, None](source_id="src")
        assert opts.source_id == "src"
        assert opts.mode == "check"
        assert opts.output_format == "human"
        assert opts.audited_at is None
        assert opts.fail_on_suspect is False

    def test_frozen(self) -> None:
        opts = RunOptionsBase[None, None](source_id="src")
        with pytest.raises((AttributeError, TypeError)):
            opts.source_id = "other"  # type: ignore[misc]

    def test_full_config(self) -> None:
        opts = RunOptionsBase[None, None](
            source_id="src",
            mode="apply",
            output_format="markdown",
            audited_at="2026-06-10T12:00:00Z",
            fail_on_suspect=True,
        )
        assert opts.mode == "apply"
        assert opts.output_format == "markdown"
        assert opts.audited_at == "2026-06-10T12:00:00Z"
        assert opts.fail_on_suspect is True
