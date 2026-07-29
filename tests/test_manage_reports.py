"""Tests CLI `tools/manage_reports.py`.

Smoke tests : --list, --show, --resolve, --dismiss, --export.

Le CLI lit/écrit dans `tools/output/reports/`. On monkeypatch `REPORTS_DIR`
vers un tmpdir pour isoler les tests du dossier réel.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import manage_reports


def _mk_report(
    tmp_root: Path,
    report_id: str,
    *,
    source_id: str = "un-bon-moment",
    status: str = "pending",
    category: str = "error",
    details: str = "Titre incorrect, c'est en fait *Inception*.",
) -> Path:
    """Crée un report JSON minimal dans `tmp_root/<source>/<id>.json`."""
    d = tmp_root / source_id
    d.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "id": report_id,
        "sourceId": source_id,
        "recoId": "ubm-0001",
        "category": category,
        "details": details,
        "submitter": {"wantCredit": False},
        "submittedAt": "2026-06-11T10:00:00+00:00",
        "status": status,
        "resolvedAt": None,
        "resolvedBy": None,
        "notes": None,
    }
    p = d / f"{report_id}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


@pytest.fixture
def reports_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige `manage_reports.REPORTS_DIR` vers tmp_path."""
    monkeypatch.setattr(manage_reports, "REPORTS_DIR", tmp_path)

    # Le verrou pipeline est un no-op dans les tests (sinon il créerait un
    # fichier lock dans tools/output réel).
    import contextlib

    @contextlib.contextmanager
    def fake_lock(force: bool = False):  # noqa: ARG001
        yield

    monkeypatch.setattr(manage_reports, "acquire_pipeline_lock", fake_lock)
    return tmp_path


def test_list_returns_0_and_prints_ids(
    reports_tmp: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _mk_report(reports_tmp, "rep-aaa")
    _mk_report(reports_tmp, "rep-bbb", status="resolved")

    rc = manage_reports.main(["--source", "un-bon-moment", "--list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "rep-aaa" in out
    assert "rep-bbb" in out


def test_list_filters_by_status(
    reports_tmp: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _mk_report(reports_tmp, "rep-pending", status="pending")
    _mk_report(reports_tmp, "rep-resolved", status="resolved")

    rc = manage_reports.main(
        ["--source", "un-bon-moment", "--list", "--status", "pending"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "rep-pending" in out
    assert "rep-resolved" not in out


def test_show_existing_report(
    reports_tmp: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _mk_report(reports_tmp, "rep-show", details="Détail à afficher.")
    rc = manage_reports.main(["--source", "un-bon-moment", "--show", "rep-show"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Détail à afficher" in out
    assert "rep-show" in out


def test_show_missing_report_returns_1(reports_tmp: Path) -> None:
    rc = manage_reports.main(["--source", "un-bon-moment", "--show", "rep-nope"])
    assert rc == 1


def test_resolve_mutates_status_and_sets_metadata(reports_tmp: Path) -> None:
    p = _mk_report(reports_tmp, "rep-resolve-me")
    rc = manage_reports.main(
        [
            "--source", "un-bon-moment",
            "--resolve", "rep-resolve-me",
            "--note", "Corrigé dans le pipeline d'enrichissement.",
        ]
    )
    assert rc == 0
    updated = json.loads(p.read_text(encoding="utf-8"))
    assert updated["status"] == "resolved"
    assert updated["resolvedAt"] is not None
    assert updated["resolvedBy"] is not None
    assert updated["notes"] == "Corrigé dans le pipeline d'enrichissement."


def test_dismiss_mutates_status(reports_tmp: Path) -> None:
    p = _mk_report(reports_tmp, "rep-dismiss-me")
    rc = manage_reports.main(["--source", "all", "--dismiss", "rep-dismiss-me"])
    assert rc == 0
    updated = json.loads(p.read_text(encoding="utf-8"))
    assert updated["status"] == "dismissed"


def test_resolve_missing_returns_1(reports_tmp: Path) -> None:
    rc = manage_reports.main(["--source", "all", "--resolve", "rep-ghost"])
    assert rc == 1


def test_export_all_sources_writes_file(
    reports_tmp: Path, tmp_path: Path
) -> None:
    _mk_report(reports_tmp, "rep-a", source_id="src-a")
    _mk_report(reports_tmp, "rep-b", source_id="src-b")
    out = tmp_path / "out.json"
    rc = manage_reports.main(["--source", "all", "--export", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["count"] == 2
    assert {r["id"] for r in payload["reports"]} == {"rep-a", "rep-b"}


def test_export_filtered_by_source(reports_tmp: Path, tmp_path: Path) -> None:
    _mk_report(reports_tmp, "rep-a", source_id="src-a")
    _mk_report(reports_tmp, "rep-b", source_id="src-b")
    out = tmp_path / "out.json"
    rc = manage_reports.main(["--source", "src-a", "--export", str(out)])
    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["count"] == 1
    assert payload["sourceFilter"] == "src-a"


def test_list_empty_dir_returns_0(
    reports_tmp: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = manage_reports.main(["--source", "all", "--list"])
    assert rc == 0
    assert "Aucun" in capsys.readouterr().out


def test_argparse_requires_action() -> None:
    with pytest.raises(SystemExit):
        manage_reports.main(["--source", "all"])


# ===== Énumération des sources et filtrage des fichiers ====================
def test_list_source_ids_empty_when_dir_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aucun signalement encore reçu : dossier absent → liste vide, pas
    d'exception au démarrage du CLI."""
    monkeypatch.setattr(manage_reports, "REPORTS_DIR", tmp_path / "jamais-cree")

    assert manage_reports._list_source_ids() == []


def test_list_source_ids_ignores_stray_files(
    reports_tmp: Path
) -> None:
    """Seuls les SOUS-DOSSIERS sont des sources (un fichier égaré à la racine
    n'en est pas une)."""
    _mk_report(reports_tmp, "rep-aaa", source_id="podcast-b")
    (reports_tmp / "README.md").write_text("pas une source", encoding="utf-8")

    assert manage_reports._list_source_ids() == ["podcast-b"]


def test_atomic_write_leftovers_are_ignored(
    reports_tmp: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un `.json.tmp` laissé par une écriture atomique interrompue ne doit pas
    être lu comme un signalement.

    Note : c'est le `glob("*.json")` qui l'exclut, pas la garde
    `endswith(".tmp")` de `_iter_report_paths` — celle-ci est inatteignable
    par construction. Le test vérifie donc le COMPORTEMENT attendu, pas cette
    ligne-là."""
    _mk_report(reports_tmp, "rep-aaa")
    (reports_tmp / "un-bon-moment" / "rep-zzz.json.tmp").write_text(
        '{"id": "rep-zzz"}', encoding="utf-8")

    rc = manage_reports.main(["--source", "un-bon-moment", "--list"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "rep-aaa" in out
    assert "rep-zzz" not in out


def test_unreadable_report_is_skipped_in_list(
    reports_tmp: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un JSON corrompu est ignoré (avec un warning) : la liste reste
    utilisable au lieu de planter."""
    _mk_report(reports_tmp, "rep-aaa")
    (reports_tmp / "un-bon-moment" / "rep-casse.json").write_text(
        "{ tronqué", encoding="utf-8")

    rc = manage_reports.main(["--source", "un-bon-moment", "--list"])

    assert rc == 0
    assert "rep-aaa" in capsys.readouterr().out


def test_read_report_returns_none_on_invalid_json(reports_tmp: Path) -> None:
    p = reports_tmp / "un-bon-moment"
    p.mkdir(parents=True, exist_ok=True)
    broken = p / "rep-casse.json"
    broken.write_text("{{{", encoding="utf-8")

    assert manage_reports._read_report(broken) is None


def test_read_report_returns_none_when_file_is_missing(
    reports_tmp: Path
) -> None:
    assert manage_reports._read_report(reports_tmp / "absent.json") is None


def test_find_report_scans_past_non_matching_ids(reports_tmp: Path) -> None:
    """La recherche par id doit parcourir tous les fichiers, pas s'arrêter au
    premier qui ne correspond pas."""
    _mk_report(reports_tmp, "rep-aaa")
    _mk_report(reports_tmp, "rep-bbb")
    _mk_report(reports_tmp, "rep-ccc")

    found = manage_reports._find_report("rep-ccc", "un-bon-moment")

    assert found is not None
    path, report = found
    assert report["id"] == "rep-ccc"
    assert path.name == "rep-ccc.json"


def test_find_report_returns_none_when_absent(reports_tmp: Path) -> None:
    _mk_report(reports_tmp, "rep-aaa")

    assert manage_reports._find_report("rep-zzz", "un-bon-moment") is None


# ===== Idempotence des mutations ===========================================
def test_resolving_an_already_resolved_report_is_a_noop(
    reports_tmp: Path
) -> None:
    """Re-résoudre sans note ne réécrit pas le fichier — on ne veut pas écraser
    `resolvedAt`/`resolvedBy` d'origine par un second passage."""
    path = _mk_report(reports_tmp, "rep-aaa", status="resolved")
    before = path.read_text(encoding="utf-8")

    rc = manage_reports.main(
        ["--source", "un-bon-moment", "--resolve", "rep-aaa"])

    assert rc == 0
    assert path.read_text(encoding="utf-8") == before


def test_resolving_again_with_a_note_does_write(reports_tmp: Path) -> None:
    """Avec une note, en revanche, la mutation s'applique : c'est le seul moyen
    d'annoter un signalement déjà traité."""
    path = _mk_report(reports_tmp, "rep-aaa", status="resolved")

    rc = manage_reports.main([
        "--source", "un-bon-moment", "--resolve", "rep-aaa",
        "--note", "corrigé dans la foulée",
    ])

    assert rc == 0
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["notes"] == "corrigé dans la foulée"
    assert payload["resolvedAt"] is not None
