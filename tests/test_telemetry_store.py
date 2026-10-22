"""Télémétrie, PR1 : schéma, enregistreur, runs et tentatives d'étape."""
from __future__ import annotations

import json
import sqlite3
import threading
import time

import pytest

import telemetry
from telemetry import context as ctx
from telemetry.recorder import SQLiteTelemetryRecorder, get_recorder
from telemetry.schema import SCHEMA_VERSION
from telemetry.store import Store

SOURCE = "demo-source"


def _lignes(chemin, sql, params=()):
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


# ===== schéma ================================================================
def test_la_base_est_migree_et_la_migration_est_rejouable(tmp_path):
    chemin = tmp_path / "m.sqlite"
    store = Store(chemin)
    assert store.version() == SCHEMA_VERSION
    assert store.migrate() == 0
    store.close()

    tables = {r["name"] for r in _lignes(chemin, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"workflow_runs", "stage_attempts", "llm_calls", "llm_batches",
            "batch_requests", "review_events"} <= tables
    assert Store(chemin).migrate() == 0  # redémarrage : rien à rejouer


def test_deux_processus_qui_demarrent_ensemble_ne_migrent_qu_une_fois(tmp_path):
    chemin = tmp_path / "m.sqlite"
    erreurs = []

    def ouvrir():
        try:
            Store(chemin).close()
        except Exception as exc:  # noqa: BLE001
            erreurs.append(exc)

    fils = [threading.Thread(target=ouvrir) for _ in range(4)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    assert erreurs == []
    assert Store(chemin).version() == SCHEMA_VERSION


def test_le_journal_se_dispute_un_moment_puis_abandonne(tmp_path, monkeypatch):
    from telemetry import store as store_mod
    monkeypatch.setattr(store_mod.time, "sleep", lambda _s: None)
    store = Store(tmp_path / "m.sqlite")
    vraie = store.conn

    class Disputee:
        def __init__(self, echecs):
            self.echecs = echecs

        def execute(self, sql):
            if self.echecs:
                self.echecs -= 1
                raise sqlite3.OperationalError("database is locked")
            return vraie.execute(sql)

    store.conn = Disputee(3)
    store._journal("delete")
    assert vraie.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    store.conn = Disputee(10_000)
    with pytest.raises(sqlite3.OperationalError):
        store._journal("wal")
    store.conn = vraie
    store.close()


def test_des_insertions_paralleles_ne_perdent_rien(tmp_path):
    chemin = tmp_path / "m.sqlite"
    Store(chemin).close()

    def ecrire(n):
        store = Store(chemin)  # une connexion par fil, comme deux conteneurs
        for i in range(25):
            store.insert("workflow_runs", {
                "id": f"{n}-{i}", "source_id": SOURCE, "trigger": "cli", "intent": "unknown",
                "workflow_version": "pipeline-v1", "config_fingerprint": "x",
                "started_at": "2026-10-22T00:00:00+00:00", "status": "started"})
        store.close()

    fils = [threading.Thread(target=ecrire, args=(n,)) for n in range(4)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    assert _lignes(chemin, "SELECT COUNT(*) AS n FROM workflow_runs")[0]["n"] == 100


def test_une_ligne_ne_se_finalise_qu_une_fois(tmp_path):
    store = Store(tmp_path / "m.sqlite")
    store.insert("workflow_runs", {
        "id": "r", "source_id": SOURCE, "trigger": "cli", "intent": "unknown",
        "workflow_version": "pipeline-v1", "config_fingerprint": "x",
        "started_at": "t0", "status": "started"})
    assert store.finish("workflow_runs", "r", {"status": "succeeded", "ended_at": "t1",
                                               "elapsed_ms": 5}) is True
    assert store.finish("workflow_runs", "r", {"status": "failed", "ended_at": "t2",
                                               "elapsed_ms": 0}) is False
    assert store.query("SELECT status, elapsed_ms FROM workflow_runs")[0] == {
        "status": "succeeded", "elapsed_ms": 5}


def test_une_migration_ratee_ne_laisse_rien_a_moitie(tmp_path, monkeypatch):
    from telemetry import schema
    from telemetry import store as store_mod
    monkeypatch.setattr(store_mod, "MIGRATIONS", schema.MIGRATIONS + ["CREATE TABLE ("])
    monkeypatch.setattr(store_mod, "SCHEMA_VERSION", len(schema.MIGRATIONS) + 1)
    with pytest.raises(sqlite3.OperationalError):
        Store(tmp_path / "m.sqlite")
    assert _lignes(tmp_path / "m.sqlite", "PRAGMA user_version")[0]["user_version"] == 0


def test_le_journal_se_choisit_pour_un_disque_partage(tmp_path, monkeypatch):
    monkeypatch.setenv("RECO_METRICS_JOURNAL", "delete")
    store = Store(tmp_path / "m.sqlite")
    assert store.query("PRAGMA journal_mode")[0]["journal_mode"] == "delete"
    assert store.execute("DELETE FROM workflow_runs") == 0
    store.close()
    store.close()  # fermer deux fois n'est pas une erreur
    monkeypatch.setenv("RECO_METRICS_JOURNAL", "n'importe quoi")  # ignoré, pas injecté
    store = Store(tmp_path / "m.sqlite")
    with pytest.raises(ValueError):
        store.insert("sqlite_master; DROP", {"id": "x"})
    with pytest.raises(ValueError):
        store.update("workflow_runs", "x", {"status = 'x' --": 1})
    store.close()


def test_les_appels_les_lots_et_les_evenements_s_ecrivent(metrics_db):
    recorder = get_recorder()
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t") as run, \
            run.stage("extract", episode_guid="g") as etape:
        attempt = etape.id
    assert recorder.record_batch({"id": "b1", "provider": "anthropic", "model": "m",
                                  "request_count": 2, "submitted_at": "t"}) is True
    assert recorder.update_batch("b1", {"last_status": "ended"}) is True
    assert recorder.map_batch_requests([
        {"batch_id": "b1", "custom_id": f"req-{i}", "stage_attempt_id": attempt,
         "episode_guid": "g", "chunk_index": i} for i in range(2)]) == 2
    assert set(recorder.batch_mapping("b1")) == {"req-0", "req-1"}
    appel = {"id": "c1", "stage_attempt_id": attempt, "provider": "anthropic", "model": "m",
             "transport": "batch", "batch_id": "b1", "batch_custom_id": "req-0",
             "status": "succeeded", "usage_source": "provider", "recorded_at": "t"}
    assert recorder.record_llm_call(appel) is True
    assert recorder.record_llm_call({**appel, "id": "c2"}) is False  # même entrée de lot
    assert recorder.record_review_event({
        "id": "e1", "source_id": SOURCE, "reco_id": "r", "actor_kind": "human",
        "action": "validate", "occurred_at": "t", "provenance_quality": "unknown"}) is True
    assert recorder.lost == 0


# ===== runs et étapes ========================================================
def test_un_run_et_une_tentative_sont_persistes_avec_une_duree_fiable(metrics_db):
    with telemetry.workflow_run(SOURCE, trigger="cli", command="test",
                                config={"model": "large-v3"}) as run, \
            run.stage("transcribe", episode_guid="yt-a", season=6,
                      config={"engine": "faster-whisper"}) as etape:
        time.sleep(0.03)
        etape.measure("transcribe_ms", 30, "ms")
        etape.set(media_origin="youtube", model="large-v3", media_duration_ms=60_000)

    run_row = _lignes(metrics_db, "SELECT * FROM workflow_runs")[0]
    tentative = _lignes(metrics_db, "SELECT * FROM stage_attempts")[0]
    assert run_row["status"] == "succeeded" and run_row["trigger"] == "cli"
    assert run_row["lost_observations"] == 0
    assert run_row["elapsed_ms"] >= 25
    assert tentative["workflow_run_id"] == run_row["id"]
    assert tentative["status"] == "succeeded" and tentative["elapsed_ms"] >= 25
    assert tentative["season"] == 6 and tentative["correlation_id"] == f"{SOURCE}:yt-a"
    assert tentative["telemetry_complete"] == 1
    assert json.loads(tentative["measurements_json"]) == {
        "transcribe_ms": {"value": 30, "unit": "ms"}}
    assert tentative["config_fingerprint"] == telemetry.fingerprint({"engine": "faster-whisper"})
    machine = json.loads(run_row["machine_json"])
    assert machine["machine_id"] and "hostname" not in machine


def test_une_cli_appelee_par_un_orchestrateur_rejoint_son_run(metrics_db):
    assert telemetry.current_run() is None
    with telemetry.workflow_run(SOURCE, trigger="cli", command="run_pipeline") as racine:
        assert telemetry.current_run() is racine
        with telemetry.workflow_run(SOURCE, trigger="cli", command="transcribe") as imbrique:
            assert imbrique is racine
            with telemetry.stage("transcribe", source_id=SOURCE, episode_guid="g"):
                pass
    assert len(_lignes(metrics_db, "SELECT id FROM workflow_runs")) == 1
    assert _lignes(metrics_db, "SELECT workflow_run_id FROM stage_attempts")[0][
        "workflow_run_id"] == racine.id


def test_une_etape_hors_run_ouvre_un_run_implicite(metrics_db):
    with telemetry.stage("extract", source_id=SOURCE, episode_guid="g"):
        pass
    assert _lignes(metrics_db, "SELECT trigger, command FROM workflow_runs") == [
        {"trigger": "library", "command": "extract"}]


def test_un_echec_finalise_la_tentative_sans_toucher_aux_precedentes(metrics_db):
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t") as run:
        with run.stage("transcribe", episode_guid="a") as premiere:
            premiere.measure("transcribe_ms", 10, "ms")
        with pytest.raises(RuntimeError), run.stage("transcribe", episode_guid="b"):
            raise RuntimeError("panne https://x.test/a?key=SECRET token=abc")
        with run.stage("transcribe", episode_guid="c"):
            pass

    rows = {r["episode_guid"]: r for r in _lignes(metrics_db, "SELECT * FROM stage_attempts")}
    assert len({r["id"] for r in rows.values()}) == 3
    assert rows["a"]["status"] == "succeeded"
    assert json.loads(rows["a"]["measurements_json"])["transcribe_ms"]["value"] == 10
    assert rows["b"]["status"] == "failed" and rows["b"]["error_category"] == "RuntimeError"
    assert "SECRET" not in rows["b"]["error_message_safe"]
    assert "abc" not in rows["b"]["error_message_safe"]
    assert "<url>" in rows["b"]["error_message_safe"]
    assert rows["b"]["telemetry_complete"] == 0
    assert _lignes(metrics_db, "SELECT status FROM workflow_runs")[0]["status"] == "partial"


def test_un_run_qui_leve_est_en_echec_et_une_interruption_est_marquee(metrics_db):
    with pytest.raises(ValueError), telemetry.workflow_run(SOURCE, trigger="cli", command="a"):
        raise ValueError("x")
    with pytest.raises(KeyboardInterrupt), \
            telemetry.workflow_run(SOURCE, trigger="cli", command="b") as run, \
            run.stage("transcribe", episode_guid="g"):
        raise KeyboardInterrupt
    statuts = {r["command"]: r["status"] for r in _lignes(metrics_db, "SELECT * FROM workflow_runs")}
    assert statuts == {"a": "failed", "b": "interrupted"}
    assert _lignes(metrics_db, "SELECT status FROM stage_attempts")[0]["status"] == "interrupted"


def test_un_passage_sans_travail_ne_laisse_aucun_run(metrics_db):
    with telemetry.workflow_run(SOURCE, trigger="scheduler", command="transcrire"):
        pass
    assert _lignes(metrics_db, "SELECT id FROM workflow_runs") == []


def test_un_saut_n_est_pas_une_execution(metrics_db):
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t") as run, \
            run.stage("transcribe", episode_guid="g") as etape:
        etape.skip("cache_hit")
    row = _lignes(metrics_db, "SELECT status, skip_reason FROM stage_attempts")[0]
    assert row == {"status": "skipped", "skip_reason": "cache_hit"}


def test_une_etape_sans_ses_champs_requis_n_est_pas_complete(metrics_db):
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t") as run:
        with run.stage("transcribe", episode_guid="g") as etape:
            etape.set(media_origin="youtube", model="large-v3")  # durée audio inconnue
        with run.stage("extract", episode_guid="g") as etape:
            etape.set(provider="anthropic", model="claude-opus-5-5")  # aucun appel observé
        with run.stage("publish", episode_guid="g") as etape:
            etape.fail("refusée")
    rows = {r["stage"]: r for r in _lignes(metrics_db, "SELECT * FROM stage_attempts")}
    assert rows["transcribe"]["telemetry_complete"] == 0
    assert rows["transcribe"]["media_duration_ms"] is None  # jamais 0 par défaut
    assert rows["extract"]["telemetry_complete"] == 0
    assert rows["publish"]["status"] == "failed"


def test_un_champ_d_etape_inconnu_est_refuse(metrics_db):
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t") as run, \
            run.stage("transcribe") as etape, pytest.raises(ValueError):
        etape.set(transcript_text="interdit")


def test_une_intention_inconnue_est_refusee(metrics_db):
    with pytest.raises(ValueError):
        with telemetry.workflow_run(SOURCE, trigger="cli", command="t", intent="vite"):
            pass
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t") as run, \
            pytest.raises(ValueError), run.stage("transcribe", intent="vite"):
        pass


def test_l_intention_par_defaut_vient_de_l_environnement(metrics_db, monkeypatch):
    monkeypatch.setenv("RECO_RUN_INTENT", "experiment")
    monkeypatch.setenv("RECO_PIPELINE_PROFILE", "ubm-s6-prod-2026-10")
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t") as run, \
            run.stage("extract", episode_guid="g"):
        pass
    assert _lignes(metrics_db, "SELECT intent, pipeline_profile FROM workflow_runs")[0] == {
        "intent": "experiment", "pipeline_profile": "ubm-s6-prod-2026-10"}
    assert _lignes(metrics_db, "SELECT intent FROM stage_attempts")[0]["intent"] == "experiment"


def test_la_chaine_qualifie_premiere_passe_reprise_et_retraitement(metrics_db):
    def tentative(succes=True, skip=False):
        with telemetry.workflow_run(SOURCE, trigger="scheduler", command="chaine",
                                    intent="standard_first_pass") as run:
            try:
                with run.stage("extract", episode_guid="yt-a", season=6) as etape:
                    if skip:
                        etape.skip("missing_input")
                    elif not succes:
                        raise RuntimeError("429")
            except RuntimeError:
                pass

    tentative(skip=True)          # un saut ne compte pas comme passe
    tentative(succes=False)
    tentative()
    tentative()
    rows = _lignes(metrics_db, "SELECT intent, status, retry_of_attempt_id, id "
                               "FROM stage_attempts ORDER BY started_at")
    assert [r["intent"] for r in rows] == [
        "standard_first_pass", "standard_first_pass", "retry", "unknown"]
    assert rows[2]["retry_of_attempt_id"] == rows[1]["id"]


def test_la_saison_inconnue_reste_nulle(metrics_db):
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t") as run, \
            run.stage("transcribe", episode_guid="g"):
        pass
    assert _lignes(metrics_db, "SELECT season FROM stage_attempts")[0]["season"] is None


def test_hors_etape_les_mesures_ne_vont_nulle_part(metrics_db):
    etape = telemetry.current_stage()
    etape.measure("x", 1, "count")
    etape.add("x", 2, "count")
    etape.set(model="ignoré")
    assert etape.measurements["x"]["value"] == 3
    assert not metrics_db.exists()


# ===== activation et échecs d'écriture ======================================
def test_desactivee_rien_n_est_ecrit(tmp_path, monkeypatch):
    chemin = tmp_path / "rien.sqlite"
    monkeypatch.setenv("RECO_METRICS_DB", str(chemin))
    monkeypatch.setenv("RECO_METRICS_ENABLED", "0")
    assert isinstance(get_recorder(), telemetry.NoopTelemetryRecorder)
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t") as run, \
            run.stage("transcribe"):
        pass
    assert not chemin.exists()


def test_par_defaut_la_base_est_sous_tools_output(monkeypatch, tmp_path):
    import common
    monkeypatch.setattr(common, "OUTPUT_DIR", tmp_path / "output")
    from telemetry.recorder import default_db_path
    assert default_db_path() == tmp_path / "output" / "telemetry" / "reco_metrics.sqlite"


def test_une_base_inaccessible_compte_les_pertes_sans_casser(tmp_path, caplog):
    bloque = tmp_path / "fichier"
    bloque.write_text("pas un dossier", encoding="utf-8")
    recorder = SQLiteTelemetryRecorder(bloque / "m.sqlite")
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t", recorder=recorder) as run, \
            run.stage("transcribe"):
        pass
    assert recorder.lost == 4  # début et fin, du run et de l'étape
    assert "observation perdue" in caplog.text


def test_en_mode_strict_une_perte_arrete_l_execution(tmp_path, monkeypatch):
    bloque = tmp_path / "fichier"
    bloque.write_text("x", encoding="utf-8")
    monkeypatch.setenv("RECO_METRICS_ENABLED", "1")
    monkeypatch.setenv("RECO_METRICS_STRICT", "1")
    monkeypatch.setenv("RECO_METRICS_DB", str(bloque / "m.sqlite"))
    with pytest.raises(telemetry.TelemetryError):
        with telemetry.workflow_run(SOURCE, trigger="cli", command="t") as run,                 run.stage("transcribe"):
            pass


def test_une_ecriture_refusee_par_sqlite_est_une_perte(metrics_db):
    recorder = get_recorder()
    assert recorder.start_run({"id": "r"}) is False  # colonnes obligatoires absentes
    assert recorder.lost == 1


def test_les_lectures_d_une_base_neuve_sont_vides(metrics_db):
    recorder = get_recorder()
    assert recorder.prior_attempts(SOURCE, None, "extract") == []
    assert recorder.prior_attempts(SOURCE, "g", "extract") == []
    assert recorder.batch_mapping("b") == {}


def test_l_enregistreur_nul_respecte_le_contrat():
    nul = telemetry.NoopTelemetryRecorder()
    assert not any([nul.start_run({}), nul.finish_run("r", {}), nul.start_stage({}),
                    nul.finish_stage("s", {}), nul.record_llm_call({}), nul.record_batch({}),
                    nul.update_batch("b", {}), nul.record_review_event({})])
    assert nul.map_batch_requests([{}]) == 0
    assert nul.prior_attempts(SOURCE, "g", "x") == [] and nul.batch_mapping("b") == {}


# ===== utilitaires ==========================================================
def test_l_empreinte_change_avec_la_configuration():
    a = telemetry.fingerprint({"model": "a", "chunk": 1})
    assert a == telemetry.fingerprint({"chunk": 1, "model": "a"})
    assert a != telemetry.fingerprint({"model": "b", "chunk": 1})


def test_le_commit_est_lu_dans_le_depot(tmp_path, monkeypatch):
    import common
    depot = tmp_path / "depot"
    (depot / ".git" / "refs" / "heads").mkdir(parents=True)
    (depot / "tools").mkdir()
    monkeypatch.setattr(common, "TOOLS_DIR", depot / "tools")

    def lire():
        ctx.git_commit.cache_clear()
        return ctx.git_commit()

    (depot / ".git" / "HEAD").write_text("abc123\n", encoding="utf-8")
    assert lire() == "abc123"
    (depot / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (depot / ".git" / "refs" / "heads" / "main").write_text("def456\n", encoding="utf-8")
    assert lire() == "def456"
    (depot / ".git" / "refs" / "heads" / "main").unlink()
    (depot / ".git" / "packed-refs").write_text(
        "# pack\n789abc refs/heads/main\n", encoding="utf-8")
    assert lire() == "789abc"
    (depot / ".git" / "packed-refs").write_text("# vide\n", encoding="utf-8")
    assert lire() is None
    (depot / ".git" / "HEAD").unlink()
    assert lire() is None
    ctx.git_commit.cache_clear()


def test_le_modele_de_cpu_se_lit_ou_se_devine(monkeypatch):
    from pathlib import Path

    def texte(self, encoding=None):
        if str(self).endswith("cpuinfo"):
            return "processor\t: 0\nmodel name\t: Ryzen 7\n"
        raise OSError
    monkeypatch.setattr(Path, "read_text", texte)
    assert ctx._modele_cpu() == "Ryzen 7"

    def absent(self, encoding=None):
        raise OSError
    monkeypatch.setattr(Path, "read_text", absent)
    monkeypatch.setattr(ctx.platform, "processor", lambda: "")
    assert ctx._modele_cpu() is None
