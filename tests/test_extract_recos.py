"""Tests pour `tools/extract_recos.py`.

Couvre les briques pures (`_norm`, `_dedupe`, `_chunk_transcript`,
`_extract_json_block`, `_normalize_reco`) et les fonctions de haut niveau
(`extract_for_episode`, `extract_all_batch`, `main`) en mockant les clients
LLM (Anthropic + OpenAI) — aucun appel réseau réel.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import common
import extract_recos
from extract_recos import (
    _chunk_transcript,
    _dedupe,
    _extract_json_block,
    _find_episode_by_guid,
    _next_reco_index,
    _norm,
    _normalize_reco,
    _parse_recos_from_content,
    _persist_recos,
    extract_all_batch,
    extract_for_episode,
    main,
)


# ===== Fixtures ============================================================
@pytest.fixture
def tmp_source(tmp_path: Path, monkeypatch):
    """Crée un mini répertoire projet (sources, épisodes, recos, transcripts).

    Renvoie un objet avec : `source_id`, `guid`, `episode_path`, `transcript_path`,
    `recos_dir`, et `transcript_text` initial.
    """
    # Réorganise les constantes de chemins pour pointer dans tmp_path.
    content = tmp_path / "src" / "content"
    sources_dir = content / "sources"
    episodes_dir = content / "episodes"
    recos_dir = content / "recos"
    transcripts_dir = tmp_path / "tools" / "output" / "transcripts"
    for d in (sources_dir, episodes_dir, recos_dir, transcripts_dir):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(common, "SOURCES_DIR", sources_dir)
    monkeypatch.setattr(common, "EPISODES_DIR", episodes_dir)
    monkeypatch.setattr(common, "RECOS_DIR", recos_dir)
    monkeypatch.setattr(common, "TRANSCRIPTS_DIR", transcripts_dir)

    source_id = "un-bon-moment"
    guid = "EP001"

    # Source : meta basique.
    (sources_dir / f"{source_id}.json").write_text(
        json.dumps({"id": source_id, "title": "Un Bon Moment",
                    "hosts": ["Kyan Khojandi", "Navo"]}),
        encoding="utf-8",
    )

    # Épisode JSON.
    src_episodes = episodes_dir / source_id
    src_episodes.mkdir(parents=True, exist_ok=True)
    ep_path = src_episodes / "0001.json"
    ep_path.write_text(json.dumps({"guid": guid, "title": "Pilote"}),
                       encoding="utf-8")

    # Transcription : 2 chunks via CHUNK_CHARS petit.
    trans_dir = transcripts_dir / source_id
    trans_dir.mkdir(parents=True, exist_ok=True)
    transcript_text = "Ligne 1.\nLigne 2.\nLigne 3.\n"
    trans_path = trans_dir / f"{guid}.txt"
    trans_path.write_text(transcript_text, encoding="utf-8")

    # Recos cible.
    recos_for = recos_dir / source_id
    recos_for.mkdir(parents=True, exist_ok=True)

    return SimpleNamespace(
        source_id=source_id, guid=guid, episode_path=ep_path,
        transcript_path=trans_path, recos_dir=recos_for,
        transcript_text=transcript_text,
    )


def _fake_anthropic_message(payload: dict):
    """Construit un faux message Anthropic avec blocs de contenu texte."""
    block = SimpleNamespace(type="text", text=json.dumps(payload))
    return SimpleNamespace(content=[block])


def _fake_openai_response(payload: dict | str):
    """Construit une fausse réponse OpenAI Chat Completions."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    choice = SimpleNamespace(message=SimpleNamespace(content=raw))
    return SimpleNamespace(choices=[choice])


# ===== _norm ===============================================================
def test_norm_strips_accents_case_punct():
    expected = _norm("Mortel")
    assert _norm("MORTEL") == expected
    assert _norm("mortél") == expected
    assert _norm("mortel.") == expected


def test_norm_collapses_whitespace():
    assert _norm("Full   Metal   Jacket") == _norm("Full Metal Jacket")


@pytest.mark.parametrize("inp,exp", [("", ""), (None, ""), ("   ", "")])
def test_norm_empty_or_none(inp, exp):
    assert _norm(inp) == exp


def test_norm_keeps_digits():
    assert "2001" in _norm("2001 : l'Odyssée de l'espace")


# ===== _dedupe =============================================================
def test_dedupe_collapses_and_merges():
    recos = [
        {"title": "Mortel", "creator": None},
        {"title": "MORTEL", "creator": "Frédéric Garcia"},
    ]
    out = _dedupe(recos)
    assert len(out) == 1
    assert out[0]["creator"] == "Frédéric Garcia"


def test_dedupe_keeps_distinct_titles():
    out = _dedupe([{"title": "A"}, {"title": "B"}])
    assert len(out) == 2


def test_dedupe_preserves_first_when_both_have_field():
    recos = [
        {"title": "X", "creator": "Alice"},
        {"title": "X", "creator": "Bob"},
    ]
    out = _dedupe(recos)
    assert out[0]["creator"] == "Alice"


# ===== _chunk_transcript ===================================================
def test_chunk_transcript_single_chunk():
    text = "abc\ndef\n"
    assert _chunk_transcript(text, max_chars=100) == [text]


def test_chunk_transcript_splits_on_lines():
    text = "AAAA\nBBBB\nCCCC\n"
    chunks = _chunk_transcript(text, max_chars=6)
    # Chaque ligne fait 5 chars, donc on doit obtenir plusieurs chunks.
    assert len(chunks) >= 2
    assert "".join(chunks) == text


def test_chunk_transcript_empty():
    assert _chunk_transcript("") == [""]


# ===== _extract_json_block =================================================
def test_extract_json_plain():
    assert _extract_json_block('{"a": 1}') == {"a": 1}


def test_extract_json_with_fence():
    raw = '```json\n{"a": 2}\n```'
    assert _extract_json_block(raw) == {"a": 2}


def test_extract_json_with_surrounding_text():
    raw = 'Voici le résultat : {"a": 3} et voilà.'
    assert _extract_json_block(raw) == {"a": 3}


def test_extract_json_invalid_raises():
    with pytest.raises(json.JSONDecodeError):
        _extract_json_block("pas du json du tout")


# ===== _normalize_reco =====================================================
def test_normalize_reco_minimal():
    r = _normalize_reco({"title": "Foo", "type": "film"})
    assert r == {"title": "Foo", "type": "film"}


def test_normalize_reco_no_title_returns_none():
    assert _normalize_reco({"title": "  ", "type": "film"}) is None
    assert _normalize_reco({}) is None


def test_normalize_reco_invalid_type_becomes_autre():
    r = _normalize_reco({"title": "Foo", "type": "n_importe_quoi"})
    assert r["type"] == "autre"


def test_normalize_reco_strips_optional_fields():
    r = _normalize_reco({
        "title": "Foo", "type": "film",
        "creator": "  Réa  ", "quote": "", "timestamp": "00:01:00",
        "recommendedBy": None,
    })
    assert r["creator"] == "Réa"
    assert r["timestamp"] == "00:01:00"
    assert "quote" not in r
    assert "recommendedBy" not in r


@pytest.mark.parametrize("year_in,year_out", [
    (1984, 1984),
    ("1984", 1984),
    ("pas une annee", None),
    (None, None),
])
def test_normalize_reco_year_variants(year_in, year_out):
    r = _normalize_reco({"title": "Foo", "type": "film", "year": year_in})
    assert r.get("year") == year_out


# ===== _parse_recos_from_content ===========================================
def test_parse_recos_from_content_ok():
    msg = _fake_anthropic_message({"recos": [{"title": "X", "type": "film"}]})
    out = _parse_recos_from_content(msg.content)
    assert out == [{"title": "X", "type": "film"}]


def test_parse_recos_from_content_bad_json():
    block = SimpleNamespace(type="text", text="pas du json")
    out = _parse_recos_from_content([block])
    assert out == []


def test_parse_recos_from_content_not_dict():
    block = SimpleNamespace(type="text", text='[1,2,3]')
    # `[1,2,3]` n'est pas un dict mais reste un JSON valide.
    # _extract_json_block extrait via regex `\{.*\}` -> non match -> json.loads([1,2,3]) -> list -> renvoie [].
    out = _parse_recos_from_content([block])
    assert out == []


# ===== _next_reco_index + _persist_recos ===================================
def test_next_reco_index_empty(tmp_source):
    assert _next_reco_index(tmp_source.source_id) == 1


def test_next_reco_index_with_files(tmp_source):
    (tmp_source.recos_dir / "0003.json").write_text("{}", encoding="utf-8")
    (tmp_source.recos_dir / "0001.json").write_text("{}", encoding="utf-8")
    assert _next_reco_index(tmp_source.source_id) == 4


def test_persist_recos_new(tmp_source):
    raw = [{"title": "Mortel", "type": "serie", "creator": "F. Garcia",
            "year": 2019, "timestamp": "00:42:00"}]
    n = _persist_recos(tmp_source.source_id, tmp_source.guid, raw,
                       provider="anthropic")
    assert n == 1
    files = list(tmp_source.recos_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["title"] == "Mortel"
    assert data["status"] == "draft"
    assert data["links"] == []
    assert data["extractors"] == ["anthropic"]
    assert data["id"].startswith("ubm-")


def test_persist_recos_empty_returns_zero(tmp_source):
    assert _persist_recos(tmp_source.source_id, tmp_source.guid, [], "anthropic") == 0


def test_persist_recos_invalid_titles_filtered(tmp_source):
    # Tout est filtré au normalize -> 0 écrit.
    raw = [{"title": "", "type": "film"}, {"title": "  "}]
    assert _persist_recos(tmp_source.source_id, tmp_source.guid, raw, "anthropic") == 0


def test_persist_recos_upsert_updates(tmp_source):
    # 1er passage : crée.
    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Mortel", "type": "serie", "timestamp": "00:10:00"}],
                   "anthropic")
    # 2e passage : même reco mais nouveau timestamp + nouveau provider.
    n = _persist_recos(tmp_source.source_id, tmp_source.guid,
                       [{"title": "Mortel", "type": "serie", "creator": "F. Garcia",
                         "timestamp": "00:11:00", "quote": "j'ai adoré"}],
                       "openai")
    assert n == 1
    files = list(tmp_source.recos_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    assert data["timestamp"] == "00:11:00"
    assert data["creator"] == "F. Garcia"
    assert sorted(data["extractors"]) == ["anthropic", "openai"]
    assert data["quote"] == "j'ai adoré"


def test_persist_recos_preserves_validated_quote(tmp_source):
    # Reco déjà validée : son quote ne doit pas être écrasé.
    existing = {
        "id": "ubm-0001", "sourceId": tmp_source.source_id,
        "episodeGuid": tmp_source.guid,
        "title": "Mortel", "type": "serie",
        "quote": "citation curée à la main",
        "links": [], "status": "validated", "extractors": ["anthropic"],
    }
    (tmp_source.recos_dir / "0001.json").write_text(
        json.dumps(existing, ensure_ascii=False), encoding="utf-8")

    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Mortel", "type": "serie",
                     "quote": "nouvelle citation auto", "timestamp": "00:12:00"}],
                   "anthropic")
    data = json.loads((tmp_source.recos_dir / "0001.json").read_text(encoding="utf-8"))
    assert data["quote"] == "citation curée à la main"
    # Timestamp est toujours mis à jour.
    assert data["timestamp"] == "00:12:00"


def test_persist_recos_skips_corrupted_existing_file(tmp_source):
    # Fichier corrompu dans recos_dir : indexé via try/except, ignoré.
    (tmp_source.recos_dir / "0099.json").write_text("PAS DU JSON", encoding="utf-8")
    n = _persist_recos(tmp_source.source_id, tmp_source.guid,
                       [{"title": "Foo", "type": "film"}], "anthropic")
    assert n == 1


# ===== extract_for_episode (sync) ==========================================
def test_extract_for_episode_dry_run(tmp_source, caplog):
    n = extract_for_episode(tmp_source.source_id, tmp_source.episode_path,
                            client=None, dry_run=True)
    assert n == 0


def test_extract_for_episode_no_transcript(tmp_source):
    tmp_source.transcript_path.unlink()
    n = extract_for_episode(tmp_source.source_id, tmp_source.episode_path,
                            client=MagicMock(), dry_run=False)
    assert n == 0


def test_extract_for_episode_client_none_raises(tmp_source):
    with pytest.raises(RuntimeError, match="Client Anthropic"):
        extract_for_episode(tmp_source.source_id, tmp_source.episode_path,
                            client=None, dry_run=False)


def test_extract_for_episode_anthropic_sync(tmp_source):
    client = MagicMock(spec=["messages"])
    # `hasattr(client, "chat")` doit être False -> on utilise spec sans 'chat'.
    client.messages.create.return_value = _fake_anthropic_message(
        {"recos": [{"title": "Mortel", "type": "serie"}]}
    )
    n = extract_for_episode(tmp_source.source_id, tmp_source.episode_path,
                            client=client, dry_run=False)
    assert n == 1
    assert client.messages.create.called


def test_extract_for_episode_openai_sync(tmp_source):
    # Client OpenAI : a un attribut .chat.
    client = MagicMock()
    # On veut que hasattr(client, "chat") -> True (MagicMock l'a par défaut).
    client.chat.completions.create.return_value = _fake_openai_response(
        {"recos": [{"title": "Hozier", "type": "artiste"}]}
    )
    n = extract_for_episode(tmp_source.source_id, tmp_source.episode_path,
                            client=client, dry_run=False, provider="openai",
                            model="gpt-4o-mini")
    assert n == 1
    client.chat.completions.create.assert_called_once()


def test_extract_for_episode_openai_bad_json(tmp_source):
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response(
        "ceci n'est pas du JSON valide"
    )
    n = extract_for_episode(tmp_source.source_id, tmp_source.episode_path,
                            client=client, dry_run=False, provider="openai")
    # Aucune reco extraite -> 0 fichier.
    assert n == 0


def test_extract_for_episode_anthropic_bad_json(tmp_source):
    client = MagicMock(spec=["messages"])
    block = SimpleNamespace(type="text", text="pas du json")
    client.messages.create.return_value = SimpleNamespace(content=[block])
    n = extract_for_episode(tmp_source.source_id, tmp_source.episode_path,
                            client=client, dry_run=False)
    assert n == 0


# ===== extract_all_batch ===================================================
def test_extract_all_batch_basic(tmp_source):
    client = MagicMock(spec=["messages"])
    # 1er retrieve -> in_progress ; 2e -> ended.
    client.messages.batches.create.return_value = SimpleNamespace(id="batch_abc")
    client.messages.batches.retrieve.side_effect = [
        SimpleNamespace(processing_status="in_progress"),
        SimpleNamespace(processing_status="ended"),
    ]
    # Résultats : 1 succès + 1 échec.
    ok_msg = _fake_anthropic_message({"recos": [{"title": "Mortel", "type": "serie"}]})
    ok_entry = SimpleNamespace(
        custom_id="req-0",
        result=SimpleNamespace(type="succeeded",
                               message=SimpleNamespace(content=ok_msg.content)),
    )
    bad_entry = SimpleNamespace(
        custom_id="inconnu",  # custom_id non mappé -> ignoré
        result=SimpleNamespace(type="errored"),
    )
    err_entry = SimpleNamespace(
        custom_id="req-1",
        result=SimpleNamespace(type="errored"),
    )
    # Forcer plus de chunks pour avoir req-1 : on monkey-patche CHUNK_CHARS.
    with patch.object(extract_recos, "CHUNK_CHARS", 10):
        client.messages.batches.results.return_value = [ok_entry, bad_entry, err_entry]
        n = extract_all_batch(tmp_source.source_id, [tmp_source.episode_path],
                              client=client, poll_seconds=0)
    assert n == 1


def test_extract_all_batch_no_transcript(tmp_source):
    tmp_source.transcript_path.unlink()
    client = MagicMock()
    n = extract_all_batch(tmp_source.source_id, [tmp_source.episode_path],
                          client=client, poll_seconds=0)
    assert n == 0
    client.messages.batches.create.assert_not_called()


# ===== _find_episode_by_guid ===============================================
def test_find_episode_by_guid_ok(tmp_source):
    p = _find_episode_by_guid(tmp_source.source_id, tmp_source.guid)
    assert p == tmp_source.episode_path


def test_find_episode_by_guid_missing(tmp_source):
    with pytest.raises(FileNotFoundError):
        _find_episode_by_guid(tmp_source.source_id, "GUID_INEXISTANT")


# ===== main() ==============================================================
def _run_main(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", argv)
    main()


def test_main_dry_run_guid(tmp_source, monkeypatch):
    _run_main(monkeypatch, [
        "extract_recos.py", "--source", tmp_source.source_id,
        "--guid", tmp_source.guid, "--dry-run",
    ])
    # Dry-run : aucun fichier reco créé.
    assert list(tmp_source.recos_dir.glob("*.json")) == []


def test_main_anthropic_sync(tmp_source, monkeypatch):
    fake_client = MagicMock(spec=["messages"])
    fake_client.messages.create.return_value = _fake_anthropic_message(
        {"recos": [{"title": "Truc", "type": "film"}]}
    )
    monkeypatch.setattr(extract_recos, "_make_client", lambda: fake_client)
    _run_main(monkeypatch, [
        "extract_recos.py", "--source", tmp_source.source_id,
        "--guid", tmp_source.guid,
    ])
    assert len(list(tmp_source.recos_dir.glob("*.json"))) == 1


def test_main_openai_switches_default_model(tmp_source, monkeypatch):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_openai_response(
        {"recos": [{"title": "Truc", "type": "film"}]}
    )
    monkeypatch.setattr(extract_recos, "_make_openai_client", lambda: fake_client)
    _run_main(monkeypatch, [
        "extract_recos.py", "--source", tmp_source.source_id,
        "--guid", tmp_source.guid, "--provider", "openai",
    ])
    # Le modèle envoyé doit être gpt-4o-mini (switch auto).
    kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-4o-mini"


def test_main_openai_batch_warning(tmp_source, monkeypatch, caplog):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_openai_response(
        {"recos": []}
    )
    monkeypatch.setattr(extract_recos, "_make_openai_client", lambda: fake_client)
    # --batch + --provider openai : doit warn et basculer en sync.
    _run_main(monkeypatch, [
        "extract_recos.py", "--source", tmp_source.source_id,
        "--guid", tmp_source.guid, "--provider", "openai", "--batch",
    ])
    fake_client.chat.completions.create.assert_called()


def test_main_all_with_limit(tmp_source, monkeypatch):
    # Ajoute un 2e épisode pour tester --limit.
    src_ep_dir = tmp_source.episode_path.parent
    ep2 = src_ep_dir / "0002.json"
    ep2.write_text(json.dumps({"guid": "EP002"}), encoding="utf-8")
    # Pas de transcript pour EP002 -> il sera silently skipped (return 0).
    fake_client = MagicMock(spec=["messages"])
    fake_client.messages.create.return_value = _fake_anthropic_message({"recos": []})
    monkeypatch.setattr(extract_recos, "_make_client", lambda: fake_client)
    _run_main(monkeypatch, [
        "extract_recos.py", "--source", tmp_source.source_id,
        "--all", "--limit", "1",
    ])
    # 1 seul épisode traité -> 1 appel create.
    assert fake_client.messages.create.call_count == 1


def test_main_batch_mode(tmp_source, monkeypatch):
    fake_client = MagicMock(spec=["messages"])
    fake_client.messages.batches.create.return_value = SimpleNamespace(id="b1")
    fake_client.messages.batches.retrieve.return_value = SimpleNamespace(
        processing_status="ended"
    )
    ok_msg = _fake_anthropic_message({"recos": [{"title": "B", "type": "film"}]})
    fake_client.messages.batches.results.return_value = [
        SimpleNamespace(custom_id="req-0",
                        result=SimpleNamespace(
                            type="succeeded",
                            message=SimpleNamespace(content=ok_msg.content))),
    ]
    monkeypatch.setattr(extract_recos, "_make_client", lambda: fake_client)
    _run_main(monkeypatch, [
        "extract_recos.py", "--source", tmp_source.source_id,
        "--all", "--batch", "--poll-interval", "0",
    ])
    fake_client.messages.batches.create.assert_called_once()


def test_main_episode_extraction_failure_is_logged(tmp_source, monkeypatch, caplog):
    # Force extract_for_episode à lever -> main() doit attraper et continuer.
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(extract_recos, "extract_for_episode", boom)
    fake_client = MagicMock(spec=["messages"])
    monkeypatch.setattr(extract_recos, "_make_client", lambda: fake_client)
    _run_main(monkeypatch, [
        "extract_recos.py", "--source", tmp_source.source_id,
        "--guid", tmp_source.guid,
    ])
    # Pas d'exception remontée jusqu'ici -> test OK.


# ===== _make_client / _make_openai_client (erreurs clés API) ===============
def test_make_client_missing_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # On empêche load_dotenv de réécrire la variable.
    monkeypatch.setattr(extract_recos, "load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        extract_recos._make_client()


def test_make_openai_client_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(extract_recos, "load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        extract_recos._make_openai_client()


def test_make_client_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(extract_recos, "load_dotenv", lambda *a, **k: None)
    fake_anthropic = MagicMock()
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)
    extract_recos._make_client()
    fake_anthropic.Anthropic.assert_called_once_with(api_key="fake-key")


def test_make_openai_client_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setattr(extract_recos, "load_dotenv", lambda *a, **k: None)
    fake_openai = MagicMock()
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    extract_recos._make_openai_client()
    fake_openai.OpenAI.assert_called_once_with(api_key="fake-key")
