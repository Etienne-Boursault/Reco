"""Tests end-to-end de `tools/refresh_enrichment.py`.

Aucun appel réseau : providers fakes injectés via `provider_factory`.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import common
import refresh_enrichment as ren
from enrichment.tracker import now_iso


NOW = datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc)


def _write_reco(dir_: Path, reco_id: str, **overrides) -> Path:
    base = {
        "id": reco_id,
        "sourceId": "demo-src",
        "episodeGuid": "g1",
        "title": f"Title {reco_id}",
        "types": ["film"],
        "links": [],
    }
    base.update(overrides)
    p = dir_ / f"{reco_id}.json"
    p.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirige RECOS_DIR + OUTPUT_DIR vers un tmp_path frais."""
    recos_dir = tmp_path / "recos"
    src_dir = recos_dir / "demo-src"
    src_dir.mkdir(parents=True)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    monkeypatch.setattr(common, "RECOS_DIR", recos_dir)
    monkeypatch.setattr(ren, "RECOS_DIR", recos_dir)
    monkeypatch.setattr(ren, "OUTPUT_DIR", output_dir)
    # `recos_dir_for` lit `RECOS_DIR` au module import → patch direct.
    monkeypatch.setattr(common, "recos_dir_for", lambda sid: recos_dir / sid)
    monkeypatch.setattr(ren, "recos_dir_for", lambda sid: recos_dir / sid)
    # Lock review_server : bypass.
    monkeypatch.setattr(ren, "acquire_pipeline_lock",
                        lambda force=False: _NullLock())
    return src_dir, output_dir


class _NullLock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


# --- parse_duration via CLI args -------------------------------------------
def test_invalid_duration_returns_exit_2(sandbox):
    rc = ren.main([
        "--source", "demo-src",
        "--refresh-older-than", "garbage",
        "--dry-run",
    ])
    assert rc == 2


def test_apply_without_api_key_returns_2(sandbox, monkeypatch):
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    # Empêche load_dotenv de remettre la clé.
    monkeypatch.setattr(ren, "load_dotenv", lambda *a, **kw: None)
    rc = ren.main([
        "--source", "demo-src", "--apply", "--provider", "tmdb",
    ])
    assert rc == 2


# --- plan_refresh : pure logic ---------------------------------------------
def test_plan_refresh_skips_non_film_for_tmdb():
    reco = {"types": ["livre"]}
    provider, fields = ren.plan_refresh(
        reco, older_than=timedelta(days=90), now=NOW,
        provider_filter="tmdb", field_filter=None,
    )
    assert provider is None and fields == []


def test_plan_refresh_returns_all_fields_when_no_enrichedat():
    reco = {"types": ["film"], "title": "Parasite"}
    provider, fields = ren.plan_refresh(
        reco, older_than=timedelta(days=90), now=NOW,
        provider_filter="tmdb", field_filter=None,
    )
    assert provider is not None and provider.name == "tmdb"
    assert set(fields) == set(ren.TMDB_FIELDS)


def test_plan_refresh_skips_fresh_fields():
    reco = {
        "types": ["film"],
        "enrichedAt": {f: now_iso() for f in ren.TMDB_FIELDS},
    }
    # Avec older_than=90d et timestamps "now", rien n'est stale.
    provider, fields = ren.plan_refresh(
        reco, older_than=timedelta(days=90), now=NOW,
        provider_filter="tmdb", field_filter=None,
    )
    assert provider is None and fields == []


def test_plan_refresh_field_filter():
    reco = {"types": ["film"]}
    provider, fields = ren.plan_refresh(
        reco, older_than=timedelta(days=90), now=NOW,
        provider_filter="tmdb", field_filter="watchProviders",
    )
    assert fields == ["watchProviders"]


def test_plan_refresh_field_filter_no_match():
    reco = {"types": ["film"]}
    provider, fields = ren.plan_refresh(
        reco, older_than=timedelta(days=90), now=NOW,
        provider_filter="tmdb", field_filter="bogus",
    )
    assert provider is None and fields == []


def test_plan_refresh_music_provider():
    reco = {"types": ["musique"]}
    provider, fields = ren.plan_refresh(
        reco, older_than=timedelta(days=90), now=NOW,
        provider_filter="musicbrainz", field_filter=None,
    )
    assert provider is not None and provider.name == "music"
    assert set(fields) == set(ren.MUSIC_FIELDS)


# --- run() end-to-end via fake provider ------------------------------------
class FakeTmdbProvider(ren.Provider):
    name = "tmdb"
    fields = ren.TMDB_FIELDS
    applies_to = ren.TmdbProvider.applies_to
    last_call: dict | None = None

    def refresh(self, reco, fields, session):
        FakeTmdbProvider.last_call = {"id": reco["id"], "fields": list(fields)}
        # Simule un refresh complet : pose tous les champs + timestamps
        ts = now_iso()
        from enrichment.field_refresher import partial_update, update_nested
        update_nested(reco, "externalIds.tmdb", "999", timestamp=ts)
        update_nested(reco, "externalIds.justwatch",
                      "https://justwatch.fr/x", timestamp=ts)
        partial_update(reco, "watchProviders",
                       [{"label": "Netflix",
                         "url": "https://netflix.com/x",
                         "ethics": "neutral"}],
                       timestamp=ts)
        return len(fields), "ok"


def test_run_dry_run_does_not_write(sandbox):
    src_dir, output_dir = sandbox
    p = _write_reco(src_dir, "0001")

    stats = ren.run(
        source_arg="demo-src",
        older_than=timedelta(days=90),
        provider_filter="tmdb",
        field_filter=None,
        apply=False,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb=None,
    )
    assert stats.items_scanned == 1
    assert stats.items_refreshed == 1
    assert stats.fields_refreshed == len(ren.TMDB_FIELDS)
    # Fichier inchangé en dry-run
    data = json.loads(p.read_text(encoding="utf-8"))
    assert "enrichedAt" not in data


def test_run_apply_writes_and_traces_enrichedat(sandbox):
    src_dir, output_dir = sandbox
    p = _write_reco(src_dir, "0001")

    stats = ren.run(
        source_arg="demo-src",
        older_than=timedelta(days=90),
        provider_filter="tmdb",
        field_filter=None,
        apply=True,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb="fake",
        provider_factory=lambda name: FakeTmdbProvider() if name == "tmdb" else None,
    )
    assert stats.items_refreshed == 1
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["externalIds"]["tmdb"] == "999"
    assert "watchProviders" in data
    assert set(data["enrichedAt"].keys()) >= set(ren.TMDB_FIELDS)


def test_run_skips_when_all_fresh(sandbox):
    src_dir, output_dir = sandbox
    fresh = {f: now_iso() for f in ren.TMDB_FIELDS}
    _write_reco(src_dir, "0001", enrichedAt=fresh)
    stats = ren.run(
        source_arg="demo-src",
        older_than=timedelta(days=90),
        provider_filter="tmdb",
        field_filter=None,
        apply=False,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb=None,
    )
    assert stats.items_scanned == 1
    assert stats.items_refreshed == 0


def test_run_respects_limit(sandbox):
    src_dir, output_dir = sandbox
    for i in range(5):
        _write_reco(src_dir, f"000{i}")
    stats = ren.run(
        source_arg="demo-src",
        older_than=timedelta(days=90),
        provider_filter="tmdb",
        field_filter=None,
        apply=False,
        limit=2,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb=None,
    )
    assert stats.items_scanned == 2


def test_run_all_sources(sandbox):
    src_dir, output_dir = sandbox
    # crée une 2e source
    (src_dir.parent / "other-src").mkdir()
    _write_reco(src_dir, "0001")
    _write_reco(src_dir.parent / "other-src", "0002", sourceId="other-src")
    stats = ren.run(
        source_arg="all",
        older_than=timedelta(days=90),
        provider_filter="tmdb",
        field_filter=None,
        apply=False,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb=None,
    )
    assert stats.items_scanned == 2


def test_run_unknown_source_warns(sandbox, caplog):
    src_dir, output_dir = sandbox
    stats = ren.run(
        source_arg="ghost",
        older_than=timedelta(days=90),
        provider_filter="tmdb",
        field_filter=None,
        apply=False,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb=None,
    )
    assert stats.items_scanned == 0


def test_run_handles_provider_exception(sandbox):
    src_dir, output_dir = sandbox
    _write_reco(src_dir, "0001")

    class BoomProvider(ren.Provider):
        name = "tmdb"
        fields = ren.TMDB_FIELDS
        applies_to = ren.TmdbProvider.applies_to

        def refresh(self, reco, fields, session):
            raise RuntimeError("network down")

    stats = ren.run(
        source_arg="demo-src",
        older_than=timedelta(days=90),
        provider_filter="tmdb",
        field_filter=None,
        apply=True,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb="fake",
        provider_factory=lambda name: BoomProvider(),
    )
    assert stats.errors == 1


def test_run_not_found_increments_counter(sandbox):
    src_dir, output_dir = sandbox
    _write_reco(src_dir, "0001")

    class NotFoundProvider(ren.Provider):
        name = "tmdb"
        fields = ren.TMDB_FIELDS
        applies_to = ren.TmdbProvider.applies_to

        def refresh(self, reco, fields, session):
            return 0, "not_found"

    stats = ren.run(
        source_arg="demo-src",
        older_than=timedelta(days=90),
        provider_filter="tmdb",
        field_filter=None,
        apply=True,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb="fake",
        provider_factory=lambda name: NotFoundProvider(),
    )
    assert stats.not_found == 1
    assert stats.items_refreshed == 0


def test_main_cli_dry_run(sandbox, monkeypatch):
    src_dir, output_dir = sandbox
    _write_reco(src_dir, "0001")
    # Patch OUTPUT_DIR cache path
    rc = ren.main([
        "--source", "demo-src", "--dry-run",
        "--refresh-older-than", "0d", "--limit", "5",
    ])
    assert rc == 0


def test_main_with_field_filter(sandbox):
    src_dir, output_dir = sandbox
    _write_reco(src_dir, "0001")
    rc = ren.main([
        "--source", "demo-src", "--dry-run",
        "--field", "watchProviders", "--refresh-older-than", "0d",
    ])
    assert rc == 0


def test_main_lock_busy_returns_1(sandbox, monkeypatch):
    from review_lock import ServerLockBusy

    def _raise(force=False):
        raise ServerLockBusy("server actif")

    monkeypatch.setattr(ren, "acquire_pipeline_lock", _raise)
    rc = ren.main(["--source", "demo-src", "--dry-run"])
    assert rc == 1


def test_stats_summary():
    s = ren.RefreshStats()
    s.items_scanned = 10
    s.items_refreshed = 3
    s.fields_refreshed = 7
    s.by_provider["tmdb"] = 3
    out = s.summary()
    assert "scanned=10" in out
    assert "refreshed=3" in out
    assert "tmdb=3" in out


def test_iter_source_ids_returns_singleton(sandbox):
    src_dir, _ = sandbox
    assert ren._iter_source_ids("demo-src") == ["demo-src"]


def test_iter_source_ids_all(sandbox):
    src_dir, _ = sandbox
    (src_dir.parent / "zzz").mkdir()
    (src_dir.parent / "aaa").mkdir()
    ids = ren._iter_source_ids("all")
    assert ids == sorted(ids)
    assert "demo-src" in ids and "zzz" in ids and "aaa" in ids


# --- TmdbProvider.refresh : intégration avec un faux enrich_tmdb -----------
def test_tmdb_provider_refreshes_via_enrich_one(monkeypatch):
    """Le TmdbProvider doit déléguer à enrich_tmdb.enrich_one et tracer."""
    captured = {}

    def fake_enrich_one(reco, *, session, api_key, force):
        captured["called"] = True
        reco["externalIds"] = {"tmdb": "12345", "tmdbType": "movie",
                               "justwatch": "https://justwatch.fr/p"}
        reco["watchProviders"] = [
            {"label": "Mubi", "url": "https://mubi.com/x", "ethics": "indie"},
        ]
        reco["_enrich_status"] = "ok"
        return reco

    import enrich_tmdb as et
    monkeypatch.setattr(et, "enrich_one", fake_enrich_one)

    from enrichment.http_cache import CachedSession

    class FakeSess:
        from_cache = False

        def close(self):
            pass

    cs = CachedSession(session=FakeSess())  # type: ignore[arg-type]
    p = ren.TmdbProvider(api_key="k")
    reco = {"id": "x", "title": "Parasite", "types": ["film"]}
    n, status = p.refresh(reco, list(ren.TMDB_FIELDS), cs)
    assert status == "ok"
    assert n == len(ren.TMDB_FIELDS)
    assert reco["externalIds"]["tmdb"] == "12345"
    assert "watchProviders" in reco
    assert "enrichedAt" in reco
    for f in ren.TMDB_FIELDS:
        assert f in reco["enrichedAt"]


def test_tmdb_provider_traces_unchanged_justwatch(monkeypatch):
    """Si justwatch est inchangé, on trace l'audit `enrichedAt` quand même."""
    def fake_enrich_one(reco, *, session, api_key, force):
        # Met les mêmes valeurs : justwatch identique au before.
        reco.setdefault("externalIds", {})
        reco["externalIds"]["tmdb"] = "1"
        reco["externalIds"]["justwatch"] = "https://jw/p"
        reco["watchProviders"] = []
        reco["_enrich_status"] = "ok"
        return reco

    import enrich_tmdb as et
    monkeypatch.setattr(et, "enrich_one", fake_enrich_one)

    from enrichment.http_cache import CachedSession

    class FakeSess:
        def close(self):
            pass

    cs = CachedSession(session=FakeSess())  # type: ignore[arg-type]
    p = ren.TmdbProvider()
    reco = {
        "id": "x", "title": "Same", "types": ["film"],
        "externalIds": {"tmdb": "1", "justwatch": "https://jw/p"},
    }
    n, status = p.refresh(reco, ["externalIds.justwatch", "watchProviders"], cs)
    assert status == "ok"
    assert reco["enrichedAt"]["externalIds.justwatch"].endswith("Z")


def test_music_provider_applies_and_refreshes(monkeypatch):
    def fake_music_enrich(reco, *, session, spotify_token):
        reco.setdefault("externalIds", {})
        reco["externalIds"]["deezer"] = "https://deezer.com/track/1"
        return reco

    import enrich_music as em
    monkeypatch.setattr(em, "enrich_one", fake_music_enrich)

    from enrichment.http_cache import CachedSession

    class FakeSess:
        def close(self):
            pass

    cs = CachedSession(session=FakeSess())  # type: ignore[arg-type]
    p = ren.MusicProvider()
    reco = {"id": "x", "title": "Track", "types": ["musique"]}
    assert p.applies_to(reco)
    n, status = p.refresh(reco, list(ren.MUSIC_FIELDS), cs)
    assert status == "ok"
    assert reco["externalIds"]["deezer"].startswith("https://deezer")
    assert "externalIds.deezer" in reco["enrichedAt"]


def test_music_provider_does_not_apply_to_film():
    assert ren.MusicProvider().applies_to({"types": ["film"]}) is False


def test_music_provider_traces_when_no_hit(monkeypatch):
    """Aucun lien trouvé → trace l'audit (vérifié) sans poser de valeur.

    C4 : on doit fournir un token Spotify ; sans token, le champ spotify
    est skip (pas de faux audit). On teste donc deezer ici (existant identique).
    """
    def fake_music_enrich(reco, *, session, spotify_token):
        # Pas de résultat — externalIds non touché.
        return reco

    import enrich_music as em
    monkeypatch.setattr(em, "enrich_one", fake_music_enrich)

    from enrichment.http_cache import CachedSession

    class FakeSess:
        def close(self):
            pass

    cs = CachedSession(session=FakeSess())  # type: ignore[arg-type]
    p = ren.MusicProvider(spotify_token="fake-bearer-token")
    reco = {
        "id": "x", "title": "Track", "types": ["musique"],
        "externalIds": {"deezer": "https://prev"},  # existant
    }
    # On limite au champ spotify (absent → new_v=None, trace seulement)
    n, status = p.refresh(reco, ["externalIds.spotify"], cs)
    assert status == "ok"
    assert "externalIds.spotify" in reco["enrichedAt"]


def test_music_provider_skips_spotify_audit_without_token(monkeypatch):
    """C4 : sans token Spotify, NE PAS tracer enrichedAt[spotify]
    (sinon faux audit "vérifié alors qu'on a skip")."""
    def fake_music_enrich(reco, *, session, spotify_token):
        return reco

    import enrich_music as em
    monkeypatch.setattr(em, "enrich_one", fake_music_enrich)

    from enrichment.http_cache import CachedSession

    class FakeSess:
        def close(self):
            pass

    cs = CachedSession(session=FakeSess())  # type: ignore[arg-type]
    p = ren.MusicProvider(spotify_token=None)  # pas de token
    reco = {"id": "x", "title": "Track", "types": ["musique"]}
    n, status = p.refresh(reco, ["externalIds.spotify"], cs)
    assert status == "ok"
    # Pas de trace audit Spotify car pas vérifié réellement.
    assert "externalIds.spotify" not in (reco.get("enrichedAt") or {})


def test_main_lock_release_swallows_error(sandbox, monkeypatch):
    """Le lock.__exit__ qui crash ne doit pas faire planter le CLI."""
    class FaultyLock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            raise RuntimeError("release failed")

    monkeypatch.setattr(ren, "acquire_pipeline_lock", lambda force=False: FaultyLock())
    src_dir, _ = sandbox
    _write_reco(src_dir, "0001")
    rc = ren.main(["--source", "demo-src", "--dry-run", "--refresh-older-than", "0d"])
    assert rc == 0


def test_tmdb_provider_returns_not_found(monkeypatch):
    def fake_enrich_one(reco, *, session, api_key, force):
        reco["_enrich_status"] = "not_found"
        return reco

    import enrich_tmdb as et
    monkeypatch.setattr(et, "enrich_one", fake_enrich_one)

    from enrichment.http_cache import CachedSession

    class FakeSess:
        def close(self):
            pass

    cs = CachedSession(session=FakeSess())  # type: ignore[arg-type]
    p = ren.TmdbProvider()
    reco = {"id": "x", "title": "Ghost", "types": ["film"]}
    n, status = p.refresh(reco, list(ren.TMDB_FIELDS), cs)
    assert status == "not_found"
    assert n == 0


# ============================================================================
# Pass A — régressions CRITICAL bugs production (C3/C4/C5/C6/P0-5)
# ============================================================================


def test_C3_tmdb_provider_propagates_api_key_via_run(sandbox, monkeypatch):
    """C3 : `run()` doit instancier TmdbProvider AVEC `api_key_tmdb`. Vérifie
    que la valeur arrive bien à `enrich_one` (avant : api_key=None silencieux)."""
    src_dir, output_dir = sandbox
    _write_reco(src_dir, "0001")
    captured = {}

    def fake_enrich_one(reco, *, session, api_key, force):
        captured["api_key"] = api_key
        reco["externalIds"] = {"tmdb": "42", "tmdbType": "movie"}
        reco["_enrich_status"] = "ok"
        return reco

    import enrich_tmdb as et
    monkeypatch.setattr(et, "enrich_one", fake_enrich_one)

    stats = ren.run(
        source_arg="demo-src",
        older_than=timedelta(days=90),
        provider_filter="tmdb",
        field_filter=None,
        apply=True,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb="REAL-KEY-XYZ",
    )
    assert stats.items_refreshed == 1
    assert captured["api_key"] == "REAL-KEY-XYZ"


def test_C4_music_provider_propagates_spotify_token_via_run(sandbox, monkeypatch):
    """C4 : `run()` doit dériver et passer le token Spotify au MusicProvider."""
    src_dir, output_dir = sandbox
    _write_reco(src_dir, "0001", types=["musique"])
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "secret")

    captured = {}

    def fake_spotify_token(session, client_id, client_secret):
        captured["client_id"] = client_id
        return "BEARER-XYZ"

    def fake_music_enrich(reco, *, session, spotify_token):
        captured["spotify_token"] = spotify_token
        reco["externalIds"] = {"spotify": "https://open.spotify.com/x",
                               "deezer": "https://deezer.com/x"}
        return reco

    import enrich_music as em
    monkeypatch.setattr(em, "spotify_token", fake_spotify_token)
    monkeypatch.setattr(em, "enrich_one", fake_music_enrich)

    stats = ren.run(
        source_arg="demo-src",
        older_than=timedelta(days=90),
        provider_filter="music",
        field_filter=None,
        apply=True,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb=None,
    )
    assert stats.items_refreshed == 1
    assert captured["client_id"] == "id"
    assert captured["spotify_token"] == "BEARER-XYZ"


def test_C4_no_spotify_audit_when_no_creds(sandbox, monkeypatch):
    """C4 : sans SPOTIFY_CLIENT_ID/SECRET, on NE trace PAS enrichedAt[spotify]."""
    src_dir, output_dir = sandbox
    p = _write_reco(src_dir, "0001", types=["musique"])
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    monkeypatch.setattr(ren, "load_dotenv", lambda *a, **kw: None)

    def fake_music_enrich(reco, *, session, spotify_token):
        # Sans token, on simule juste Deezer.
        reco.setdefault("externalIds", {})["deezer"] = "https://deezer.com/x"
        return reco

    import enrich_music as em
    monkeypatch.setattr(em, "enrich_one", fake_music_enrich)

    stats = ren.run(
        source_arg="demo-src",
        older_than=timedelta(days=90),
        provider_filter="music",
        field_filter=None,
        apply=True,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb=None,
    )
    data = json.loads(p.read_text(encoding="utf-8"))
    ea = data.get("enrichedAt") or {}
    # Pas de trace Spotify (skip honnête au lieu de faux audit).
    assert "externalIds.spotify" not in ea
    # Mais Deezer doit être tracé.
    assert "externalIds.deezer" in ea


def test_C5_unified_audit_semantics_tmdb(monkeypatch):
    """C5 : tous les champs TMDB doivent suivre la même politique d'audit :
    si l'appel a réussi, on trace enrichedAt[f] pour CHAQUE field demandé,
    qu'il ait changé ou pas. (Avant : `or "tmdb" in ext` toujours True.)"""
    def fake_enrich_one(reco, *, session, api_key, force):
        reco.setdefault("externalIds", {})
        reco["externalIds"]["tmdb"] = "1"
        reco["externalIds"]["justwatch"] = "https://jw/p"
        reco["watchProviders"] = []
        reco["_enrich_status"] = "ok"
        return reco

    import enrich_tmdb as et
    monkeypatch.setattr(et, "enrich_one", fake_enrich_one)

    from enrichment.http_cache import CachedSession

    class FakeSess:
        def close(self):
            pass

    cs = CachedSession(session=FakeSess())  # type: ignore[arg-type]
    p = ren.TmdbProvider(api_key="k")
    # Reco déjà enrichie avec valeurs identiques → audit doit tracer quand même.
    reco = {
        "id": "x", "title": "Same", "types": ["film"],
        "externalIds": {"tmdb": "1", "justwatch": "https://jw/p"},
        "watchProviders": [],
        "enrichedAt": {
            "externalIds.tmdb": "2020-01-01T00:00:00Z",
            "externalIds.justwatch": "2020-01-01T00:00:00Z",
            "watchProviders": "2020-01-01T00:00:00Z",
        },
    }
    n, status = p.refresh(reco, list(ren.TMDB_FIELDS), cs)
    assert status == "ok"
    # Les 3 champs doivent avoir une trace d'audit récente (sauf tmdb idempotent
    # si valeur ET timestamp inchangés, justwatch/watchProviders toujours tracés).
    assert reco["enrichedAt"]["externalIds.justwatch"] != "2020-01-01T00:00:00Z"
    assert reco["enrichedAt"]["watchProviders"] != "2020-01-01T00:00:00Z"


def test_C6_not_found_separate_counters_tmdb(sandbox, monkeypatch):
    """C6 : compteur `not_found_tmdb` séparé de `not_found_music`."""
    src_dir, output_dir = sandbox
    _write_reco(src_dir, "0001", types=["film"])

    class NotFoundTmdb(ren.Provider):
        name = "tmdb"
        fields = tuple(ren.TMDB_FIELDS)
        applies_to = ren.TmdbProvider.applies_to

        def refresh(self, reco, fields, session):
            return 0, "not_found"

    stats = ren.run(
        source_arg="demo-src",
        older_than=timedelta(days=90),
        provider_filter="tmdb",
        field_filter=None,
        apply=True,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb="fake",
        provider_factory=lambda name: NotFoundTmdb() if name == "tmdb" else None,
    )
    assert stats.not_found == 1
    assert stats.not_found_tmdb == 1
    assert stats.not_found_music == 0


def test_C6_not_found_separate_counters_music(sandbox, monkeypatch):
    """C6 : not_found_music distinct."""
    src_dir, output_dir = sandbox
    _write_reco(src_dir, "0001", types=["musique"])

    class NotFoundMusic(ren.Provider):
        name = "music"
        fields = tuple(ren.MUSIC_FIELDS)
        applies_to = ren.MusicProvider.applies_to

        def refresh(self, reco, fields, session):
            return 0, "not_found"

    stats = ren.run(
        source_arg="demo-src",
        older_than=timedelta(days=90),
        provider_filter="music",
        field_filter=None,
        apply=True,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb=None,
        provider_factory=lambda name: NotFoundMusic() if name == "music" else None,
    )
    assert stats.not_found_music == 1
    assert stats.not_found_tmdb == 0


def test_C6_music_provider_returns_not_found_status(monkeypatch):
    """C6 : MusicProvider expose `_enrich_status = not_found` correctement
    (aligné sur convention enrich_one)."""
    def fake_music_enrich(reco, *, session, spotify_token):
        reco["_enrich_status"] = "not_found"
        return reco

    import enrich_music as em
    monkeypatch.setattr(em, "enrich_one", fake_music_enrich)

    from enrichment.http_cache import CachedSession

    class FakeSess:
        def close(self):
            pass

    cs = CachedSession(session=FakeSess())  # type: ignore[arg-type]
    p = ren.MusicProvider()
    reco = {"id": "x", "title": "Ghost", "types": ["musique"]}
    n, status = p.refresh(reco, list(ren.MUSIC_FIELDS), cs)
    assert status == "not_found"
    assert n == 0


def test_P0_5_enrichedat_corrupted_raises():
    """P0-5 : `enrichedAt` non-dict → EnrichedAtCorruptedError, jamais écrasé."""
    item = {"id": "x", "enrichedAt": "broken-string-not-dict"}
    with pytest.raises(ren.EnrichedAtCorruptedError):
        ren._ensure_enrichedat_dict(item, item_id="x")
    # L'item n'a pas été modifié.
    assert item["enrichedAt"] == "broken-string-not-dict"


def test_P0_5_enrichedat_absent_or_dict_ok():
    """P0-5 : absent OU dict → passe sans exception."""
    ren._ensure_enrichedat_dict({"id": "x"})  # absent
    ren._ensure_enrichedat_dict({"id": "x", "enrichedAt": {}})  # vide
    ren._ensure_enrichedat_dict({"id": "x", "enrichedAt": {"k": "v"}})


def test_P0_5_corrupted_item_skipped_during_run(sandbox):
    """P0-5 : un item avec enrichedAt corrompu est skipped et compté."""
    src_dir, output_dir = sandbox
    _write_reco(src_dir, "0001", enrichedAt="oups-string")
    _write_reco(src_dir, "0002")  # sain

    stats = ren.run(
        source_arg="demo-src",
        older_than=timedelta(days=90),
        provider_filter="tmdb",
        field_filter=None,
        apply=False,
        limit=None,
        cache_path=output_dir / "http.sqlite",
        api_key_tmdb=None,
    )
    assert stats.items_scanned == 2
    assert stats.corrupted_skipped == 1
    # L'item sain est planifié pour refresh.
    assert stats.items_refreshed == 1


def test_M7_apply_with_errors_returns_1(sandbox, monkeypatch):
    """M7 : exit code 1 si stats.errors > 0 en mode --apply."""
    src_dir, output_dir = sandbox
    _write_reco(src_dir, "0001")

    def boom_enrich_one(reco, *, session, api_key, force):
        raise RuntimeError("boom")

    monkeypatch.setenv("TMDB_API_KEY", "fake")
    monkeypatch.setattr(ren, "load_dotenv", lambda *a, **kw: None)
    import enrich_tmdb as et
    monkeypatch.setattr(et, "enrich_one", boom_enrich_one)

    rc = ren.main([
        "--source", "demo-src", "--apply",
        "--provider", "tmdb", "--refresh-older-than", "0d",
    ])
    assert rc == 1


def test_L5_provider_alias_music_works(sandbox, monkeypatch):
    """L5 : `--provider music` (nouveau nom canonique) doit fonctionner."""
    src_dir, _ = sandbox
    _write_reco(src_dir, "0001", types=["musique"])
    rc = ren.main([
        "--source", "demo-src", "--dry-run",
        "--provider", "music", "--refresh-older-than", "0d",
    ])
    assert rc == 0


def test_L1_provider_fields_is_tuple():
    """L1 : Provider.fields est un tuple immutable au niveau classe."""
    assert isinstance(ren.TmdbProvider.fields, tuple)
    assert isinstance(ren.MusicProvider.fields, tuple)
    assert isinstance(ren.Provider.fields, tuple)
