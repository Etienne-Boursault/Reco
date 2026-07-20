"""Tests des nouvelles garanties d'atomicité + cache mtime-based de _load_groups.

Couvre :
  - common.atomic_write_text : pas de fichier partiel en cas de crash en
    cours d'écriture (le fichier d'origine reste intact).
  - review_routes._allocate_new_reco : passe par atomic_write_text (pas de
    write_text direct → pas de corruption possible).
  - review_render._load_groups : retourne le cache tant que mtime inchangé,
    re-scanne quand un fichier reco est modifié.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import common
import review_render
import review_routes


# ===== atomic_write_text ====================================================
def test_atomic_write_creates_file_with_content(tmp_path: Path):
    p = tmp_path / "out.json"
    common.atomic_write_text(p, '{"k":1}\n')
    assert p.read_text(encoding="utf-8") == '{"k":1}\n'


def test_atomic_write_overwrites_existing_file(tmp_path: Path):
    p = tmp_path / "out.json"
    p.write_text('{"old":true}', encoding="utf-8")
    common.atomic_write_text(p, '{"new":true}')
    assert p.read_text(encoding="utf-8") == '{"new":true}'


def test_atomic_write_failure_does_not_corrupt_target(tmp_path: Path, monkeypatch):
    """Si fsync/replace échoue après que le tmp est écrit, la cible
    d'origine doit rester intacte (pas de fichier tronqué)."""
    p = tmp_path / "out.json"
    p.write_text('{"original":true}', encoding="utf-8")

    real_replace = common.os.replace

    def boom_replace(src, dst):
        raise OSError("simulated fail")

    monkeypatch.setattr(common.os, "replace", boom_replace)
    with pytest.raises(OSError):
        common.atomic_write_text(p, '{"new":true}')
    # La cible originale est intacte.
    assert p.read_text(encoding="utf-8") == '{"original":true}'
    # Le .tmp a été nettoyé (defensive cleanup dans le finally).
    assert not (p.with_suffix(p.suffix + ".tmp")).exists()
    # Restore (paranoia, monkeypatch fait déjà le job).
    monkeypatch.setattr(common.os, "replace", real_replace)


# ===== _allocate_new_reco uses atomic write =================================
def test_allocate_new_reco_atomic_no_partial_on_write_failure(
    tmp_path: Path, monkeypatch,
):
    """Si l'écriture du stub échoue, le fichier final ne doit pas exister
    (pas de corruption silencieuse — soit complet, soit absent)."""
    import common as _common
    src_id = "demo-alloc"
    recos_dir = tmp_path / "recos" / src_id
    recos_dir.mkdir(parents=True)
    monkeypatch.setattr(_common, "RECOS_DIR", tmp_path / "recos")

    # Simule un crash après écriture du .tmp mais avant le rename : le
    # fichier final ne doit pas exister.
    def boom_replace(src, dst):
        raise OSError("crash")

    monkeypatch.setattr(_common.os, "replace", boom_replace)
    with pytest.raises(OSError):
        review_routes._allocate_new_reco(src_id, "ep-001")
    # Aucun fichier final.
    assert list(recos_dir.glob("*.json")) == []
    # Le .tmp a été nettoyé.
    assert list(recos_dir.glob("*.tmp")) == []


def test_allocate_new_reco_success_writes_valid_json(
    tmp_path: Path, monkeypatch,
):
    """Sanity check : sur le happy path, le fichier final est valide."""
    import common as _common
    src_id = "demo-alloc-ok"
    recos_dir = tmp_path / "recos" / src_id
    recos_dir.mkdir(parents=True)
    monkeypatch.setattr(_common, "RECOS_DIR", tmp_path / "recos")
    new_id, new_path = review_routes._allocate_new_reco(src_id, "ep-001")
    data = json.loads(new_path.read_text(encoding="utf-8"))
    assert data["id"] == new_id
    assert data["episodeGuid"] == "ep-001"
    assert data["status"] == "draft"


# ===== _load_groups mtime-based cache ========================================
def _make_minimal_source(tmp_path: Path, monkeypatch, src_id="demo-cache"):
    import common as _common
    sources_dir = tmp_path / "sources"
    episodes_dir = tmp_path / "episodes" / src_id
    recos_dir = tmp_path / "recos" / src_id
    for d in (sources_dir, episodes_dir, recos_dir):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_common, "SOURCES_DIR", sources_dir)
    monkeypatch.setattr(_common, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(_common, "RECOS_DIR", tmp_path / "recos")
    (sources_dir / f"{src_id}.json").write_text(
        json.dumps({"title": "X", "hosts": []}), encoding="utf-8",
    )
    (episodes_dir / "ep-001.json").write_text(
        json.dumps({"guid": "ep-001", "title": "Ep 1"}), encoding="utf-8",
    )
    (recos_dir / "0001.json").write_text(
        json.dumps({"id": "x-0001", "episodeGuid": "ep-001",
                    "title": "T", "types": ["autre"], "status": "draft"}),
        encoding="utf-8",
    )
    return src_id


def test_load_groups_returns_cache_when_unchanged(tmp_path, monkeypatch):
    """Deuxième appel sans modif disque → pas de re-lecture des fichiers."""
    src_id = _make_minimal_source(tmp_path, monkeypatch)
    review_render._clear_groups_cache()
    # Premier appel : remplit le cache.
    r1 = review_render._load_groups(src_id)
    # Patch read_json pour détecter toute relecture.
    with patch.object(review_render, "read_json",
                      side_effect=AssertionError("ne devrait pas relire")) as m:
        r2 = review_render._load_groups(src_id)
    # Mêmes objets : le cache renvoie directement le tuple précédent.
    assert r2 is r1
    assert m.call_count == 0


def test_load_groups_invalidates_on_mtime_change(tmp_path, monkeypatch):
    """Modifier un reco → le cache doit se réinvalider et relire."""
    import os
    src_id = _make_minimal_source(tmp_path, monkeypatch)
    review_render._clear_groups_cache()
    source1, episodes1, groups1 = review_render._load_groups(src_id)
    assert "ep-001" in groups1 and groups1["ep-001"][0]["title"] == "T"

    # Modifier le fichier reco — bump explicite du mtime pour vaincre la
    # granularité fs (1 s sur certains FS Windows).
    reco_path = tmp_path / "recos" / src_id / "0001.json"
    reco_path.write_text(
        json.dumps({"id": "x-0001", "episodeGuid": "ep-001",
                    "title": "T-UPDATED", "types": ["autre"], "status": "draft"}),
        encoding="utf-8",
    )
    future = reco_path.stat().st_mtime + 10
    os.utime(reco_path, (future, future))

    source2, episodes2, groups2 = review_render._load_groups(src_id)
    assert groups2["ep-001"][0]["title"] == "T-UPDATED"


def test_load_groups_invalidates_reco_path_cache_on_new_file(
    tmp_path, monkeypatch,
):
    """Bonus : un nouveau fichier reco créé par le pipeline doit être
    découvert par `_reco_path` après le prochain `_load_groups`."""
    import os
    import review_handler_base as rhb
    src_id = _make_minimal_source(tmp_path, monkeypatch)
    review_render._clear_groups_cache()
    rhb._RECO_PATH_CACHE.clear()
    # Premier load : remplit le cache groups + _RECO_PATH_CACHE.
    review_render._load_groups(src_id)
    rhb._rebuild_reco_path_cache(src_id)
    assert rhb._reco_path(src_id, "x-0002") is None

    # Le pipeline (extract_recos) crée un nouveau fichier reco.
    new_reco = tmp_path / "recos" / src_id / "0002.json"
    new_reco.write_text(
        json.dumps({"id": "x-0002", "episodeGuid": "ep-001",
                    "title": "New", "types": ["autre"], "status": "draft"}),
        encoding="utf-8",
    )
    # Bump mtime du dossier pour garantir détection cross-FS.
    future = new_reco.stat().st_mtime + 10
    os.utime(new_reco, (future, future))
    # Le prochain `_load_groups` doit invalider `_RECO_PATH_CACHE`
    # → `_reco_path` retrouve maintenant le nouveau fichier.
    review_render._load_groups(src_id)
    assert rhb._reco_path(src_id, "x-0002") is not None
    review_render._clear_groups_cache()
    rhb._RECO_PATH_CACHE.clear()
