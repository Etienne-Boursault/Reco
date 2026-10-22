"""Télémétrie, PR3 : appels LLM synchrones et par lot, coûts, expériences.

Clients SDK simulés : aucun appel payant.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from decimal import Decimal
from types import SimpleNamespace

import pytest

import telemetry
from telemetry import llm, pricing

SOURCE = "demo-source"
MODELE = "claude-opus-5-5"


def _lignes(chemin, sql, params=()):
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _mesures(ligne):
    return {k: v["value"] for k, v in json.loads(ligne["measurements_json"]).items()}


def _message(n, titres, *, usage=True):
    corps = json.dumps({"recos": [{"title": t, "type": "film"} for t in titres]})
    return SimpleNamespace(
        id=f"msg_{n}", content=[SimpleNamespace(type="text", text=corps)],
        usage=SimpleNamespace(input_tokens=1000 * n, output_tokens=100 * n,
                              cache_read_input_tokens=0, cache_creation_input_tokens=0)
        if usage else None)


class ClientAnthropic:
    """Rend un message par appel, avec un usage différent à chaque fois."""

    def __init__(self, titres=("Alien", "Brazil"), usage=True, erreur=None):
        self.n, self.titres, self.usage, self.erreur = 0, titres, usage, erreur
        self.messages = SimpleNamespace(create=self.create)
        self.reco_cost_owner = "reco_managed"

    def create(self, **params):
        if self.erreur is not None:
            raise self.erreur
        self.n += 1
        return _message(self.n, self.titres, usage=self.usage)


@pytest.fixture
def depot(tmp_path, monkeypatch):
    """Deux épisodes de la saison 6, transcrits, chacun en deux chunks."""
    import common
    for nom, sous in (("SOURCES_DIR", "sources"), ("EPISODES_DIR", "episodes"),
                      ("RECOS_DIR", "recos"), ("OUTPUT_DIR", "output"),
                      ("TRANSCRIPTS_DIR", "output/transcripts"), ("AUDIO_DIR", "output/audio")):
        monkeypatch.setattr(common, nom, tmp_path / sous)
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / f"{SOURCE}.json").write_text(
        json.dumps({"id": SOURCE, "title": "Démo", "hosts": ["A"]}), encoding="utf-8")
    (tmp_path / "episodes" / SOURCE).mkdir(parents=True)
    (tmp_path / "output" / "transcripts" / SOURCE).mkdir(parents=True)
    chemins = {}
    for numero in (1, 2):
        guid = f"yt-ep{numero}"
        chemin = tmp_path / "episodes" / SOURCE / f"{guid}.json"
        chemin.write_text(json.dumps({
            "sourceId": SOURCE, "guid": guid, "title": f"Invité S6-E0{numero}", "season": 6,
            "transcriptStatus": "auto", "transcriptSource": "youtube"}), encoding="utf-8")
        lignes = "".join(f"[00:{i // 60:02d}:{i % 60:02d}] phrase secrète numéro {i}\n"
                         for i in range(900))
        (tmp_path / "output" / "transcripts" / SOURCE / f"{guid}.txt").write_text(
            lignes, encoding="utf-8")
        chemins[guid] = chemin
    return chemins


# ===== synchrone ============================================================
def test_deux_episodes_sont_isoles_et_les_jetons_sont_exacts(metrics_db, depot):
    import extract_recos as er
    client = ClientAnthropic()
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t"):
        for chemin in depot.values():
            er.extract_for_episode(SOURCE, chemin, client, False, model=MODELE)

    etapes = {e["episode_guid"]: e for e in _lignes(metrics_db, "SELECT * FROM stage_attempts")}
    appels = _lignes(metrics_db, "SELECT * FROM llm_calls ORDER BY recorded_at")
    assert len(appels) == client.n == 4
    for etape in etapes.values():
        siens = [a for a in appels if a["stage_attempt_id"] == etape["id"]]
        assert [a["chunk_index"] for a in siens] == [0, 1]
        assert {a["chunk_count"] for a in siens} == {2}
        assert all(a["chars_in_chunk"] > 0 for a in siens)
        m = _mesures(etape)
        assert m["raw_candidates"] == 4 and m["unique_candidates"] == 2  # répétés, pas additionnés
        assert m["chunk_count"] == 2
        assert etape["status"] == "succeeded" and etape["telemetry_complete"] == 1
        assert etape["provider"] == "anthropic" and etape["model"] == MODELE
        assert etape["season"] == 6
    assert _mesures(etapes["yt-ep1"])["recos_created"] == 2
    # Somme exacte des réponses : 1000+2000+3000+4000 en entrée.
    assert sum(a["input_tokens"] for a in appels) == 10_000
    assert sum(a["output_tokens"] for a in appels) == 1_000
    premier = appels[0]
    assert premier["usage_source"] == "provider" and premier["provider_request_id"] == "msg_1"
    assert premier["status"] == "succeeded" and premier["parse_status"] == "json"
    assert premier["candidates_raw"] == 2 and premier["transport"] == "sync"
    assert premier["cache_read_input_tokens"] == 0  # mesuré à zéro, pas inconnu
    assert Decimal(premier["cost_decimal"]) == Decimal("0.006")  # 1000 x 4 $ + 100 x 20 $
    assert premier["cost_currency"] == "USD"
    assert premier["cost_owner"] == "reco_managed"  # marque du client
    assert premier["pricing_snapshot_id"].startswith("2026-10-22:anthropic:claude-opus-5-5:sync")
    requete = json.loads(premier["request_json"])
    assert requete["max_tokens"] == er.MAX_TOKENS_RAISONNEMENT and requete["effort"] == "medium"


def test_ni_le_prompt_ni_la_transcription_ne_sont_ecrits(metrics_db, depot):
    import extract_recos as er
    er.extract_for_episode(SOURCE, depot["yt-ep1"], ClientAnthropic(), False, model=MODELE)
    with sqlite3.connect(metrics_db) as conn:
        dump = "\n".join(conn.iterdump())
    assert "phrase secrète" not in dump and "Extrais la liste" not in dump
    etape = _lignes(metrics_db, "SELECT * FROM stage_attempts")[0]
    assert etape["prompt_sha256"] == llm.prompt_sha256(er.SYSTEM_PROMPT, er.USER_TEMPLATE)
    assert etape["prompt_version"] == "recos-extraction-v1"
    assert etape["recipe_version"] == "cultural-recommendations-v1"


def test_un_prompt_modifie_change_les_empreintes(monkeypatch):
    import extract_recos as er
    import extraction_mesures as em
    avant = em.configuration("anthropic", MODELE, "sync")
    monkeypatch.setattr(er, "USER_TEMPLATE", er.USER_TEMPLATE + "\nNouvelle règle.")
    apres = em.configuration("anthropic", MODELE, "sync")
    assert avant["prompt_sha256"] != apres["prompt_sha256"]
    assert telemetry.fingerprint(avant) != telemetry.fingerprint(apres)
    assert em.configuration("anthropic", "claude-haiku-4-5", "sync")["effort"] is None


def test_une_api_sans_usage_laisse_les_jetons_inconnus(metrics_db, depot):
    import extract_recos as er
    er.extract_for_episode(SOURCE, depot["yt-ep1"], ClientAnthropic(usage=False), False,
                           model=MODELE)
    appel = _lignes(metrics_db, "SELECT * FROM llm_calls")[0]
    assert appel["input_tokens"] is None and appel["output_tokens"] is None
    assert appel["usage_source"] == "unavailable"
    assert appel["cost_decimal"] is None and appel["pricing_snapshot_id"] is None
    assert _lignes(metrics_db, "SELECT telemetry_complete FROM stage_attempts")[0][
        "telemetry_complete"] == 0


@pytest.mark.parametrize(("erreur", "statut", "code"), [
    (type("RateLimit", (Exception,), {"status_code": 429})("trop"), "failed", "429"),
    (TimeoutError("coupé"), "billing_uncertain", "TimeoutError"),
])
def test_un_appel_qui_echoue_n_a_pas_de_cout_invente(metrics_db, depot, erreur, statut, code):
    import extract_recos as er
    with pytest.raises(type(erreur)):
        er.extract_for_episode(SOURCE, depot["yt-ep1"], ClientAnthropic(erreur=erreur), False,
                               model=MODELE)
    appel = _lignes(metrics_db, "SELECT * FROM llm_calls")[0]
    assert (appel["status"], appel["error_code"]) == (statut, code)
    assert appel["cost_decimal"] is None and appel["usage_source"] == "unavailable"
    assert appel["elapsed_ms"] is not None
    assert _lignes(metrics_db, "SELECT status FROM stage_attempts")[0]["status"] == "failed"


def test_une_reponse_non_json_est_signalee(metrics_db, depot):
    import extract_recos as er

    class NonJson(ClientAnthropic):
        def create(self, **params):
            message = super().create(**params)
            message.content = [SimpleNamespace(type="text", text="désolé, pas de JSON")]
            return message

    er.extract_for_episode(SOURCE, depot["yt-ep1"], NonJson(), False, model=MODELE)
    appels = _lignes(metrics_db, "SELECT parse_status, candidates_raw FROM llm_calls")
    assert appels[0] == {"parse_status": "non_json", "candidates_raw": 0}


def test_openai_rend_ses_jetons_detailles(metrics_db, depot):
    import extract_recos as er
    reponse = SimpleNamespace(
        id="chatcmpl-1",
        choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"recos": [{"title": "Alien", "type": "film"}]}'))],
        usage=SimpleNamespace(prompt_tokens=900, completion_tokens=80,
                              prompt_tokens_details=SimpleNamespace(cached_tokens=100),
                              completion_tokens_details=SimpleNamespace(reasoning_tokens=30)))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **k: reponse)))
    er.extract_for_episode(SOURCE, depot["yt-ep1"], client, False, model="gpt-x",
                           provider="openai")
    appel = _lignes(metrics_db, "SELECT * FROM llm_calls")[0]
    assert (appel["provider"], appel["model"], appel["provider_request_id"]) == (
        "openai", "gpt-x", "chatcmpl-1")
    assert (appel["input_tokens"], appel["output_tokens"]) == (900, 80)
    assert (appel["cache_read_input_tokens"], appel["reasoning_tokens"]) == (100, 30)
    assert appel["usage_source"] == "provider"
    assert appel["cost_decimal"] is None  # aucun tarif OpenAI relevé : inconnu, pas zéro


def test_openai_non_json(metrics_db, depot):
    import extract_recos as er
    reponse = SimpleNamespace(id="c", usage=None, choices=[SimpleNamespace(
        message=SimpleNamespace(content="pas du json"))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **k: reponse)))
    assert er.extract_for_episode(SOURCE, depot["yt-ep1"], client, False, model="gpt-x",
                                  provider="openai") == 0
    assert {a["parse_status"] for a in _lignes(metrics_db, "SELECT * FROM llm_calls")} == {
        "non_json"}


def test_un_dry_run_n_est_pas_une_execution(metrics_db, depot):
    import extract_recos as er
    er.extract_for_episode(SOURCE, depot["yt-ep1"], None, True, model=MODELE)
    etape = _lignes(metrics_db, "SELECT * FROM stage_attempts")[0]
    assert (etape["status"], etape["skip_reason"]) == ("skipped", "dry_run")
    assert _mesures(etape)["planned_calls"] == 2
    assert _lignes(metrics_db, "SELECT COUNT(*) AS n FROM llm_calls")[0]["n"] == 0


def test_une_transcription_absente_est_un_saut(metrics_db, depot, tmp_path):
    import extract_recos as er
    (tmp_path / "output" / "transcripts" / SOURCE / "yt-ep1.txt").unlink()
    assert er.extract_for_episode(SOURCE, depot["yt-ep1"], None, False) == 0
    assert _lignes(metrics_db, "SELECT skip_reason FROM stage_attempts")[0]["skip_reason"] == \
        "missing_input"


def test_la_cli_d_extraction_declare_son_intention(metrics_db, depot, monkeypatch):
    import extract_recos as er
    monkeypatch.setattr(sys, "argv", ["extract_recos.py", "--source", SOURCE, "--guid", "yt-ep1",
                                      "--dry-run", "--intent", "manual_rerun"])
    er.main()
    run = _lignes(metrics_db, "SELECT * FROM workflow_runs")[0]
    assert (run["command"], run["intent"]) == ("extract_recos", "manual_rerun")
    assert _lignes(metrics_db, "SELECT intent FROM stage_attempts")[0]["intent"] == "manual_rerun"


# ===== lot ==================================================================
class ClientLot:
    def __init__(self, echec_de=None):
        self.echec_de = echec_de
        self.statuts = iter(["in_progress", "ended"])
        self.soumises = []
        self.messages = SimpleNamespace(batches=SimpleNamespace(
            create=self.create, retrieve=self.retrieve, results=self.results))

    def create(self, requests):
        self.soumises = requests
        return SimpleNamespace(id="msgbatch_1")

    def retrieve(self, batch_id):
        return SimpleNamespace(processing_status=next(self.statuts))

    def results(self, batch_id):
        for n, req in enumerate(self.soumises, 1):
            if req["custom_id"] == self.echec_de:
                yield SimpleNamespace(custom_id=req["custom_id"],
                                      result=SimpleNamespace(type="errored"))
            else:
                yield SimpleNamespace(custom_id=req["custom_id"], result=SimpleNamespace(
                    type="succeeded", message=_message(n, ["Alien"])))


def test_un_lot_range_chaque_resultat_dans_son_episode(metrics_db, depot):
    import extract_recos as er
    client = ClientLot(echec_de="req-3")
    with telemetry.workflow_run(SOURCE, trigger="cli", command="t"):
        er.extract_all_batch(SOURCE, list(depot.values()), client, MODELE, poll_seconds=0)

    lot = _lignes(metrics_db, "SELECT * FROM llm_batches")[0]
    assert (lot["id"], lot["request_count"], lot["last_status"]) == ("msgbatch_1", 4, "ended")
    assert lot["wait_ms"] is not None and lot["submit_elapsed_ms"] is not None
    assert lot["result_processing_ms"] is not None
    correspondance = _lignes(metrics_db, "SELECT * FROM batch_requests ORDER BY custom_id")
    assert [(c["custom_id"], c["episode_guid"], c["chunk_index"]) for c in correspondance] == [
        ("req-0", "yt-ep1", 0), ("req-1", "yt-ep1", 1), ("req-2", "yt-ep2", 0),
        ("req-3", "yt-ep2", 1)]
    etapes = {e["episode_guid"]: e for e in _lignes(metrics_db, "SELECT * FROM stage_attempts")}
    appels = _lignes(metrics_db, "SELECT * FROM llm_calls")
    par_episode = {g: [a for a in appels if a["stage_attempt_id"] == e["id"]]
                   for g, e in etapes.items()}
    assert sorted(a["batch_custom_id"] for a in par_episode["yt-ep1"]) == ["req-0", "req-1"]
    assert sum(a["input_tokens"] for a in par_episode["yt-ep1"]) == 3000
    assert all(a["transport"] == "batch" and a["elapsed_ms"] is None for a in appels)
    echoue = next(a for a in appels if a["batch_custom_id"] == "req-3")
    assert (echoue["status"], echoue["usage_source"], echoue["error_code"]) == (
        "failed", "unavailable", "errored")
    reussi = next(a for a in appels if a["batch_custom_id"] == "req-0")
    assert Decimal(reussi["cost_decimal"]) == Decimal("0.003")  # tarif de lot : 2 $ / 10 $
    assert etapes["yt-ep1"]["status"] == "succeeded"
    assert etapes["yt-ep2"]["status"] == "failed"
    assert _mesures(etapes["yt-ep1"])["unique_candidates"] == 1
    # Aucune durée de lot répartie entre épisodes.
    assert "batch_wait_ms" not in _mesures(etapes["yt-ep1"])

    # Collecte rejouée : aucun doublon de consommation.
    suivi_rejoue = __import__("extraction_mesures").SuiviLot(
        SOURCE, "anthropic", MODELE, [], [], {})
    assert suivi_rejoue.etapes == {}
    recorder = telemetry.get_recorder()
    mapping = recorder.batch_mapping("msgbatch_1")
    assert set(mapping) == {"req-0", "req-1", "req-2", "req-3"}
    avant = len(appels)
    for entry in client.results("msgbatch_1"):
        etape = next(e for e in etapes.values()
                     if e["id"] == mapping[entry.custom_id]["stage_attempt_id"])
        handle = telemetry.StageHandle(recorder, {**etape, "id": etape["id"]})
        appel = llm.Appel("anthropic", MODELE, "batch", None)
        if entry.result.type == "succeeded":
            appel.reponse(entry.result.message)
        llm.enregistrer(handle, appel, extra={"batch_id": "msgbatch_1",
                                              "batch_custom_id": entry.custom_id})
    assert len(_lignes(metrics_db, "SELECT id FROM llm_calls")) == avant


def test_un_lot_qui_casse_ferme_ses_tentatives_en_echec(metrics_db, depot):
    import extract_recos as er

    class Panne(ClientLot):
        def retrieve(self, batch_id):
            raise ConnectionError("réseau")

    with pytest.raises(ConnectionError):
        er.extract_all_batch(SOURCE, list(depot.values()), Panne(), MODELE, poll_seconds=0)
    assert {e["status"] for e in _lignes(metrics_db, "SELECT * FROM stage_attempts")} == {"failed"}
    # La correspondance était écrite avant de scruter : le lot reste attribuable.
    assert len(_lignes(metrics_db, "SELECT * FROM batch_requests")) == 4


def test_un_lot_sans_requete_n_ouvre_rien(metrics_db, depot, tmp_path):
    import extract_recos as er
    for f in (tmp_path / "output" / "transcripts" / SOURCE).iterdir():
        f.unlink()
    assert er.extract_all_batch(SOURCE, list(depot.values()), ClientLot(), MODELE) == 0
    assert not metrics_db.exists()


def test_le_suivi_de_lot_hors_run_n_ecrit_rien(metrics_db):
    import extraction_mesures as em
    suivi = em.SuiviLot(SOURCE, "anthropic", MODELE, [], ["g"], {})
    suivi.soumis("b", 0)
    suivi.statut("ended")
    suivi.attente_terminee()
    suivi.entree(SimpleNamespace(custom_id="inconnu"), None)
    suivi.fermer()
    assert not metrics_db.exists()


# ===== chaîne : secours sur 404 ==============================================
def test_le_secours_est_une_reprise_rattachee(metrics_db, depot):
    import extract_recos as er
    import traiter_nouveaux_episodes as chaine

    class Introuvable(Exception):
        status_code = 404

    class Client(ClientAnthropic):
        def create(self, **params):
            if params["model"] == "claude-disparu":
                raise Introuvable("modèle inconnu")
            return super().create(**params)

    client = Client()
    episode = json.loads(depot["yt-ep1"].read_text(encoding="utf-8"))
    kwargs = {"extractor": er.extract_for_episode, "client": client, "model": "claude-disparu",
              "secours": MODELE, "source": None}
    with telemetry.workflow_run(SOURCE, trigger="scheduler", command="e",
                                intent="standard_first_pass"):
        chaine._extraire_ou_secourir(SOURCE, depot["yt-ep1"], episode, lambda _m: None, kwargs)
    echec, secours = _lignes(metrics_db, "SELECT * FROM stage_attempts ORDER BY started_at")
    assert (echec["model"], echec["status"], echec["error_code"]) == (
        "claude-disparu", "failed", "404")
    assert (secours["model"], secours["intent"]) == (MODELE, "retry")
    assert secours["retry_of_attempt_id"] == echec["id"]
    statuts = [a["status"] for a in _lignes(metrics_db, "SELECT * FROM llm_calls "
                                                        "ORDER BY recorded_at")]
    assert statuts[0] == "failed"


# ===== banc d'essai =========================================================
def test_le_banc_est_une_experience(metrics_db, depot):
    import banc_modeles
    episodes = [json.loads(p.read_text(encoding="utf-8")) for p in depot.values()]
    with telemetry.workflow_run(SOURCE, trigger="cli", command="banc_modeles",
                                intent="experiment"):
        banc_modeles.mesurer(ClientAnthropic(), SOURCE, [MODELE], episodes)
    etapes = _lignes(metrics_db, "SELECT * FROM stage_attempts")
    assert {e["intent"] for e in etapes} == {"experiment"}
    assert {e["stage"] for e in etapes} == {"extract"}
    assert all(_mesures(e)["unique_candidates"] == 2 for e in etapes)
    assert len(_lignes(metrics_db, "SELECT id FROM llm_calls")) == 4


# ===== tarifs ===============================================================
def test_les_tarifs_sont_dates_et_sans_defaut():
    assert pricing.tarif("anthropic", MODELE, "sync", "2026-10-21T10:00:00") is None
    t = pricing.tarif("anthropic", MODELE, "sync", "2026-11-01T00:00:00")
    assert t["input"] == "4" and t["currency"] == "USD"
    assert pricing.tarif("anthropic", "claude-opus-5-5-20261001", "sync",
                         "2026-11-01")["model"] == MODELE
    assert pricing.tarif("openai", "gpt-4o-mini", "sync", "2026-11-01") is None
    assert pricing.cout(None, {"input_tokens": 1, "output_tokens": 1}) is None
    assert pricing.cout(t, {"input_tokens": None, "output_tokens": 1}) is None
    assert pricing.cout(t, {"input_tokens": 1, "output_tokens": 1,
                            "cache_read_input_tokens": 5}) is None  # prix du cache non relevé
    avec_cache = {**t, "cache_read": "0.4"}
    assert pricing.cout(avec_cache, {"input_tokens": 0, "output_tokens": 0,
                                     "cache_read_input_tokens": 1_000_000}) == Decimal("0.4")
    # Un micro-coût n'est pas arrondi à zéro.
    assert pricing.cout(t, {"input_tokens": 1, "output_tokens": 0}) == Decimal("0.000004")


def test_le_proprietaire_du_cout_vient_du_client(monkeypatch):
    import anthropic
    import openai

    import common
    assert llm.cost_owner(None) == "unknown"
    assert llm.cost_owner(SimpleNamespace(reco_cost_owner="n'importe")) == "unknown"
    assert llm.cost_owner(SimpleNamespace(reco_cost_owner="user_byok")) == "user_byok"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(common, "load_dotenv", lambda *_a, **_k: None, raising=False)
    assert isinstance(common.make_anthropic_client(), anthropic.Anthropic)
    assert llm.cost_owner(common.make_anthropic_client()) == "reco_managed"
    assert isinstance(common.make_openai_client(), openai.OpenAI)
    assert llm.cost_owner(common.make_openai_client()) == "reco_managed"


def test_un_usage_illisible_ne_casse_rien(caplog):
    appel = llm.Appel("anthropic", MODELE, "sync", None)

    class Bizarre:
        @property
        def usage(self):
            raise RuntimeError("forme inattendue")

    appel.reponse(Bizarre())
    assert appel.usage == {} and "Usage illisible" in caplog.text
    assert llm._scalaires({"a": {"b": {"c": 1}}}, 1) == {}
    assert llm._scalaires(SimpleNamespace(a=1, _b=2)) == {"a": 1}

    class Pydantic:  # forme des objets du SDK
        def model_dump(self):
            return {"input_tokens": 3, "server_tool_use": None, "service_tier": "standard"}
    assert llm._scalaires(Pydantic()) == {"input_tokens": 3, "service_tier": "standard"}
    assert llm.enregistrer(telemetry.current_stage(), appel) is False  # hors étape
