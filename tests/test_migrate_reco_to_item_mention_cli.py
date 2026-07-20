"""Tests CLI `tools/migrate_reco_to_item_mention.py`.

Test direct via import + `main(argv=[...])`. Pas de subprocess (plus
rapide et plus déterministe pour la couverture).
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

import migrate_reco_to_item_mention as cli
import review_lock


SOURCE = "un-bon-moment"


@pytest.fixture
def _redirect_content_paths(tmp_path, monkeypatch):
    """Redirige les chemins src/content/{recos,items,mentions} vers tmp_path."""
    recos_root = tmp_path / "recos"
    items_root = tmp_path / "items"
    mentions_root = tmp_path / "mentions"
    monkeypatch.setattr(cli, "RECOS_BASE_DIR", recos_root)
    monkeypatch.setattr(cli, "ITEMS_BASE_DIR", items_root)
    monkeypatch.setattr(cli, "MENTIONS_BASE_DIR", mentions_root)
    return recos_root, items_root, mentions_root


def _seed_one_reco(recos_root: Path) -> None:
    d = recos_root / SOURCE
    d.mkdir(parents=True)
    (d / "0001.json").write_text(json.dumps({
        "id": "ubm-cli-1", "sourceId": SOURCE,
        "title": "CLI Movie", "types": ["film"],
    }), encoding="utf-8")


def _run(*argv: str) -> tuple[int, str, str]:
    buf_out, buf_err = io.StringIO(), io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        code = cli.main(list(argv))
    return code, buf_out.getvalue(), buf_err.getvalue()


# ---------------------------------------------------------------------------
# Dry-run par défaut
# ---------------------------------------------------------------------------


def test_cli_dry_run_default_no_writes(_redirect_content_paths):
    recos_root, items_root, _mentions_root = _redirect_content_paths
    _seed_one_reco(recos_root)

    code, out, _err = _run("--source", SOURCE)
    assert code == 0
    payload = json.loads(out)
    assert payload["n_recos_read"] == 1
    assert payload["n_items_created"] == 1
    # Rien écrit côté items.
    assert not items_root.exists() or list(items_root.glob("**/*.json")) == []


def test_cli_explicit_dry_run_same_behaviour(_redirect_content_paths):
    recos_root, items_root, _m = _redirect_content_paths
    _seed_one_reco(recos_root)

    code, out, _err = _run("--source", SOURCE, "--dry-run")
    assert code == 0
    assert json.loads(out)["n_recos_read"] == 1
    assert not items_root.exists() or list(items_root.glob("**/*.json")) == []


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def test_cli_apply_writes(_redirect_content_paths):
    recos_root, items_root, mentions_root = _redirect_content_paths
    _seed_one_reco(recos_root)

    code, out, _err = _run("--source", SOURCE, "--apply")
    assert code == 0
    payload = json.loads(out)
    assert payload["n_items_created"] == 1
    # Présence sur disque.
    items_written = list((items_root / SOURCE).glob("*.json"))
    mentions_written = list((mentions_root / SOURCE).glob("*.json"))
    assert len(items_written) == 1
    assert len(mentions_written) == 1


def test_cli_apply_requires_explicit_flag(_redirect_content_paths):
    """Sans `--apply`, rien n'est écrit même si un script appelle migrate."""
    recos_root, items_root, _m = _redirect_content_paths
    _seed_one_reco(recos_root)
    code, _out, _err = _run("--source", SOURCE)  # défaut = dry-run
    assert code == 0
    assert not items_root.exists() or list(items_root.glob("**/*.json")) == []


def test_cli_dry_run_and_apply_mutually_exclusive(_redirect_content_paths):
    with pytest.raises(SystemExit):
        _run("--source", SOURCE, "--dry-run", "--apply")


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def test_cli_verify_returns_zero_after_apply(_redirect_content_paths):
    recos_root, _i, _m = _redirect_content_paths
    _seed_one_reco(recos_root)
    _run("--source", SOURCE, "--apply")
    code, out, _err = _run("--source", SOURCE, "--verify")
    assert code == 0
    payload = json.loads(out)
    assert payload["n_errors"] == 0


def test_cli_verify_returns_nonzero_if_mismatch(_redirect_content_paths):
    recos_root, _i, _m = _redirect_content_paths
    _seed_one_reco(recos_root)
    # On ne migre PAS → mention manquante → verify échoue.
    code, out, _err = _run("--source", SOURCE, "--verify")
    assert code == 2
    payload = json.loads(out)
    assert payload["n_errors"] >= 1


# ---------------------------------------------------------------------------
# Migrate avec erreurs → code retour 1
# ---------------------------------------------------------------------------


def test_cli_migrate_returns_nonzero_if_errors(_redirect_content_paths):
    recos_root, _i, _m = _redirect_content_paths
    d = recos_root / SOURCE
    d.mkdir(parents=True)
    (d / "bad.json").write_text("{not json", encoding="utf-8")
    code, _out, _err = _run("--source", SOURCE)
    assert code == 1


# ---------------------------------------------------------------------------
# Lock pipeline
# ---------------------------------------------------------------------------


def test_cli_acquires_pipeline_lock(_redirect_content_paths, monkeypatch):
    """Vérifie que le CLI appelle bien `acquire_pipeline_lock`."""
    recos_root, _i, _m = _redirect_content_paths
    _seed_one_reco(recos_root)

    calls = {"n": 0, "force": None}
    real_acq = review_lock.acquire_pipeline_lock

    def _spy(*, force=False):
        calls["n"] += 1
        calls["force"] = force
        return real_acq(force=force)

    monkeypatch.setattr(cli.review_lock, "acquire_pipeline_lock", _spy)
    code, _out, _err = _run("--source", SOURCE)
    assert code == 0
    assert calls["n"] == 1
    assert calls["force"] is False


def test_cli_ignore_server_lock_passes_force(_redirect_content_paths, monkeypatch):
    recos_root, _i, _m = _redirect_content_paths
    _seed_one_reco(recos_root)

    captured = {"force": None}
    real_acq = review_lock.acquire_pipeline_lock

    def _spy(*, force=False):
        captured["force"] = force
        return real_acq(force=force)

    monkeypatch.setattr(cli.review_lock, "acquire_pipeline_lock", _spy)
    code, _out, _err = _run("--source", SOURCE, "--ignore-server-lock")
    assert code == 0
    assert captured["force"] is True


def test_cli_handles_lock_busy(_redirect_content_paths, monkeypatch):
    """Si `acquire_pipeline_lock` lève `LockBusy`, le CLI renvoie 3."""
    from contextlib import contextmanager

    @contextmanager
    def _busy(*, force=False):
        raise review_lock.ServerLockBusy("simulé : server tourne")
        yield  # pragma: no cover

    monkeypatch.setattr(cli.review_lock, "acquire_pipeline_lock", _busy)
    code, _out, err = _run("--source", SOURCE)
    assert code == 3
    assert "verrou" in err.lower()


# ---------------------------------------------------------------------------
# Source manquante
# ---------------------------------------------------------------------------


def test_cli_missing_source_argument():
    with pytest.raises(SystemExit):
        _run()  # pas de --source


# ---------------------------------------------------------------------------
# B12 — args --items-dir / --mentions-dir / --recos-dir
# ---------------------------------------------------------------------------


def test_cli_args_override_paths_without_monkeypatch(tmp_path):
    """Les chemins peuvent être passés en args (plus propre que monkeypatch)."""
    recos_root = tmp_path / "r"
    items_root = tmp_path / "i"
    mentions_root = tmp_path / "m"
    d = recos_root / SOURCE
    d.mkdir(parents=True)
    (d / "0001.json").write_text(json.dumps({
        "id": "ubm-args-1", "sourceId": SOURCE,
        "title": "Args Movie", "types": ["film"],
    }), encoding="utf-8")

    code, out, _err = _run(
        "--source", SOURCE,
        "--recos-dir", str(recos_root),
        "--items-dir", str(items_root),
        "--mentions-dir", str(mentions_root),
        "--apply",
    )
    assert code == 0
    payload = json.loads(out)
    assert payload["n_items_created"] == 1
    # Écritures sur les chemins choisis.
    assert (items_root / SOURCE).exists()
    assert (mentions_root / SOURCE).exists()


# ---------------------------------------------------------------------------
# C8 — Modes mutuellement exclusifs
# ---------------------------------------------------------------------------


def test_cli_apply_and_verify_mutually_exclusive(_redirect_content_paths):
    with pytest.raises(SystemExit):
        _run("--source", SOURCE, "--apply", "--verify")


def test_cli_dry_run_and_verify_mutually_exclusive(_redirect_content_paths):
    with pytest.raises(SystemExit):
        _run("--source", SOURCE, "--dry-run", "--verify")


# ---------------------------------------------------------------------------
# D1 — Le CLI gère tous les sous-types de LockBusy (Server + Pipeline)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("exc_cls,msg", [
    (review_lock.ServerLockBusy, "server tourne"),
    (review_lock.PipelineLockBusy, "pipeline tourne déjà"),
])
def test_cli_handles_all_lock_busy_subclasses(
    _redirect_content_paths, monkeypatch, exc_cls, msg,
):
    """Le CLI catch `review_lock.LockBusy` → tous les sous-types remontent
    proprement avec code 3."""
    from contextlib import contextmanager

    @contextmanager
    def _busy(*, force=False):
        raise exc_cls(msg)
        yield  # pragma: no cover

    monkeypatch.setattr(cli.review_lock, "acquire_pipeline_lock", _busy)
    code, _out, err = _run("--source", SOURCE)
    assert code == 3
    assert "verrou" in err.lower()


# ---------------------------------------------------------------------------
# D8 — Log header structuré sur stderr (mode + source + timestamp)
# ---------------------------------------------------------------------------


def test_cli_emits_structured_header_to_stderr(_redirect_content_paths):
    recos_root, _i, _m = _redirect_content_paths
    _seed_one_reco(recos_root)
    code, out, err = _run("--source", SOURCE)
    assert code == 0
    # stdout reste du JSON pur, stderr porte le header.
    json.loads(out)  # ne crash pas
    assert "mode=dry-run" in err
    assert f"source={SOURCE}" in err
    assert "timestamp=" in err


def test_cli_header_apply_mode(_redirect_content_paths):
    recos_root, _i, _m = _redirect_content_paths
    _seed_one_reco(recos_root)
    code, _out, err = _run("--source", SOURCE, "--apply")
    assert code == 0
    assert "mode=apply" in err


def test_cli_header_verify_mode(_redirect_content_paths):
    recos_root, _i, _m = _redirect_content_paths
    _seed_one_reco(recos_root)
    _run("--source", SOURCE, "--apply")  # seed disque
    code, _out, err = _run("--source", SOURCE, "--verify")
    assert code == 0
    assert "mode=verify" in err
