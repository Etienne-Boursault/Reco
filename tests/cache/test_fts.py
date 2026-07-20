"""Tests cache.fts — sanitisation FTS5 + recherche via reader."""
from __future__ import annotations

from pathlib import Path

from cache.builder import CacheBuilder
from cache.fts import fts_query
from cache.reader import CacheReader


class TestFtsQuery:
    def test_simple_word(self) -> None:
        q = fts_query("bong")
        assert q == '"bong"*'

    def test_multi_words_joined(self) -> None:
        q = fts_query("bong joon")
        assert q == '"bong"* "joon"*'

    def test_strips_reserved_words(self) -> None:
        # AND/OR/NOT en majuscules sont opérateurs FTS5 — on les retire.
        q = fts_query("film AND coréen")
        assert "AND" not in q
        assert '"film"*' in q
        assert '"coréen"*' in q

    def test_escapes_internal_quotes(self) -> None:
        # Le tokenizer split sur les guillemets ; on vérifie au moins
        # que la requête est bien formée (pas de SQL injection FTS5).
        q = fts_query('say "hello"')
        assert '"say"*' in q
        assert '"hello"*' in q

    def test_quote_acts_as_separator(self) -> None:
        # `"` n'est pas un caractère de mot → split → deux tokens.
        q = fts_query('foo"bar')
        assert '"foo"*' in q
        assert '"bar"*' in q

    def test_empty_returns_no_match(self) -> None:
        # Sentinel durci par Fixer P2.8 (CR senior M6) : `\x01\x01NOMATCH\x01\x01`
        # improbable à reproduire par un utilisateur (au lieu de `__nomatch__`).
        assert fts_query("") == '"\x01\x01NOMATCH\x01\x01"'

    def test_only_punctuation_returns_no_match(self) -> None:
        assert fts_query("!?.,") == '"\x01\x01NOMATCH\x01\x01"'

    def test_no_prefix_option(self) -> None:
        q = fts_query("foo", prefix=False)
        assert q == '"foo"'

    def test_unicode_diacritics_preserved(self) -> None:
        # On laisse passer les accents — sqlite remove_diacritics les gérera.
        q = fts_query("forêt")
        assert '"forêt"*' == q

    def test_apostrophe_kept_in_token(self) -> None:
        # `\w'` autorise l'apostrophe → "l'horizon" reste un seul token.
        q = fts_query("l'horizon")
        assert q == '"l\'horizon"*'


class TestSearchItems:
    def test_finds_by_title(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            hits = r.search_items("Parasite")
            assert len(hits) >= 1
            assert hits[0].title == "Parasite"
            assert hits[0].rank < 0  # BM25 négatif (FTS5)

    def test_finds_by_recommended_by(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            hits = r.search_items("Bong")
            ids = {h.id for h in hits}
            # item-001 est recommandé par Bong Joon-ho.
            assert "item-001" in ids

    def test_finds_via_episode_guests(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            # "Joon" matche guests_parsed via GROUP_CONCAT.
            hits = r.search_items("Joon")
            assert any(h.id == "item-001" for h in hits)

    def test_prefix_matching(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            # "Para" doit matcher "Parasite" via prefix `*`.
            hits = r.search_items("Para")
            assert any(h.title == "Parasite" for h in hits)

    def test_limit_respected(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            # Query "e" matche large ; limite à 1.
            hits = r.search_items("e", limit=1)
            assert len(hits) <= 1

    def test_no_match_returns_empty(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            assert r.search_items("zzzunlikelyzzz") == []

    def test_empty_query_returns_empty(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            assert r.search_items("") == []


class TestSearchEpisodes:
    def test_finds_by_title(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            hits = r.search_episodes("Bong")
            assert len(hits) >= 1
            assert hits[0].id == "ep-A1"

    def test_finds_by_host(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            hits = r.search_episodes("Khojandi")
            assert any(h.id == "ep-A1" for h in hits)

    def test_no_match(self, built_cache: tuple[Path, CacheBuilder]) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            assert r.search_episodes("zzznopezzz") == []

    def test_bm25_ranking_ordered(
        self, built_cache: tuple[Path, CacheBuilder]
    ) -> None:
        db_path, _ = built_cache
        with CacheReader(db_path) as r:
            hits = r.search_episodes("Bong")
            # Liste triée par rank ascendant (BM25 négatif → plus négatif d'abord).
            ranks = [h.rank for h in hits]
            assert ranks == sorted(ranks)
