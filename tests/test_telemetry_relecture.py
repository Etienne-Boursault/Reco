"""Télémétrie, PR4 : journal de relecture et temps actif.

Harnais de `test_review_server` : le contenu vit dans `tmp_path`.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

import review_telemetrie as rt
import telemetry
from test_review_server import (  # noqa: F401 — fixtures réutilisées
    _clear_review_server_caches,
    _FakeHandler,
    fake_source,
)

SESSION = "0f8b7c2e-1a2b-4c3d-9e8f-001122334455"


def _lignes(chemin, sql, params=()):
    if not chemin.exists():
        return []
    conn = sqlite3.connect(chemin)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _post(source_id, route, body, *, cookie=True):
    h = _FakeHandler(source_id, route, body.encode("utf-8"))
    if cookie:
        h.headers["Cookie"] = f"autre=1; {rt.COOKIE}={SESSION}"
    h.do_POST()
    return h


def _evenements(chemin):
    return _lignes(chemin, "SELECT * FROM review_events ORDER BY occurred_at, rowid")


def _reco(fake_source, rid):
    from common import recos_dir_for
    return json.loads((recos_dir_for(fake_source) / f"{rid}.json").read_text(encoding="utf-8"))


def test_une_session_valide_corrige_puis_annule_dans_l_ordre(metrics_db, fake_source):
    _post(fake_source, "/save", "id=ubm-001&action=validate&who=Alice")
    _post(fake_source, "/edit", "id=ubm-001&title=Mortel%20(s%C3%A9rie)&types=serie"
                                "&creator=F.%20Garcia")
    _post(fake_source, "/save", "id=ubm-002&action=discard")
    _post(fake_source, "/undo-save", "")

    evts = _evenements(metrics_db)
    assert [(e["reco_id"], e["action"]) for e in evts] == [
        ("ubm-001", "validate"), ("ubm-001", "edit"), ("ubm-002", "discard"),
        ("ubm-002", "undo")]
    valide, edite, ecarte, annule = evts
    assert (valide["status_before"], valide["status_after"]) == ("draft", "validated")
    assert "status" in json.loads(valide["changed_fields_json"])
    assert "reassign_speaker" in json.loads(valide["derived_categories_json"])
    champs = json.loads(edite["changed_fields_json"])
    assert {"title", "types"} <= set(champs)
    assert {"title_corrected", "type_corrected"} <= set(
        json.loads(edite["derived_categories_json"]))
    assert "Mortel (série)" not in edite["changed_fields_json"]  # noms, jamais valeurs
    assert (annule["status_before"], annule["status_after"]) == ("discarded", "validated")
    assert all(e["actor_kind"] == "human" for e in evts)
    assert all(e["review_session_id"] == SESSION for e in evts)
    assert all(e["active_duration_ms"] is None for e in evts)  # jamais deviné
    assert all(e["episode_guid"] == "ep-001" for e in evts)
    assert json.loads(ecarte["metadata_json"]) == {"route": "/save"}


def test_une_action_refusee_ou_sans_effet_n_ecrit_rien(metrics_db, fake_source):
    _post(fake_source, "/save", "id=ubm-001&action=pirater")
    _post(fake_source, "/merge-recos", "guid=ep-001&action=cancel")  # rien n'est écrit
    _post(fake_source, "/undo-save", "")  # rien à annuler
    _post(fake_source, "/route-inconnue", "id=ubm-001")
    assert _evenements(metrics_db) == []


def test_ajout_et_suppression_sont_journalises(metrics_db, fake_source):
    _post(fake_source, "/add-reco", "guid=ep-002")
    nouvelle = _evenements(metrics_db)[0]
    assert (nouvelle["action"], nouvelle["episode_guid"]) == ("add", "ep-002")
    assert nouvelle["status_before"] is None
    _post(fake_source, "/delete-reco", f"id={nouvelle['reco_id']}")
    supprimee = _evenements(metrics_db)[1]
    assert (supprimee["action"], supprimee["reco_id"]) == ("delete", nouvelle["reco_id"])
    assert supprimee["status_after"] is None


def test_la_consolidation_journalise_chaque_decision(metrics_db, fake_source):
    _post(fake_source, "/consolidate", "member=ubm-001&member=ubm-002&keep=ubm-001")
    assert {(e["reco_id"], e["action"]) for e in _evenements(metrics_db)} == {
        ("ubm-001", "validate"), ("ubm-002", "discard")}


def test_retirer_un_lien_est_une_correction_de_lien(metrics_db, fake_source):
    from common import recos_dir_for
    chemin = recos_dir_for(fake_source) / "ubm-001.json"
    reco = json.loads(chemin.read_text(encoding="utf-8"))
    reco["links"] = [{"url": "https://exemple.test/a", "platform": "x"}]
    chemin.write_text(json.dumps(reco), encoding="utf-8")
    _post(fake_source, "/retirer-lien", "id=ubm-001&url=https://exemple.test/a")
    evt = _evenements(metrics_db)[0]
    assert evt["action"] == "edit"
    assert json.loads(evt["derived_categories_json"]) == ["external_link_corrected"]
    assert "exemple.test" not in json.dumps(evt)


def test_sans_cookie_la_session_est_inconnue(metrics_db, fake_source):
    _post(fake_source, "/save", "id=ubm-001&action=validate", cookie=False)
    assert _evenements(metrics_db)[0]["review_session_id"] is None


def test_l_attribution_a_l_extraction_n_est_jamais_arbitraire(metrics_db, fake_source):
    def extraction():
        with telemetry.workflow_run(fake_source, trigger="cli", command="x") as run, \
                run.stage("extract", episode_guid="ep-001"):
            pass

    extraction()
    _post(fake_source, "/save", "id=ubm-001&action=validate")
    seule = _evenements(metrics_db)[0]
    tentative = _lignes(metrics_db, "SELECT id FROM stage_attempts")[0]["id"]
    assert (seule["source_stage_attempt_id"], seule["provenance_quality"]) == (
        tentative, "inferred")
    extraction()  # deux extractions : laquelle a trouvé la reco ? on ne sait pas
    _post(fake_source, "/save", "id=ubm-001&action=discard")
    deux = _evenements(metrics_db)[1]
    assert (deux["source_stage_attempt_id"], deux["provenance_quality"]) == (None, "unknown")


def test_une_panne_de_telemetrie_ne_bloque_pas_la_relecture(metrics_db, fake_source,
                                                            monkeypatch, caplog):
    def panne():
        raise RuntimeError("disque plein")
    monkeypatch.setattr(telemetry, "get_recorder", panne)
    h = _post(fake_source, "/save", "id=ubm-001&action=validate")
    assert h._status == 303
    assert _reco(fake_source, "ubm-001")["status"] == "validated"
    assert "Télémétrie de relecture" in caplog.text


def test_une_photo_impossible_ne_bloque_pas_la_relecture(metrics_db, fake_source,
                                                         monkeypatch, caplog):
    def casse(*a, **k):
        raise OSError("illisible")
    with monkeypatch.context() as m:
        m.setattr(rt.ReviewJournalMixin, "_photo_avant", casse)
        _post(fake_source, "/save", "id=ubm-001&action=validate")
    assert _reco(fake_source, "ubm-001")["status"] == "validated"
    monkeypatch.setattr(rt.ReviewJournalMixin, "_photo_apres", casse)
    _post(fake_source, "/save", "id=ubm-001&action=discard")
    assert _reco(fake_source, "ubm-001")["status"] == "discarded"
    assert caplog.text.count("Télémétrie de relecture") == 2
    assert _evenements(metrics_db) == []


def test_le_renommage_d_un_invite_photographie_l_episode(metrics_db, fake_source):
    _post(fake_source, "/rename-guest", "guid=ep-001&old=Alice&new=Alicia")
    for evt in _evenements(metrics_db):
        assert evt["action"] == "edit"


# ===== agent ================================================================
def test_un_verdict_d_agent_n_est_pas_du_travail_humain(metrics_db, fake_source):
    import apply_verdicts as av
    drafts = av.load_episode_recos(fake_source, "ep-001")
    av.apply_verdicts({"ubm-001": {"verdict": "discard", "confidence": "high",
                                   "reason": "mention", "recommendedBy": ""}},
                      drafts, model="claude-opus-5-5", today="2026-10-22")
    evt = _evenements(metrics_db)[0]
    assert (evt["actor_kind"], evt["action"], evt["status_after"]) == (
        "agent", "discard", "discarded")
    assert json.loads(evt["metadata_json"]) == {"model": "claude-opus-5-5"}
    assert evt["active_duration_ms"] is None
    assert _lignes(metrics_db, "SELECT * FROM review_activity") == []


def test_un_doute_d_agent_s_ecrit_mark_unsure(metrics_db, fake_source):
    import apply_verdicts as av
    drafts = av.load_episode_recos(fake_source, "ep-001")
    av.apply_verdicts({"ubm-001": {"verdict": "unsure", "confidence": "low",
                                   "reason": "?", "recommendedBy": ""}},
                      drafts, model="m", today="2026-10-22")
    assert _evenements(metrics_db)[0]["action"] == "mark_unsure"


# ===== temps actif ==========================================================
def test_les_battements_sont_bornes_et_dedoublonnes(metrics_db, fake_source, monkeypatch):
    horloge = iter([1000.0, 1005.0, 1016.0, 1016.0])
    monkeypatch.setattr(rt.time, "monotonic", lambda: next(horloge))
    rt._DERNIERS_BATTEMENTS.clear()
    corps = f"session={SESSION}&page=/ep&guid=ep-001"
    assert _post(fake_source, "/activite", corps)._status == 204
    assert _post(fake_source, "/activite", corps)._status == 204  # +5 s : ignoré
    assert _post(fake_source, "/activite", corps)._status == 204  # +16 s : compté
    autre = "session=aaaaaaaa-bbbb&page=/doutes"
    assert _post(fake_source, "/activite", autre)._status == 204  # autre onglet
    lignes = _lignes(metrics_db, "SELECT * FROM review_activity ORDER BY received_at")
    assert len(lignes) == 3
    assert {r["interval_ms"] for r in lignes} == {rt.INTERVALLE_MS}
    assert lignes[0]["episode_guid"] == "ep-001" and lignes[0]["page"] == "/ep"
    assert lignes[2]["episode_guid"] is None


@pytest.mark.parametrize("corps", [
    "session=court&page=/ep", f"session={SESSION}&page=https://ailleurs.test",
    f"session={SESSION}&page=/ep&guid=<script>", "page=/ep"])
def test_un_battement_invalide_est_refuse(metrics_db, fake_source, corps):
    assert _post(fake_source, "/activite", corps)._status == 400
    assert _lignes(metrics_db, "SELECT * FROM review_activity") == []


def test_un_battement_qui_ne_s_ecrit_pas_ne_bloque_rien(metrics_db, fake_source, monkeypatch):
    rt._DERNIERS_BATTEMENTS.clear()

    def panne():
        raise RuntimeError("x")
    monkeypatch.setattr(telemetry, "get_recorder", panne)
    assert _post(fake_source, "/activite", f"session={SESSION}&page=/ep")._status == 204


def test_le_script_d_activite_est_servi_avec_la_page():
    from review_render_common import _CLIENT_JS
    assert "reco_revue_session" in _CLIENT_JS and "/activite" in _CLIENT_JS
    assert "visibilityState" in _CLIENT_JS


# ===== règles ===============================================================
def test_actions_et_categories():
    a, b = {"status": "draft"}, {"status": "validated"}
    assert rt.action_pour("/merge-recos", {}, a, None) == "merge"
    assert rt.action_pour("/merge-recos", {}, a, b) == "merge"
    assert rt.action_pour("/undo-merge", {}, None, b) == "undo"
    assert rt.action_pour("/consolidate", {}, a, {"status": "draft"}) == "edit"
    assert rt.action_pour("/reenrich", {}, a, b) == "reenrich"
    assert rt.action_pour("/save", {}, a, b) == "validate"
    assert rt.action_pour("/autre", {}, a, b) == "autre"
    assert rt.categories(["links", "linksRejected", "agentReview"]) == ["external_link_corrected"]
    assert rt.champs_modifies(None, {"a": 1}) == ["a"]
