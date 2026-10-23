"""Télémétrie, PR5 : cohortes, couverture, résumés, export.

Données synthétiques écrites par l'API de télémétrie elle-même : S6 nominale,
S6 reprise, migration Acast -> YouTube, usage manquant, durée manquante,
expérience, configuration différente, saison inconnue.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import metrics_report
import telemetry
from telemetry import cohorts, llm, reports
from telemetry.donnees import Donnees, catalogue

SOURCE = "demo-source"
CONFIG_T = {"engine": "faster-whisper", "model": "large-v3-turbo"}
CONFIG_E = {"provider": "anthropic", "model": "claude-opus-5-5", "prompt_sha256": "abc"}
HEURE = 3_600_000


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    import common
    for nom, sous in (("SOURCES_DIR", "sources"), ("EPISODES_DIR", "episodes"),
                      ("RECOS_DIR", "recos"), ("OUTPUT_DIR", "output")):
        monkeypatch.setattr(common, nom, tmp_path / sous)
    (tmp_path / "episodes" / SOURCE).mkdir(parents=True)
    (tmp_path / "recos" / SOURCE).mkdir(parents=True)

    def episode(guid, season, statuts=()):
        data = {"guid": guid, "sourceId": SOURCE, "title": guid, "transcriptSource": "youtube"}
        if season is not None:
            data["season"] = season
        (tmp_path / "episodes" / SOURCE / f"{guid}.json").write_text(
            json.dumps(data), encoding="utf-8")
        for i, statut in enumerate(statuts):
            (tmp_path / "recos" / SOURCE / f"{guid}-{i}.json").write_text(json.dumps(
                {"id": f"{guid}-{i}", "episodeGuid": guid, "status": statut}), encoding="utf-8")
    return episode


def _appel(etape, n, *, usage=True):
    appel = llm.Appel("anthropic", "claude-opus-5-5", "sync", None)
    if usage:
        appel.usage = {"input_tokens": 10_000 * n, "output_tokens": 1_000 * n}
    llm.enregistrer(etape, appel)


def passe(guid, *, intent="standard_first_pass", season=6, config_t=CONFIG_T, config_e=CONFIG_E,
          origine="youtube", duree=HEURE, usage=True, extraction_ok=True, candidats=10):
    with telemetry.workflow_run(SOURCE, trigger="scheduler", command="chaine",
                                intent=intent) as run:
        with run.stage("transcribe", episode_guid=guid, season=season, intent=intent,
                       config=config_t) as t:
            t.set(media_origin=origine, model="large-v3-turbo", media_duration_ms=duree,
                  provider="local")
        try:
            with run.stage("extract", episode_guid=guid, season=season, intent=intent,
                           config=config_e) as e:
                e.set(provider="anthropic", model="claude-opus-5-5")
                if not extraction_ok:
                    raise RuntimeError("panne")
                _appel(e, 1, usage=usage)
                _appel(e, 2, usage=usage)
                e.measure("unique_candidates", candidats, "count")
        except RuntimeError:
            pass


@pytest.fixture
def jeu(metrics_db, corpus):
    for guid in ("s6-a", "s6-b", "s6-c"):
        corpus(guid, 6, ["validated", "discarded"])
        passe(guid)
    corpus("s6-reprise", 6)
    passe("s6-reprise", extraction_ok=False)
    with telemetry.workflow_run(SOURCE, trigger="cli", command="x", intent="retry") as run, \
            run.stage("extract", episode_guid="s6-reprise", season=6, intent="retry") as e:
        _appel(e, 1)
    corpus("s6-migration", 6)
    passe("s6-migration")
    passe("s6-migration", intent="source_migration", origine="acast")
    corpus("s6-sans-usage", 6)
    passe("s6-sans-usage", usage=False)
    corpus("s6-sans-duree", 6)
    passe("s6-sans-duree", duree=None)
    corpus("s6-experience", 6)
    passe("s6-experience", intent="experiment")
    corpus("s6-autre-config", 6)
    passe("s6-autre-config", config_e={**CONFIG_E, "model": "claude-opus-5"})
    corpus("s6-acast", 6)
    passe("s6-acast", origine="acast")
    corpus("s6-jamais", 6)
    corpus("s5-x", 5)
    passe("s5-x", season=5)
    corpus("historique", None, ["validated"])
    return metrics_db


def _donnees(base):
    return Donnees.charger(SOURCE, base)


# ===== cohorte ===============================================================
def test_la_selection_s6_explique_chaque_exclusion(jeu):
    sel = cohorts.selection(_donnees(jeu), catalogue(SOURCE), season=6)
    assert sel["includedEpisodes"] == ["s6-a", "s6-b", "s6-c"]
    assert sel["status"] == "qualified" and sel["isQualified"] is True
    assert sel["candidateEpisodeCount"] == 11
    exclus = {e["reason"]: e for e in sel["excluded"]}
    assert exclus["retry_only"]["episodes"] == ["s6-reprise"]
    assert exclus["source_migration"]["episodes"] == ["s6-migration"]
    assert exclus["missing_usage"]["episodes"] == ["s6-sans-usage"]
    assert exclus["missing_duration"]["episodes"] == ["s6-sans-duree"]
    assert exclus["experiment_only"]["episodes"] == ["s6-experience"]
    assert exclus["mixed_configuration"]["episodes"] == ["s6-autre-config"]
    assert exclus["media_mismatch"]["episodes"] == ["s6-acast"]
    assert exclus["no_telemetry"]["episodes"] == ["s6-jamais"]
    assert (exclus["not_season"]["count"], exclus["not_season"]["episodes"]) == (1, None)
    assert exclus["season_unknown"]["count"] == 1  # jamais « 6 » par supposition
    assert sel["reference"]["media_origin"] == "youtube"
    assert sel["reference"]["config"]["extract"] == telemetry.fingerprint(CONFIG_E)
    assert sel["finalState"]["s6-a"]["recos"] == {"discarded": 1, "validated": 1}


def test_trop_peu_d_episodes_est_un_resultat_honnete(jeu):
    sel = cohorts.selection(_donnees(jeu), catalogue(SOURCE), season=6, min_episodes=4)
    assert sel["status"] == "insufficient_data" and sel["includedEpisodeCount"] == 3


def test_un_profil_n_efface_jamais_un_changement_de_configuration(metrics_db, corpus,
                                                                  monkeypatch):
    # Même étiquette, mais le modèle a changé sans qu'on la renomme.
    monkeypatch.setenv("RECO_PIPELINE_PROFILE", "ubm-s6-prod-2026-10")
    for guid in ("s6-a", "s6-b", "s6-c"):
        corpus(guid, 6)
        passe(guid)
    corpus("s6-sonnet", 6)
    passe("s6-sonnet", config_e={**CONFIG_E, "model": "claude-sonnet-5-5"})
    sel = cohorts.selection(_donnees(metrics_db), catalogue(SOURCE), season=6)
    assert sel["includedEpisodes"] == ["s6-a", "s6-b", "s6-c"]
    assert sel["excluded"] == [{"reason": "mixed_configuration", "count": 1,
                                "episodes": ["s6-sonnet"]}]
    assert sel["workflowProfile"] == "ubm-s6-prod-2026-10"  # étiquette, rien de plus
    assert sel["reference"]["chosenBy"] == "most_frequent_fingerprint"


def test_plusieurs_profils_ne_donnent_pas_d_etiquette(jeu):
    assert cohorts.selection(_donnees(jeu), catalogue(SOURCE), season=6)[
        "workflowProfile"] is None


def test_l_echec_sans_reprise_n_est_pas_qualifie(metrics_db, corpus):
    corpus("s6-x", 6)
    passe("s6-x", extraction_ok=False)
    sel = cohorts.selection(_donnees(metrics_db), catalogue(SOURCE), season=6)
    assert sel["excluded"] == [{"reason": "not_succeeded", "count": 1, "episodes": ["s6-x"]}]


def test_une_reprise_seule_sans_premiere_passe(metrics_db, corpus):
    corpus("s6-y", 6)
    with telemetry.workflow_run(SOURCE, trigger="cli", command="x", intent="manual_rerun") as run:
        for etape in ("transcribe", "extract"):
            with run.stage(etape, episode_guid="s6-y"):
                pass
    sel = cohorts.selection(_donnees(metrics_db), catalogue(SOURCE), season=6)
    assert sel["excluded"][0]["reason"] == "not_standard"


# ===== export ================================================================
def test_l_export_est_conforme_et_ses_sommes_exactes(jeu):
    donnees = _donnees(jeu)
    sel = cohorts.selection(donnees, catalogue(SOURCE), season=6)
    exp = reports.export(donnees, sel, maintenant=datetime(2026, 11, 1, tzinfo=UTC))
    assert reports.valider(exp) == []
    obs = exp["observed"]
    assert (obs["llmInputTokens"], obs["llmOutputTokens"]) == (90_000, 9_000)
    assert obs["audioDurationMs"] == 3 * HEURE and obs["uniqueCandidates"] == 30
    assert obs["costCurrency"] == "USD"
    # Par épisode : 30 000 x 4 $ + 3 000 x 20 $ par million = 0,18 $.
    assert Decimal(obs["costKnown"]) == Decimal("0.54")
    assert obs["humanActiveMs"] is None and obs["reviewActions"] == 0
    assert Decimal(exp["derived"]["costPerAudioHour"]) == Decimal("0.18")
    assert exp["derived"]["candidatesPerAudioHour"] == 10
    assert exp["derived"]["humanMinutesPerReviewAction"] is None
    assert exp["derived"]["reviewMinutesPerCandidate"] is None
    assert exp["derived"]["sampleSize"] == 3
    # Reprises, expériences et migrations : à part, jamais dans le nominal.
    assert set(exp["overhead"]) == {"experiment", "retry", "source_migration"}
    assert exp["overhead"]["retry"]["llmCalls"] == 1
    assert exp["coverage"]["llmUsage"] < 1 and exp["coverage"]["audioDuration"] < 1
    assert exp["warnings"]


def test_une_base_vide_n_exporte_que_des_null(tmp_path, corpus):
    corpus("s6-a", 6)
    donnees = Donnees.charger(SOURCE, tmp_path / "absente.sqlite")
    assert not (tmp_path / "absente.sqlite").exists()
    exp = reports.export(donnees, cohorts.selection(donnees, catalogue(SOURCE), season=6))
    assert reports.valider(exp) == []
    assert exp["cohort"]["status"] == "insufficient_data"
    assert set(exp["observed"].values()) == {None}
    assert set(exp["coverage"].values()) == {None}
    assert set(v for k, v in exp["derived"].items() if k != "sampleSize") == {None}


def test_la_validation_attrape_les_ecarts():
    assert reports.valider([]) == ["export : objet attendu"]
    erreurs = reports.valider({"schemaVersion": "1", "cohort": {"isQualified": 1}})
    assert "export.schemaVersion : type str" in erreurs
    assert "export.sourceId : absent" in erreurs
    assert "export.cohort.isQualified : type int" in erreurs
    assert reports.valider({"x": True}, {"x": int}) == ["export.x : booléen inattendu"]


# ===== résumés ===============================================================
def test_le_resume_separe_nominal_et_surcout(jeu):
    donnees = _donnees(jeu)
    tout = reports.resume(donnees)
    assert tout["nominal"]["episodes"] == 10  # toutes les premières passes
    sel = cohorts.selection(donnees, catalogue(SOURCE), season=6)
    qualifie = reports.resume(donnees, sel)
    assert qualifie["nominal"]["episodes"] == 3
    assert qualifie["nominal"]["llmCallsByModel"] == {"anthropic:claude-opus-5-5": 6}
    assert qualifie["nominal"]["cost"]["unknownCostCalls"] == 0
    assert tout["nominal"]["inputTokens"] is None  # un appel sans usage : somme inconnue
    assert tout["nominal"]["cost"]["unknownCostCalls"] == 2


def test_la_couverture_compte_les_trous(jeu):
    cov = reports.couverture(_donnees(jeu))
    assert cov["runs"] == 13 and cov["llmCalls"] > 0
    assert cov["attemptsByIntent"]["experiment"] == 2
    assert 0 < cov["coverage"]["tokens"] < 1
    assert cov["coverage"]["humanTime"] is None  # aucune décision humaine
    assert cov["lostObservations"] == 0 and cov["startedNotFinished"] == 0


def test_le_temps_actif_fait_l_union_des_onglets():
    t0 = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)

    def battement(s, session="a"):
        return {"received_at": (t0 + timedelta(seconds=s)).isoformat(), "interval_ms": 15_000,
                "session_id": session}
    assert reports.temps_actif_ms([]) is None
    # Deux onglets aux mêmes instants : 30 s, pas 60.
    assert reports.temps_actif_ms([battement(15), battement(30), battement(15, "b"),
                                   battement(30, "b")]) == 30_000
    # Une pause : deux intervalles disjoints.
    assert reports.temps_actif_ms([battement(15), battement(300)]) == 30_000


def test_le_bout_en_bout_garde_les_pauses_mais_pas_les_seances_d_ecart():
    t0 = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)

    def battement(s, episode="a"):
        return {"received_at": (t0 + timedelta(seconds=s)).isoformat(), "interval_ms": 15_000,
                "episode_guid": episode}
    assert reports.temps_bout_en_bout_ms([]) is None
    # Trois minutes de recherches hors de la page : actif 30 s, bout en bout 5 min.
    pause = [battement(15), battement(300)]
    assert (reports.temps_actif_ms(pause), reports.temps_bout_en_bout_ms(pause)) == (
        30_000, 300_000)
    # Une heure d'écart : deux séances de 15 s, pas une heure de relecture.
    assert reports.temps_bout_en_bout_ms([battement(15), battement(3615)]) == 30_000
    # Le trou entre deux épisodes relus à la suite n'est pas de la relecture.
    assert reports.temps_bout_en_bout_ms([battement(15), battement(30), battement(600, "b"),
                                          battement(615, "b")]) == 60_000
    # Aller-retour entre deux épisodes : le chevauchement ne compte pas double.
    assert reports.temps_bout_en_bout_ms([battement(15), battement(300), battement(150, "b"),
                                          battement(165, "b")]) == 300_000


def test_le_temps_humain_et_les_corrections_par_cohorte(jeu):
    import review_telemetrie as rt
    recorder = telemetry.get_recorder()
    for s in (15, 30):
        recorder.record_activity({"id": f"b{s}", "source_id": SOURCE, "session_id": "sess-0001",
                                  "received_at": f"2026-10-22T10:00:{s:02d}+00:00",
                                  "page": "/ep", "episode_guid": "s6-a", "interval_ms": 15_000})
    rt.enregistrer_evenement(SOURCE, "s6-a-0", "edit", {"episodeGuid": "s6-a", "title": "a"},
                             {"episodeGuid": "s6-a", "title": "b"}, actor_kind="human",
                             session="sess-0001")
    rt.enregistrer_evenement(SOURCE, "s6-a-1", "validate", {"episodeGuid": "s6-a"},
                             {"episodeGuid": "s6-a", "status": "validated"}, actor_kind="human",
                             session="sess-0001")
    donnees = _donnees(jeu)
    sel = cohorts.selection(donnees, catalogue(SOURCE), season=6)
    exp = reports.export(donnees, sel)
    assert exp["observed"]["humanActiveMs"] == 30_000 and exp["observed"]["reviewActions"] == 2
    assert exp["observed"]["humanElapsedMs"] == 30_000
    assert exp["derived"]["humanMinutesPerReviewAction"] == 0.25
    assert exp["derived"]["manualReworkRate"] == 0.5
    assert exp["coverage"]["humanActiveTime"] == 1.0
    resume = reports.resume(donnees, sel)
    assert resume["review"]["humanCorrectionCategories"] == {"title_corrected": 1}
    assert (resume["review"]["humanActiveMs"], resume["review"]["humanElapsedMs"]) == (
        30_000, 30_000)


# ===== ligne de commande =====================================================
def test_la_ligne_de_commande_produit_chaque_rapport(jeu, tmp_path, capsys):
    base = ["--source", SOURCE, "--db", str(jeu)]
    for commande, extra in (("coverage", []), ("cohort", []), ("summary", ["--cohort", "all"]),
                            ("workflows", [])):
        assert metrics_report.main([commande, *base, *extra]) == 0
        json.loads(capsys.readouterr().out)
    assert metrics_report.main(["summary", *base, "--format", "markdown"]) == 0
    texte = capsys.readouterr().out
    assert "Cohorte `s6-standard-first-pass` : **qualified**" in texte
    assert "surcoût".lower() in texte.lower() and "`retry`" in texte
    assert "| relecture de bout en bout (humain) | non mesuré |" in texte
    assert metrics_report.main(["workflows", *base, "--format", "csv"]) == 0
    csv = capsys.readouterr().out.splitlines()
    assert csv[0].startswith("started_at,workflow_run_id") and len(csv) > 10
    cible = tmp_path / "out" / "export.json"
    assert metrics_report.main(["export", *base, "--output", str(cible)]) == 0
    assert reports.valider(json.loads(cible.read_text(encoding="utf-8"))) == []


def test_un_export_non_conforme_echoue(jeu, monkeypatch, capsys):
    monkeypatch.setattr(reports, "valider", lambda _o: ["export.x : absent"])
    assert metrics_report.main(["export", "--source", SOURCE, "--db", str(jeu)]) == 1
    assert "non conforme" in capsys.readouterr().err


def test_recuperer_les_interrompus_sans_rien_effacer(metrics_db, corpus, capsys):
    with pytest.raises(KeyboardInterrupt), \
            telemetry.workflow_run(SOURCE, trigger="cli", command="x") as run, \
            run.stage("transcribe", episode_guid="g"):
        raise KeyboardInterrupt
    conn = sqlite3.connect(metrics_db)
    conn.execute("INSERT INTO workflow_runs (id, source_id, trigger, intent, workflow_version, "
                 "config_fingerprint, started_at, status) VALUES ('vieux', ?, 'cli', 'unknown', "
                 "'pipeline-v1', 'x', '2026-10-01T00:00:00+00:00', 'started')", [SOURCE])
    conn.execute("INSERT INTO workflow_runs (id, source_id, trigger, intent, workflow_version, "
                 "config_fingerprint, started_at, status) VALUES ('recent', ?, 'cli', 'unknown', "
                 "'pipeline-v1', 'x', '2026-10-22T09:00:00+00:00', 'started')", [SOURCE])
    conn.commit()
    conn.close()
    maintenant = datetime(2026, 10, 22, 12, tzinfo=UTC)
    assert metrics_report.main(["recover", "--db", str(metrics_db)], maintenant=maintenant) == 0
    assert json.loads(capsys.readouterr().out) == {
        "interrupted": {"workflow_runs": 1, "stage_attempts": 0}}
    statuts = dict(sqlite3.connect(metrics_db).execute("SELECT id, status FROM workflow_runs"))
    assert statuts["vieux"] == "interrupted" and statuts["recent"] == "started"


def test_purger_les_battements_anciens(metrics_db, capsys, tmp_path):
    recorder = telemetry.get_recorder()
    for ident, quand in (("vieux", "2025-01-01T00:00:00+00:00"),
                         ("neuf", "2026-10-20T00:00:00+00:00")):
        recorder.record_activity({"id": ident, "source_id": SOURCE, "session_id": "sess-0001",
                                  "received_at": quand, "page": "/ep", "interval_ms": 15_000})
    maintenant = datetime(2026, 10, 22, tzinfo=UTC)
    assert metrics_report.main(["purge", "--db", str(metrics_db)], maintenant=maintenant) == 0
    assert json.loads(capsys.readouterr().out) == {"activityRowsDeleted": 1}
    for commande in ("purge", "recover"):  # base absente : rien à faire, rien de créé
        assert metrics_report.main([commande, "--db", str(tmp_path / "rien.sqlite")]) == 0
    assert not (tmp_path / "rien.sqlite").exists()


# ===== tolérance du chargement ==============================================
def test_le_chargement_tolere_une_base_ancienne_et_des_restes_abimes(tmp_path, corpus):
    from telemetry import schema
    from telemetry import store as store_mod
    ancienne = tmp_path / "v1.sqlite"  # base v1, sans review_activity
    conn = sqlite3.connect(ancienne)
    for instruction in store_mod._statements(schema.MIGRATIONS[0]):
        conn.execute(instruction)
    conn.execute("PRAGMA user_version=1")
    conn.execute("INSERT INTO workflow_runs (id, source_id, trigger, intent, workflow_version, "
                 "config_fingerprint, started_at, status) VALUES "
                 "('r', ?, 'cli', 'unknown', 'v', 'x', 't', 'succeeded')", [SOURCE])
    conn.execute("INSERT INTO stage_attempts (id, workflow_run_id, source_id, stage, intent, "
                 "status, started_at, measurements_json, config_json) VALUES "
                 "('a', 'r', ?, 'extract', 'unknown', 'succeeded', 't', 'pas du json', '[]')",
                 [SOURCE])
    conn.commit()
    conn.close()
    donnees = Donnees.charger(SOURCE, ancienne)
    assert donnees.schema_version == 1 and donnees.activity == []
    assert donnees.attempts[0]["measurements"] == {} and donnees.attempts[0]["config"] == []
    assert donnees.tentatives_par_episode() == {}

    import common
    corpus("ok", 6, ["validated"])
    (common.EPISODES_DIR / SOURCE / "abime.json").write_text("{", encoding="utf-8")
    (common.EPISODES_DIR / SOURCE / "sans-guid.json").write_text("{}", encoding="utf-8")
    (common.RECOS_DIR / SOURCE / "abimee.json").write_text("{", encoding="utf-8")
    (common.RECOS_DIR / SOURCE / "orpheline.json").write_text(
        json.dumps({"id": "o", "episodeGuid": "inconnu"}), encoding="utf-8")
    cat = catalogue(SOURCE)
    assert set(cat) == {"ok"} and cat["ok"]["recos"] == {"validated": 1}
    import shutil
    shutil.rmtree(common.RECOS_DIR / SOURCE)
    assert catalogue(SOURCE)["ok"]["recos"] == {}
