"""Télémétrie, PR2 : runs des orchestrateurs et mesures de la transcription.

Aucun téléchargement ni transcription réels : yt-dlp, requests et
faster-whisper sont remplacés par des doublures.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import types
from pathlib import Path

import pytest

import telemetry
import transcription_mesures as mesures

SOURCE = "demo-source"
GUID = "yt-abcdefghijk"


def _lignes(chemin, sql, params=()):
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _mesures(ligne):
    return {k: v["value"] for k, v in json.loads(ligne["measurements_json"]).items()}


@pytest.fixture
def depot(tmp_path, monkeypatch):
    """Corpus minimal : une source, un épisode YouTube de la saison 6."""
    import common
    import transcribe
    for nom, sous in (("SOURCES_DIR", "sources"), ("EPISODES_DIR", "episodes"),
                      ("RECOS_DIR", "recos"), ("OUTPUT_DIR", "output"),
                      ("TRANSCRIPTS_DIR", "output/transcripts"), ("AUDIO_DIR", "output/audio")):
        monkeypatch.setattr(common, nom, tmp_path / sous)
    monkeypatch.setattr(transcribe, "AUDIO_DIR", tmp_path / "output/audio")
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / f"{SOURCE}.json").write_text(
        json.dumps({"id": SOURCE, "title": "Démo", "hosts": ["A"]}), encoding="utf-8")
    episodes = tmp_path / "episodes" / SOURCE
    episodes.mkdir(parents=True)
    chemin = episodes / f"{GUID}.json"
    chemin.write_text(json.dumps({
        "sourceId": SOURCE, "guid": GUID, "title": "Invité S6-E07", "season": 6,
        "youtubeUrl": "https://www.youtube.com/watch?v=abcdefghijk",
        "transcriptStatus": "none"}), encoding="utf-8")
    return {"tmp": tmp_path, "episode": chemin}


@pytest.fixture
def doublures(monkeypatch):
    """yt-dlp écrit un faux mp3 ; faster-whisper rend deux segments."""
    etat = {"telechargements": 0, "panne": False, "duree": 120.5}

    class FakeYDL:
        def __init__(self, opts):
            self.modele = opts["outtmpl"]

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def download(self, urls):
            etat["telechargements"] += 1
            Path(self.modele.replace(".%(ext)s", ".mp3")).write_bytes(b"ID3" + b"\0" * 64)

    class FakeWhisper:
        def __init__(self, *a, **k):
            pass

        def transcribe(self, *a, **k):
            if etat["panne"]:
                raise RuntimeError("décodage impossible")
            seg = types.SimpleNamespace
            info = seg(language="fr", language_probability=0.98)
            if etat["duree"] is not None:
                info.duration, info.duration_after_vad = etat["duree"], 100.0
            return iter([seg(start=0.0, text=" Bonjour"), seg(start=4.0, text=" et merci")]), info

    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYDL))
    fw = types.ModuleType("faster_whisper")
    fw.WhisperModel = FakeWhisper
    monkeypatch.setitem(sys.modules, "faster_whisper", fw)
    return etat


# ===== transcribe.py =========================================================
def test_deux_passes_donnent_une_transcription_puis_un_cache_hit(metrics_db, depot, doublures):
    import transcribe
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t"):
        assert transcribe.transcribe_episode(SOURCE, depot["episode"], "large-v3-turbo",
                                             "fr", False) is True
        assert transcribe.transcribe_episode(SOURCE, depot["episode"], "large-v3-turbo",
                                             "fr", False) is False

    premiere, seconde = _lignes(metrics_db, "SELECT * FROM stage_attempts ORDER BY started_at")
    assert premiere["status"] == "succeeded" and premiere["telemetry_complete"] == 1
    assert premiere["season"] == 6 and premiere["provider"] == "local"
    assert premiere["model"] == "large-v3-turbo"
    assert premiere["media_origin"] == "youtube"
    assert premiere["media_identifier"] == "youtube:abcdefghijk"
    assert premiere["media_checksum"].startswith("sha256:")
    assert premiere["media_duration_ms"] == 120_500
    assert premiere["transcript_id_or_hash"].startswith("sha256:")
    m = _mesures(premiere)
    assert m["audio_cache_hit"] is False and m["download_bytes"] == 67
    assert m["speech_duration_ms"] == 100_000 and m["language_detected"] == "fr"
    for chrono in ("download_ms", "model_load_ms", "transcribe_ms", "gap_repair_ms"):
        assert isinstance(m[chrono], int)
    assert m["gap_candidates"] == 0 and m["gaps_unfilled"] == 0
    config = json.loads(premiere["config_json"])
    assert config["engine"] == "faster-whisper" and config["amorce"] is False
    assert seconde["status"] == "skipped" and seconde["skip_reason"] == "cache_hit"
    assert seconde["media_duration_ms"] is None and _mesures(seconde) == {}
    assert _lignes(metrics_db, "SELECT COUNT(*) AS n FROM llm_calls")[0]["n"] == 0
    assert doublures["telechargements"] == 1


def test_un_audio_deja_la_n_est_pas_un_telechargement(metrics_db, depot, doublures):
    import transcribe
    transcribe.transcribe_episode(SOURCE, depot["episode"], "small", "fr", False)
    transcribe.transcribe_episode(SOURCE, depot["episode"], "small", "fr", True)  # --force
    derniere = _lignes(metrics_db, "SELECT * FROM stage_attempts ORDER BY started_at")[-1]
    assert _mesures(derniere)["audio_cache_hit"] is True
    assert "download_ms" not in _mesures(derniere)
    assert doublures["telechargements"] == 1


def test_sans_duree_rendue_par_le_decodeur_la_duree_reste_nulle(metrics_db, depot, doublures):
    import transcribe
    doublures["duree"] = None
    transcribe.transcribe_episode(SOURCE, depot["episode"], "small", "fr", False)
    ligne = _lignes(metrics_db, "SELECT * FROM stage_attempts")[0]
    assert ligne["status"] == "succeeded"
    assert ligne["media_duration_ms"] is None and ligne["telemetry_complete"] == 0


def test_l_url_acast_n_est_gardee_qu_en_empreinte(metrics_db, depot, doublures, monkeypatch):
    import transcribe
    data = json.loads(depot["episode"].read_text(encoding="utf-8"))
    data.pop("youtubeUrl")
    data["audioUrl"] = "https://cdn.acast.test/ep.mp3?token=SECRET123"
    depot["episode"].write_text(json.dumps(data), encoding="utf-8")

    def http(url, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x" * 10)
        mesures.telechargement(dest, 0)
        return dest
    monkeypatch.setattr(transcribe, "_download_http", http)

    transcribe.transcribe_episode(SOURCE, depot["episode"], "small", "fr", False)
    ligne = _lignes(metrics_db, "SELECT * FROM stage_attempts")[0]
    assert ligne["media_origin"] == "acast"
    assert ligne["media_identifier"].startswith("acast:url-sha256:")
    texte = json.dumps(_lignes(metrics_db, "SELECT * FROM stage_attempts"))
    assert "SECRET123" not in texte and "cdn.acast.test" not in texte


def test_une_transcription_en_panne_est_un_echec_mesure(metrics_db, depot, doublures):
    import transcribe
    doublures["panne"] = True
    with pytest.raises(RuntimeError):
        transcribe.transcribe_episode(SOURCE, depot["episode"], "small", "fr", False)
    ligne = _lignes(metrics_db, "SELECT * FROM stage_attempts")[0]
    assert ligne["status"] == "failed" and ligne["error_category"] == "RuntimeError"
    assert ligne["media_origin"] == "youtube"  # le média était là, la mesure le garde


def test_la_cli_declare_son_intention(metrics_db, depot, doublures, monkeypatch):
    import transcribe
    monkeypatch.setattr(sys, "argv", ["transcribe.py", "--source", SOURCE, "--guid", GUID,
                                      "--intent", "source_migration"])
    transcribe.main()
    run = _lignes(metrics_db, "SELECT * FROM workflow_runs")[0]
    assert (run["trigger"], run["command"], run["intent"]) == (
        "cli", "transcribe", "source_migration")
    assert _lignes(metrics_db, "SELECT intent FROM stage_attempts")[0]["intent"] == \
        "source_migration"


def test_la_cli_sans_intention_reste_inconnue(metrics_db, depot, doublures, monkeypatch):
    import transcribe
    monkeypatch.setattr(sys, "argv", ["transcribe.py", "--source", SOURCE, "--all"])
    transcribe.main()
    assert _lignes(metrics_db, "SELECT intent FROM workflow_runs")[0]["intent"] == "unknown"


# ===== mesures ==============================================================
def test_la_saison_n_est_jamais_devinee():
    assert mesures.saison({"season": 6}) == 6
    assert mesures.saison({"season": "6"}) is None
    assert mesures.saison({"season": True}) is None
    assert mesures.saison({"title": "S6-E01"}) is None


def test_l_identifiant_du_media_selon_son_origine():
    assert mesures.identifiant_media({"youtubeUrl": "https://youtu.be/abcdefghijk"},
                                     "youtube") == "youtube:abcdefghijk"
    assert mesures.identifiant_media({"youtubeUrl": "https://example.test"}, "youtube") is None
    assert mesures.identifiant_media({}, "acast") is None


def test_les_mesures_tolerent_un_fichier_absent(tmp_path):
    etape = telemetry.current_stage()
    mesures.telechargement(tmp_path / "absent.mp3", 0)
    assert etape is not None
    assert mesures._empreinte_fichier(tmp_path / "absent.mp3") is None


def test_une_version_de_paquet_absente_est_nulle():
    assert mesures._version("paquet-qui-n-existe-pas-reco") is None


# ===== chaîne de venus =======================================================
def test_la_chaine_qualifie_premiere_passe_puis_reprise(metrics_db, depot, doublures):
    import traiter_nouveaux_episodes as chaine
    doublures["panne"] = True
    assert chaine.main(["transcrire", "--source", SOURCE, "--notify", "none"]) == 0
    doublures["panne"] = False
    assert chaine.main(["transcrire", "--source", SOURCE, "--notify", "none"]) == 0
    assert chaine.main(["transcrire", "--source", SOURCE, "--notify", "none"]) == 0  # rien à faire

    runs = _lignes(metrics_db, "SELECT * FROM workflow_runs ORDER BY started_at")
    assert [(r["trigger"], r["command"], r["intent"], r["status"]) for r in runs] == [
        ("scheduler", "traiter_nouveaux_episodes:transcrire", "standard_first_pass", "partial"),
        ("scheduler", "traiter_nouveaux_episodes:transcrire", "standard_first_pass", "succeeded"),
    ]
    echec, reprise = _lignes(metrics_db, "SELECT * FROM stage_attempts ORDER BY started_at")
    assert (echec["intent"], echec["status"]) == ("standard_first_pass", "failed")
    assert (reprise["intent"], reprise["status"]) == ("retry", "succeeded")
    assert reprise["retry_of_attempt_id"] == echec["id"]
    config = json.loads(runs[0]["config_json"])
    assert config["etape"] == "transcrire" and config["workflow_version"] == "pipeline-v1"


def test_le_declencheur_et_l_intention_se_surchargent(metrics_db, depot, doublures, monkeypatch):
    import traiter_nouveaux_episodes as chaine
    monkeypatch.setenv("RECO_TRIGGER", "cli")
    monkeypatch.setenv("RECO_RUN_INTENT", "backfill")
    chaine.main(["transcrire", "--source", SOURCE, "--notify", "none"])
    assert _lignes(metrics_db, "SELECT trigger, intent FROM workflow_runs")[0] == {
        "trigger": "cli", "intent": "backfill"}


def test_une_etape_globale_en_echec_est_mesuree(metrics_db, depot, monkeypatch):
    import traiter_nouveaux_episodes as chaine
    monkeypatch.setattr(chaine, "publier", lambda *a, **k: 1)
    monkeypatch.setattr(chaine, "commenter", lambda *a, **k: 0)
    assert chaine.main(["publier", "--source", SOURCE, "--notify", "none"]) == 1
    assert chaine.main(["commenter", "--source", SOURCE, "--notify", "none"]) == 0
    rows = {r["stage"]: r for r in _lignes(metrics_db, "SELECT * FROM stage_attempts")}
    assert rows["publish"]["status"] == "failed" and rows["publish"]["episode_guid"] is None
    assert rows["comment"]["status"] == "succeeded"


def test_la_finalisation_refusee_est_un_echec_mesure(metrics_db, depot, monkeypatch):
    import contextlib

    import traiter_nouveaux_episodes as chaine
    episode = json.loads(depot["episode"].read_text(encoding="utf-8"))
    monkeypatch.setattr(chaine, "a_finaliser", lambda s, st: [(depot["episode"], episode)])
    resultats = iter([False, True])
    monkeypatch.setattr(chaine, "_finaliser_un", lambda *a, **k: next(resultats))
    for _ in range(2):
        with telemetry.workflow_run(SOURCE, trigger="scheduler", command="f",
                                    intent="standard_first_pass"):
            chaine.finaliser(SOURCE, print, {"lastErrors": {}, "finalized": []},
                             publier=lambda *a, **k: None, lock=contextlib.nullcontext)
    echec, reprise = _lignes(metrics_db, "SELECT * FROM stage_attempts ORDER BY started_at")
    assert (echec["stage"], echec["status"], echec["season"]) == ("finalize", "failed", 6)
    assert (reprise["intent"], reprise["status"]) == ("retry", "succeeded")


def test_reecoute_et_calage_des_citations_sont_des_etapes(metrics_db, depot):
    import traiter_nouveaux_episodes as chaine
    episode = json.loads(depot["episode"].read_text(encoding="utf-8"))

    def preciseur(*a, **k):
        raise RuntimeError("audio introuvable")

    with telemetry.workflow_run(SOURCE, trigger="scheduler", command="e",
                                intent="standard_first_pass"):
        chaine._extract_one(SOURCE, depot["episode"], episode, {"lastErrors": {}, "extracted": []},
                            lambda _m: None, client=None, model="m", source={}, secours=None,
                            extractor=lambda *a, **k: 2, preciseur=preciseur,
                            caleur=lambda *a, **k: types.SimpleNamespace(noms=[], minutages=[]),
                            review_url="http://x")
    rows = {r["stage"]: r for r in _lignes(metrics_db, "SELECT * FROM stage_attempts")}
    assert rows["quote_relisten"]["status"] == "failed"
    assert rows["quote_align"]["status"] == "succeeded"
    assert rows["quote_align"]["correlation_id"] == f"{SOURCE}:{GUID}"


# ===== run_pipeline ==========================================================
def test_run_pipeline_ouvre_un_seul_run_pour_ses_etapes(metrics_db, depot, doublures,
                                                         monkeypatch):
    import fetch_episodes
    import run_pipeline
    monkeypatch.setattr(fetch_episodes, "fetch_episodes", lambda *a, **k: None)
    run_pipeline.run(SOURCE, ["fetch", "transcribe"], None, "small", "claude-opus-5",
                     False, "fr", False, False, intent="backfill")
    runs = _lignes(metrics_db, "SELECT * FROM workflow_runs")
    assert len(runs) == 1 and runs[0]["command"] == "run_pipeline"
    assert runs[0]["intent"] == "backfill"
    etapes = _lignes(metrics_db, "SELECT stage, intent, workflow_run_id FROM stage_attempts "
                                 "ORDER BY started_at")
    assert [e["stage"] for e in etapes] == ["fetch", "transcribe"]
    assert {e["workflow_run_id"] for e in etapes} == {runs[0]["id"]}
    assert {e["intent"] for e in etapes} == {"backfill"}


def test_run_pipeline_garde_sa_ligne_de_commande(monkeypatch):
    import run_pipeline
    vu = {}
    monkeypatch.setattr(run_pipeline, "run", lambda **k: vu.update(k))
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--source", SOURCE, "--steps", "fetch",
                                      "--intent", "experiment"])
    run_pipeline.main()
    assert vu["intent"] == "experiment" and vu["steps"] == ["fetch"]
