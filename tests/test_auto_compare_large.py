"""Tests de `tools/auto_compare_large.py` — orchestrateur de l'étude large-v3.

Le script polle des workers GPU (portable + Mac) en HTTP, rapatrie les
transcripts, échange le transcript de production et relance `extract_recos.py`
en sous-processus. TOUTES ces frontières sont mockées : aucun test ne fait de
requête réseau, ne lance de sous-processus, ni n'écrit hors de `tmp_path`.

Points d'attention couverts : idempotence du rapatriement, tolérance à un
worker injoignable, préservation d'un `transcriptStatus: validated`, et sortie
de la boucle de poll.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import auto_compare_large as acl


# ===== Doublures ===========================================================
class _FakeResponse:
    """Réponse HTTP minimale : `.text`, `.content`, `.raise_for_status()`."""

    def __init__(self, text: str = "", content: bytes = b"", status_ok: bool = True):
        self.text = text
        self.content = content
        self._ok = status_ok

    def raise_for_status(self) -> None:
        if not self._ok:
            raise RuntimeError("HTTP 500")


def _listing_html(*names: str) -> str:
    """Reproduit l'index Apache/`python -m http.server` que parse HREF_RE."""
    links = "".join(f'<li><a href="{n}">{n}</a></li>' for n in names)
    return f"<html><body><ul>{links}</ul></body></html>"


@pytest.fixture
def paths(tmp_path: Path, monkeypatch):
    """Redirige toutes les constantes de chemin du module vers `tmp_path`."""
    cmp_dir = tmp_path / "whisper-cmp"
    ns = SimpleNamespace(
        cmp=cmp_dir,
        baseline=cmp_dir / "baseline",
        large=cmp_dir / "large-v3",
        progress=cmp_dir / "auto_progress.json",
        guids=tmp_path / "dispatch" / "whisper_large_guids.txt",
        transcripts=tmp_path / "transcripts",
        recos=tmp_path / "recos",
        episodes=tmp_path / "episodes",
    )
    monkeypatch.setattr(acl, "CMP_DIR", ns.cmp)
    monkeypatch.setattr(acl, "BASELINE_DIR", ns.baseline)
    monkeypatch.setattr(acl, "LARGE_DIR", ns.large)
    monkeypatch.setattr(acl, "PROGRESS_FILE", ns.progress)
    monkeypatch.setattr(acl, "GUIDS_FILE", ns.guids)
    ns.transcripts.mkdir(parents=True)
    ns.recos.mkdir(parents=True)
    ns.episodes.mkdir(parents=True)
    monkeypatch.setattr(acl, "transcript_path_for",
                        lambda src, guid: ns.transcripts / f"{guid}.txt")
    monkeypatch.setattr(acl, "recos_dir_for", lambda src: ns.recos)
    return ns


def _write_reco(recos_dir: Path, name: str, **fields) -> None:
    (recos_dir / name).write_text(json.dumps(fields), encoding="utf-8")


# ===== _expected_guids / progression =======================================
def test_expected_guids_strips_blank_lines(paths):
    paths.guids.parent.mkdir(parents=True)
    paths.guids.write_text("g1\n\n  g2  \n\n", encoding="utf-8")

    assert acl._expected_guids() == ["g1", "g2"]


def test_load_progress_defaults_when_file_absent(paths):
    assert acl._load_progress() == {"done": [], "stats": {}}


def test_save_then_load_progress_roundtrip(paths):
    payload = {"done": ["g1"], "stats": {"g1": {"delta": {"total": 2}}}}
    acl._save_progress(payload)

    assert paths.progress.exists()
    assert acl._load_progress() == payload


# ===== _list_remote_transcripts ============================================
def test_listing_merges_sources_and_first_source_wins(paths, monkeypatch):
    """Un même transcript exposé par les deux workers : on garde le premier
    (le second passera, le rapatriement est idempotent)."""
    def fake_get(url, timeout=None):
        if url.startswith("http://etienne.home"):
            return _FakeResponse(text=_listing_html("a.txt", "b.txt"))
        return _FakeResponse(text=_listing_html("b.txt", "c.txt"))

    monkeypatch.setattr(acl, "requests", SimpleNamespace(get=fake_get))
    remote = acl._list_remote_transcripts()

    assert set(remote) == {"a.txt", "b.txt", "c.txt"}
    assert remote["b.txt"].startswith("http://etienne.home")
    assert remote["c.txt"].startswith("http://mac.home")


def test_listing_tolerates_unreachable_worker(paths, monkeypatch):
    """Un worker éteint ne doit pas empêcher d'exploiter l'autre."""
    def fake_get(url, timeout=None):
        if url.startswith("http://etienne.home"):
            raise ConnectionError("portable éteint")
        return _FakeResponse(text=_listing_html("c.txt"))

    monkeypatch.setattr(acl, "requests", SimpleNamespace(get=fake_get))
    assert set(acl._list_remote_transcripts()) == {"c.txt"}


def test_listing_skips_worker_returning_http_error(paths, monkeypatch):
    def fake_get(url, timeout=None):
        if url.startswith("http://etienne.home"):
            return _FakeResponse(text=_listing_html("a.txt"), status_ok=False)
        return _FakeResponse(text=_listing_html("c.txt"))

    monkeypatch.setattr(acl, "requests", SimpleNamespace(get=fake_get))
    assert set(acl._list_remote_transcripts()) == {"c.txt"}


def test_listing_ignores_non_txt_and_nested_hrefs(paths, monkeypatch):
    """HREF_RE n'accepte que des `*.txt` sans slash (pas de sous-dossiers)."""
    html = ('<a href="../">..</a><a href="sub/x.txt">x</a>'
            '<a href="notes.md">m</a><a href="ok.txt">ok</a>')

    monkeypatch.setattr(acl, "requests",
                        SimpleNamespace(get=lambda url, timeout=None:
                                        _FakeResponse(text=html)))
    assert set(acl._list_remote_transcripts()) == {"ok.txt"}


# ===== _download ===========================================================
def test_download_writes_file_from_worker(paths, monkeypatch):
    calls: list[str] = []

    def fake_get(url, timeout=None):
        calls.append(url)
        return _FakeResponse(content=b"transcript large-v3")

    monkeypatch.setattr(acl, "requests", SimpleNamespace(get=fake_get))
    remote = {"g1.txt": "http://worker/dir"}

    assert acl._download("g1", remote) is True
    assert (paths.large / "g1.txt").read_bytes() == b"transcript large-v3"
    assert calls == ["http://worker/dir/g1.txt"]


def test_download_is_idempotent_when_already_local(paths, monkeypatch):
    """Fichier déjà rapatrié : aucun appel réseau (l'autre worker « passe »)."""
    paths.large.mkdir(parents=True)
    (paths.large / "g1.txt").write_text("déjà là", encoding="utf-8")

    def boom(*_a, **_k):
        raise AssertionError("aucune requête ne doit partir")

    monkeypatch.setattr(acl, "requests", SimpleNamespace(get=boom))
    assert acl._download("g1", {}) is True


def test_download_returns_false_when_no_worker_has_it(paths, monkeypatch):
    monkeypatch.setattr(acl, "requests", SimpleNamespace(get=lambda *a, **k: None))
    assert acl._download("g1", {"autre.txt": "http://worker/dir"}) is False


def test_download_returns_false_on_network_error(paths, monkeypatch):
    def fake_get(url, timeout=None):
        raise TimeoutError("worker injoignable")

    monkeypatch.setattr(acl, "requests", SimpleNamespace(get=fake_get))

    assert acl._download("g1", {"g1.txt": "http://worker/dir"}) is False
    assert not (paths.large / "g1.txt").exists()


# ===== _backup_baseline ====================================================
def test_backup_copies_current_transcript_once(paths):
    src = paths.transcripts / "g1.txt"
    src.write_text("baseline small", encoding="utf-8")

    acl._backup_baseline("g1")
    dest = paths.baseline / "g1.txt"
    assert dest.read_text(encoding="utf-8") == "baseline small"

    # 2e passage : le backup existant N'EST PAS écrasé (sinon on perdrait la
    # vraie baseline après un swap).
    src.write_text("large-v3 (déjà swappé)", encoding="utf-8")
    acl._backup_baseline("g1")
    assert dest.read_text(encoding="utf-8") == "baseline small"


def test_backup_noop_when_no_transcript_yet(paths):
    acl._backup_baseline("inconnu")
    assert not paths.baseline.exists()


# ===== _count_recos ========================================================
def test_count_recos_counts_only_the_episode(paths):
    _write_reco(paths.recos, "1.json", episodeGuid="g1",
                extractors=["anthropic"], status="validated")
    _write_reco(paths.recos, "2.json", episodeGuid="g1",
                extractors=["anthropic", "openai"], status="discarded")
    _write_reco(paths.recos, "3.json", episodeGuid="g1", extractors=["openai"])
    _write_reco(paths.recos, "4.json", episodeGuid="autre",
                extractors=["anthropic"], status="validated")

    assert acl._count_recos("g1") == {
        "total": 3, "anthropic": 2, "openai": 2, "both": 1,
        "validated": 1, "discarded": 1,
    }


def test_count_recos_handles_missing_extractors_field(paths):
    _write_reco(paths.recos, "1.json", episodeGuid="g1", extractors=None)

    assert acl._count_recos("g1") == {
        "total": 1, "anthropic": 0, "openai": 0, "both": 0,
        "validated": 0, "discarded": 0,
    }


# ===== _run_extract ========================================================
def test_run_extract_builds_the_expected_command(paths, monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(acl.subprocess, "run", fake_run)

    assert acl._run_extract("anthropic", "g1") == 0
    assert seen["cmd"][1].endswith("extract_recos.py")
    assert seen["cmd"][2:] == ["--source", "un-bon-moment",
                               "--provider", "anthropic", "--guid", "g1"]


def test_run_extract_returns_nonzero_and_logs_truncated_stderr(
    paths, monkeypatch, caplog,
):
    """Un extract en échec renvoie son code et journalise la FIN du stderr,
    tronquée à 500 caractères (une stacktrace complète noierait la sortie de
    l'orchestrateur, qui traite des dizaines d'épisodes)."""
    stderr = "".join(f"ligne {i}\n" for i in range(400))
    monkeypatch.setattr(
        acl.subprocess, "run",
        lambda cmd, **kw: SimpleNamespace(returncode=2, stderr=stderr),
    )

    with caplog.at_level("WARNING", logger="reco"):
        assert acl._run_extract("openai", "g1") == 2

    logged = caplog.text
    assert stderr[-500:] in logged
    assert stderr[:100] not in logged  # le début est bien coupé
    assert "exit=2" in logged


# ===== _process ============================================================
@pytest.fixture
def process_env(paths, monkeypatch):
    """Prépare un `_process` mockable : episode JSON + extract neutralisé."""
    ep_path = paths.episodes / "g1.json"
    ep_path.write_text(json.dumps({"guid": "g1"}), encoding="utf-8")
    monkeypatch.setattr(acl, "find_episode_by_guid", lambda src, guid: ep_path)
    monkeypatch.setattr(acl, "read_json",
                        lambda p: json.loads(Path(p).read_text(encoding="utf-8")))
    monkeypatch.setattr(
        acl, "write_json_if_changed",
        lambda p, d: Path(p).write_text(json.dumps(d), encoding="utf-8"),
    )
    monkeypatch.setattr(acl, "_run_extract", lambda prov, guid: 0)
    return SimpleNamespace(ep_path=ep_path, paths=paths)


def test_process_swaps_transcript_and_stamps_episode(process_env, monkeypatch):
    paths = process_env.paths
    paths.large.mkdir(parents=True)
    (paths.large / "g1.txt").write_text("texte large-v3", encoding="utf-8")
    (paths.transcripts / "g1.txt").write_text("texte small", encoding="utf-8")

    # Une reco apparaît après extraction : delta = +1.
    counts = iter([
        {"total": 0, "anthropic": 0, "openai": 0, "both": 0,
         "validated": 0, "discarded": 0},
        {"total": 1, "anthropic": 1, "openai": 0, "both": 0,
         "validated": 0, "discarded": 0},
    ])
    monkeypatch.setattr(acl, "_count_recos", lambda guid: next(counts))

    stats = acl._process("g1", {"g1.txt": "http://worker/dir"})

    assert stats["delta"]["total"] == 1
    assert stats["delta"]["anthropic"] == 1
    # Le transcript de production a bien été remplacé, la baseline sauvegardée.
    assert (paths.transcripts / "g1.txt").read_text(encoding="utf-8") == "texte large-v3"
    assert (paths.baseline / "g1.txt").read_text(encoding="utf-8") == "texte small"
    ep = json.loads(process_env.ep_path.read_text(encoding="utf-8"))
    assert ep["transcriptModel"] == "large-v3"
    assert ep["transcriptSource"] == "youtube"
    assert ep["transcriptStatus"] == "auto"


def test_process_preserves_validated_transcript_status(process_env, monkeypatch):
    """Un transcript relu à la main reste `validated` — le swap ne le rétrograde
    pas en `auto`."""
    paths = process_env.paths
    paths.large.mkdir(parents=True)
    (paths.large / "g1.txt").write_text("texte large-v3", encoding="utf-8")
    process_env.ep_path.write_text(
        json.dumps({"guid": "g1", "transcriptStatus": "validated"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(acl, "_count_recos", lambda guid: dict.fromkeys(
        ("total", "anthropic", "openai", "both", "validated", "discarded"), 0))

    acl._process("g1", {"g1.txt": "http://worker/dir"})

    ep = json.loads(process_env.ep_path.read_text(encoding="utf-8"))
    assert ep["transcriptStatus"] == "validated"
    assert ep["transcriptModel"] == "large-v3"


def test_process_returns_none_when_download_fails(process_env, monkeypatch):
    monkeypatch.setattr(acl, "_download", lambda guid, remote: False)
    assert acl._process("g1", {}) is None


def test_process_continues_when_episode_json_missing(process_env, monkeypatch):
    """Transcript rapatrié mais aucun épisode JSON : on log et on poursuit
    l'extraction (le transcript est déjà en place)."""
    paths = process_env.paths
    paths.large.mkdir(parents=True)
    (paths.large / "g1.txt").write_text("texte large-v3", encoding="utf-8")

    def _missing(src, guid):
        raise FileNotFoundError(f"pas d'épisode pour {guid}")

    monkeypatch.setattr(acl, "find_episode_by_guid", _missing)
    monkeypatch.setattr(acl, "_count_recos", lambda guid: dict.fromkeys(
        ("total", "anthropic", "openai", "both", "validated", "discarded"), 0))

    stats = acl._process("g1", {"g1.txt": "http://worker/dir"})

    assert stats is not None
    assert (paths.transcripts / "g1.txt").read_text(encoding="utf-8") == "texte large-v3"


def test_process_logs_failed_extraction_but_still_returns_stats(
    process_env, monkeypatch,
):
    """Les deux extractions échouent : l'épisode est quand même compté comme
    traité (stats à zéro) — sinon la boucle de poll le rejouerait sans fin."""
    paths = process_env.paths
    paths.large.mkdir(parents=True)
    (paths.large / "g1.txt").write_text("texte", encoding="utf-8")
    attempts: list[str] = []
    monkeypatch.setattr(acl, "_run_extract",
                        lambda prov, guid: attempts.append(prov) or 1)
    zeros = dict.fromkeys(
        ("total", "anthropic", "openai", "both", "validated", "discarded"), 0)
    monkeypatch.setattr(acl, "_count_recos", lambda guid: dict(zeros))

    stats = acl._process("g1", {"g1.txt": "http://worker/dir"})

    # Les deux providers sont tentés, malgré l'échec du premier.
    assert attempts == ["anthropic", "openai"]
    assert stats == {"before": zeros, "after": zeros, "delta": zeros}


# ===== main ================================================================
def test_main_processes_ready_guids_then_stops(paths, monkeypatch):
    paths.guids.parent.mkdir(parents=True)
    paths.guids.write_text("g1\ng2\n", encoding="utf-8")
    monkeypatch.setattr(acl, "_list_remote_transcripts",
                        lambda: {"g1.txt": "u", "g2.txt": "u"})
    monkeypatch.setattr(acl, "_process",
                        lambda guid, remote: {"delta": {"total": 1}})
    monkeypatch.setattr(acl.time, "sleep",
                        lambda s: pytest.fail("aucun poll ne devait être nécessaire"))

    acl.main()

    progress = json.loads(paths.progress.read_text(encoding="utf-8"))
    assert progress["done"] == ["g1", "g2"]
    assert progress["stats"]["g2"] == {"delta": {"total": 1}}


def test_main_skips_already_done_guids(paths, monkeypatch):
    paths.guids.parent.mkdir(parents=True)
    paths.guids.write_text("g1\ng2\n", encoding="utf-8")
    paths.progress.parent.mkdir(parents=True, exist_ok=True)
    paths.progress.write_text(
        json.dumps({"done": ["g1"], "stats": {}}), encoding="utf-8")
    monkeypatch.setattr(acl, "_list_remote_transcripts",
                        lambda: {"g1.txt": "u", "g2.txt": "u"})
    processed: list[str] = []

    def fake_process(guid, remote):
        processed.append(guid)
        return {"ok": True}

    monkeypatch.setattr(acl, "_process", fake_process)
    acl.main()

    assert processed == ["g2"]


def test_main_polls_again_after_a_failed_download(paths, monkeypatch):
    """Un guid qui échoue au 1er tour n'est pas marqué `done` : la boucle
    dort puis re-tente au tour suivant."""
    paths.guids.parent.mkdir(parents=True)
    paths.guids.write_text("g1\n", encoding="utf-8")
    monkeypatch.setattr(acl, "_list_remote_transcripts", lambda: {"g1.txt": "u"})
    monkeypatch.setattr(acl, "POLL_SECONDS", 0)
    slept: list[int] = []
    monkeypatch.setattr(acl.time, "sleep", lambda s: slept.append(s))
    outcomes = iter([None, {"delta": {"total": 3}}])
    monkeypatch.setattr(acl, "_process", lambda guid, remote: next(outcomes))

    acl.main()

    assert slept == [0]
    progress = json.loads(paths.progress.read_text(encoding="utf-8"))
    assert progress["done"] == ["g1"]
    assert progress["stats"]["g1"] == {"delta": {"total": 3}}


def test_main_stops_immediately_when_nothing_expected(paths, monkeypatch):
    paths.guids.parent.mkdir(parents=True)
    paths.guids.write_text("", encoding="utf-8")
    monkeypatch.setattr(acl, "_list_remote_transcripts", dict)
    monkeypatch.setattr(acl.time, "sleep",
                        lambda s: pytest.fail("ne doit pas dormir"))

    acl.main()  # ne lève pas, sort au premier tour
