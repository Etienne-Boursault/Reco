"""Tests pour ``tools.reco_init`` — mode ``--ci`` + flags."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from tools.reco_init import run


def test_ci_minimal(tmp_path: Path) -> None:
    out = io.StringIO()
    code = run(
        [
            "--ci",
            "--slug=demo",
            "--name=Demo",
            "--rss-url=https://example.com/rss",
            f"--output-dir={tmp_path}",
        ],
        stdin=io.StringIO(""),
        stdout=out,
    )
    assert code == 0
    path = tmp_path / "demo.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["id"] == "demo"
    assert data["title"] == "Demo"
    assert data["rssUrl"] == "https://example.com/rss"
    # Defaults theme
    assert data["theme"]["colors"]["accent"] == "#5eead4"


def test_ci_full_flags(tmp_path: Path) -> None:
    out = io.StringIO()
    code = run(
        [
            "--ci",
            "--slug=full-demo",
            "--name=Full Demo",
            "--rss-url=https://example.com/rss",
            "--site-url=https://full-demo.fr",
            "--hosts=Alice,Bob,Charlie",
            "--reco-prefix=fd",
            "--accent=#ffd23f",
            "--bg=#101015",
            f"--output-dir={tmp_path}",
        ],
        stdout=out,
    )
    assert code == 0
    data = json.loads((tmp_path / "full-demo.json").read_text(encoding="utf-8"))
    assert data["hosts"] == ["Alice", "Bob", "Charlie"]
    assert data["recoPrefix"] == "fd"
    assert data["website"] == "https://full-demo.fr"
    assert data["theme"]["colors"]["accent"] == "#ffd23f"
    assert data["theme"]["colors"]["bg"] == "#101015"


def test_ci_missing_required_exits(tmp_path: Path) -> None:
    out = io.StringIO()
    with pytest.raises(SystemExit):
        run(
            ["--ci", "--slug=demo", f"--output-dir={tmp_path}"],
            stdout=out,
        )


def test_ci_dry_run_no_file(tmp_path: Path) -> None:
    out = io.StringIO()
    code = run(
        [
            "--ci", "--dry-run",
            "--slug=dryrun", "--name=DryRun",
            "--rss-url=https://example.com/rss",
            f"--output-dir={tmp_path}",
        ],
        stdout=out,
    )
    assert code == 0
    assert not (tmp_path / "dryrun.json").exists()
    assert "DRY-RUN" in out.getvalue()
    assert '"id": "dryrun"' in out.getvalue()


def test_ci_existing_file_without_force_fails(tmp_path: Path) -> None:
    out = io.StringIO()
    args_base = [
        "--ci", "--slug=demo", "--name=Demo",
        "--rss-url=https://example.com/rss",
        f"--output-dir={tmp_path}",
    ]
    assert run(args_base, stdout=out) == 0
    code = run(args_base, stdout=io.StringIO())
    assert code == 2


def test_ci_force_overwrites(tmp_path: Path) -> None:
    out = io.StringIO()
    args = [
        "--ci", "--slug=demo", "--name=Demo V1",
        "--rss-url=https://example.com/rss",
        f"--output-dir={tmp_path}",
    ]
    assert run(args, stdout=out) == 0
    args2 = args[:2] + ["--name=Demo V2"] + args[3:] + ["--force"]
    assert run(args2, stdout=io.StringIO()) == 0
    data = json.loads((tmp_path / "demo.json").read_text(encoding="utf-8"))
    assert data["title"] == "Demo V2"


def test_ci_invalid_slug_exits_with_error(tmp_path: Path) -> None:
    out = io.StringIO()
    code = run(
        [
            "--ci", "--slug=BAD SLUG", "--name=Bad",
            "--rss-url=https://example.com/rss",
            f"--output-dir={tmp_path}",
        ],
        stdout=out,
    )
    assert code == 2
    assert "slug invalide" in out.getvalue().lower() or "Validation" in out.getvalue()
