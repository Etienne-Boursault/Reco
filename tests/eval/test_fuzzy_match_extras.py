"""Tests Unicode & ponctuation pour ``normalize_text`` / ``fuzzy_match_score``.

Couvre les edge cases identifiés par la CR senior (H2, H5) : NFD vs NFC,
casefold ß, ponctuation française (« » ' œ æ), guillemets typographiques.
"""
from __future__ import annotations

import unicodedata

from tools.eval.fuzzy_match import fuzzy_match_score, normalize_text
from tools.eval.types import EvalConfig


class TestNormalizeTextUnicode:
    def test_nfd_vs_nfc_equal(self) -> None:
        nfc = "café"  # composé
        nfd = unicodedata.normalize("NFD", nfc)  # décomposé
        assert normalize_text(nfc) == normalize_text(nfd) == "cafe"

    def test_strips_punctuation(self) -> None:
        assert normalize_text("Drive!") == "drive"
        assert normalize_text("Star Wars: Episode IV") \
            == "star wars episode iv"

    def test_french_typographic_quotes(self) -> None:
        # « et » sont des Pi/Pf en Unicode → retirés.
        assert normalize_text("« Drive »") == "drive"

    def test_apostrophe_curly(self) -> None:
        # Apostrophe typographique (U+2019) doit être normalisée.
        a = normalize_text("l'œuf")
        b = normalize_text("l’oeuf")
        # Les deux doivent être normalisés et casefoldés.
        assert "œ" in a or "oe" in a
        assert a.replace("œ", "oe") == b.replace("œ", "oe")

    def test_ss_casefold(self) -> None:
        # casefold transforme ß en ss (ce que .lower() ne fait pas).
        assert normalize_text("Straße") == "strasse"

    def test_only_punctuation_returns_empty(self) -> None:
        assert normalize_text("!!! ??? ...") == ""

    def test_mixed_case_collapsed(self) -> None:
        assert normalize_text("DRIVE drive Drive") == "drive drive drive"


class TestFuzzyMatchConfigurable:
    def test_config_threshold_changes_boost(self) -> None:
        cfg_loose = EvalConfig(
            fuzzy_threshold=0.5, creator_boost=0.3,
            creator_boost_threshold=0.5,
        )
        cfg_tight = EvalConfig(
            fuzzy_threshold=0.5, creator_boost=0.01,
            creator_boost_threshold=0.5,
        )
        s_loose = fuzzy_match_score("Matrix", "Wachowski", "The Matrix",
                                    "Wachowski", config=cfg_loose)
        s_tight = fuzzy_match_score("Matrix", "Wachowski", "The Matrix",
                                    "Wachowski", config=cfg_tight)
        assert s_loose > s_tight

    def test_default_config_used_when_none(self) -> None:
        # Sanity : appel sans config = appel avec EvalConfig().
        s1 = fuzzy_match_score("Drive", "Refn", "Drive", "Refn")
        s2 = fuzzy_match_score("Drive", "Refn", "Drive", "Refn",
                               config=EvalConfig())
        assert s1 == s2
