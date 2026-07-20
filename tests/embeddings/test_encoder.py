"""tests pour embeddings.encoder."""
from __future__ import annotations

import pytest

from embeddings.encoder import (
    DEFAULT_DIM,
    DEFAULT_MODEL,
    EmbeddingInput,
    FastEmbedEncoder,
    build_input_text,
    source_hash,
)


def test_build_input_text_title_only() -> None:
    txt = build_input_text(EmbeddingInput(title="Mortel"))
    assert txt == "Mortel"


def test_build_input_text_all_fields() -> None:
    txt = build_input_text(
        EmbeddingInput(
            title="Mortel",
            creator="Frédéric Garcia",
            types=("serie", "drama"),
            description="Une série française sur Netflix.",
        )
    )
    assert (
        txt
        == "Mortel | Frédéric Garcia | serie, drama | Une série française sur Netflix."
    )


def test_build_input_text_strips_and_skips_empty() -> None:
    txt = build_input_text(
        EmbeddingInput(
            title="  Mortel  ", creator="   ", types=("", "serie", " "), description=""
        )
    )
    assert txt == "Mortel | serie"


def test_build_input_text_truncates_long_description() -> None:
    long_desc = ("mot " * 200).strip()  # ~800 char
    txt = build_input_text(EmbeddingInput(title="X", description=long_desc))
    # 256 char + ellipsis approximatif.
    desc_part = txt.split(" | ", 1)[1]
    assert len(desc_part) <= 260
    assert desc_part.endswith("…")


def test_build_input_text_truncation_without_late_space() -> None:
    # Pas d'espace dans la première moitié => coupe brute.
    desc = "a" * 300
    txt = build_input_text(EmbeddingInput(title="X", description=desc))
    desc_part = txt.split(" | ", 1)[1]
    assert desc_part.endswith("…")
    assert "a" in desc_part


def test_build_input_text_raises_on_empty_title() -> None:
    with pytest.raises(ValueError):
        build_input_text(EmbeddingInput(title="   "))


def test_source_hash_is_deterministic_and_sensitive() -> None:
    a = source_hash("Mortel | serie")
    b = source_hash("Mortel | serie")
    c = source_hash("mortel | serie")
    assert a == b
    assert a != c
    assert len(a) == 64  # hex sha256


def test_fastembed_encoder_raises_on_missing_lib(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans fastembed installé, l'instanciation explique comment installer."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "fastembed":
            raise ImportError("no fastembed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="fastembed"):
        FastEmbedEncoder()


def test_default_model_constants() -> None:
    assert isinstance(DEFAULT_MODEL, str) and DEFAULT_MODEL
    assert DEFAULT_DIM > 0
