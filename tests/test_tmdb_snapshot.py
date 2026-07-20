"""Tests pour ``tools/tmdb_snapshot.py`` (P1.8).

Aucune requête HTTP réelle : on injecte un fetcher fake. Idempotence,
fraîcheur, rate-limit, erreurs, CLI : tous testés.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from unittest.mock import patch

import pytest

import tmdb_snapshot as ts
from domain.item import ExternalIds, Item, ItemType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write_item(items_dir: Path, source: str, item_id: str, **ext_kwargs) -> None:
    """Écrit un item minimal valide pour ItemRepoJson."""
    item = Item(
        id=item_id,
        types=(ItemType.FILM,),
        title=f"Title {item_id}",
        external_ids=ExternalIds(**ext_kwargs),
    )
    # Utiliser le repo pour écrire (au format attendu).
    from repository.item_repo import ItemRepoJson

    repo = ItemRepoJson(items_dir, source)
    repo.upsert(item)


def _fake_now(year: int = 2026, month: int = 6, day: int = 10):
    return lambda: _dt.datetime(year, month, day, 12, 0, 0)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def test_utcnow_iso_uses_injection():
    out = ts._utcnow_iso(now=_fake_now())
    assert out == "2026-06-10T12:00:00Z"


@pytest.mark.parametrize(
    "value,expected_type",
    [
        ("2026-06-10T12:00:00Z", _dt.datetime),
        ("2026-06-10T12:00:00+00:00", _dt.datetime),
        ("not-a-date", type(None)),
        (123, type(None)),
        ("", type(None)),
    ],
)
def test_parse_iso(value, expected_type):
    assert isinstance(ts._parse_iso(value), expected_type)


def test_is_fresh_true_within_window():
    payload = {
        "_cacheVersion": 1,
        "fetchedAt": "2026-06-01T00:00:00Z",
    }
    assert ts._is_fresh(payload, now=_fake_now()) is True


def test_is_fresh_handles_aware_now():
    """Le helper coerce now() aware en naive UTC pour comparer sans erreur."""
    aware = lambda: _dt.datetime(2026, 6, 10, tzinfo=_dt.timezone.utc)
    payload = {"_cacheVersion": 1, "fetchedAt": "2026-06-01T00:00:00Z"}
    assert ts._is_fresh(payload, now=aware) is True


def test_is_fresh_false_when_too_old():
    payload = {
        "_cacheVersion": 1,
        "fetchedAt": "2026-01-01T00:00:00Z",
    }
    assert ts._is_fresh(payload, now=_fake_now()) is False


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"_cacheVersion": 2, "fetchedAt": "2026-06-01T00:00:00Z"},
        {"_cacheVersion": 1, "fetchedAt": "not-a-date"},
        {"_cacheVersion": 1},
        "not-a-dict",
    ],
)
def test_is_fresh_false_for_invalid_inputs(payload):
    assert ts._is_fresh(payload, now=_fake_now()) is False


def test_build_cache_entry_shape():
    entry = ts._build_cache_entry(
        kind="movie", payload={"id": 42, "title": "X"}, now=_fake_now(),
    )
    assert entry["_cacheVersion"] == 1
    assert entry["kind"] == "movie"
    assert entry["fetchedAt"] == "2026-06-10T12:00:00Z"
    assert entry["payload"] == {"id": 42, "title": "X"}


def test_read_existing_returns_none_on_missing(tmp_path):
    assert ts._read_existing(tmp_path / "absent.json") is None


def test_read_existing_returns_none_on_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert ts._read_existing(p) is None


def test_read_existing_returns_dict(tmp_path):
    p = tmp_path / "ok.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    assert ts._read_existing(p) == {"a": 1}


# ---------------------------------------------------------------------------
# HTTP fetcher (rejet de kind invalide ; on ne teste pas le call réseau)
# ---------------------------------------------------------------------------
def test_make_http_fetcher_rejects_invalid_kind():
    fetcher = ts._make_http_fetcher("APIKEY")
    with pytest.raises(ValueError, match="kind invalide"):
        fetcher("audio", 1)


def test_make_http_fetcher_makes_a_request(monkeypatch):
    """Le fetcher passe les bons paramètres URL (mock urlopen)."""
    captured = {}

    class _Resp:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._body

    def _fake_urlopen(req, timeout=30):  # noqa: ARG001
        captured["url"] = req.full_url
        return _Resp(b'{"id": 99}')

    monkeypatch.setattr(ts.urllib.request, "urlopen", _fake_urlopen)
    fetcher = ts._make_http_fetcher("KEY", language="en-US")
    out = fetcher("movie", 99)
    assert out == {"id": 99}
    assert "https://api.themoviedb.org/3/movie/99" in captured["url"]
    assert "api_key=KEY" in captured["url"]
    assert "language=en-US" in captured["url"]


# ---------------------------------------------------------------------------
# Orchestration : run_snapshot
# ---------------------------------------------------------------------------
def test_run_snapshot_writes_v1_envelope(tmp_path):
    items_dir = tmp_path / "items"
    cache_dir = tmp_path / "cache"
    _write_item(items_dir, "src", "item-1", tmdb=42, tmdb_type="movie")

    def fetcher(kind, tmdb_id):
        return {"id": tmdb_id, "title": "Hello"}

    stats = ts.run_snapshot(
        source_id="src",
        items_dir=items_dir,
        cache_dir=cache_dir,
        fetcher=fetcher,
        apply=True,
        sleep=lambda _: None,
        now=_fake_now(),
    )
    assert stats.seen == 1
    assert stats.written == 1
    assert stats.skipped_fresh == 0

    written = json.loads((cache_dir / "42.json").read_text(encoding="utf-8"))
    assert written["_cacheVersion"] == 1
    assert written["kind"] == "movie"
    assert written["fetchedAt"] == "2026-06-10T12:00:00Z"
    assert written["payload"] == {"id": 42, "title": "Hello"}


def test_run_snapshot_dry_run_does_not_write(tmp_path):
    items_dir = tmp_path / "items"
    cache_dir = tmp_path / "cache"
    _write_item(items_dir, "src", "item-1", tmdb=42, tmdb_type="movie")

    stats = ts.run_snapshot(
        source_id="src",
        items_dir=items_dir,
        cache_dir=cache_dir,
        fetcher=lambda k, i: {"id": i},
        apply=False,
        sleep=lambda _: None,
        now=_fake_now(),
    )
    assert stats.seen == 1
    assert stats.written == 1
    assert not (cache_dir / "42.json").exists()


def test_run_snapshot_skips_items_without_tmdb(tmp_path):
    items_dir = tmp_path / "items"
    cache_dir = tmp_path / "cache"
    _write_item(items_dir, "src", "item-1")  # no tmdb
    _write_item(items_dir, "src", "item-2", tmdb=99)  # no kind

    calls = []

    def fetcher(kind, tmdb_id):  # pragma: no cover
        calls.append((kind, tmdb_id))
        return {}

    stats = ts.run_snapshot(
        source_id="src",
        items_dir=items_dir,
        cache_dir=cache_dir,
        fetcher=fetcher,
        apply=True,
        sleep=lambda _: None,
        now=_fake_now(),
    )
    assert stats.seen == 2
    assert stats.skipped_no_tmdb == 2
    assert stats.written == 0
    assert calls == []


def test_run_snapshot_skips_fresh_cache(tmp_path):
    items_dir = tmp_path / "items"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "42.json").write_text(
        json.dumps({
            "_cacheVersion": 1,
            "kind": "movie",
            "fetchedAt": "2026-06-01T00:00:00Z",
            "payload": {"id": 42},
        }),
        encoding="utf-8",
    )
    _write_item(items_dir, "src", "item-1", tmdb=42, tmdb_type="movie")

    calls = []

    def fetcher(kind, tmdb_id):  # pragma: no cover
        calls.append((kind, tmdb_id))
        return {}

    stats = ts.run_snapshot(
        source_id="src",
        items_dir=items_dir,
        cache_dir=cache_dir,
        fetcher=fetcher,
        apply=True,
        sleep=lambda _: None,
        now=_fake_now(),
    )
    assert stats.skipped_fresh == 1
    assert stats.written == 0
    assert calls == []


def test_run_snapshot_refresh_ignores_freshness(tmp_path):
    items_dir = tmp_path / "items"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "42.json").write_text(
        json.dumps({
            "_cacheVersion": 1,
            "kind": "movie",
            "fetchedAt": "2026-06-01T00:00:00Z",
            "payload": {"id": 42, "title": "Old"},
        }),
        encoding="utf-8",
    )
    _write_item(items_dir, "src", "item-1", tmdb=42, tmdb_type="movie")

    stats = ts.run_snapshot(
        source_id="src",
        items_dir=items_dir,
        cache_dir=cache_dir,
        fetcher=lambda k, i: {"id": i, "title": "New"},
        apply=True,
        refresh=True,
        sleep=lambda _: None,
        now=_fake_now(),
    )
    assert stats.skipped_fresh == 0
    assert stats.written == 1
    written = json.loads((cache_dir / "42.json").read_text(encoding="utf-8"))
    assert written["payload"]["title"] == "New"


def test_run_snapshot_counts_errors(tmp_path):
    items_dir = tmp_path / "items"
    cache_dir = tmp_path / "cache"
    _write_item(items_dir, "src", "item-1", tmdb=42, tmdb_type="movie")

    def fetcher(kind, tmdb_id):
        raise ts.urllib.error.URLError("boom")

    stats = ts.run_snapshot(
        source_id="src",
        items_dir=items_dir,
        cache_dir=cache_dir,
        fetcher=fetcher,
        apply=True,
        sleep=lambda _: None,
        now=_fake_now(),
    )
    assert stats.errors == 1
    assert stats.written == 0


def test_run_snapshot_rate_limits_between_calls(tmp_path):
    items_dir = tmp_path / "items"
    cache_dir = tmp_path / "cache"
    _write_item(items_dir, "src", "item-1", tmdb=42, tmdb_type="movie")
    _write_item(items_dir, "src", "item-2", tmdb=43, tmdb_type="tv")

    sleeps: list[float] = []

    stats = ts.run_snapshot(
        source_id="src",
        items_dir=items_dir,
        cache_dir=cache_dir,
        fetcher=lambda k, i: {"id": i},
        apply=True,
        rate_limit_seconds=10.0,  # large pour forcer un sleep
        sleep=sleeps.append,
        now=_fake_now(),
    )
    assert stats.written == 2
    # Au moins un sleep entre les 2 requêtes.
    assert len(sleeps) >= 1
    assert sleeps[0] > 0


def test_run_snapshot_no_items(tmp_path):
    items_dir = tmp_path / "items"
    cache_dir = tmp_path / "cache"
    stats = ts.run_snapshot(
        source_id="src",
        items_dir=items_dir,
        cache_dir=cache_dir,
        fetcher=lambda k, i: {},  # pragma: no cover
        apply=True,
        sleep=lambda _: None,
        now=_fake_now(),
    )
    assert stats == ts.SnapshotStats()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def test_main_returns_missing_key_when_env_absent(monkeypatch, tmp_path):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    rc = ts.main([
        "--source", "src",
        "--items-dir", str(tmp_path / "items"),
        "--tmdb-cache-dir", str(tmp_path / "cache"),
    ])
    assert rc == ts.EXIT_MISSING_KEY


def test_main_dry_run_with_env(monkeypatch, tmp_path):
    monkeypatch.setenv("TMDB_API_KEY", "FAKE")
    # Pas d'items → run sans erreur, exit 0.
    rc = ts.main([
        "--source", "src",
        "--items-dir", str(tmp_path / "items"),
        "--tmdb-cache-dir", str(tmp_path / "cache"),
    ])
    assert rc == ts.EXIT_OK


def test_main_apply_calls_fetcher(monkeypatch, tmp_path):
    monkeypatch.setenv("TMDB_API_KEY", "FAKE")
    items_dir = tmp_path / "items"
    cache_dir = tmp_path / "cache"
    _write_item(items_dir, "src", "item-1", tmdb=42, tmdb_type="movie")

    calls = []

    def _fake_fetcher_factory(api_key, *, language="fr-FR"):
        assert api_key == "FAKE"

        def _fetch(kind, tmdb_id):
            calls.append((kind, tmdb_id))
            return {"id": tmdb_id}

        return _fetch

    monkeypatch.setattr(ts, "_make_http_fetcher", _fake_fetcher_factory)
    rc = ts.main([
        "--source", "src",
        "--items-dir", str(items_dir),
        "--tmdb-cache-dir", str(cache_dir),
        "--apply",
    ])
    assert rc == ts.EXIT_OK
    assert calls == [("movie", 42)]
    assert (cache_dir / "42.json").exists()


def test_main_returns_error_on_lock_busy(monkeypatch, tmp_path):
    monkeypatch.setenv("TMDB_API_KEY", "FAKE")

    from contextlib import contextmanager

    @contextmanager
    def _busy(*, force):  # noqa: ARG001
        raise ts.ServerLockBusy("lock busy")
        yield  # pragma: no cover

    monkeypatch.setattr(ts, "acquire_pipeline_lock", _busy)
    rc = ts.main([
        "--source", "src",
        "--items-dir", str(tmp_path / "items"),
        "--tmdb-cache-dir", str(tmp_path / "cache"),
    ])
    assert rc == ts.EXIT_ERROR


def test_build_parser_accepts_dry_run_flag():
    args = ts.build_parser().parse_args(["--source", "x", "--dry-run"])
    assert args.dry_run is True
    assert args.apply is False


def test_build_parser_apply_and_dry_run_mutually_exclusive():
    with pytest.raises(SystemExit):
        ts.build_parser().parse_args(["--source", "x", "--apply", "--dry-run"])
