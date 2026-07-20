"""Tests pour tools/reco_dedup.py — cible 100% couverture."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import reco_dedup as rd
from reco_dedup import (
    Cluster, cluster_recos, merge_cluster, pick_canonical, restore_last_backup,
    _can_match, _is_active, _kind_of, _title_similarity, _ts_to_seconds,
    _union_list_of_dicts_by_key,
)


# ===== Helpers ==============================================================
def _r(rid: str, title: str, *, guid: str = "ep-1", ts: str = "00:10:00",
       status: str = "draft", kind: str = "reco",
       transcript_source: str = "acast", extractors=None,
       quote: str = "", **extra) -> dict:
    """Fabrique de reco minimale."""
    d = {
        "id": rid, "episodeGuid": guid, "title": title,
        "timestamp": ts, "status": status, "kind": kind,
        "transcriptSource": transcript_source,
    }
    if extractors is not None:
        d["extractors"] = list(extractors)
    if quote:
        d["quote"] = quote
    d.update(extra)
    return d


# ===== _ts_to_seconds, _is_active, _kind_of =================================
def test_ts_to_seconds_basic():
    assert _ts_to_seconds("00:00:30") == 30
    assert _ts_to_seconds("01:02:03") == 3723
    assert _ts_to_seconds("10:30") == 630
    assert _ts_to_seconds("42") == 42


def test_ts_to_seconds_none():
    assert _ts_to_seconds(None) is None
    assert _ts_to_seconds("") is None
    assert _ts_to_seconds("xxx") is None


def test_is_active_default_is_draft():
    assert _is_active({}) is True
    assert _is_active({"status": "draft"}) is True
    assert _is_active({"status": "validated"}) is True
    assert _is_active({"status": "discarded"}) is False


def test_kind_of_default_reco():
    assert _kind_of({}) == "reco"
    assert _kind_of({"kind": "citation"}) == "citation"


# ===== _title_similarity ====================================================
def test_title_similarity_identical():
    assert _title_similarity("Inception", "Inception") == 1.0


def test_title_similarity_close_typos():
    # Très similaire : > 0.80
    assert _title_similarity("Hannes", "Annes") >= 0.70
    assert _title_similarity("Half Man", "Halfman") >= 0.75


def test_title_similarity_distinct():
    assert _title_similarity("Mortel", "Stranger Things") < 0.5


def test_title_similarity_empty():
    assert _title_similarity("", "X") == 0.0
    assert _title_similarity("X", "") == 0.0


# ===== _can_match ===========================================================
def test_can_match_high_similarity_always_ok():
    a, b = _r("a", "X"), _r("b", "X")
    assert _can_match(a, b, sim=0.95, time_window_sec=120)


def test_can_match_low_similarity_rejected():
    a, b = _r("a", "X"), _r("b", "Y")
    assert not _can_match(a, b, sim=0.60, time_window_sec=120)


def test_can_match_borderline_requires_time_proximity():
    a = _r("a", "X", ts="00:10:00")
    b_close = _r("b", "Y", ts="00:10:30")  # 30s
    b_far = _r("c", "Y", ts="00:30:00")  # 1200s
    assert _can_match(a, b_close, sim=0.75, time_window_sec=120)
    assert not _can_match(a, b_far, sim=0.75, time_window_sec=120)


def test_can_match_borderline_missing_timestamp_rejected():
    a = _r("a", "X", ts="")
    b = _r("b", "Y")
    assert not _can_match(a, b, sim=0.75, time_window_sec=120)


def test_can_match_different_episode_never_matches():
    a = _r("a", "X", guid="ep-1")
    b = _r("b", "X", guid="ep-2")
    assert not _can_match(a, b, sim=0.99, time_window_sec=120)


def test_can_match_different_kind_never_matches():
    a = _r("a", "X", kind="reco")
    b = _r("b", "X", kind="citation")
    assert not _can_match(a, b, sim=0.99, time_window_sec=120)


# ===== cluster_recos ========================================================
def test_cluster_groups_hannes_annes_anness():
    recos = [
        _r("ubm-1", "Hannes", ts="00:10:00"),
        _r("ubm-2", "Annes",  ts="00:10:05"),
        _r("ubm-3", "Anness", ts="00:10:10"),
    ]
    clusters = cluster_recos(recos)
    assert len(clusters) == 1
    ids = {m["id"] for m in clusters[0].members}
    assert ids == {"ubm-1", "ubm-2", "ubm-3"}


def test_cluster_groups_halfman_half_men_half_man():
    recos = [
        _r("ubm-1", "Halfman",  ts="00:15:00"),
        _r("ubm-2", "Half Men", ts="00:15:10"),
        _r("ubm-3", "Half Man", ts="00:15:20"),
    ]
    clusters = cluster_recos(recos)
    assert len(clusters) == 1
    assert len(clusters[0].members) == 3


def test_cluster_isolates_distinct_titles():
    recos = [
        _r("ubm-1", "Mortel"),
        _r("ubm-2", "Inception"),
        _r("ubm-3", "Dune"),
    ]
    clusters = cluster_recos(recos)
    assert clusters == []


def test_cluster_rejects_close_timecode_with_low_title_similarity():
    """Δt = 0 mais titres trop différents → pas de match."""
    recos = [
        _r("ubm-1", "Inception",       ts="00:10:00"),
        _r("ubm-2", "Stranger Things", ts="00:10:00"),
    ]
    clusters = cluster_recos(recos)
    assert clusters == []


def test_cluster_excludes_discarded_status():
    recos = [
        _r("ubm-1", "Mortel", ts="00:10:00"),
        _r("ubm-2", "Mortal", ts="00:10:05", status="discarded"),
    ]
    clusters = cluster_recos(recos)
    assert clusters == []  # le 2ᵉ est ignoré → plus de doublon


def test_cluster_separates_reco_from_citation():
    recos = [
        _r("ubm-1", "Mortel", kind="reco"),
        _r("ubm-2", "Mortel", kind="citation"),
    ]
    clusters = cluster_recos(recos)
    assert clusters == []


def test_cluster_separates_by_episode_guid():
    recos = [
        _r("ubm-1", "Mortel", guid="ep-1"),
        _r("ubm-2", "Mortel", guid="ep-2"),
    ]
    clusters = cluster_recos(recos)
    assert clusters == []


def test_cluster_sets_canonical_id():
    recos = [
        _r("ubm-1", "Mortel", status="draft",     extractors=["claude"]),
        _r("ubm-2", "Mortel", status="validated", extractors=["claude"]),
    ]
    clusters = cluster_recos(recos)
    assert len(clusters) == 1
    # validated > draft → canonical = ubm-2
    assert clusters[0].canonical_id == "ubm-2"


def test_cluster_avg_timecode_delta_computed():
    recos = [
        _r("ubm-1", "Mortel", ts="00:10:00"),
        _r("ubm-2", "Mortel", ts="00:10:20"),
        _r("ubm-3", "Mortel", ts="00:10:40"),
    ]
    clusters = cluster_recos(recos)
    assert len(clusters) == 1
    # base = 600 ; deltas = 0, 20, 40 ; avg = 20
    assert clusters[0].avg_timecode_delta == 20


def test_cluster_similarity_score_is_min_of_pairs():
    recos = [
        _r("ubm-1", "Mortel",  ts="00:10:00"),
        _r("ubm-2", "Mortal",  ts="00:10:05"),  # très proche de Mortel
        _r("ubm-3", "Mortels", ts="00:10:10"),  # plus loin
    ]
    clusters = cluster_recos(recos)
    assert len(clusters) == 1
    assert 0.7 <= clusters[0].similarity <= 1.0


def test_cluster_respects_custom_similarity_threshold():
    """Si seuil = 0.99 → presque aucun match, même pour des titres proches."""
    recos = [
        _r("ubm-1", "Mortel"),
        _r("ubm-2", "Mortal"),  # similarité ~0.83, sous 0.99
    ]
    clusters = cluster_recos(recos, similarity_threshold=0.99)
    assert clusters == []


def test_cluster_respects_custom_time_window():
    """Une fenêtre 0 → exige une similarité haute (>= 0.80) pour fusionner."""
    recos = [
        _r("ubm-1", "Halfman", ts="00:10:00"),
        _r("ubm-2", "Halfmen", ts="00:11:00"),  # 60s, sim ~0.85
    ]
    clusters = cluster_recos(recos, time_window_sec=0)
    # Similarité haute → match indépendamment de la fenêtre.
    assert len(clusters) == 1


def test_cluster_empty_recos():
    assert cluster_recos([]) == []


def test_cluster_single_reco_no_cluster():
    assert cluster_recos([_r("ubm-1", "Mortel")]) == []


# ===== pick_canonical =======================================================
def test_pick_canonical_prefers_validated():
    members = [
        _r("a", "X", status="draft"),
        _r("b", "X", status="validated"),
        _r("c", "X", status="draft"),
    ]
    assert pick_canonical(members) == "b"


def test_pick_canonical_prefers_youtube_source():
    members = [
        _r("a", "X", transcript_source="acast"),
        _r("b", "X", transcript_source="youtube"),
    ]
    assert pick_canonical(members) == "b"


def test_pick_canonical_prefers_more_extractors():
    members = [
        _r("a", "X", extractors=["claude"]),
        _r("b", "X", extractors=["claude", "gpt"]),
        _r("c", "X", extractors=["claude", "gpt", "haiku"]),
    ]
    assert pick_canonical(members) == "c"


def test_pick_canonical_prefers_longer_quote():
    members = [
        _r("a", "X", quote="court"),
        _r("b", "X", quote="quote beaucoup plus longue avec des détails"),
    ]
    assert pick_canonical(members) == "b"


def test_pick_canonical_deterministic_on_tie():
    """Égalité totale → tri lexicographique des id ASC."""
    members = [_r("zz", "X"), _r("aa", "X"), _r("bb", "X")]
    assert pick_canonical(members) == "aa"


def test_pick_canonical_priority_order():
    """validated > youtube > extractors > quote (vérif. ordre strict)."""
    members = [
        # Pas validated mais YT + 5 extracteurs + grosse quote.
        _r("loser", "X", transcript_source="youtube",
           extractors=list("abcde"), quote="x" * 1000),
        # Validated mais rien d'autre.
        _r("winner", "X", status="validated"),
    ]
    assert pick_canonical(members) == "winner"


# ===== merge_cluster ========================================================
@pytest.fixture
def patched_recos_dir(tmp_path, monkeypatch):
    """Reroute common.RECOS_DIR + BACKUP_DIR vers tmp_path."""
    import common
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    # On laisse BACKUP_DIR fixe et on passe backup_root explicite aux APIs.
    return tmp_path


def _write_recos(source_id: str, recos: list[dict], tmp_path: Path) -> dict[str, Path]:
    d = tmp_path / "recos" / source_id
    d.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for r in recos:
        p = d / f"{r['id']}.json"
        p.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
        paths[r["id"]] = p
    return paths


def test_merge_cluster_unions_extraction_history(patched_recos_dir):
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "Mortel", extractors=["claude"])
    r1["extractionHistory"] = [{
        "at": "2026-01-01T00:00:00+00:00",
        "transcriptModel": "(assumed)", "transcriptSource": "acast",
        "llmProvider": "anthropic", "llmModel": "haiku",
        "worker": "main-cpu", "timestamp_at_extraction": "00:10:00",
    }]
    r2 = _r("ubm-2", "Mortal", extractors=["gpt"])
    r2["extractionHistory"] = [{
        "at": "2026-02-01T00:00:00+00:00",
        "transcriptModel": "(assumed)", "transcriptSource": "youtube",
        "llmProvider": "openai", "llmModel": "gpt-4o",
        "worker": "gpu", "timestamp_at_extraction": "00:10:05",
    }]
    _write_recos("src", [r1, r2], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merged = merge_cluster(cluster, keep_id="ubm-1", source_id="src",
                           backup=False)
    assert len(merged["extractionHistory"]) == 2
    # extractors dérivés.
    assert set(merged["extractors"]) == {"anthropic", "openai"}
    # YT dans l'historique → top-level transcriptSource = youtube.
    assert merged["transcriptSource"] == "youtube"


def test_merge_cluster_unions_custom_links_dedup_by_url(patched_recos_dir):
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X")
    r1["customLinks"] = [
        {"label": "FNAC", "url": "https://fnac.com/x"},
        {"label": "Site", "url": "https://x.com"},
    ]
    r2 = _r("ubm-2", "X")
    r2["customLinks"] = [
        {"label": "Cultura", "url": "https://cultura.com/x"},
        {"label": "Site doublon", "url": "https://x.com"},  # url duplicate
    ]
    _write_recos("src", [r1, r2], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merged = merge_cluster(cluster, keep_id="ubm-1", source_id="src",
                           backup=False)
    urls = [l["url"] for l in merged["customLinks"]]
    assert urls == [
        "https://fnac.com/x", "https://x.com", "https://cultura.com/x",
    ]


def test_merge_cluster_merges_external_ids_kept_wins_on_conflict(patched_recos_dir):
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X")
    r1["externalIds"] = {"tmdb": "kept", "imdb": "imdb-1"}
    r2 = _r("ubm-2", "X")
    r2["externalIds"] = {"tmdb": "loser", "isbn": "isbn-2"}
    _write_recos("src", [r1, r2], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merged = merge_cluster(cluster, keep_id="ubm-1", source_id="src",
                           backup=False)
    assert merged["externalIds"]["tmdb"] == "kept"     # kept wins on conflict
    assert merged["externalIds"]["imdb"] == "imdb-1"
    assert merged["externalIds"]["isbn"] == "isbn-2"   # nouveau depuis perdant


def test_merge_cluster_unions_watch_providers(patched_recos_dir):
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X")
    r1["watchProviders"] = [{"label": "Netflix", "url": "https://netflix.com/x"}]
    r2 = _r("ubm-2", "X")
    r2["watchProviders"] = [
        {"label": "Canal", "url": "https://canal.tv/x"},
        {"label": "Doublon", "url": "https://netflix.com/x"},  # url duplicate
    ]
    _write_recos("src", [r1, r2], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merged = merge_cluster(cluster, keep_id="ubm-1", source_id="src",
                           backup=False)
    urls = [w["url"] for w in merged["watchProviders"]]
    assert urls == ["https://netflix.com/x", "https://canal.tv/x"]


def test_merge_cluster_keeps_longest_quote(patched_recos_dir):
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X", quote="court")
    r2 = _r("ubm-2", "X", quote="une quote beaucoup plus longue")
    r3 = _r("ubm-3", "X", quote="moyen")
    _write_recos("src", [r1, r2, r3], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2, r3])
    merged = merge_cluster(cluster, keep_id="ubm-1", source_id="src",
                           backup=False)
    assert merged["quote"] == "une quote beaucoup plus longue"


def test_merge_cluster_aliases_preserves_deleted_titles(patched_recos_dir):
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "Hannes")
    r2 = _r("ubm-2", "Annes")
    r3 = _r("ubm-3", "Anness")
    _write_recos("src", [r1, r2, r3], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2, r3])
    merged = merge_cluster(cluster, keep_id="ubm-1", source_id="src",
                           backup=False)
    assert "Annes" in merged["aliases"]
    assert "Anness" in merged["aliases"]
    assert "Hannes" not in merged["aliases"]  # le titre kept n'est pas un alias


def test_merge_cluster_aliases_dedup_against_existing(patched_recos_dir):
    """Si un alias est égal au titre kept (modulo normalisation) → ignoré."""
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "Mortel")
    r2 = _r("ubm-2", "mortel")  # même titre normalisé
    _write_recos("src", [r1, r2], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merged = merge_cluster(cluster, keep_id="ubm-1", source_id="src",
                           backup=False)
    assert merged.get("aliases", []) == []


def test_merge_cluster_kept_status_kind_unchanged(patched_recos_dir):
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X", status="validated", kind="reco",
            creator="A", year=2024, recommendedBy="Kyan")
    r2 = _r("ubm-2", "X", status="draft", creator="OtherCreator",
            year=2025, recommendedBy="Navo")
    _write_recos("src", [r1, r2], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merged = merge_cluster(cluster, keep_id="ubm-1", source_id="src",
                           backup=False)
    assert merged["status"] == "validated"
    assert merged["kind"] == "reco"
    assert merged["creator"] == "A"
    assert merged["year"] == 2024
    assert merged["recommendedBy"] == "Kyan"


def test_merge_cluster_creates_backup_before_delete(patched_recos_dir):
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X")
    r2 = _r("ubm-2", "X")
    paths = _write_recos("src", [r1, r2], tmp)
    backup_root = tmp / "backup"
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merge_cluster(cluster, keep_id="ubm-1", source_id="src",
                  backup=True, backup_root=backup_root)
    # ubm-2 supprimé du dossier des recos
    assert not paths["ubm-2"].exists()
    # ubm-1 conservé
    assert paths["ubm-1"].exists()
    # Un backup existe dans <ts>/src/ubm-2.json
    found = list(backup_root.rglob("ubm-2.json"))
    assert len(found) == 1


def test_merge_cluster_idempotent_on_second_call(patched_recos_dir):
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X")
    r2 = _r("ubm-2", "X")
    _write_recos("src", [r1, r2], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merge_cluster(cluster, keep_id="ubm-1", source_id="src", backup=False)
    # Deuxième appel : ubm-2 n'existe plus → ne plante pas.
    merge_cluster(cluster, keep_id="ubm-1", source_id="src", backup=False)


def test_merge_cluster_keep_id_not_in_members_raises(patched_recos_dir):
    # #13 — Cluster.__post_init__ exige >=2 members + canonical_id présent.
    # On contourne via une instance valide (2 membres), puis appelle merge
    # avec un keep_id absent (le ValueError vient maintenant de merge_cluster).
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X")
    r2 = _r("ubm-2", "X")
    _write_recos("src", [r1, r2], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    with pytest.raises(ValueError):
        merge_cluster(cluster, keep_id="ubm-zzz", source_id="src",
                      backup=False)


def test_merge_cluster_keep_path_missing_raises(patched_recos_dir):
    """keep_id présent dans members mais fichier introuvable → erreur."""
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X")
    r2 = _r("ubm-2", "X")
    # On n'écrit que r2 sur disque ; r1 absent.
    _write_recos("src", [r2], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    with pytest.raises(FileNotFoundError):
        merge_cluster(cluster, keep_id="ubm-1", source_id="src", backup=False)


# ===== restore_last_backup ===================================================
def test_restore_last_backup_recreates_deleted_files(patched_recos_dir):
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X")
    r2 = _r("ubm-2", "X")
    paths = _write_recos("src", [r1, r2], tmp)
    backup_root = tmp / "backup"
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merge_cluster(cluster, keep_id="ubm-1", source_id="src",
                  backup=True, backup_root=backup_root)
    assert not paths["ubm-2"].exists()
    result = restore_last_backup("src", backup_root=backup_root)
    # 2 fichiers restaurés : le kept (état pré-merge) + le loser supprimé.
    assert result["n_restored"] == 2
    assert paths["ubm-2"].exists()
    assert paths["ubm-1"].exists()


def test_restore_last_backup_no_backup_returns_zero(patched_recos_dir):
    tmp = patched_recos_dir
    backup_root = tmp / "backup-vide"
    result = restore_last_backup("src", backup_root=backup_root)
    assert result["n_restored"] == 0
    assert result["timestamp_restored"] is None


def test_restore_last_backup_no_matching_source(patched_recos_dir):
    """Le dossier de backup existe mais pas pour `source_id` demandé."""
    tmp = patched_recos_dir
    backup_root = tmp / "backup"
    d = backup_root / "2026-01-01T00-00-00+00-00_aaaaaaaa"
    (d / "autre-src").mkdir(parents=True)
    (d / "manifest.json").write_text(
        json.dumps({"source_id": "autre-src", "merge_id": "x"}), encoding="utf-8",
    )
    result = restore_last_backup("src", backup_root=backup_root)
    assert result["n_restored"] == 0


def test_restore_last_backup_dir_without_manifest_skipped(patched_recos_dir):
    """Dossier sans manifest.json → skip (vieux backup pré-fix Bug B)."""
    tmp = patched_recos_dir
    backup_root = tmp / "backup"
    d = backup_root / "2026-01-01T00-00-00+00-00"
    (d / "src").mkdir(parents=True)
    result = restore_last_backup("src", backup_root=backup_root)
    assert result["n_restored"] == 0


def test_restore_last_backup_corrupt_manifest_skipped(patched_recos_dir):
    """Manifest JSON cassé → skip silencieux du backup, retourne zero."""
    tmp = patched_recos_dir
    backup_root = tmp / "backup"
    d = backup_root / "2026-01-01T00-00-00+00-00_aaaaaaaa"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text("{not json", encoding="utf-8")
    result = restore_last_backup("src", backup_root=backup_root)
    assert result["n_restored"] == 0


def test_restore_last_backup_manifest_without_src_dir(patched_recos_dir):
    """Manifest valide mais dossier source disparu (bizarre) → skip."""
    tmp = patched_recos_dir
    backup_root = tmp / "backup"
    d = backup_root / "2026-01-01T00-00-00+00-00_aaaaaaaa"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(
        json.dumps({"source_id": "src", "merge_id": "x"}), encoding="utf-8",
    )
    # Pas de sous-dossier `src/`
    result = restore_last_backup("src", backup_root=backup_root)
    assert result["n_restored"] == 0


def test_restore_normalizes_old_format_backup(patched_recos_dir):
    """Backup historique avec `ubm-1325.json` → restoré comme `1325.json`."""
    tmp = patched_recos_dir
    backup_root = tmp / "backup"
    d = backup_root / "2026-06-06T08-26-45+00-00_old00001"
    src_dir = d / "un-bon-moment"
    src_dir.mkdir(parents=True)
    payload = {"id": "ubm-1325", "title": "X", "episodeGuid": "g"}
    (src_dir / "ubm-1325.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )
    (d / "manifest.json").write_text(
        json.dumps({"source_id": "un-bon-moment", "merge_id": "old0001"}),
        encoding="utf-8",
    )
    result = restore_last_backup("un-bon-moment", backup_root=backup_root)
    assert result["n_restored"] == 1
    assert result.get("n_failed", 0) == 0
    dst = tmp / "recos" / "un-bon-moment"
    assert (dst / "1325.json").exists()
    # NE doit PAS recréer le nom legacy → pas de doublon disque.
    assert not (dst / "ubm-1325.json").exists()


def test_restore_keeps_new_format_backup(patched_recos_dir):
    """Backup récent `0569.json` → restoré identique (identité)."""
    tmp = patched_recos_dir
    backup_root = tmp / "backup"
    d = backup_root / "2026-06-06T21-30-00+00-00_new00001"
    src_dir = d / "un-bon-moment"
    src_dir.mkdir(parents=True)
    payload = {"id": "ubm-0569", "title": "Y", "episodeGuid": "g"}
    (src_dir / "0569.json").write_text(
        json.dumps(payload), encoding="utf-8",
    )
    (d / "manifest.json").write_text(
        json.dumps({"source_id": "un-bon-moment", "merge_id": "new0001"}),
        encoding="utf-8",
    )
    result = restore_last_backup("un-bon-moment", backup_root=backup_root)
    assert result["n_restored"] == 1
    dst = tmp / "recos" / "un-bon-moment"
    assert (dst / "0569.json").exists()


def test_normalize_backup_filename_helper():
    from reco_dedup_merge import _normalize_backup_filename
    # Migration : prefix + tiret + chiffres + .json → strip prefix.
    assert _normalize_backup_filename("ubm-1325.json", "un-bon-moment") == "1325.json"
    assert _normalize_backup_filename("ubm-0569.json", "un-bon-moment") == "0569.json"
    # Identité : déjà au nouveau format.
    assert _normalize_backup_filename("1325.json", "un-bon-moment") == "1325.json"
    # Identité : nom non-conforme (pas de chiffre derrière le tiret).
    assert _normalize_backup_filename("ubm-foo.json", "un-bon-moment") == "ubm-foo.json"
    # Source différente : pas de strip.
    assert _normalize_backup_filename("ubm-1325.json", "autre-src") == "ubm-1325.json"


# ===== Utilitaires internes =================================================
def test_union_list_of_dicts_by_key_skips_missing_key():
    """Un item sans la clé est sauté (None → skip)."""
    a = [{"url": "u1"}, {"label": "no-url"}]
    b = [{"url": "u2"}, {"url": "u1"}]
    out = _union_list_of_dicts_by_key(a, b, "url")
    assert out == [{"url": "u1"}, {"label": "no-url"}, {"url": "u2"}] or out == \
           [{"url": "u1"}, {"url": "u2"}]
    # Au minimum : u1 et u2 présents, u1 pas dupliqué.
    urls = [x.get("url") for x in out if "url" in x]
    assert urls == ["u1", "u2"]


def test_path_for_reco_returns_none_when_dir_missing(tmp_path, monkeypatch):
    import common
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "nope")
    assert rd._path_for_reco("zzz", "ubm-1") is None


def test_merge_cluster_loser_linkOverrides_filled_into_kept(patched_recos_dir):
    """Un loser apporte un linkOverride absent du kept → ajouté."""
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X")  # pas d'overrides
    r2 = _r("ubm-2", "X")
    r2["linkOverrides"] = {"JustWatch": "https://jw.com/x"}
    _write_recos("src", [r1, r2], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merged = merge_cluster(cluster, keep_id="ubm-1", source_id="src", backup=False)
    assert merged["linkOverrides"]["JustWatch"] == "https://jw.com/x"


def test_merge_cluster_skips_empty_title_alias(patched_recos_dir):
    """Un member avec un titre vide → pas d'alias vide créé."""
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "Hannes")
    r2 = _r("ubm-2", "")  # titre vide
    _write_recos("src", [r1, r2], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merged = merge_cluster(cluster, keep_id="ubm-1", source_id="src", backup=False)
    # Aucun alias vide ajouté.
    assert "" not in (merged.get("aliases") or [])


def test_path_for_reco_skips_corrupt_json(tmp_path, monkeypatch):
    import common
    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "recos")
    d = tmp_path / "recos" / "src"
    d.mkdir(parents=True)
    (d / "broken.json").write_text("{not json", encoding="utf-8")
    (d / "good.json").write_text(json.dumps({"id": "ubm-1"}), encoding="utf-8")
    assert rd._path_for_reco("src", "ubm-1").name == "good.json"
    assert rd._path_for_reco("src", "missing") is None


# ===== Bug A fix : backup du kept pré-merge =================================
def test_merge_cluster_backups_kept_pre_merge(patched_recos_dir):
    """Le kept doit aussi être backupé AVANT mutation."""
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "Hannes")
    r1["aliases"] = ["X"]
    r1["extractionHistory"] = [{
        "at": "2026-01-01T00:00:00+00:00",
        "transcriptModel": "(assumed)", "transcriptSource": "acast",
        "llmProvider": "anthropic", "llmModel": "haiku",
        "worker": "main-cpu", "timestamp_at_extraction": "00:10:00",
    }]
    r2 = _r("ubm-2", "Annes")
    _write_recos("src", [r1, r2], tmp)
    backup_root = tmp / "backup"
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merge_cluster(cluster, keep_id="ubm-1", source_id="src",
                  backup=True, backup_root=backup_root)
    backup_dirs = [d for d in backup_root.iterdir() if d.is_dir()]
    assert len(backup_dirs) == 1
    backed_up_kept = backup_dirs[0] / "src" / "ubm-1.json"
    assert backed_up_kept.exists()
    pre_merge_kept = json.loads(backed_up_kept.read_text(encoding="utf-8"))
    assert pre_merge_kept.get("aliases") == ["X"]
    assert len(pre_merge_kept.get("extractionHistory", [])) == 1


def test_merge_then_undo_restores_kept_original_state(patched_recos_dir):
    """Roundtrip : merge → undo → kept retrouve son état initial."""
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "Hannes")
    r1["aliases"] = ["X"]
    r1["extractionHistory"] = [{
        "at": "2026-01-01T00:00:00+00:00",
        "transcriptModel": "(assumed)", "transcriptSource": "acast",
        "llmProvider": "anthropic", "llmModel": "haiku",
        "worker": "main-cpu", "timestamp_at_extraction": "00:10:00",
    }]
    r2 = _r("ubm-2", "Y")
    paths = _write_recos("src", [r1, r2], tmp)
    backup_root = tmp / "backup"
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merge_cluster(cluster, keep_id="ubm-1", source_id="src",
                  backup=True, backup_root=backup_root)
    # Après merge : kept a aliases=["X", "Y"], history avec 2 entrées (ou plus).
    after_merge = json.loads(paths["ubm-1"].read_text(encoding="utf-8"))
    assert "Y" in after_merge.get("aliases", [])
    # Undo
    restore_last_backup("src", backup_root=backup_root)
    # Kept revenu à son état initial
    restored = json.loads(paths["ubm-1"].read_text(encoding="utf-8"))
    assert restored.get("aliases") == ["X"]
    assert len(restored.get("extractionHistory", [])) == 1


# ===== Bug B fix : manifest.json par merge ==================================
def test_two_merges_each_creates_own_manifest(patched_recos_dir):
    """Chaque merge crée son propre dossier daté + manifest.json."""
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "Hannes")
    r2 = _r("ubm-2", "Annes")
    r3 = _r("ubm-3", "Anness")
    _write_recos("src", [r1, r2, r3], tmp)
    backup_root = tmp / "backup"
    c1 = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merge_cluster(c1, keep_id="ubm-1", source_id="src",
                  backup=True, backup_root=backup_root)
    # Recharge l'état du kept post-merge1
    kept_after_1 = json.loads((tmp / "recos" / "src" / "ubm-1.json").read_text(encoding="utf-8"))
    c2 = Cluster(canonical_id="ubm-1", members=[kept_after_1, r3])
    merge_cluster(c2, keep_id="ubm-1", source_id="src",
                  backup=True, backup_root=backup_root)
    backup_dirs = sorted([d for d in backup_root.iterdir() if d.is_dir()])
    assert len(backup_dirs) == 2
    for d in backup_dirs:
        manifest_path = d / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "merge_id" in manifest
        assert "source_id" in manifest
        assert manifest["source_id"] == "src"
        assert "keep_id" in manifest
        assert "loser_ids" in manifest
        assert "at" in manifest


def test_undo_restores_only_last_merge(patched_recos_dir):
    """Undo en cascade : 2 merges → undo → seul le 2ᵉ est défait."""
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "Hannes")
    r2 = _r("ubm-2", "Annes")
    r3 = _r("ubm-3", "Anness")
    paths = _write_recos("src", [r1, r2, r3], tmp)
    backup_root = tmp / "backup"
    c1 = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merge_cluster(c1, keep_id="ubm-1", source_id="src",
                  backup=True, backup_root=backup_root)
    kept_after_1 = json.loads(paths["ubm-1"].read_text(encoding="utf-8"))
    # Après merge 1 : aliases doit contenir "Annes" (from r2).
    assert "Annes" in kept_after_1.get("aliases", [])
    c2 = Cluster(canonical_id="ubm-1", members=[kept_after_1, r3])
    merge_cluster(c2, keep_id="ubm-1", source_id="src",
                  backup=True, backup_root=backup_root)
    kept_after_2 = json.loads(paths["ubm-1"].read_text(encoding="utf-8"))
    assert "Anness" in kept_after_2.get("aliases", [])
    # 1er undo : défait merge 2
    restore_last_backup("src", backup_root=backup_root)
    # ubm-3 doit revenir, ubm-2 doit rester supprimé
    assert paths["ubm-3"].exists()
    assert not paths["ubm-2"].exists()
    a_after_undo = json.loads(paths["ubm-1"].read_text(encoding="utf-8"))
    # Doit avoir aliases post-merge1 (avec "Annes" venant de r2 mais pas "Anness")
    assert "Annes" in a_after_undo.get("aliases", [])
    assert "Anness" not in a_after_undo.get("aliases", [])


def test_undo_after_restore_cascade(patched_recos_dir):
    """2 merges, 2 undos → état initial."""
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "Hannes")
    r2 = _r("ubm-2", "Annes")
    r3 = _r("ubm-3", "Anness")
    paths = _write_recos("src", [r1, r2, r3], tmp)
    backup_root = tmp / "backup"
    c1 = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merge_cluster(c1, keep_id="ubm-1", source_id="src",
                  backup=True, backup_root=backup_root)
    kept_after_1 = json.loads(paths["ubm-1"].read_text(encoding="utf-8"))
    c2 = Cluster(canonical_id="ubm-1", members=[kept_after_1, r3])
    merge_cluster(c2, keep_id="ubm-1", source_id="src",
                  backup=True, backup_root=backup_root)
    # 2 undos
    restore_last_backup("src", backup_root=backup_root)
    restore_last_backup("src", backup_root=backup_root)
    # Tous les fichiers initiaux présents
    assert paths["ubm-1"].exists()
    assert paths["ubm-2"].exists()
    assert paths["ubm-3"].exists()
    # Kept revenu à son état initial (pas d'aliases)
    restored = json.loads(paths["ubm-1"].read_text(encoding="utf-8"))
    assert not restored.get("aliases")


# ===== Helpers purs de fusion (#18 — extractions de _merge_cluster_locked) ===
from reco_dedup import (
    _apply_merged_fields,
    _collect_aliases,
    _collect_losers_to_delete,
    _longest_quote,
    _merge_custom_links,
    _merge_external_ids,
    _merge_link_overrides,
    _merge_watch_providers,
)


def test_merge_custom_links_pure_dedup_by_url():
    kept = {"id": "k", "customLinks": [{"url": "a"}]}
    losers = [{"id": "l", "customLinks": [{"url": "b"}, {"url": "a"}]}]
    out = _merge_custom_links(kept, [kept] + losers, keep_id="k")
    assert [x["url"] for x in out] == ["a", "b"]


def test_merge_custom_links_empty_kept():
    kept = {"id": "k"}
    losers = [{"id": "l", "customLinks": [{"url": "z"}]}]
    out = _merge_custom_links(kept, [kept] + losers, keep_id="k")
    assert out == [{"url": "z"}]


def test_merge_watch_providers_pure_dedup_by_url():
    kept = {"id": "k", "watchProviders": [{"url": "netflix"}]}
    losers = [{"id": "l", "watchProviders": [{"url": "canal"}, {"url": "netflix"}]}]
    out = _merge_watch_providers(kept, [kept] + losers, keep_id="k")
    assert [x["url"] for x in out] == ["netflix", "canal"]


def test_merge_link_overrides_kept_wins_on_conflict():
    kept = {"id": "k", "linkOverrides": {"jw": "k-url"}}
    losers = [{"id": "l", "linkOverrides": {"jw": "l-url", "imdb": "imdb-l"}}]
    out = _merge_link_overrides(kept, [kept] + losers, keep_id="k")
    assert out == {"jw": "k-url", "imdb": "imdb-l"}


def test_merge_link_overrides_empty_kept():
    kept = {"id": "k"}
    losers = [{"id": "l", "linkOverrides": {"x": "y"}}]
    out = _merge_link_overrides(kept, [kept] + losers, keep_id="k")
    assert out == {"x": "y"}


def test_merge_external_ids_kept_wins_on_conflict():
    kept = {"id": "k", "externalIds": {"tmdb": "kept"}}
    losers = [{"id": "l", "externalIds": {"tmdb": "loser", "isbn": "isbn-l"}}]
    out = _merge_external_ids(kept, [kept] + losers, keep_id="k")
    assert out == {"tmdb": "kept", "isbn": "isbn-l"}


def test_longest_quote_picks_longest_across_members():
    kept = {"id": "k", "quote": "court"}
    losers = [
        {"id": "l1", "quote": "moyen plus moyen"},
        {"id": "l2", "quote": "quote vraiment très longue avec des détails"},
    ]
    assert _longest_quote(kept, losers) == "quote vraiment très longue avec des détails"


def test_longest_quote_returns_kept_if_no_loser():
    kept = {"id": "k", "quote": "seule"}
    assert _longest_quote(kept, []) == "seule"


def test_longest_quote_empty_kept_no_members():
    assert _longest_quote({"id": "k"}, []) == ""


def test_collect_aliases_propagates_loser_title_and_aliases():
    kept = {"id": "k", "title": "Hannes", "aliases": []}
    losers = [
        {"id": "l1", "title": "Annes", "aliases": ["Anness"]},
        {"id": "l2", "title": "Yannes"},
    ]
    out = _collect_aliases(kept, [kept] + losers, keep_id="k")
    assert "Annes" in out
    assert "Anness" in out
    assert "Yannes" in out
    assert "Hannes" not in out  # le titre du kept n'est jamais alias de lui-même


def test_collect_aliases_dedups_against_normalized_kept_title():
    """Un alias normalisé identique au titre du kept est ignoré."""
    kept = {"id": "k", "title": "Mortel"}
    losers = [{"id": "l", "title": "mortel"}]
    out = _collect_aliases(kept, [kept] + losers, keep_id="k")
    assert out == []


def test_collect_aliases_skips_empty_strings():
    kept = {"id": "k", "title": "X"}
    losers = [{"id": "l", "title": "", "aliases": ["", "  "]}]
    out = _collect_aliases(kept, [kept] + losers, keep_id="k")
    assert out == []


def test_collect_losers_to_delete_filters_keep_id_and_missing(tmp_path):
    p_a = tmp_path / "a.json"
    p_a.write_text("{}", encoding="utf-8")
    p_b = tmp_path / "b.json"
    p_b.write_text("{}", encoding="utf-8")
    members = [{"id": "k"}, {"id": "a"}, {"id": "b"}, {"id": "ghost"}]
    paths = {"k": tmp_path / "k.json", "a": p_a, "b": p_b}  # ghost absent du dict
    paths["k"].write_text("{}", encoding="utf-8")
    out = _collect_losers_to_delete(members, "k", paths)
    ids = [rid for rid, _ in out]
    assert ids == ["a", "b"]  # k filtré (keep_id), ghost filtré (path absent)


def test_collect_losers_to_delete_skips_already_deleted(tmp_path):
    p_a = tmp_path / "a.json"
    p_a.write_text("{}", encoding="utf-8")
    members = [{"id": "a"}, {"id": "b"}]
    paths = {"a": p_a, "b": tmp_path / "b-missing.json"}
    out = _collect_losers_to_delete(members, "k", paths)
    assert [rid for rid, _ in out] == ["a"]  # b n'existe pas


def test_apply_merged_fields_orchestrates_helpers():
    """Smoke test : tous les champs sont mutés correctement."""
    kept = {
        "id": "k", "title": "Hannes",
        "customLinks": [{"url": "a"}],
        "externalIds": {"tmdb": "kept"},
        "quote": "court",
    }
    losers = [
        {
            "id": "l1", "title": "Annes",
            "customLinks": [{"url": "b"}],
            "externalIds": {"tmdb": "loser", "imdb": "imdb-1"},
            "linkOverrides": {"jw": "jw-1"},
            "watchProviders": [{"url": "netflix"}],
            "quote": "vraiment très très longue quote détaillée",
        },
    ]
    _apply_merged_fields(kept, [kept] + losers, keep_id="k")
    assert [x["url"] for x in kept["customLinks"]] == ["a", "b"]
    assert kept["externalIds"]["tmdb"] == "kept"  # kept wins
    assert kept["externalIds"]["imdb"] == "imdb-1"
    assert kept["linkOverrides"] == {"jw": "jw-1"}
    assert kept["watchProviders"] == [{"url": "netflix"}]
    assert kept["quote"] == "vraiment très très longue quote détaillée"
    assert "Annes" in kept["aliases"]


# ===== Tests phase 4 — nouveaux tests #I, #J/K, #3, #37, #18, #25 ============

def test_apply_merged_fields_preserves_kept_field_when_losers_have_nothing():
    """#I — Invariant : ne jamais diminuer un champ du kept.

    Si tous les losers ont une liste vide pour customLinks, le kept doit
    conserver le sien intact.
    """
    kept = {"id": "K", "customLinks": [{"url": "X"}]}
    members = [kept, {"id": "L", "customLinks": []}]
    _apply_merged_fields(kept, members, "K")
    assert kept["customLinks"] == [{"url": "X"}]


def test_merge_cluster_link_overrides_kept_wins_on_conflict(patched_recos_dir):
    """#3 review — intégration : si kept ET loser ont linkOverrides[k]
    différents, kept gagne (sémantique du _merge_link_overrides)."""
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X", linkOverrides={"jw": "kept-url"})
    r2 = _r("ubm-2", "X", linkOverrides={"jw": "loser-url", "imdb": "imdb-l"})
    _write_recos("src", [r1, r2], tmp)
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merge_cluster(cluster, keep_id="ubm-1", source_id="src", backup=False)
    kept = json.loads(
        (tmp / "recos" / "src" / "ubm-1.json").read_text(encoding="utf-8"),
    )
    assert kept["linkOverrides"]["jw"] == "kept-url"
    assert kept["linkOverrides"]["imdb"] == "imdb-l"


def test_merge_cluster_uses_fresh_loser_state_from_disk(patched_recos_dir):
    """#37 review — édit sur disque entre détection cluster et merge :
    la fusion DOIT utiliser l'état disque (fresh), pas la version mémoire."""
    tmp = patched_recos_dir
    r1 = _r("ubm-1", "X")
    r2 = _r("ubm-2", "X")
    _write_recos("src", [r1, r2], tmp)
    # On modifie le disque (simulant un edit fait après la détection).
    r2_path = tmp / "recos" / "src" / "ubm-2.json"
    fresh = json.loads(r2_path.read_text(encoding="utf-8"))
    fresh["customLinks"] = [{"url": "added-after-detect.example"}]
    r2_path.write_text(json.dumps(fresh), encoding="utf-8")
    # Le cluster.members reflète encore l'état mémoire AVANT l'édit.
    cluster = Cluster(canonical_id="ubm-1", members=[r1, r2])
    merge_cluster(cluster, keep_id="ubm-1", source_id="src", backup=False)
    kept = json.loads(
        (tmp / "recos" / "src" / "ubm-1.json").read_text(encoding="utf-8"),
    )
    # La fusion doit avoir intégré le customLink ajouté entre temps.
    urls = [c.get("url") for c in (kept.get("customLinks") or [])]
    assert "added-after-detect.example" in urls


def test_collect_aliases_dedups_across_multiple_losers():
    """#18 review — dedup global : un même titre apparaissant chez
    plusieurs losers ne génère qu'un alias."""
    kept = {"id": "K", "title": "Anness"}
    members = [
        kept,
        {"id": "L1", "title": "Annes"},
        {"id": "L2", "title": "Annes"},  # même titre que L1
        {"id": "L3", "title": "Hannes"},
    ]
    aliases = _collect_aliases(kept, members, "K")
    # Pas de doublon "Annes".
    assert aliases.count("Annes") == 1
    # Tous les titres distincts sont présents.
    assert "Annes" in aliases
    assert "Hannes" in aliases


def test_atomic_write_json_cleans_tmp_on_disk_full(tmp_path, monkeypatch):
    """#25 sécu — si os.replace lève (disk full / permission), le tmp est
    nettoyé pour ne pas laisser de fichier orphelin."""
    target = tmp_path / "out.json"

    def boom_replace(*a, **kw):
        raise OSError("disk full")

    import reco_dedup_merge
    monkeypatch.setattr(reco_dedup_merge.os, "replace", boom_replace)
    with pytest.raises(OSError):
        reco_dedup_merge._atomic_write_json(target, {"a": 1})
    tmp = target.with_suffix(target.suffix + ".tmp")
    assert not tmp.exists(), "le tmp doit être nettoyé même en cas d'échec"
