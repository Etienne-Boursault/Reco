"""Tests audit_core.sidecar — _safe_segment, ensure_output_within."""
from __future__ import annotations

from pathlib import Path

import pytest

from audit_core.sidecar import _safe_segment, ensure_output_within


class TestSafeSegment:
    def test_valid_slug(self) -> None:
        assert _safe_segment("source_id", "un-bon-moment") == "un-bon-moment"

    def test_valid_hex_id(self) -> None:
        assert _safe_segment(
            "item_id", "abc12345_xyz"
        ) == "abc12345_xyz"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="non vide"):
            _safe_segment("x", "")

    def test_non_str_raises(self) -> None:
        with pytest.raises(ValueError, match="non vide"):
            _safe_segment("x", None)  # type: ignore[arg-type]

    def test_nul_byte_raises(self) -> None:
        with pytest.raises(ValueError, match="NUL"):
            _safe_segment("x", "abc\x00def")

    def test_slash_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalide"):
            _safe_segment("x", "a/b")

    def test_backslash_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalide"):
            _safe_segment("x", "a\\b")

    def test_dotdot_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalide"):
            _safe_segment("x", "..")

    def test_uppercase_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalide"):
            _safe_segment("x", "Foo")

    def test_starts_with_dash_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalide"):
            _safe_segment("x", "-abc")

    def test_starts_with_underscore_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalide"):
            _safe_segment("x", "_abc")

    def test_windows_reserved_con_rejected(self) -> None:
        with pytest.raises(ValueError, match="réservé Windows"):
            _safe_segment("x", "con")

    def test_windows_reserved_com1_rejected(self) -> None:
        with pytest.raises(ValueError, match="réservé Windows"):
            _safe_segment("x", "com1")

    def test_windows_reserved_lpt9_rejected(self) -> None:
        with pytest.raises(ValueError, match="réservé Windows"):
            _safe_segment("x", "lpt9")

    def test_windows_reserved_case_insensitive(self) -> None:
        # même si la regex impose lowercase, doublons safety net :
        # une str "CON" est déjà rejetée par la regex.
        with pytest.raises(ValueError):
            _safe_segment("x", "CON")

    def test_too_long_rejected(self) -> None:
        with pytest.raises(ValueError, match="invalide"):
            _safe_segment("x", "a" + "b" * 129)

    def test_max_length_accepted(self) -> None:
        s = "a" + "b" * 128  # 129 chars
        assert _safe_segment("x", s) == s


class TestEnsureOutputWithin:
    def test_inside_ok(self, tmp_path: Path) -> None:
        target = tmp_path / "sub" / "out.md"
        result = ensure_output_within(tmp_path, target)
        assert result == target.resolve()

    def test_outside_rejected(self, tmp_path: Path) -> None:
        other = tmp_path.parent / "elsewhere.md"
        with pytest.raises(ValueError, match="hors de base"):
            ensure_output_within(tmp_path, other)

    def test_traversal_rejected(self, tmp_path: Path) -> None:
        target = tmp_path / ".." / "evil.md"
        with pytest.raises(ValueError, match="hors de base"):
            ensure_output_within(tmp_path, target)
