"""Tests embeddings.settings (P3.5-B / ADR 0033)."""
from __future__ import annotations

from pathlib import Path

import pytest

from embeddings.settings import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_DB_PATH,
    DEFAULT_DEDUP_THRESHOLD,
    DEFAULT_DESC_MAX_CHARS,
    DEFAULT_MODEL,
    EmbeddingsSettings,
)


class TestDefaults:
    def test_default_values(self) -> None:
        s = EmbeddingsSettings()
        assert s.model_name == DEFAULT_MODEL
        assert s.batch_size == DEFAULT_BATCH_SIZE
        assert s.dedup_threshold == DEFAULT_DEDUP_THRESHOLD
        assert s.db_path == DEFAULT_DB_PATH
        assert s.desc_max_chars == DEFAULT_DESC_MAX_CHARS


class TestValidation:
    def test_empty_model_rejected(self) -> None:
        with pytest.raises(ValueError, match="model_name"):
            EmbeddingsSettings(model_name="   ")

    def test_zero_batch_rejected(self) -> None:
        with pytest.raises(ValueError, match="batch_size"):
            EmbeddingsSettings(batch_size=0)

    def test_negative_batch_rejected(self) -> None:
        with pytest.raises(ValueError, match="batch_size"):
            EmbeddingsSettings(batch_size=-1)

    def test_bool_batch_rejected(self) -> None:
        with pytest.raises(ValueError, match="batch_size"):
            EmbeddingsSettings(batch_size=True)  # type: ignore[arg-type]

    def test_threshold_out_of_bounds(self) -> None:
        with pytest.raises(ValueError, match="dedup_threshold"):
            EmbeddingsSettings(dedup_threshold=1.5)
        with pytest.raises(ValueError, match="dedup_threshold"):
            EmbeddingsSettings(dedup_threshold=-2.0)

    def test_threshold_bool_rejected(self) -> None:
        with pytest.raises(ValueError, match="dedup_threshold"):
            EmbeddingsSettings(dedup_threshold=True)  # type: ignore[arg-type]

    def test_negative_one_threshold_accepted(self) -> None:
        # Borne inclusive [-1, 1] — cosine peut être négative.
        s = EmbeddingsSettings(dedup_threshold=-1.0)
        assert s.dedup_threshold == -1.0

    def test_negative_desc_max_rejected(self) -> None:
        with pytest.raises(ValueError, match="desc_max_chars"):
            EmbeddingsSettings(desc_max_chars=0)

    def test_db_path_str_coerced_to_path(self) -> None:
        s = EmbeddingsSettings(db_path="/tmp/x.sqlite")  # type: ignore[arg-type]
        assert isinstance(s.db_path, Path)


class TestFromSourceExtra:
    def test_none_extra_defaults(self) -> None:
        assert EmbeddingsSettings.from_source_extra(None) == EmbeddingsSettings()

    def test_missing_key_defaults(self) -> None:
        s = EmbeddingsSettings.from_source_extra({"other": {"x": 1}})
        assert s == EmbeddingsSettings()

    def test_payload_used(self) -> None:
        s = EmbeddingsSettings.from_source_extra(
            {"embeddings": {"batch_size": 128, "dedup_threshold": 0.9}}
        )
        assert s.batch_size == 128
        assert s.dedup_threshold == 0.9

    def test_overrides_win(self) -> None:
        s = EmbeddingsSettings.from_source_extra(
            {"embeddings": {"batch_size": 32}},
            overrides={"batch_size": 256},
        )
        assert s.batch_size == 256

    def test_overrides_none_ignored(self) -> None:
        # CLI passe None pour les flags non précisés → ne doit pas écraser
        # la config source.
        s = EmbeddingsSettings.from_source_extra(
            {"embeddings": {"batch_size": 32}},
            overrides={"batch_size": None, "dedup_threshold": None},
        )
        assert s.batch_size == 32
        assert s.dedup_threshold == DEFAULT_DEDUP_THRESHOLD

    def test_unknown_key_ignored(self) -> None:
        # forward-compat — un fork peut shipper un nouveau seuil avant
        # que le code l'utilise.
        s = EmbeddingsSettings.from_source_extra(
            {"embeddings": {"future_param": "x"}}
        )
        assert s == EmbeddingsSettings()


class TestFrozen:
    def test_immutable(self) -> None:
        s = EmbeddingsSettings()
        with pytest.raises((AttributeError, TypeError)):
            s.batch_size = 99  # type: ignore[misc]
