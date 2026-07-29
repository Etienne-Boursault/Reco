"""Tests de `tools/eval_local_llm.py` — évaluation d'un LLM local.

Le script interroge un serveur compatible OpenAI (llama-server) et compare ses
extractions aux recos de référence du projet. Il n'écrit JAMAIS dans
`src/content/recos`, et ces tests ne sortent jamais du `tmp_path` : `requests`
est doublé et tous les accès disque du module passent par des doublures.

Contrairement aux autres scripts de comparaison LLM du dossier, celui-ci a une
procédure documentée (`docs/llm-local.md`) et se rejoue à la demande : il est
donc traité comme un outil maintenu, pas comme un one-shot.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

import eval_local_llm as ell


# ===== Doublures ===========================================================
class _Resp:
    """Réponse HTTP minimale : statut, JSON, `raise_for_status`."""

    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def _completion(content: str) -> dict:
    return {"choices": [{"message": {"content": content}}]}


def _reco_payload(*titles: str) -> str:
    return json.dumps({"recos": [{"title": t, "type": "film"} for t in titles]})


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    """Redirige tous les accès disque du module vers `tmp_path`."""
    recos = tmp_path / "recos"
    episodes = tmp_path / "episodes"
    transcripts = tmp_path / "transcripts"
    for d in (recos, episodes, transcripts):
        d.mkdir(parents=True)

    monkeypatch.setattr(ell, "recos_dir_for", lambda sid: recos)
    monkeypatch.setattr(ell, "transcript_path_for",
                        lambda sid, guid: transcripts / f"{guid}.txt")
    monkeypatch.setattr(ell, "list_episode_files",
                        lambda sid: sorted(episodes.glob("*.json")))
    monkeypatch.setattr(ell, "load_source",
                        lambda sid: {"title": "Un Bon Moment",
                                     "hosts": ["Kyan", "Navo"]})
    return SimpleNamespace(recos=recos, episodes=episodes,
                           transcripts=transcripts, root=tmp_path)


def _write_reco(env, name: str, **fields) -> None:
    (env.recos / name).write_text(json.dumps(fields), encoding="utf-8")


def _write_episode(env, guid: str, *, date: str = "2026-06-01",
                   title: str = "Un épisode", transcript: str | None = None,
                   **extra) -> None:
    payload = {"guid": guid, "date": date, "title": title}
    payload.update(extra)
    (env.episodes / f"{guid}.json").write_text(json.dumps(payload),
                                               encoding="utf-8")
    if transcript is not None:
        (env.transcripts / f"{guid}.txt").write_text(transcript,
                                                     encoding="utf-8")


# ===== _load_reference_recos ===============================================
def test_reference_recos_empty_when_dir_absent(env, monkeypatch):
    monkeypatch.setattr(ell, "recos_dir_for", lambda sid: env.root / "jamais")

    assert ell._load_reference_recos("src") == {}


def test_reference_recos_grouped_by_episode(env):
    _write_reco(env, "1.json", episodeGuid="g1", title="Parasite")
    _write_reco(env, "2.json", episodeGuid="g1", title="Mortel")
    _write_reco(env, "3.json", episodeGuid="g2", title="Dune")

    refs = ell._load_reference_recos("src")

    assert sorted(refs) == ["g1", "g2"]
    assert [r["title"] for r in refs["g1"]] == ["Parasite", "Mortel"]


def test_reference_recos_exclude_discarded(env):
    """Une reco écartée n'est pas une référence : la compter ferait chuter le
    rappel du modèle local pour une œuvre que le projet a rejetée."""
    _write_reco(env, "1.json", episodeGuid="g1", title="Parasite")
    _write_reco(env, "2.json", episodeGuid="g1", title="Rejetée",
                status="discarded")

    assert [r["title"] for r in ell._load_reference_recos("src")["g1"]] == [
        "Parasite"]


def test_reference_recos_skip_unreadable_files(env):
    _write_reco(env, "1.json", episodeGuid="g1", title="Parasite")
    (env.recos / "casse.json").write_text("{ tronqué", encoding="utf-8")

    assert len(ell._load_reference_recos("src")["g1"]) == 1


def test_reference_recos_group_missing_guid_under_empty_key(env):
    _write_reco(env, "1.json", title="Sans épisode")

    assert list(ell._load_reference_recos("src")) == [""]


# ===== _select_episodes ====================================================
def test_select_episodes_keeps_recent_first_and_applies_limit(env, monkeypatch):
    for i, guid in enumerate(["g1", "g2", "g3"], 1):
        _write_reco(env, f"r{i}.json", episodeGuid=guid, title=f"Œuvre {i}")
        _write_episode(env, guid, date=f"2026-06-0{i}", transcript="texte")

    selected = ell._select_episodes("src", limit=2)

    assert [p.stem for p in selected] == ["g3", "g2"]


def test_select_episodes_skips_without_transcript(env):
    _write_reco(env, "r1.json", episodeGuid="g1", title="Œuvre")
    _write_episode(env, "g1")  # pas de transcript

    assert ell._select_episodes("src", limit=10) == []


def test_select_episodes_skips_without_reference_recos(env):
    _write_episode(env, "g1", transcript="texte")  # aucune reco de référence

    assert ell._select_episodes("src", limit=10) == []


def test_select_episodes_skips_episode_without_guid(env):
    _write_reco(env, "r1.json", episodeGuid="", title="Œuvre")
    (env.episodes / "sans-guid.json").write_text(
        json.dumps({"title": "Sans guid"}), encoding="utf-8")

    assert ell._select_episodes("src", limit=10) == []


def test_select_episodes_tolerates_missing_date(env):
    """`date` absente : l'épisode reste sélectionnable (trié en dernier)."""
    _write_reco(env, "r1.json", episodeGuid="g1", title="Œuvre 1")
    _write_reco(env, "r2.json", episodeGuid="g2", title="Œuvre 2")
    _write_episode(env, "g1", transcript="texte")
    (env.episodes / "g2.json").write_text(
        json.dumps({"guid": "g2", "title": "Sans date"}), encoding="utf-8")
    (env.transcripts / "g2.txt").write_text("texte", encoding="utf-8")

    assert [p.stem for p in ell._select_episodes("src", limit=10)] == ["g1", "g2"]


# ===== _chat_completion ====================================================
def test_chat_completion_posts_expected_payload(monkeypatch):
    seen = {}

    def _post(url, json=None, timeout=None):
        seen["url"] = url
        seen["payload"] = json
        seen["timeout"] = timeout
        return _Resp(_completion("réponse"))

    monkeypatch.setattr(ell.requests, "post", _post)

    out = ell._chat_completion("http://llm.local:8080/v1/", "modele-x",
                               "sys", "user", timeout=30, max_tokens=42)

    assert out == "réponse"
    assert seen["url"] == "http://llm.local:8080/v1/chat/completions"
    assert seen["timeout"] == 30
    assert seen["payload"]["max_tokens"] == 42
    assert seen["payload"]["temperature"] == 0.0
    assert seen["payload"]["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in seen["payload"]["messages"]] == ["system", "user"]


def test_chat_completion_retries_without_json_mode_on_400(monkeypatch):
    """Certains llama-server refusent `response_format` : on retente sans,
    plutôt que d'abandonner l'évaluation."""
    calls = []

    def _post(url, json=None, timeout=None):
        # Copie : le module retente avec le MÊME dict, dont il a retiré
        # `response_format` — sans photo, on relirait l'objet déjà muté.
        calls.append(dict(json))
        if len(calls) == 1:
            return _Resp(status_code=400, text="unsupported response_format")
        return _Resp(_completion("ok"))

    monkeypatch.setattr(ell.requests, "post", _post)

    assert ell._chat_completion("http://x/v1", "m", "s", "u", 5, 10) == "ok"
    assert "response_format" in calls[0]
    assert "response_format" not in calls[1]


def test_chat_completion_raises_on_server_error(monkeypatch):
    monkeypatch.setattr(ell.requests, "post",
                        lambda *a, **k: _Resp(status_code=500, text="boom"))

    with pytest.raises(requests.HTTPError):
        ell._chat_completion("http://x/v1", "m", "s", "u", 5, 10)


def test_chat_completion_returns_empty_string_on_null_content(monkeypatch):
    """`content: null` (modèle qui n'a rien produit) → chaîne vide, pas None :
    l'appelant fait un parse JSON dessus."""
    monkeypatch.setattr(
        ell.requests, "post",
        lambda *a, **k: _Resp({"choices": [{"message": {"content": None}}]}))

    assert ell._chat_completion("http://x/v1", "m", "s", "u", 5, 10) == ""


# ===== _extract_chunk ======================================================
def test_extract_chunk_normalizes_recos(monkeypatch):
    monkeypatch.setattr(
        ell, "_chat_completion",
        lambda *a, **k: _reco_payload("Parasite", "Mortel"))

    out = ell._extract_chunk("http://x/v1", "m", "Podcast", "Kyan",
                             "chunk", 5, 10)

    assert [r["title"] for r in out] == ["Parasite", "Mortel"]
    assert out[0]["types"] == ["film"]


def test_extract_chunk_returns_empty_on_non_json_answer(monkeypatch, caplog):
    """Un modèle local qui bavarde au lieu de répondre en JSON ne doit pas
    interrompre l'évaluation."""
    monkeypatch.setattr(ell, "_chat_completion",
                        lambda *a, **k: "Bien sûr ! Voici mes réflexions…")

    with caplog.at_level("WARNING", logger="reco"):
        assert ell._extract_chunk("http://x/v1", "m", "P", "K", "c", 5, 10) == []

    assert "non JSON" in caplog.text


def test_extract_chunk_ignores_non_dict_payload(monkeypatch):
    monkeypatch.setattr(ell, "_chat_completion", lambda *a, **k: "[1, 2, 3]")

    assert ell._extract_chunk("http://x/v1", "m", "P", "K", "c", 5, 10) == []


def test_extract_chunk_drops_untitled_entries(monkeypatch):
    monkeypatch.setattr(
        ell, "_chat_completion",
        lambda *a, **k: json.dumps({"recos": [{"title": ""}, {"title": "Dune"}]}))

    out = ell._extract_chunk("http://x/v1", "m", "P", "K", "c", 5, 10)

    assert [r["title"] for r in out] == ["Dune"]


def test_extract_chunk_asks_for_no_think_mode(monkeypatch):
    """Le préfixe `/no_think` et la consigne système évitent que Qwen3 noie sa
    réponse JSON dans son raisonnement."""
    seen = {}

    def _fake(base_url, model, system, user, timeout, max_tokens):
        seen["system"] = system
        seen["user"] = user
        return _reco_payload("Dune")

    monkeypatch.setattr(ell, "_chat_completion", _fake)
    ell._extract_chunk("http://x/v1", "m", "Podcast", "Kyan", "texte", 5, 10)

    assert seen["user"].startswith("/no_think\n")
    assert "/no_think" in seen["system"]
    assert "Podcast" in seen["user"]


# ===== _title_match ========================================================
@pytest.mark.parametrize("a, b, expected", [
    ("Parasite", "parasite", True),           # casse ignorée
    ("Un Bon Moment", "Un bon moment !", True),  # ponctuation ignorée
    ("Kaamelott", "Kaamelot", True),          # coquille → fuzzy (0.94)
    ("Le Parrain", "Le Parrain 2", True),     # 0.91, juste au-dessus du seuil
    ("Parasite", "Dune", False),
    ("", "Parasite", False),
    ("Parasite", "", False),
    ("!!!", "Parasite", False),               # normalisation → chaîne vide
])
def test_title_match(a, b, expected):
    assert ell._title_match(a, b) is expected


@pytest.mark.parametrize("a, b", [
    ("Parasite", "Parasite (2019)"),   # 0.76
    ("Dune", "Dune : partie 2"),       # 0.47
    ("Mortel", "Mortelle"),            # 0.86, juste sous le seuil
])
def test_title_match_rejects_below_the_fuzzy_threshold(a, b):
    """Le seuil de 0.88 est strict par choix : un titre suffixé d'une année ou
    d'un numéro de partie compte comme une AUTRE œuvre. Ces cas sont donc des
    non-matchs assumés, pas des ratés — les figer évite qu'on desserre le seuil
    sans s'en rendre compte."""
    assert ell._title_match(a, b) is False


# ===== _compare ============================================================
def test_compare_counts_matches_extras_and_misses():
    local = [{"title": "Parasite"}, {"title": "Inventé"}]
    ref = [{"title": "parasite"}, {"title": "Mortel"}]

    out = ell._compare(local, ref)

    assert out["matched_count"] == 1
    assert out["extra_local_titles"] == ["Inventé"]
    assert out["missed_reference_titles"] == ["Mortel"]
    assert out["recall"] == 0.5
    assert out["precision_proxy"] == 0.5
    assert out["matches"] == [{"local": "Parasite", "reference": "parasite"}]


def test_compare_does_not_reuse_a_reference_twice():
    """Deux extractions du même titre ne doivent pas matcher la même référence
    (sinon le rappel serait surévalué)."""
    local = [{"title": "Parasite"}, {"title": "Parasite"}]
    ref = [{"title": "Parasite"}]

    out = ell._compare(local, ref)

    assert out["matched_count"] == 1
    assert out["extra_local_titles"] == ["Parasite"]


def test_compare_ratios_are_zero_without_data():
    empty = ell._compare([], [])

    assert empty["recall"] == 0.0
    assert empty["precision_proxy"] == 0.0
    assert empty["matched_count"] == 0


def test_compare_handles_titleless_entries():
    out = ell._compare([{}], [{}])

    assert out["matched_count"] == 0
    assert out["extra_local_titles"] == [""]


# ===== evaluate ============================================================
def _args(**overrides) -> argparse.Namespace:
    base = dict(
        source="src", limit=10, base_url="http://x/v1", model="m",
        chunk_chars=8000, chunk_overlap_chars=500, max_chunks=None,
        max_tokens=100, timeout=30, output=None, dry_run=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_evaluate_aggregates_totals(env, monkeypatch):
    _write_reco(env, "r1.json", episodeGuid="g1", title="Parasite")
    _write_reco(env, "r2.json", episodeGuid="g1", title="Mortel")
    _write_episode(env, "g1", transcript="00:00:00 bla bla")
    monkeypatch.setattr(ell, "_extract_chunk",
                        lambda *a, **k: [{"title": "Parasite", "types": ["film"]}])

    report = ell.evaluate(_args())

    assert report["summary"]["episode_count"] == 1
    assert report["summary"]["reference_count"] == 2
    assert report["summary"]["matched_count"] == 1
    assert report["summary"]["recall"] == 0.5
    assert report["summary"]["precision_proxy"] == 1.0
    assert report["episodes"][0]["guid"] == "g1"
    assert report["episodes"][0]["chunk_errors"] == []


def test_evaluate_without_episodes_returns_zero_ratios(env):
    report = ell.evaluate(_args())

    assert report["summary"]["episode_count"] == 0
    assert report["summary"]["recall"] == 0.0
    assert report["summary"]["precision_proxy"] == 0.0
    assert report["episodes"] == []


def test_evaluate_records_chunk_errors_and_continues(env, monkeypatch, caplog):
    """Un chunk qui échoue côté serveur est journalisé et l'évaluation
    continue : un timeout ne doit pas jeter tout le lot."""
    _write_reco(env, "r1.json", episodeGuid="g1", title="Parasite")
    _write_episode(env, "g1", transcript="00:00:00 bla")

    def _boom(*a, **k):
        raise requests.ConnectionError("llama-server injoignable")

    monkeypatch.setattr(ell, "_extract_chunk", _boom)

    with caplog.at_level("ERROR", logger="reco"):
        report = ell.evaluate(_args())

    errors = report["episodes"][0]["chunk_errors"]
    assert len(errors) == 1
    assert "injoignable" in errors[0]["error"]
    assert report["summary"]["local_count"] == 0


def test_evaluate_includes_response_body_in_chunk_error(env, monkeypatch):
    """Quand le serveur a répondu, son corps (tronqué) est joint à l'erreur —
    c'est là que llama-server explique le refus."""
    _write_reco(env, "r1.json", episodeGuid="g1", title="Parasite")
    _write_episode(env, "g1", transcript="00:00:00 bla")

    def _boom(*a, **k):
        raise requests.HTTPError("400 Bad Request",
                                 response=_Resp(status_code=400,
                                                text="contexte trop long" * 100))

    monkeypatch.setattr(ell, "_extract_chunk", _boom)

    message = ell.evaluate(_args())["episodes"][0]["chunk_errors"][0]["error"]

    assert "::" in message
    assert "contexte trop long" in message
    assert len(message) < 700  # corps tronqué à 500 caractères


def test_evaluate_honours_max_chunks(env, monkeypatch):
    """`--max-chunks` borne le coût d'une évaluation exploratoire."""
    _write_reco(env, "r1.json", episodeGuid="g1", title="Parasite")
    _write_episode(env, "g1", transcript="\n".join(
        f"00:00:{i:02d} ligne {i}" for i in range(200)))
    calls = []
    monkeypatch.setattr(ell, "_extract_chunk",
                        lambda *a, **k: calls.append(1) or [])

    report = ell.evaluate(_args(chunk_chars=200, max_chunks=2))

    assert len(calls) == 2
    assert report["episodes"][0]["chunk_count"] == 2


def test_evaluate_falls_back_to_youtube_title(env, monkeypatch):
    """Titre RSS absent : on retombe sur le titre YouTube (politique Story 3 —
    le titre RSS prime quand il existe)."""
    _write_reco(env, "r1.json", episodeGuid="g1", title="Parasite")
    (env.episodes / "g1.json").write_text(json.dumps({
        "guid": "g1", "date": "2026-06-01", "youtubeTitle": "S5·E1 — Spécial",
    }), encoding="utf-8")
    (env.transcripts / "g1.txt").write_text("00:00:00 bla", encoding="utf-8")
    monkeypatch.setattr(ell, "_extract_chunk", lambda *a, **k: [])

    report = ell.evaluate(_args())

    assert report["episodes"][0]["title"] == "S5·E1 — Spécial"


# ===== main ================================================================
def test_main_dry_run_lists_without_calling_the_llm(env, monkeypatch, capsys):
    _write_reco(env, "r1.json", episodeGuid="g1", title="Parasite")
    _write_episode(env, "g1", title="Épisode Un", transcript="texte")
    monkeypatch.setattr(ell.requests, "post", lambda *a, **k: pytest.fail(
        "--dry-run ne doit appeler aucun serveur"))
    monkeypatch.setattr(ell, "write_json_if_changed", lambda p, d: pytest.fail(
        "--dry-run ne doit rien écrire"))
    monkeypatch.setattr("sys.argv", ["eval_local_llm.py", "--dry-run"])

    ell.main()

    out = capsys.readouterr().out
    assert "g1" in out
    assert "1 recos" in out
    assert "Épisode Un" in out


def test_main_writes_the_report(env, monkeypatch):
    _write_reco(env, "r1.json", episodeGuid="g1", title="Parasite")
    _write_episode(env, "g1", transcript="00:00:00 bla")
    monkeypatch.setattr(ell, "_extract_chunk",
                        lambda *a, **k: [{"title": "Parasite", "types": ["film"]}])
    written = {}
    monkeypatch.setattr(ell, "write_json_if_changed",
                        lambda p, d: written.update(path=p, data=d))
    out_path = env.root / "rapport.json"
    monkeypatch.setattr("sys.argv",
                        ["eval_local_llm.py", "--output", str(out_path)])

    ell.main()

    assert written["path"] == out_path
    assert written["data"]["summary"]["matched_count"] == 1


def test_main_default_output_path_is_derived(env, monkeypatch):
    """Sans `--output`, le rapport va dans `tools/output/local_llm_eval/` avec
    source, modèle et horodatage dans le nom."""
    _write_reco(env, "r1.json", episodeGuid="g1", title="Parasite")
    _write_episode(env, "g1", transcript="00:00:00 bla")
    monkeypatch.setattr(ell, "_extract_chunk", lambda *a, **k: [])
    monkeypatch.setattr(ell, "OUTPUT_DIR", env.root / "eval-out")
    written = {}
    monkeypatch.setattr(ell, "write_json_if_changed",
                        lambda p, d: written.update(path=p))
    monkeypatch.setattr("sys.argv",
                        ["eval_local_llm.py", "--model", "qwen3-4b"])

    ell.main()

    assert written["path"].parent == env.root / "eval-out"
    assert written["path"].name.startswith("un-bon-moment-qwen3-4b-")
    assert (env.root / "eval-out").is_dir()
