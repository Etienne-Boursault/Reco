"""Tests : tools.enrich_audit.flag_writer — sidecar I/O + archive."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from enrich_audit.flag_writer import (
    ARCHIVE_DIR_NAME,
    archive_dir,
    clear_source,
    list_archives,
    list_sidecars,
    read_sidecar,
    restore_archive,
    sidecar_path,
    write_sidecar,
)
from enrich_audit.service import AuditResult
from enrich_audit.types import (
    AUDITOR_VERSION,
    SIDECAR_SCHEMA_VERSION,
    Severity,
    Suspicion,
)


# ===== sidecar_path ========================================================


def test_sidecar_path_under_source(tmp_path: Path):
    p = sidecar_path("src", "abc12345", base_dir=tmp_path)
    assert p == tmp_path / "src" / "abc12345.json"


def test_sidecar_path_rejects_traversal_source(tmp_path: Path):
    with pytest.raises(ValueError):
        sidecar_path("../evil", "x", base_dir=tmp_path)


def test_sidecar_path_rejects_traversal_item(tmp_path: Path):
    with pytest.raises(ValueError):
        sidecar_path("src", "../evil", base_dir=tmp_path)


def test_sidecar_path_rejects_empty_source(tmp_path: Path):
    with pytest.raises(ValueError):
        sidecar_path("", "x", base_dir=tmp_path)


def test_sidecar_path_rejects_empty_item(tmp_path: Path):
    with pytest.raises(ValueError):
        sidecar_path("src", "", base_dir=tmp_path)


def test_sidecar_path_rejects_backslash_in_source(tmp_path: Path):
    with pytest.raises(ValueError):
        sidecar_path("a\\b", "x", base_dir=tmp_path)


def test_sidecar_path_rejects_backslash_in_item(tmp_path: Path):
    with pytest.raises(ValueError):
        sidecar_path("src", "a\\b", base_dir=tmp_path)


def test_sidecar_path_rejects_null_byte(tmp_path: Path):
    """CR senior M6 : refuse \\x00."""
    with pytest.raises(ValueError):
        sidecar_path("src", "a\x00b", base_dir=tmp_path)


def test_sidecar_path_rejects_windows_reserved(tmp_path: Path):
    """CR senior M6 : refuse CON, NUL, AUX, etc."""
    with pytest.raises(ValueError):
        sidecar_path("con", "x", base_dir=tmp_path)
    with pytest.raises(ValueError):
        sidecar_path("src", "nul", base_dir=tmp_path)


def test_sidecar_path_rejects_uppercase(tmp_path: Path):
    """CR senior M6 : whitelist stricte minuscules + chiffres + - _."""
    with pytest.raises(ValueError):
        sidecar_path("SRC", "x", base_dir=tmp_path)


def test_sidecar_path_accepts_legacy_ids_with_underscore(tmp_path: Path):
    """Underscores tolérés pour les ids legacy 8-char hex variants."""
    p = sidecar_path("src", "abc_1234", base_dir=tmp_path)
    assert p.name == "abc_1234.json"


# ===== write/read roundtrip ================================================


def _suspect_result() -> AuditResult:
    return AuditResult(
        item_id="abc12345",
        is_suspect=True,
        suspicions=(
            Suspicion(kind="title_mismatch", detail="X != Y",
                      severity=Severity.WARNING, confidence=0.8),
            Suspicion(kind="year_mismatch", detail="2010 vs 2020",
                      severity=Severity.CRITICAL),
        ),
    )


_FIXED_TS = "2026-06-10T12:00:00Z"


def test_write_then_read_preserves_payload(tmp_path: Path):
    r = _suspect_result()
    write_sidecar(r, "src", base_dir=tmp_path, audited_at=_FIXED_TS)
    loaded = read_sidecar("src", "abc12345", base_dir=tmp_path)
    assert loaded == r


def test_write_includes_schema_version_and_auditor(tmp_path: Path):
    """CR archi #14 : sidecar versionné + auditor stamped."""
    p = write_sidecar(_suspect_result(), "src",
                      base_dir=tmp_path, audited_at=_FIXED_TS)
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["schemaVersion"] == SIDECAR_SCHEMA_VERSION
    assert raw["auditorVersion"] == AUDITOR_VERSION
    assert raw["auditedAt"] == _FIXED_TS


def test_write_includes_tmdb_id_when_provided(tmp_path: Path):
    """CR senior L8 : tmdbId stocké pour debug."""
    p = write_sidecar(_suspect_result(), "src",
                      base_dir=tmp_path, audited_at=_FIXED_TS, tmdb_id=1234)
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["tmdbId"] == 1234


def test_write_omits_tmdb_id_when_none(tmp_path: Path):
    p = write_sidecar(_suspect_result(), "src",
                      base_dir=tmp_path, audited_at=_FIXED_TS)
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert "tmdbId" not in raw


def test_write_includes_tmdb_data_date_when_provided(tmp_path: Path):
    p = write_sidecar(_suspect_result(), "src",
                      base_dir=tmp_path, audited_at=_FIXED_TS,
                      tmdb_data_date="2026-05-01T00:00:00Z")
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert raw["tmdbDataDate"] == "2026-05-01T00:00:00Z"


def test_write_creates_parent_directory(tmp_path: Path):
    write_sidecar(_suspect_result(), "src",
                  base_dir=tmp_path, audited_at=_FIXED_TS)
    assert (tmp_path / "src").exists()


def test_write_clean_result(tmp_path: Path):
    r = AuditResult(item_id="zzz", is_suspect=False, suspicions=())
    write_sidecar(r, "src", base_dir=tmp_path, audited_at=_FIXED_TS)
    loaded = read_sidecar("src", "zzz", base_dir=tmp_path)
    assert loaded is not None
    assert loaded.is_suspect is False


def test_payload_uses_camelcase_keys(tmp_path: Path):
    p = write_sidecar(_suspect_result(), "src",
                      base_dir=tmp_path, audited_at=_FIXED_TS)
    raw = json.loads(p.read_text(encoding="utf-8"))
    assert "enrichmentSuspect" in raw
    assert "itemId" in raw
    assert "suspicions" in raw
    assert raw["enrichmentSuspect"] is True


def test_payload_sorted_keys_idempotent(tmp_path: Path):
    p1 = write_sidecar(_suspect_result(), "src",
                       base_dir=tmp_path, audited_at=_FIXED_TS)
    content1 = p1.read_text(encoding="utf-8")
    p2 = write_sidecar(_suspect_result(), "src",
                       base_dir=tmp_path, audited_at=_FIXED_TS)
    content2 = p2.read_text(encoding="utf-8")
    assert content1 == content2


def test_write_default_audited_at_now_when_none(tmp_path: Path):
    """Sans `audited_at` fourni, on écrit l'horodatage courant."""
    p = write_sidecar(_suspect_result(), "src", base_dir=tmp_path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    # Au moins un timestamp ISO8601 plausible.
    assert raw["auditedAt"].startswith("20")
    assert raw["auditedAt"].endswith("Z")


# ===== read defensive ======================================================


def test_read_returns_none_when_missing(tmp_path: Path):
    assert read_sidecar("src", "nonexistent", base_dir=tmp_path) is None


def test_read_returns_none_on_invalid_json(tmp_path: Path):
    p = sidecar_path("src", "broken", base_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not json", encoding="utf-8")
    assert read_sidecar("src", "broken", base_dir=tmp_path) is None


def test_read_returns_none_on_non_object_root(tmp_path: Path):
    p = sidecar_path("src", "x", base_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[]", encoding="utf-8")
    assert read_sidecar("src", "x", base_dir=tmp_path) is None


def test_read_returns_none_on_bad_suspicions_shape(tmp_path: Path):
    p = sidecar_path("src", "x", base_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"itemId": "x", "suspicions": "nope"}), encoding="utf-8")
    assert read_sidecar("src", "x", base_dir=tmp_path) is None


def test_read_ignores_non_dict_suspicion_entries(tmp_path: Path):
    p = sidecar_path("src", "x", base_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "itemId": "x",
        "enrichmentSuspect": False,
        "suspicions": ["string-bogus"],
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    loaded = read_sidecar("src", "x", base_dir=tmp_path)
    assert loaded is not None
    assert loaded.suspicions == ()


def test_read_returns_none_when_suspicion_missing_kind(tmp_path: Path):
    p = sidecar_path("src", "x", base_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "itemId": "x",
        "enrichmentSuspect": True,
        "suspicions": [{"detail": "no kind"}],
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    assert read_sidecar("src", "x", base_dir=tmp_path) is None


def test_read_returns_none_when_severity_invalid(tmp_path: Path):
    p = sidecar_path("src", "x", base_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "itemId": "x",
        "enrichmentSuspect": True,
        "suspicions": [{"kind": "k", "detail": "d", "severity": "bogus"}],
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    assert read_sidecar("src", "x", base_dir=tmp_path) is None


def test_read_corrupted_suspect_true_empty_suspicions_uses_derived(tmp_path: Path, caplog):
    """CR senior C2/C3 : sidecar incohérent (`enrichmentSuspect: true` mais
    `suspicions: []`) → on prend la vérité dérivée (= False) + warning."""
    p = sidecar_path("src", "x", base_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "itemId": "x",
        "enrichmentSuspect": True,
        "suspicions": [],
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    with caplog.at_level("WARNING"):
        loaded = read_sidecar("src", "x", base_dir=tmp_path)
    assert loaded is not None
    assert loaded.is_suspect is False
    assert any("incohérent" in r.getMessage() for r in caplog.records)


def test_read_corrupted_suspect_false_with_suspicions_uses_derived(tmp_path: Path, caplog):
    p = sidecar_path("src", "x", base_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "itemId": "x",
        "enrichmentSuspect": False,
        "suspicions": [{"kind": "k", "detail": "d", "severity": "warning"}],
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    with caplog.at_level("WARNING"):
        loaded = read_sidecar("src", "x", base_dir=tmp_path)
    assert loaded is not None
    assert loaded.is_suspect is True


def test_read_missing_enrichmentSuspect_uses_derived(tmp_path: Path):
    """Champ absent → on dérive depuis suspicions (silencieux, pas une corruption)."""
    p = sidecar_path("src", "x", base_dir=tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "itemId": "x",
        "suspicions": [{"kind": "k", "detail": "d", "severity": "warning"}],
    }
    p.write_text(json.dumps(payload), encoding="utf-8")
    loaded = read_sidecar("src", "x", base_dir=tmp_path)
    assert loaded is not None
    assert loaded.is_suspect is True


# ===== list / clear ========================================================


def test_list_sidecars_empty_dir(tmp_path: Path):
    assert list_sidecars("src", base_dir=tmp_path) == []


def test_list_sidecars_returns_sorted(tmp_path: Path):
    r1 = AuditResult(item_id="bbb", is_suspect=False, suspicions=())
    r2 = AuditResult(item_id="aaa", is_suspect=False, suspicions=())
    write_sidecar(r1, "src", base_dir=tmp_path, audited_at=_FIXED_TS)
    write_sidecar(r2, "src", base_dir=tmp_path, audited_at=_FIXED_TS)
    files = list_sidecars("src", base_dir=tmp_path)
    assert [p.stem for p in files] == ["aaa", "bbb"]


def test_clear_source_archives_by_default(tmp_path: Path):
    """CR archi P1 #16 : clear archive au lieu de supprimer."""
    r = AuditResult(item_id="aaa", is_suspect=False, suspicions=())
    write_sidecar(r, "src", base_dir=tmp_path, audited_at=_FIXED_TS)
    n = clear_source("src", base_dir=tmp_path, archive_timestamp="20260610T120000Z")
    assert n == 1
    # Fichier déplacé dans l'archive.
    assert list_sidecars("src", base_dir=tmp_path) == []
    archive_root = tmp_path / ARCHIVE_DIR_NAME / "src" / "20260610T120000Z"
    assert (archive_root / "aaa.json").exists()


def test_clear_source_no_archive_mode(tmp_path: Path):
    r = AuditResult(item_id="aaa", is_suspect=False, suspicions=())
    write_sidecar(r, "src", base_dir=tmp_path, audited_at=_FIXED_TS)
    n = clear_source("src", base_dir=tmp_path, archive=False)
    assert n == 1
    assert list_sidecars("src", base_dir=tmp_path) == []
    # Pas d'archive créée.
    assert not (tmp_path / ARCHIVE_DIR_NAME).exists()


def test_clear_source_noop_when_missing(tmp_path: Path):
    assert clear_source("nope", base_dir=tmp_path) == 0


def test_clear_source_no_archive_tolerates_unlink_failure(tmp_path: Path, monkeypatch):
    """Si `Path.unlink` lève, on continue et on ignore."""
    r = AuditResult(item_id="aaa", is_suspect=False, suspicions=())
    write_sidecar(r, "src", base_dir=tmp_path, audited_at=_FIXED_TS)

    def boom(self, *a, **kw):
        raise OSError("locked")

    monkeypatch.setattr(Path, "unlink", boom)
    count = clear_source("src", base_dir=tmp_path, archive=False)
    assert count == 0
    # `monkeypatch` rétablit Path.unlink automatiquement à la fin du test
    # (CR senior M11) — pas de restore manuel.


# ===== archive / restore (CR archi P1 #16) ================================


def test_archive_dir_computes_path_for_timestamp(tmp_path: Path):
    p = archive_dir("src", base_dir=tmp_path, timestamp="20260610T120000Z")
    assert p == tmp_path / ARCHIVE_DIR_NAME / "src" / "20260610T120000Z"


def test_archive_dir_defaults_to_now(tmp_path: Path):
    p = archive_dir("src", base_dir=tmp_path)
    assert p.parent == tmp_path / ARCHIVE_DIR_NAME / "src"


def test_list_archives_returns_descending(tmp_path: Path):
    r = AuditResult(item_id="aaa", is_suspect=False, suspicions=())
    write_sidecar(r, "src", base_dir=tmp_path, audited_at=_FIXED_TS)
    clear_source("src", base_dir=tmp_path, archive_timestamp="20260101T000000Z")
    write_sidecar(r, "src", base_dir=tmp_path, audited_at=_FIXED_TS)
    clear_source("src", base_dir=tmp_path, archive_timestamp="20260602T000000Z")
    archives = list_archives("src", base_dir=tmp_path)
    assert [a.name for a in archives] == ["20260602T000000Z", "20260101T000000Z"]


def test_list_archives_empty_when_no_archive(tmp_path: Path):
    assert list_archives("src", base_dir=tmp_path) == []


def test_restore_archive_restores_last_snapshot(tmp_path: Path):
    """Workflow : write → clear (archive) → restore_archive."""
    r = AuditResult(item_id="aaa", is_suspect=False, suspicions=())
    write_sidecar(r, "src", base_dir=tmp_path, audited_at=_FIXED_TS)
    clear_source("src", base_dir=tmp_path, archive_timestamp="20260610T120000Z")
    assert list_sidecars("src", base_dir=tmp_path) == []
    n = restore_archive("src", base_dir=tmp_path)
    assert n == 1
    assert read_sidecar("src", "aaa", base_dir=tmp_path) is not None


def test_restore_archive_specific_timestamp(tmp_path: Path):
    r = AuditResult(item_id="aaa", is_suspect=False, suspicions=())
    write_sidecar(r, "src", base_dir=tmp_path, audited_at=_FIXED_TS)
    clear_source("src", base_dir=tmp_path, archive_timestamp="20260101T000000Z")
    n = restore_archive("src", base_dir=tmp_path,
                       archive_timestamp="20260101T000000Z")
    assert n == 1


def test_restore_archive_returns_zero_when_no_archive(tmp_path: Path):
    assert restore_archive("src", base_dir=tmp_path) == 0


def test_restore_archive_returns_zero_for_unknown_timestamp(tmp_path: Path):
    assert restore_archive("src", base_dir=tmp_path,
                          archive_timestamp="20260101T000000Z") == 0
