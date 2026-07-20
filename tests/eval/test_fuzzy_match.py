"""TDD : matching approximatif titre + créateur pour le harness eval."""
from __future__ import annotations

from tools.eval.fuzzy_match import fuzzy_match_score, normalize_text


class TestNormalizeText:
    def test_lowercases(self) -> None:
        assert normalize_text("Drive") == "drive"

    def test_strips_diacritics(self) -> None:
        assert normalize_text("Amélie") == "amelie"

    def test_collapses_whitespace(self) -> None:
        assert normalize_text("  Le   Mépris  ") == "le mepris"

    def test_empty_string(self) -> None:
        assert normalize_text("") == ""

    def test_none_returns_empty(self) -> None:
        assert normalize_text(None) == ""


class TestFuzzyMatchScore:
    def test_exact_titles_score_1(self) -> None:
        assert fuzzy_match_score("Drive", None, "Drive", None) == 1.0

    def test_diacritics_ignored(self) -> None:
        # "Amélie" vs "Amelie" doivent matcher à 1.0
        assert fuzzy_match_score("Amélie", None, "Amelie", None) == 1.0

    def test_different_titles_score_low(self) -> None:
        assert fuzzy_match_score("Drive", None, "Inception", None) < 0.5

    def test_typo_titles_score_moderate(self) -> None:
        score = fuzzy_match_score("Inception", None, "Inceptoin", None)
        assert 0.7 < score < 1.0

    def test_creator_match_boosts_score(self) -> None:
        # Même titre, avec créateur identique vs sans → score boosté ou égal
        without = fuzzy_match_score("Drive", None, "Drive", None)
        with_creator = fuzzy_match_score(
            "Drive", "Nicolas Winding Refn", "Drive", "Nicolas Winding Refn",
        )
        assert with_creator >= without
        # Sur titres très proches mais pas exacts, le créateur fait basculer
        boost_no = fuzzy_match_score("The Matrix", None, "Matrix", None)
        boost_yes = fuzzy_match_score(
            "The Matrix", "Wachowski", "Matrix", "Wachowski",
        )
        assert boost_yes > boost_no

    def test_creator_mismatch_does_not_boost(self) -> None:
        with_match = fuzzy_match_score("Drive", "Refn", "Drive", "Refn")
        with_mismatch = fuzzy_match_score("Drive", "Refn", "Drive", "Spielberg")
        assert with_match > with_mismatch

    def test_score_bounded_0_1(self) -> None:
        s = fuzzy_match_score("a", "b", "c", "d")
        assert 0.0 <= s <= 1.0

    def test_both_empty_titles_returns_zero(self) -> None:
        assert fuzzy_match_score("", None, "", None) == 0.0

    def test_whitespace_only_creator_does_not_boost(self) -> None:
        # Créateur réduit à du whitespace → normalisation vide → pas de bonus.
        a = fuzzy_match_score("Drive", "   ", "Drive", "   ")
        b = fuzzy_match_score("Drive", None, "Drive", None)
        assert a == b == 1.0
