"""Tests poll_rss CLI : run_poll avec fetcher + sender injectés.

Pas d'appel HTTP réel, pas d'I/O Discord. La source `un-bon-moment`
est lue depuis le repo (SOURCES_DIR existante) — c'est la seule
dépendance fichier (lecture seule).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import poll_rss
from poll_rss import PollOptions, run_poll
from rss.ports import FetchResult
from rss.state import load_state

RSS_FIXTURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Un Bon Moment</title>
    <link>https://exemple.fr</link>
    <item>
      <title>Ep B</title><guid>guid-B</guid><link>https://x/B</link>
      <pubDate>Wed, 11 Jun 2026 12:00:00 +0000</pubDate>
    </item>
    <item>
      <title>Ep A</title><guid>guid-A</guid><link>https://x/A</link>
      <pubDate>Wed, 04 Jun 2026 12:00:00 +0000</pubDate>
    </item>
  </channel>
</rss>
"""


class _FakeFetcher:
    def __init__(self, body=RSS_FIXTURE, *, not_modified=False, raise_exc=None):
        self.body = body
        self.not_modified = not_modified
        self.raise_exc = raise_exc
        self.calls = []

    def fetch(self, url, *, etag=None, last_modified=None):
        self.calls.append({"url": url, "etag": etag, "last_modified": last_modified})
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.not_modified:
            return FetchResult(body=b"", not_modified=True)
        return FetchResult(
            body=self.body, etag="W/\"abc\"", last_modified="Wed, 11 Jun 2026 12:00:00 GMT",
        )


class _RecordingSender:
    name = "discord"

    def __init__(self, *, ok=True):
        self.ok = ok
        self.sent = []

    def send(self, payload):
        self.sent.append(payload)
        return self.ok


class _RecordingDispatcher:
    def __init__(self, *, ok=True):
        self.ok = ok
        self.payloads = []

    def dispatch(self, payload):
        self.payloads.append(payload)
        return self.ok


def _options(tmp_path: Path, **overrides) -> PollOptions:
    base = dict(
        sources=("un-bon-moment",),
        state_dir=tmp_path / "rss",
        dry_run=False,
        force_notify=False,
        limit_new=5,
        notify_channel="discord",
    )
    base.update(overrides)
    return PollOptions(**base)


# --- run_poll core flow ----------------------------------------------------


def test_first_run_detects_all_episodes_and_notifies(tmp_path):
    fetcher = _FakeFetcher()
    sender = _RecordingSender()
    results = run_poll(
        _options(tmp_path),
        fetcher=fetcher,
        sender=sender,
        use_lock=False,
    )
    assert len(results) == 1
    r = results[0]
    assert r.feed_episode_count == 2
    assert len(r.new_episodes) == 2
    assert r.notified == 2
    assert len(sender.sent) == 2


def test_idempotent_second_run_emits_no_notification(tmp_path):
    fetcher = _FakeFetcher()
    sender = _RecordingSender()
    options = _options(tmp_path)
    run_poll(options, fetcher=fetcher, sender=sender, use_lock=False)
    sender.sent.clear()
    results2 = run_poll(options, fetcher=fetcher, sender=sender, use_lock=False)
    assert results2[0].new_episodes == ()
    assert sender.sent == []


def test_state_persisted_with_etag_after_run(tmp_path):
    fetcher = _FakeFetcher()
    sender = _RecordingSender()
    run_poll(_options(tmp_path), fetcher=fetcher, sender=sender, use_lock=False)
    state = load_state("un-bon-moment", state_dir=tmp_path / "rss")
    assert state.last_etag == "W/\"abc\""
    assert state.last_modified == "Wed, 11 Jun 2026 12:00:00 GMT"
    assert "guid-A" in state.seen_guids
    assert "guid-B" in state.seen_guids
    assert state.metadata["feedTitle"] == "Un Bon Moment"


def test_subsequent_run_sends_conditional_headers(tmp_path):
    fetcher = _FakeFetcher()
    sender = _RecordingSender()
    options = _options(tmp_path)
    run_poll(options, fetcher=fetcher, sender=sender, use_lock=False)
    fetcher.calls.clear()
    run_poll(options, fetcher=fetcher, sender=sender, use_lock=False)
    assert fetcher.calls[0]["etag"] == "W/\"abc\""


def test_dry_run_does_not_write_state_or_notify(tmp_path):
    fetcher = _FakeFetcher()
    sender = _RecordingSender()
    options = _options(tmp_path, dry_run=True)
    results = run_poll(options, fetcher=fetcher, sender=sender, use_lock=False)
    assert results[0].notified == 0
    assert sender.sent == []
    # Pas de fichier d'état créé.
    assert not (tmp_path / "rss" / "un-bon-moment" / "state.json").exists()


def test_force_notify_sends_latest_when_no_new(tmp_path):
    fetcher = _FakeFetcher()
    sender = _RecordingSender()
    options = _options(tmp_path)
    run_poll(options, fetcher=fetcher, sender=sender, use_lock=False)
    sender.sent.clear()
    options_force = _options(tmp_path, force_notify=True)
    results = run_poll(options_force, fetcher=fetcher, sender=sender, use_lock=False)
    assert results[0].notified == 1
    assert len(sender.sent) == 1


def test_limit_new_caps_first_run(tmp_path):
    fetcher = _FakeFetcher()
    sender = _RecordingSender()
    options = _options(tmp_path, limit_new=1)
    results = run_poll(options, fetcher=fetcher, sender=sender, use_lock=False)
    assert len(results[0].new_episodes) == 1
    assert results[0].notified == 1


def test_not_modified_skips_parse_and_updates_checked_at(tmp_path):
    fetcher = _FakeFetcher(not_modified=True)
    sender = _RecordingSender()
    options = _options(tmp_path)
    results = run_poll(options, fetcher=fetcher, sender=sender, use_lock=False)
    assert results[0].not_modified is True
    assert results[0].notified == 0
    # L'état est tout de même persisté pour mettre à jour `lastCheckedAt`.
    state = load_state("un-bon-moment", state_dir=tmp_path / "rss")
    assert state.last_checked_at != ""


def test_dispatch_event_called_when_new_episodes(tmp_path):
    fetcher = _FakeFetcher()
    sender = _RecordingSender()
    dispatcher = _RecordingDispatcher()
    options = _options(tmp_path)
    results = run_poll(
        options,
        fetcher=fetcher,
        sender=sender,
        dispatcher=dispatcher,
        use_lock=False,
    )
    assert results[0].dispatched is True
    assert dispatcher.payloads[0]["source_id"] == "un-bon-moment"
    assert dispatcher.payloads[0]["episode_count"] == 2


def test_fetcher_exception_logged_but_does_not_crash(tmp_path):
    fetcher = _FakeFetcher(raise_exc=ConnectionError("dns"))
    sender = _RecordingSender()
    results = run_poll(
        _options(tmp_path),
        fetcher=fetcher,
        sender=sender,
        use_lock=False,
    )
    assert results[0].feed_episode_count == 0
    assert results[0].notified == 0


def test_unknown_source_logged_and_skipped(tmp_path, caplog):
    fetcher = _FakeFetcher()
    sender = _RecordingSender()
    options = _options(tmp_path, sources=("does-not-exist",))
    results = run_poll(options, fetcher=fetcher, sender=sender, use_lock=False)
    assert results == []


# --- CLI ------------------------------------------------------------------


def test_resolve_sources_all_lists_repo_sources(monkeypatch):
    ids = poll_rss._resolve_sources("all")
    assert "un-bon-moment" in ids


def test_resolve_sources_single():
    assert poll_rss._resolve_sources("foo") == ["foo"]


def test_validate_args_rejects_negative_limit():
    args = poll_rss.build_arg_parser().parse_args(
        ["--source", "un-bon-moment", "--limit-new", "-1"],
    )
    assert poll_rss._validate_args(args) is not None


def test_validate_args_accepts_zero_limit():
    args = poll_rss.build_arg_parser().parse_args(
        ["--source", "un-bon-moment", "--limit-new", "0"],
    )
    assert poll_rss._validate_args(args) is None


def test_main_dry_run_exits_zero(tmp_path, monkeypatch, capsys):
    # Stubbe le fetcher injecté via monkeypatch sur run_poll.
    monkeypatch.setattr(
        poll_rss, "RequestsFeedFetcher", lambda **kw: _FakeFetcher(),
    )
    rc = poll_rss.main(
        [
            "--source", "un-bon-moment",
            "--state-dir", str(tmp_path),
            "--dry-run",
            "--notify", "none",
            "--json",
        ],
    )
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data[0]["sourceId"] == "un-bon-moment"
    assert data[0]["newEpisodes"]  # parsing OK


def test_main_returns_bad_args_on_unknown_source(tmp_path, monkeypatch):
    # Force `_resolve_sources("does-not-exist")` à renvoyer [].
    monkeypatch.setattr(poll_rss, "_resolve_sources", lambda s: [] if s != "all" else ["x"])
    rc = poll_rss.main(["--source", "does-not-exist", "--notify", "none"])
    assert rc == poll_rss.EXIT_BAD_ARGS


def test_main_returns_bad_args_on_negative_limit():
    rc = poll_rss.main(["--source", "un-bon-moment", "--limit-new", "-5"])
    assert rc == poll_rss.EXIT_BAD_ARGS


def test_main_handles_invalid_notify_sender_config(monkeypatch, tmp_path):
    # Sans RECO_DISCORD_WEBHOOK, DiscordWebhookSender lèvera ValueError.
    monkeypatch.delenv("RECO_DISCORD_WEBHOOK", raising=False)
    rc = poll_rss.main(
        [
            "--source", "un-bon-moment",
            "--state-dir", str(tmp_path),
            "--notify", "discord",
        ],
    )
    assert rc == poll_rss.EXIT_BAD_ARGS


# --- _build_sender --------------------------------------------------------


def test_build_sender_none():
    assert poll_rss._build_sender("none") is None


def test_build_sender_discord(monkeypatch):
    monkeypatch.setenv("RECO_DISCORD_WEBHOOK", "https://discord.com/api/webhooks/1/x")
    s = poll_rss._build_sender("discord")
    assert s.name == "discord"


def test_build_sender_slack(monkeypatch):
    monkeypatch.setenv("RECO_SLACK_WEBHOOK", "https://hooks.slack.com/services/x")
    s = poll_rss._build_sender("slack")
    assert s.name == "slack"


def test_build_sender_email_requires_host(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with pytest.raises(ValueError):
        poll_rss._build_sender("email")


def test_build_sender_email_with_host(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "a@b")
    monkeypatch.setenv("SMTP_TO", "c@d")
    s = poll_rss._build_sender("email")
    assert s.name == "email"


def test_build_sender_unknown_raises():
    with pytest.raises(ValueError):
        poll_rss._build_sender("carrier-pigeon")


# --- _build_dispatcher ----------------------------------------------------


def test_build_dispatcher_missing_token_returns_none(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert poll_rss._build_dispatcher() is None


def test_build_dispatcher_ok(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_x")
    monkeypatch.setenv("GITHUB_REPOSITORY", "etienneboursault/Reco")
    d = poll_rss._build_dispatcher()
    assert d is not None


# --- GitHubDispatcher -----------------------------------------------------


def test_dispatcher_rejects_empty_token():
    with pytest.raises(ValueError):
        poll_rss.GitHubDispatcher(token="", repository="o/r")


def test_dispatcher_rejects_bad_repository():
    with pytest.raises(ValueError):
        poll_rss.GitHubDispatcher(token="t", repository="oops")


class _DispSess:
    def __init__(self, ok=True, exc=None):
        self.ok = ok
        self.exc = exc
        self.calls = []

    def post(self, url, headers, json, timeout):  # noqa: A002
        self.calls.append({"url": url, "json": json})
        if self.exc:
            raise self.exc

        class _R:
            pass

        r = _R()
        r.ok = self.ok
        r.status_code = 204 if self.ok else 500
        return r


def test_dispatcher_dispatch_success():
    sess = _DispSess(ok=True)
    d = poll_rss.GitHubDispatcher(token="t", repository="o/r", session=sess)
    assert d.dispatch({"source_id": "x"}) is True
    assert sess.calls[0]["json"]["event_type"] == "reco-new-episode"
    assert sess.calls[0]["json"]["client_payload"] == {"source_id": "x"}


def test_dispatcher_dispatch_failure_status():
    sess = _DispSess(ok=False)
    d = poll_rss.GitHubDispatcher(token="t", repository="o/r", session=sess)
    assert d.dispatch({}) is False


def test_dispatcher_dispatch_network_error():
    sess = _DispSess(exc=ConnectionError("boom"))
    d = poll_rss.GitHubDispatcher(token="t", repository="o/r", session=sess)
    assert d.dispatch({}) is False


# --- RequestsFeedFetcher --------------------------------------------------


class _ReqSess:
    def __init__(self, status_code=200, content=b"", headers=None, exc=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.exc = exc
        self.calls = []

    def get(self, url, headers, timeout):
        self.calls.append({"url": url, "headers": dict(headers), "timeout": timeout})
        if self.exc:
            raise self.exc

        class _Resp:
            pass

        r = _Resp()
        r.status_code = self.status_code
        r.content = self.content
        r.headers = self.headers

        def _raise():
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        r.raise_for_status = _raise
        return r


def test_requests_fetcher_returns_body_and_etag():
    sess = _ReqSess(
        content=RSS_FIXTURE,
        headers={"ETag": "W/\"abc\"", "Last-Modified": "now"},
    )
    f = poll_rss.RequestsFeedFetcher(session=sess)
    result = f.fetch("https://feed", etag=None, last_modified=None)
    assert result.body == RSS_FIXTURE
    assert result.etag == "W/\"abc\""
    assert result.last_modified == "now"
    assert result.not_modified is False


def test_requests_fetcher_sends_conditional_headers():
    sess = _ReqSess(content=RSS_FIXTURE, headers={})
    f = poll_rss.RequestsFeedFetcher(session=sess)
    f.fetch("https://feed", etag="e1", last_modified="lm1")
    sent = sess.calls[0]["headers"]
    assert sent["If-None-Match"] == "e1"
    assert sent["If-Modified-Since"] == "lm1"
    assert sent["User-Agent"].startswith("reco-poll-rss")


def test_requests_fetcher_handles_304():
    sess = _ReqSess(status_code=304)
    f = poll_rss.RequestsFeedFetcher(session=sess)
    result = f.fetch("https://feed", etag="e1")
    assert result.not_modified is True
    assert result.body == b""


# --- _notify_one routing --------------------------------------------------


def test_notify_one_routes_slack():
    sender = _RecordingSender()
    sender.name = "slack"
    from rss.parser import ParsedEpisode, ParsedFeed

    feed = ParsedFeed(
        title="F", feed_url="",
        episodes=(
            ParsedEpisode(guid="g", title="T", link="https://x", published=""),
        ),
    )
    ok = poll_rss._notify_one(sender, feed, feed.episodes[0], "src")
    assert ok is True
    assert "blocks" in sender.sent[0]


def test_notify_one_routes_email():
    sender = _RecordingSender()
    sender.name = "email"
    from rss.parser import ParsedEpisode, ParsedFeed

    feed = ParsedFeed(
        title="F", feed_url="",
        episodes=(
            ParsedEpisode(guid="g", title="T", link="https://x", published=""),
        ),
    )
    ok = poll_rss._notify_one(sender, feed, feed.episodes[0], "src")
    assert ok is True
    assert "subject" in sender.sent[0]
    assert "body" in sender.sent[0]


def test_notify_one_unknown_channel_returns_false():
    sender = _RecordingSender()
    sender.name = "carrier-pigeon"
    from rss.parser import ParsedEpisode, ParsedFeed

    feed = ParsedFeed(
        title="F", feed_url="",
        episodes=(ParsedEpisode(guid="g", title="T", link="", published=""),),
    )
    ok = poll_rss._notify_one(sender, feed, feed.episodes[0], "src")
    assert ok is False


def test_notify_one_routes_matrix():
    sender = _RecordingSender()
    sender.name = "matrix"
    from rss.parser import ParsedEpisode, ParsedFeed

    feed = ParsedFeed(
        title="F", feed_url="",
        episodes=(
            ParsedEpisode(guid="g", title="T", link="https://x", published=""),
        ),
    )
    ok = poll_rss._notify_one(sender, feed, feed.episodes[0], "src")
    assert ok is True
    # Le format Matrix porte son corps en HTML (formatted_body).
    assert "formatted_body" in sender.sent[0]


# --- _resolve_sources ------------------------------------------------------


def test_resolve_sources_all_returns_empty_when_dir_missing(monkeypatch, tmp_path):
    """`--source all` sur une installation neuve (pas encore de config) :
    liste vide plutôt qu'une exception — `main` la traduit en EXIT_BAD_ARGS."""
    import common

    monkeypatch.setattr(common, "SOURCES_DIR", tmp_path / "jamais-cree")
    assert poll_rss._resolve_sources("all") == []


# --- _poll_one_source : gardes ---------------------------------------------


def test_source_without_rss_url_is_skipped(tmp_path, monkeypatch):
    """Une source déclarée sans `rssUrl` est sautée sans toucher au réseau."""
    monkeypatch.setattr(poll_rss, "load_source", lambda sid: {"title": "X"})
    fetcher = _FakeFetcher()

    results = run_poll(
        _options(tmp_path), fetcher=fetcher, sender=_RecordingSender(),
        use_lock=False,
    )

    assert results[0].feed_episode_count == 0
    assert results[0].new_episodes == ()
    assert fetcher.calls == []  # aucun fetch tenté


def test_not_modified_in_dry_run_leaves_state_untouched(tmp_path):
    """304 + `--dry-run` : on ne rafraîchit même pas `lastCheckedAt`."""
    fetcher = _FakeFetcher(not_modified=True)
    options = _options(tmp_path, dry_run=True)

    results = run_poll(options, fetcher=fetcher, sender=None, use_lock=False)

    assert results[0].not_modified is True
    assert not (tmp_path / "rss").exists()


def test_failed_notification_is_not_counted(tmp_path):
    """Un envoi qui échoue ne doit pas gonfler le compteur `notified` — sinon
    le log annoncerait des notifications jamais parties."""
    sender = _RecordingSender(ok=False)

    results = run_poll(
        _options(tmp_path), fetcher=_FakeFetcher(), sender=sender,
        use_lock=False,
    )

    assert len(results[0].new_episodes) == 2
    assert len(sender.sent) == 2  # les deux tentatives ont bien eu lieu
    assert results[0].notified == 0


def test_run_poll_takes_the_pipeline_lock(tmp_path, monkeypatch):
    """`use_lock=True` hors dry-run : le poll tourne SOUS le verrou pipeline
    (il écrit l'état RSS pendant qu'un extract pourrait tourner)."""
    import contextlib

    events = []

    @contextlib.contextmanager
    def _lock():
        events.append("lock")
        yield
        events.append("unlock")

    monkeypatch.setattr(poll_rss, "acquire_pipeline_lock", _lock)
    fetcher = _FakeFetcher()

    run_poll(_options(tmp_path), fetcher=fetcher, sender=None, use_lock=True)

    assert events == ["lock", "unlock"]
    assert len(fetcher.calls) == 1


def test_run_poll_skips_the_lock_in_dry_run(tmp_path, monkeypatch):
    def _boom():
        raise AssertionError("aucun verrou ne doit être pris en dry-run")

    monkeypatch.setattr(poll_rss, "acquire_pipeline_lock", _boom)

    run_poll(
        _options(tmp_path, dry_run=True), fetcher=_FakeFetcher(),
        sender=None, use_lock=True,
    )


# --- _build_sender matrix --------------------------------------------------


def test_build_sender_matrix(monkeypatch):
    monkeypatch.setenv("RECO_MATRIX_HOMESERVER", "https://matrix.exemple.fr")
    monkeypatch.setenv("RECO_MATRIX_TOKEN", "tok")
    monkeypatch.setenv("RECO_MATRIX_ROOM", "!salon:exemple.fr")

    sender = poll_rss._build_sender("matrix")

    assert sender is not None
    assert sender.name == "matrix"


@pytest.mark.parametrize("missing", [
    "RECO_MATRIX_HOMESERVER", "RECO_MATRIX_TOKEN", "RECO_MATRIX_ROOM",
])
def test_build_sender_matrix_incomplete_config_is_graceful(monkeypatch, missing):
    """Matrix pas encore configuré : on désactive la notification au lieu de
    lever — contrairement à email, le cron ne doit pas échouer pour ça."""
    for var in ("RECO_MATRIX_HOMESERVER", "RECO_MATRIX_TOKEN",
                "RECO_MATRIX_ROOM"):
        monkeypatch.setenv(var, "valeur")
    monkeypatch.setenv(missing, "")

    assert poll_rss._build_sender("matrix") is None


# --- GitHubDispatcher sans session injectée --------------------------------


def test_dispatcher_uses_requests_when_no_session(monkeypatch):
    """Sans session injectée, le dispatcher importe `requests` à la volée.
    On remplace le module dans `sys.modules` : aucune requête ne part."""
    import sys
    from types import SimpleNamespace

    captured = {}

    def _post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return SimpleNamespace(ok=True, status_code=204, text="")

    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(post=_post))
    disp = poll_rss.GitHubDispatcher(token="tok", repository="o/r")

    assert disp.dispatch({"source_id": "s"}) is True
    assert captured["url"].endswith("/repos/o/r/dispatches")
    assert captured["json"]["client_payload"] == {"source_id": "s"}


# --- main : sortie non-JSON et erreur inattendue ---------------------------


def test_main_without_json_flag_prints_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(poll_rss, "run_poll", lambda *a, **k: [])
    code = poll_rss.main([
        "--source", "un-bon-moment", "--dry-run",
        "--state-dir", str(tmp_path / "rss"),
    ])

    assert code == poll_rss.EXIT_OK
    assert capsys.readouterr().out == ""


def test_main_returns_error_when_poll_raises(tmp_path, monkeypatch):
    """Une erreur inattendue du poll est convertie en code de sortie, pas en
    traceback : le cron GitHub Actions doit rester lisible."""
    def _boom(*a, **k):
        raise RuntimeError("base d'état corrompue")

    monkeypatch.setattr(poll_rss, "run_poll", _boom)

    code = poll_rss.main([
        "--source", "un-bon-moment", "--state-dir", str(tmp_path / "rss"),
    ])

    assert code == poll_rss.EXIT_ERROR
