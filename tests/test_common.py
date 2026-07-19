"""Tests des utilitaires partagés du pipeline (tools/common.py)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from common import (
    episode_label,
    format_timestamp,
    normalize_text,
    parse_timestamp,
    reco_prefix,
    slugify,
    write_json_if_changed,
)


# ===== slugify ============================================================
def test_slugify_strips_accents_and_case():
    assert slugify("Bérengère KRIEF") == "berengere-krief"


def test_slugify_collapses_punctuation():
    assert slugify("Hello, World! / Test") == "hello-world-test"


def test_slugify_fallback_for_empty_or_pure_special():
    assert slugify("") == "x"
    assert slugify("@@@") == "x"


def test_slugify_keeps_digits():
    assert slugify("Saison 5 — Épisode 32") == "saison-5-episode-32"


# ===== reco_prefix ========================================================
# Depuis l'issue #14, `reco_prefix` lit EXCLUSIVEMENT la config externalisée
# (`src/content/sources/<id>.json`). L'heuristique des initiales a disparu —
# elle masquait silencieusement les sources mal configurées.


def test_reco_prefix_reads_from_externalized_config():
    """Pour `un-bon-moment` la config existe et déclare `recoPrefix=ubm`."""
    from tools.config.registry import clear_default_registry_cache

    clear_default_registry_cache()
    assert reco_prefix("un-bon-moment") == "ubm"


def test_reco_prefix_raises_when_no_config_exists(monkeypatch):
    """Un id sans fichier JSON → erreur explicite, pas une heuristique
    silencieuse qui produirait un préfixe arbitraire.

    On désactive ici la fixture de tests qui auto-vivifie les sources
    inconnues (`_AutoSourceRegistry`) pour vérifier le contrat de prod.
    """
    from tools.config import registry as reg_mod

    real = reg_mod.SourceRegistry()  # pas d'auto-vivification
    monkeypatch.setattr(reg_mod, "_default_registry", real)
    with pytest.raises(FileNotFoundError, match="config"):
        reco_prefix("source-fictive-inexistante-xyz")


# ===== write_json_if_changed ==============================================
def test_write_json_creates_when_missing(tmp_path: Path):
    target = tmp_path / "out.json"
    written = write_json_if_changed(target, {"a": 1})
    assert written is True
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1}


def test_write_json_skips_when_content_unchanged(tmp_path: Path):
    target = tmp_path / "out.json"
    write_json_if_changed(target, {"a": 1})
    # 2e écriture du même contenu → aucun écrit (idempotence).
    written = write_json_if_changed(target, {"a": 1})
    assert written is False


def test_write_json_writes_when_content_changes(tmp_path: Path):
    target = tmp_path / "out.json"
    write_json_if_changed(target, {"a": 1})
    written = write_json_if_changed(target, {"a": 2})
    assert written is True
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2}


def test_write_json_preserves_accents_utf8(tmp_path: Path):
    target = tmp_path / "out.json"
    write_json_if_changed(target, {"name": "Bérengère"})
    text = target.read_text(encoding="utf-8")
    # Le contenu doit être en UTF-8 lisible (pas d'\uXXXX).
    assert "Bérengère" in text


# ===== load_source ========================================================
def test_load_source_raises_when_missing(monkeypatch, tmp_path: Path):
    import common
    monkeypatch.setattr(common, "SOURCES_DIR", tmp_path)
    import pytest
    with pytest.raises(FileNotFoundError):
        common.load_source("inconnu")


def test_load_source_returns_data(monkeypatch, tmp_path: Path):
    import common
    monkeypatch.setattr(common, "SOURCES_DIR", tmp_path)
    (tmp_path / "ubm.json").write_text('{"id": "ubm", "title": "UBM"}', encoding="utf-8")
    data = common.load_source("ubm")
    assert data["title"] == "UBM"


# ===== list_episode_files =================================================
def test_list_episode_files_empty_when_dir_absent(monkeypatch, tmp_path: Path):
    import common
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    # Aucun sous-dossier pour 'ubm' → liste vide.
    assert common.list_episode_files("ubm") == []


def test_list_episode_files_returns_sorted(monkeypatch, tmp_path: Path):
    import common
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path)
    src_dir = tmp_path / "ubm"
    src_dir.mkdir()
    (src_dir / "b.json").write_text("{}", encoding="utf-8")
    (src_dir / "a.json").write_text("{}", encoding="utf-8")
    (src_dir / "ignore.txt").write_text("x", encoding="utf-8")  # filtre *.json
    files = common.list_episode_files("ubm")
    assert [p.name for p in files] == ["a.json", "b.json"]


# ===== Chemins helpers ====================================================
def test_path_helpers_compose_correctly():
    from common import (
        episodes_dir_for, recos_dir_for, transcript_path_for,
        EPISODES_DIR, RECOS_DIR, TRANSCRIPTS_DIR,
    )
    assert episodes_dir_for("ubm") == EPISODES_DIR / "ubm"
    assert recos_dir_for("ubm") == RECOS_DIR / "ubm"
    # transcript : le guid est slugifié pour éviter les chars problématiques.
    p = transcript_path_for("ubm", "abc-123")
    assert p.parent == TRANSCRIPTS_DIR / "ubm"
    assert p.name == "abc-123.txt"


def test_transcript_path_slugifies_guid():
    from common import transcript_path_for
    # Si le guid contient des caractères spéciaux, ils sont normalisés.
    p = transcript_path_for("ubm", "Bérengère")
    assert "berengere" in p.name


# ===== get_logger =========================================================
def test_get_logger_returns_same_logger_idempotent():
    import common, logging
    l1 = common.get_logger("reco-test-x")
    l2 = common.get_logger("reco-test-x")
    assert l1 is l2  # même instance, par nom
    assert l1.level == logging.INFO


def test_get_logger_tolerates_stdout_without_reconfigure(monkeypatch):
    """Un stdout sans `.reconfigure` (AttributeError) ne casse pas le logger :
    l'exception est avalée et le handler est quand même installé."""
    import io
    import sys

    import common
    # io.StringIO n'a pas de méthode reconfigure → AttributeError capturée.
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    logger = common.get_logger("reco-no-reconfigure-xyz")
    assert logger.handlers


# ===== normalize_text =====================================================
def test_normalize_text_strips_accents_case_punct():
    assert normalize_text("Mortél, S1") == "mortel s1"


def test_normalize_text_empty_and_none():
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


# ===== format_timestamp / parse_timestamp =================================
@pytest.mark.parametrize("secs,expected", [
    (0, "00:00:00"),
    (59, "00:00:59"),
    (3723, "01:02:03"),
    (3723.9, "01:02:03"),
])
def test_format_timestamp(secs, expected):
    assert format_timestamp(secs) == expected


@pytest.mark.parametrize("ts,expected", [
    ("01:02:03", 3723),
    ("45:30", 2730),
    ("90", 90),
    ("00:00:00", 0),
    (None, None),
    ("", None),
    ("ab:cd", None),
])
def test_parse_timestamp_variants(ts, expected):
    assert parse_timestamp(ts) == expected


def test_format_parse_timestamp_roundtrip():
    assert parse_timestamp(format_timestamp(3723)) == 3723


# ===== episode_label ======================================================
@pytest.mark.parametrize("season,number,expected", [
    (5, 12, "S5E12"),
    (None, 42, "#42"),
    (0, 42, "#42"),      # season falsy → format « #N »
    (None, None, ""),
    (5, None, ""),       # numéro absent → chaîne vide
])
def test_episode_label(season, number, expected):
    assert episode_label(season, number) == expected


# ===== download_youtube_thumbnail =========================================
def test_download_youtube_thumbnail_maxres(monkeypatch):
    import requests
    from common import download_youtube_thumbnail
    calls = []

    def fake_get(url, timeout=None):
        calls.append(url)
        return SimpleNamespace(status_code=200, content=b"x" * 3000)

    monkeypatch.setattr(requests, "get", fake_get)
    data = download_youtube_thumbnail("vid123")
    assert data == b"x" * 3000
    assert "maxresdefault" in calls[0]


def test_download_youtube_thumbnail_falls_back_to_hq(monkeypatch):
    """maxres renvoie un placeholder (< 2000 o) → on tente hqdefault."""
    import requests
    from common import download_youtube_thumbnail

    def fake_get(url, timeout=None):
        if "maxres" in url:
            return SimpleNamespace(status_code=200, content=b"x" * 100)
        return SimpleNamespace(status_code=200, content=b"y" * 3000)

    monkeypatch.setattr(requests, "get", fake_get)
    assert download_youtube_thumbnail("v") == b"y" * 3000


def test_download_youtube_thumbnail_returns_none_on_errors(monkeypatch):
    """Toutes les requêtes lèvent → None (pas de miniature)."""
    import requests
    from common import download_youtube_thumbnail

    def boom(url, timeout=None):
        raise requests.exceptions.RequestException("offline")

    monkeypatch.setattr(requests, "get", boom)
    assert download_youtube_thumbnail("v") is None


# ===== atomic_write_text : retry PermissionError (Windows) ================
def test_atomic_write_retries_on_permission_error(tmp_path: Path, monkeypatch):
    """Un lecteur concurrent (PermissionError sur os.replace) → on retente,
    puis on réussit."""
    import common
    p = tmp_path / "out.json"
    calls = {"n": 0}
    real_replace = common.os.replace

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError("verrou lecteur")
        return real_replace(src, dst)

    monkeypatch.setattr(common.os, "replace", flaky_replace)
    monkeypatch.setattr(common.time, "sleep", lambda s: None)  # pas d'attente réelle
    common.atomic_write_text(p, "contenu")
    assert p.read_text(encoding="utf-8") == "contenu"
    assert calls["n"] == 3


def test_atomic_write_raises_after_max_permission_retries(tmp_path: Path, monkeypatch):
    """PermissionError persistant sur les 4 essais → l'exception remonte,
    la cible d'origine reste intacte et le .tmp est nettoyé."""
    import common
    p = tmp_path / "out.json"
    p.write_text("orig", encoding="utf-8")

    def always_locked(src, dst):
        raise PermissionError("toujours verrouillé")

    monkeypatch.setattr(common.os, "replace", always_locked)
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    with pytest.raises(PermissionError):
        common.atomic_write_text(p, "nouveau")
    assert p.read_text(encoding="utf-8") == "orig"
    assert not (p.with_suffix(p.suffix + ".tmp")).exists()


def test_atomic_write_tmp_unlink_oserror_is_swallowed(tmp_path: Path, monkeypatch):
    """Si le nettoyage du .tmp échoue (OSError) dans le finally, l'erreur est
    avalée : c'est bien l'exception d'origine (os.replace) qui remonte."""
    import common
    p = tmp_path / "out.json"

    def boom_replace(src, dst):
        raise OSError("échec replace")

    real_unlink = Path.unlink

    def boom_unlink(self, *a, **k):
        if self.suffix == ".tmp":
            raise OSError("échec unlink")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(common.os, "replace", boom_replace)
    monkeypatch.setattr(Path, "unlink", boom_unlink)
    with pytest.raises(OSError, match="échec replace"):
        common.atomic_write_text(p, "data")


# ===== write_json_if_changed : lecture illisible ==========================
def test_write_json_if_changed_read_oserror_still_writes(tmp_path: Path, monkeypatch):
    """Si l'ancien contenu est illisible (OSError), on écrit quand même."""
    import common
    p = tmp_path / "out.json"
    p.write_text('{"a": 1}\n', encoding="utf-8")
    real_read = Path.read_text

    def boom_read(self, *a, **k):
        if self == p:
            raise OSError("illisible")
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", boom_read)
    assert common.write_json_if_changed(p, {"a": 2}) is True
