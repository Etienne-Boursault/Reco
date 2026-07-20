"""Tests audit_core.settings.from_source_extra."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from audit_core.settings import from_source_extra


@dataclass(frozen=True, slots=True)
class _Demo:
    a: int = 1
    b: float = 0.5
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.b <= 1.0:
            raise ValueError("b hors [0,1]")


class TestFromSourceExtra:
    def test_none_extra_defaults(self) -> None:
        s = from_source_extra(None, "demo", _Demo)
        assert s == _Demo()

    def test_missing_key_defaults(self) -> None:
        s = from_source_extra({"other": {"a": 99}}, "demo", _Demo)
        assert s == _Demo()

    def test_payload_overrides_defaults(self) -> None:
        s = from_source_extra({"demo": {"a": 42, "b": 0.9}}, "demo", _Demo)
        assert s.a == 42
        assert s.b == 0.9

    def test_unknown_field_ignored(self) -> None:
        # forward-compat : un fork ajoute un champ ; on l'ignore sans crasher.
        s = from_source_extra(
            {"demo": {"a": 2, "future_field": "x"}}, "demo", _Demo
        )
        assert s.a == 2

    def test_none_value_in_payload_falls_back_to_default(self) -> None:
        s = from_source_extra({"demo": {"a": None, "b": 0.3}}, "demo", _Demo)
        assert s.a == 1  # défaut conservé
        assert s.b == 0.3

    def test_overrides_win_over_payload(self) -> None:
        s = from_source_extra(
            {"demo": {"a": 5}},
            "demo",
            _Demo,
            overrides={"a": 99},
        )
        assert s.a == 99

    def test_override_none_does_not_override(self) -> None:
        s = from_source_extra(
            {"demo": {"a": 5}}, "demo", _Demo, overrides={"a": None},
        )
        assert s.a == 5

    def test_tuple_field_coerced_from_list(self) -> None:
        s = from_source_extra(
            {"demo": {"tags": ["x", "y"]}},
            "demo",
            _Demo,
            tuple_fields=frozenset({"tags"}),
        )
        assert s.tags == ("x", "y")

    def test_tuple_field_not_in_tuple_fields_passes_through(self) -> None:
        # tags livré en list, mais on ne le déclare pas en tuple_fields :
        # le dataclass __post_init__ accepterait (notre _Demo n'a pas de
        # check de type sur tags). Le résultat sera une list.
        s = from_source_extra({"demo": {"tags": ["x"]}}, "demo", _Demo)
        assert s.tags == ["x"]

    def test_non_mapping_payload_ignored(self) -> None:
        s = from_source_extra({"demo": "not-a-dict"}, "demo", _Demo)
        assert s == _Demo()

    def test_non_mapping_extra_ignored(self) -> None:
        s = from_source_extra("not-a-mapping", "demo", _Demo)  # type: ignore[arg-type]
        assert s == _Demo()

    def test_not_a_dataclass_raises(self) -> None:
        class Plain:
            pass

        with pytest.raises(TypeError, match="dataclass"):
            from_source_extra(None, "demo", Plain)

    def test_invalid_value_bubbles_up_post_init_error(self) -> None:
        with pytest.raises(ValueError, match="hors"):
            from_source_extra({"demo": {"b": 5.0}}, "demo", _Demo)

    def test_override_unknown_field_ignored(self) -> None:
        # un override CLI qui ne correspond à aucun champ du dataclass
        # est ignoré silencieusement (pas de TypeError sur **kwargs).
        s = from_source_extra(
            {"demo": {"a": 7}},
            "demo",
            _Demo,
            overrides={"unknown_flag": "x"},
        )
        assert s.a == 7
