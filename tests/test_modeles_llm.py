"""Tests de tools/modeles_llm.py et de son cablage dans la chaine de venus.

Aucun modele ne tourne : clients et extracteurs sont des doubles.
"""
from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

import modeles_llm as ml
import traiter_nouveaux_episodes as tne

SOURCE = "demo-source"
LUNDI = datetime(2026, 10, 19, 6, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _capacites_vierges(monkeypatch):
    monkeypatch.setattr(ml, "_CAPACITES_EFFORT", {})


# ===== choix du modele ======================================================
def test_le_env_choisit_le_modele_et_son_secours():
    assert ml.modele_extraction({}) == "claude-opus-5"
    assert ml.modele_secours({}) == "claude-opus-5-5"
    env = {"RECO_MODELE_EXTRACTION": " claude-sonnet-5-5 ", "RECO_MODELE_SECOURS": "claude-opus-5"}
    assert ml.modele_extraction(env) == "claude-sonnet-5-5"
    assert ml.modele_secours(env) == "claude-opus-5"


def test_pas_de_secours_coupe_ou_identique_au_modele():
    assert ml.modele_secours({"RECO_MODELE_SECOURS": "aucun"}) is None
    assert ml.modele_secours({"RECO_MODELE_EXTRACTION": "claude-opus-5-5"}) is None


def test_seul_un_404_declenche_le_secours():
    assert ml.modele_introuvable(SimpleNamespace(status_code=404)) is True
    assert ml.modele_introuvable(SimpleNamespace(status_code=429)) is False
    assert ml.modele_introuvable(ValueError("x")) is False


# ===== effort ===============================================================
@pytest.mark.parametrize(("modele", "attendu"), [
    ("claude-opus-5", True), ("claude-opus-5-5", True), ("claude-opus-4-6", True),
    ("claude-sonnet-5", True), ("claude-sonnet-4-6", True), ("claude-fable-5-1", True),
    ("claude-haiku-5-5", True), ("claude-haiku-4-5", False), ("claude-sonnet-4-5", False),
    ("claude-haiku-4-5-20251001", False), ("gpt-4o-mini", False),
])
def test_effort_deduit_du_nom(modele, attendu):
    assert ml.accepte_effort(modele) is attendu


def test_l_api_des_modeles_prime_sur_le_nom():
    def retrieve(modele):
        return SimpleNamespace(capabilities={"effort": {"supported": modele == "claude-x-9"}})
    client = SimpleNamespace(models=SimpleNamespace(retrieve=retrieve))

    ml.noter_capacites(client, "claude-x-9")
    ml.noter_capacites(client, "claude-opus-5")

    assert ml.accepte_effort("claude-x-9") is True
    assert ml.accepte_effort("claude-opus-5") is False


def test_une_api_muette_laisse_la_regle_du_nom():
    ml.noter_capacites(SimpleNamespace(), "claude-opus-5")
    assert ml.accepte_effort("claude-opus-5") is True


def test_le_cout_suit_les_tarifs_publics():
    assert ml.cout("claude-opus-5", 1_000_000, 100_000) == pytest.approx(7.5)
    assert ml.cout("modele-inconnu", 1, 1) is None


# ===== veille ===============================================================
def _modele(ident, jour, nom=None):
    return SimpleNamespace(id=ident, display_name=nom or ident,
                           created_at=datetime(2026, 1, jour, tzinfo=UTC))


def _client(*modeles):
    return SimpleNamespace(models=SimpleNamespace(list=lambda: list(modeles)))


def test_la_veille_signale_un_modele_plus_recent_une_seule_fois():
    client = _client(_modele("claude-opus-5", 1), _modele("claude-opus-5-5", 9, "Claude Opus 5.5"),
                     _modele("claude-sonnet-5-5", 9), _modele("claude-opus-4-8", 1))
    etat, recus = {}, []

    assert ml.veiller(client, etat, recus.append, source_id=SOURCE,
                      modele="claude-opus-5", secours=None, maintenant=LUNDI) == 1
    assert "claude-opus-5-5 (Claude Opus 5.5)" in recus[0]
    assert "banc_modeles.py --source demo-source --modeles claude-opus-5 claude-opus-5-5" in recus[0]

    # Une semaine plus tard : deja signale, plus rien.
    assert ml.veiller(client, etat, recus.append, source_id=SOURCE, modele="claude-opus-5",
                      secours=None, maintenant=LUNDI + timedelta(days=7)) == 0


def test_la_veille_ne_repasse_pas_avant_une_semaine():
    etat = {"veilleModeles": {"derniere": LUNDI.isoformat()}}
    client = SimpleNamespace()  # tout appel echouerait

    assert ml.veiller(client, etat, print, source_id=SOURCE, modele="claude-opus-5",
                      secours=None, maintenant=LUNDI + timedelta(days=6)) == 0


def test_la_veille_signale_un_modele_disparu():
    client = _client(_modele("claude-opus-5-5", 9), _modele("claude-haiku-4-5-20251001", 1))
    recus = []

    ml.veiller(client, {}, recus.append, source_id=SOURCE, modele="claude-opus-5",
               secours="claude-haiku-4-5", maintenant=LUNDI)

    assert len(recus) == 1  # l'alias couvre sa version datee
    assert "« claude-opus-5 » n'est plus proposé" in recus[0]
    assert "RECO_MODELE_EXTRACTION" in recus[0]


# ===== cablage dans la chaine ===============================================
@pytest.fixture
def content(tmp_path, monkeypatch):
    import common
    for name, sub in (("SOURCES_DIR", "sources"), ("EPISODES_DIR", "episodes"),
                      ("RECOS_DIR", "recos"), ("OUTPUT_DIR", "output"),
                      ("TRANSCRIPTS_DIR", "output/transcripts"), ("AUDIO_DIR", "output/audio")):
        monkeypatch.setattr(common, name, tmp_path / sub)
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / f"{SOURCE}.json").write_text(
        json.dumps({"id": SOURCE, "title": "Démo", "hosts": ["A"]}), encoding="utf-8")
    episodes = tmp_path / "episodes" / SOURCE
    episodes.mkdir(parents=True)
    (episodes / "yt-abc.json").write_text(json.dumps(
        {"sourceId": SOURCE, "guid": "yt-abc", "title": "Titre", "transcriptStatus": "auto"}),
        encoding="utf-8")
    t = common.transcript_path_for(SOURCE, "yt-abc")
    t.parent.mkdir(parents=True, exist_ok=True)
    t.write_text("[00:00:01] bonjour\n", encoding="utf-8")
    return tmp_path


class Introuvable(Exception):
    status_code = 404


def _extraire(monkeypatch, extractor, **env):
    for cle in ("RECO_MODELE_EXTRACTION", "RECO_MODELE_SECOURS"):
        monkeypatch.delenv(cle, raising=False)
    for cle, valeur in env.items():
        monkeypatch.setenv(cle, valeur)
    state, recus = tne.load_state(SOURCE), []
    tne.extraire(SOURCE, recus.append, state, review_url="u", client_factory=lambda: "client",
                 extractor=extractor, lock=contextlib.nullcontext,
                 preciseur=lambda *a, **k: SimpleNamespace(precisees=[]),
                 caleur=lambda *a, **k: None)
    return state, recus


def test_la_chaine_lit_le_modele_dans_le_env(content, monkeypatch):
    vus = []
    _extraire(monkeypatch, lambda *a, model, source: vus.append(model) or 2,
              RECO_MODELE_EXTRACTION="claude-sonnet-5-5")
    assert vus == ["claude-sonnet-5-5"]


def test_un_modele_disparu_passe_au_secours_et_previent(content, monkeypatch):
    vus = []

    def extractor(*a, model, source):
        vus.append(model)
        if model == "claude-opus-5":
            raise Introuvable("model: claude-opus-5")
        return 3

    state, recus = _extraire(monkeypatch, extractor)

    assert vus == ["claude-opus-5", "claude-opus-5-5"]
    assert state["extracted"] == ["yt-abc"]
    assert "introuvable" in recus[0] and "claude-opus-5-5" in recus[0]
    assert recus[1].startswith("✅ Titre : 3 reco(s)")


def test_une_autre_erreur_ne_declenche_pas_le_secours(content, monkeypatch):
    vus = []

    def extractor(*a, model, source):
        vus.append(model)
        raise RuntimeError("panne réseau")

    state, recus = _extraire(monkeypatch, extractor)

    assert vus == ["claude-opus-5"]
    assert state["extracted"] == []
    assert "Extraction impossible" in recus[0]


def test_sans_secours_un_modele_disparu_reste_une_erreur(content, monkeypatch):
    def extractor(*a, model, source):
        raise Introuvable("model")

    state, recus = _extraire(monkeypatch, extractor, RECO_MODELE_SECOURS="aucun")

    assert state["extracted"] == []
    assert "Extraction impossible" in recus[0]


def test_l_etape_de_veille_previent_une_fois_d_une_panne(content, monkeypatch):
    recus = []
    state = tne.load_state(SOURCE)

    def client():
        raise RuntimeError("clé absente")

    assert tne.veiller_modeles(SOURCE, recus.append, state, client_factory=client) == 1
    assert tne.veiller_modeles(SOURCE, recus.append, state, client_factory=client) == 1
    assert recus == ["⚠️ Veille des modèles impossible : clé absente"]

    bon = _client(_modele("claude-opus-5", 1), _modele("claude-opus-5-5", 9))
    assert tne.veiller_modeles(SOURCE, recus.append, state, client_factory=lambda: bon) == 0
    assert "veille-modeles" not in state["lastErrors"]


def test_la_veille_se_lance_par_la_ligne_de_commande(content, monkeypatch):
    appels = []
    monkeypatch.setattr(tne, "veiller_modeles", lambda s, n, st: appels.append(s) or 0)

    assert tne.main(["veiller-modeles", "--source", SOURCE, "--notify", "none"]) == 0
    assert appels == [SOURCE]
