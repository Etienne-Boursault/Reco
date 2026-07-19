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
from common import find_episode_by_guid as _find_episode_by_guid  # alias local
from extract_recos import (
    _AnthropicExtractor,
    _OpenAIExtractor,
    _RunIndex,
    _call_anthropic,
    _call_openai,
    _chunk_transcript,
    _dedupe,
    _extract_json_block,
    _make_extractor,
    _next_reco_index,
    _norm,
    _normalize_reco,
    _parse_recos_from_content,
    _persist_recos,
    _poll_batch_until_done,
    extract_all_batch,
    extract_for_episode,
    main,
    new_run_index,
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


def test_dedupe_merges_types_union():
    """Même titre, types différents → union dédupliquée (ordre stable)."""
    out = _dedupe([
        {"title": "Dune", "types": ["livre"]},
        {"title": "DUNE", "types": ["film", "livre"]},
    ])
    assert len(out) == 1
    assert out[0]["types"] == ["livre", "film"]


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
    # overlap_chars=0 : pas de recouvrement, on peut tester l'invariant
    # « la concat des chunks reproduit le texte d'origine ».
    chunks = _chunk_transcript(text, max_chars=6, overlap_chars=0)
    assert len(chunks) >= 2
    assert "".join(chunks) == text


def test_chunk_transcript_overlap_repeats_last_lines():
    """Avec un overlap > 0, le début du chunk N+1 reprend la fin du chunk N."""
    text = "AAAA\nBBBB\nCCCC\nDDDD\n"
    chunks = _chunk_transcript(text, max_chars=6, overlap_chars=5)
    # On a forcément au moins 2 chunks et le 2e doit commencer par un fragment
    # déjà présent à la fin du 1er (le recouvrement préserve les recos à cheval).
    assert len(chunks) >= 2
    assert any(line in chunks[1] for line in chunks[0].splitlines(keepends=True))


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
    # L'INPUT du LLM utilise `type` singulier (interface du prompt) ; la sortie
    # normalisée Python utilise `types` (liste, schéma interne).
    r = _normalize_reco({"title": "Foo", "type": "film"})
    assert r == {"title": "Foo", "types": ["film"]}


def test_normalize_reco_no_title_returns_none():
    assert _normalize_reco({"title": "  ", "type": "film"}) is None
    assert _normalize_reco({}) is None


def test_normalize_reco_invalid_type_becomes_autre():
    r = _normalize_reco({"title": "Foo", "type": "n_importe_quoi"})
    assert r["types"] == ["autre"]


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
    # Le LLM renvoie `type` singulier (interface du prompt) ; pass-through brut.
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


def test_next_reco_index_when_dir_absent(tmp_source, monkeypatch):
    """Dossier recos absent → prochain index = 1 (pas de crash)."""
    import common
    monkeypatch.setattr(common, "RECOS_DIR", tmp_source.recos_dir.parent / "vide")
    assert _next_reco_index("source-sans-dossier") == 1


def test_build_existing_index_skips_corrupted_file(tmp_source):
    """Un fichier reco corrompu est ignoré silencieusement à l'indexation."""
    (tmp_source.recos_dir / "0001.json").write_text(
        json.dumps({"episodeGuid": "G", "title": "Bon"}), encoding="utf-8")
    (tmp_source.recos_dir / "0002.json").write_text("PAS DU JSON", encoding="utf-8")
    idx = extract_recos._build_existing_index(tmp_source.source_id)
    assert ("G", "bon") in idx
    assert len(idx) == 1  # le corrompu n'est pas indexé


def test_build_existing_index_empty_when_dir_absent(tmp_source, monkeypatch):
    """Dossier recos absent → index vide (pas de crash)."""
    import common
    monkeypatch.setattr(common, "RECOS_DIR", tmp_source.recos_dir.parent / "absent")
    assert extract_recos._build_existing_index("src-x") == {}


def test_next_reco_index_anchors_regex_ignores_non_numeric_prefix(tmp_source):
    """L6 (revue 2026-07-19) — regex ANCRÉE (^\\d+) : un stem à préfixe non
    numérique (ou à chiffres internes) est ignoré, seul le préfixe chiffré
    des fichiers « NNNN.json » compte."""
    (tmp_source.recos_dir / "0005.json").write_text("{}", encoding="utf-8")
    # Stems piégeurs : sans ancre, la recherche capterait « 42 » / « 99 ».
    (tmp_source.recos_dir / "note-42.json").write_text("{}", encoding="utf-8")
    (tmp_source.recos_dir / "manual.json").write_text("{}", encoding="utf-8")
    (tmp_source.recos_dir / "take-99.json").write_text("{}", encoding="utf-8")
    assert _next_reco_index(tmp_source.source_id) == 6


def test_persist_recos_new(tmp_source):
    # `_persist_recos` consomme du brut LLM (type singulier) ; il normalise.
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
        "title": "Mortel", "types": ["serie"],
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


def test_merge_reco_preserves_quote_when_kind_citation(tmp_source):
    """Reco kind=citation (validée par humain) : la quote est protégée
    de la même façon qu'une reco status=validated."""
    existing = {
        "id": "ubm-0001", "sourceId": tmp_source.source_id,
        "episodeGuid": tmp_source.guid,
        "title": "Titanic", "types": ["film"],
        "quote": "ils en parlent juste en passant",
        "links": [], "status": "validated", "kind": "citation",
        "extractors": ["anthropic"],
    }
    (tmp_source.recos_dir / "0001.json").write_text(
        json.dumps(existing, ensure_ascii=False), encoding="utf-8")

    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Titanic", "type": "film",
                     "quote": "une quote auto qui ne doit PAS écraser",
                     "timestamp": "00:12:00"}],
                   "anthropic")
    data = json.loads((tmp_source.recos_dir / "0001.json").read_text(encoding="utf-8"))
    assert data["quote"] == "ils en parlent juste en passant"
    assert data["kind"] == "citation"


def test_persist_recos_merges_types_across_extractors(tmp_source):
    """Deux LLMs trouvent la même œuvre avec des types différents : fusion."""
    # LLM 1 (anthropic) : type "livre".
    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Dune", "type": "livre"}],
                   "anthropic")
    # LLM 2 (openai) : même titre mais type "film" → union dédupliquée.
    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Dune", "type": "film"}],
                   "openai")
    files = list(tmp_source.recos_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8"))
    # Types fusionnés (ordre stable : existant d'abord).
    assert data["types"] == ["livre", "film"]
    assert sorted(data["extractors"]) == ["anthropic", "openai"]


# ===== extractionHistory ===================================================
def test_create_reco_initializes_history_with_one_entry(tmp_source):
    raw = [{"title": "Dune", "type": "film", "timestamp": "00:42:00"}]
    _persist_recos(tmp_source.source_id, tmp_source.guid, raw,
                   provider="anthropic", transcript_source="youtube",
                   transcript_model="large-v3", llm_model="claude-haiku-4-5",
                   worker="portable-gpu")
    data = json.loads(next(tmp_source.recos_dir.glob("*.json"))
                      .read_text(encoding="utf-8"))
    assert "extractionHistory" in data
    assert len(data["extractionHistory"]) == 1
    h0 = data["extractionHistory"][0]
    assert h0["transcriptModel"] == "large-v3"
    assert h0["transcriptSource"] == "youtube"
    assert h0["llmProvider"] == "anthropic"
    assert h0["llmModel"] == "claude-haiku-4-5"
    assert h0["worker"] == "portable-gpu"
    assert h0["timestamp_at_extraction"] == "00:42:00"
    assert data["transcriptSource"] == "youtube"
    assert data["timestamp"] == "00:42:00"
    assert data["extractors"] == ["anthropic"]


def test_merge_reco_appends_new_entry_to_history(tmp_source):
    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Dune", "type": "film", "timestamp": "00:10:00"}],
                   provider="anthropic", transcript_source="acast",
                   transcript_model="large-v3", llm_model="claude-haiku-4-5",
                   worker="main-cpu")
    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Dune", "type": "film", "timestamp": "00:10:00"}],
                   provider="openai", transcript_source="acast",
                   transcript_model="large-v3", llm_model="gpt-4o-mini",
                   worker="main-cpu")
    data = json.loads(next(tmp_source.recos_dir.glob("*.json"))
                      .read_text(encoding="utf-8"))
    assert len(data["extractionHistory"]) == 2
    providers = sorted(e["llmProvider"] for e in data["extractionHistory"])
    assert providers == ["anthropic", "openai"]
    assert data["extractors"] == ["anthropic", "openai"]


def test_merge_reco_dedupes_same_signature_updates_at(tmp_source):
    # Même tuple (model, source, provider, llmModel) → 1 seule entry.
    for ts in ("00:10:00", "00:11:00"):
        _persist_recos(tmp_source.source_id, tmp_source.guid,
                       [{"title": "Dune", "type": "film", "timestamp": ts}],
                       provider="anthropic", transcript_source="acast",
                       transcript_model="large-v3",
                       llm_model="claude-haiku-4-5", worker="main-cpu")
    data = json.loads(next(tmp_source.recos_dir.glob("*.json"))
                      .read_text(encoding="utf-8"))
    assert len(data["extractionHistory"]) == 1
    assert data["extractionHistory"][0]["timestamp_at_extraction"] == "00:11:00"


def test_merge_reco_with_no_existing_history_creates_legacy_entry(tmp_source):
    """Reco écrite par l'ancien schéma → backfill auto d'une entry legacy."""
    legacy = {
        "id": "ubm-0001", "sourceId": tmp_source.source_id,
        "episodeGuid": tmp_source.guid,
        "title": "Dune", "types": ["film"],
        "timestamp": "00:05:00",
        "links": [], "status": "draft", "extractors": ["openai"],
    }
    (tmp_source.recos_dir / "0001.json").write_text(
        json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Dune", "type": "film", "timestamp": "00:42:00"}],
                   provider="anthropic", transcript_source="youtube",
                   transcript_model="large-v3",
                   llm_model="claude-haiku-4-5", worker="main-cpu")
    data = json.loads((tmp_source.recos_dir / "0001.json")
                      .read_text(encoding="utf-8"))
    # 2 entrées : legacy openai (acast) + nouvelle anthropic (youtube).
    assert len(data["extractionHistory"]) == 2
    providers = sorted(e["llmProvider"] for e in data["extractionHistory"])
    assert providers == ["anthropic", "openai"]
    assert data["extractors"] == ["anthropic", "openai"]


def test_merge_reco_picks_yt_timestamp_over_acast(tmp_source):
    # 1) Anthropic / acast / 00:10:00.
    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Dune", "type": "film", "timestamp": "00:10:00"}],
                   provider="anthropic", transcript_source="acast",
                   transcript_model="large-v3",
                   llm_model="claude-haiku-4-5", worker="main-cpu")
    # 2) OpenAI / youtube / 00:42:42 (timestamp YT, source d'autorité).
    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Dune", "type": "film", "timestamp": "00:42:42"}],
                   provider="openai", transcript_source="youtube",
                   transcript_model="large-v3",
                   llm_model="gpt-4o-mini", worker="main-cpu")
    # 3) Anthropic / acast / 00:11:00 (plus récent mais Acast).
    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Dune", "type": "film", "timestamp": "00:11:00"}],
                   provider="anthropic", transcript_source="acast",
                   transcript_model="large-v3",
                   llm_model="claude-haiku-4-5", worker="main-cpu")
    data = json.loads(next(tmp_source.recos_dir.glob("*.json"))
                      .read_text(encoding="utf-8"))
    # YT fait autorité → top-level garde 00:42:42 / youtube.
    assert data["timestamp"] == "00:42:42"
    assert data["transcriptSource"] == "youtube"


def test_extractors_field_is_derived_from_history(tmp_source):
    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Dune", "type": "film"}],
                   provider="anthropic", transcript_source="acast",
                   transcript_model="m1", llm_model="x", worker="w")
    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Dune", "type": "film"}],
                   provider="anthropic", transcript_source="acast",
                   transcript_model="m2", llm_model="x", worker="w")
    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Dune", "type": "film"}],
                   provider="openai", transcript_source="acast",
                   transcript_model="m1", llm_model="y", worker="w")
    data = json.loads(next(tmp_source.recos_dir.glob("*.json"))
                      .read_text(encoding="utf-8"))
    # 3 signatures distinctes (m1/anth, m2/anth, m1/openai).
    assert len(data["extractionHistory"]) == 3
    assert data["extractors"] == ["anthropic", "openai"]


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


def test_extract_all_batch_counts_failed_requests(tmp_source):
    """Une requête batch en échec (custom_id mappé) est comptée et journalisée
    (couvre la branche d'erreurs de _collect_results)."""
    client = MagicMock(spec=["messages"])
    client.messages.batches.create.return_value = SimpleNamespace(id="b")
    client.messages.batches.retrieve.return_value = SimpleNamespace(
        processing_status="ended")
    client.messages.batches.results.return_value = [
        SimpleNamespace(custom_id="req-0",
                        result=SimpleNamespace(type="errored")),
    ]
    n = extract_all_batch(tmp_source.source_id, [tmp_source.episode_path],
                          client=client, poll_seconds=0)
    assert n == 0


def test_extract_all_batch_skips_unreadable_episode_meta(tmp_source, monkeypatch):
    """La relecture des métadonnées d'épisode (transcriptSource) tolère un
    fichier devenu illisible entre-temps (race) : l'épisode est ignoré côté
    méta sans crasher, la reco reste persistée (le guid vient du batch)."""
    real_read = extract_recos.read_json
    calls = {"n": 0}

    def flaky_read(path):
        calls["n"] += 1
        # 1er read = guid (dans _build_batch_requests) OK ; 2e = relecture méta
        # (boucle ep_by_guid) → OSError.
        if calls["n"] >= 2 and path == tmp_source.episode_path:
            raise OSError("fichier disparu")
        return real_read(path)

    monkeypatch.setattr(extract_recos, "read_json", flaky_read)
    client = MagicMock(spec=["messages"])
    client.messages.batches.create.return_value = SimpleNamespace(id="b")
    client.messages.batches.retrieve.return_value = SimpleNamespace(
        processing_status="ended")
    ok = _fake_anthropic_message({"recos": [{"title": "M", "type": "serie"}]})
    client.messages.batches.results.return_value = [
        SimpleNamespace(custom_id="req-0", result=SimpleNamespace(
            type="succeeded", message=SimpleNamespace(content=ok.content))),
    ]
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


def test_extract_all_batch_propagates_episode_transcript_source(tmp_source):
    """M2 (revue 2026-07-19) — en batch, le transcriptSource/Model de l'ÉPISODE
    (ici youtube) doit être propagé aux recos, PAS hardcodé à 'acast'. Sinon le
    review_server applique un yt_offset à un timecode déjà calé sur la vidéo →
    lecteur décalé."""
    ep = json.loads(tmp_source.episode_path.read_text(encoding="utf-8"))
    ep["transcriptSource"] = "youtube"
    ep["transcriptModel"] = "large-v3-turbo"
    tmp_source.episode_path.write_text(json.dumps(ep), encoding="utf-8")

    client = MagicMock(spec=["messages"])
    client.messages.batches.create.return_value = SimpleNamespace(id="batch_yt")
    client.messages.batches.retrieve.return_value = SimpleNamespace(
        processing_status="ended")
    ok_msg = _fake_anthropic_message({"recos": [{"title": "Mortel", "type": "serie"}]})
    ok_entry = SimpleNamespace(
        custom_id="req-0",
        result=SimpleNamespace(type="succeeded",
                               message=SimpleNamespace(content=ok_msg.content)),
    )
    client.messages.batches.results.return_value = [ok_entry]
    n = extract_all_batch(tmp_source.source_id, [tmp_source.episode_path],
                          client=client, poll_seconds=0)
    assert n == 1
    reco_files = list(tmp_source.recos_dir.glob("*.json"))
    assert reco_files, "aucune reco écrite"
    reco = json.loads(reco_files[0].read_text(encoding="utf-8"))
    assert reco["transcriptSource"] == "youtube"
    assert reco["extractionHistory"][0]["transcriptSource"] == "youtube"
    assert reco["extractionHistory"][0]["transcriptModel"] == "large-v3-turbo"


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
    monkeypatch.setattr(extract_recos, "make_anthropic_client", lambda: fake_client)
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
    monkeypatch.setattr(extract_recos, "make_openai_client", lambda: fake_client)
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
    monkeypatch.setattr(extract_recos, "make_openai_client", lambda: fake_client)
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
    monkeypatch.setattr(extract_recos, "make_anthropic_client", lambda: fake_client)
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
    monkeypatch.setattr(extract_recos, "make_anthropic_client", lambda: fake_client)
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
    monkeypatch.setattr(extract_recos, "make_anthropic_client", lambda: fake_client)
    _run_main(monkeypatch, [
        "extract_recos.py", "--source", tmp_source.source_id,
        "--guid", tmp_source.guid,
    ])
    # Pas d'exception remontée jusqu'ici -> test OK.


# ===== _make_client / _make_openai_client (erreurs clés API) ===============
def test_make_client_missing_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # On empêche load_dotenv de réécrire la variable. extract_recos._make_client
    # délègue à common.make_anthropic_client qui ré-importe load_dotenv depuis
    # le module dotenv : patcher dotenv.load_dotenv couvre les deux chemins.
    import dotenv
    monkeypatch.setattr(extract_recos, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        extract_recos.make_anthropic_client()


def test_make_openai_client_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    import dotenv
    monkeypatch.setattr(extract_recos, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        extract_recos.make_openai_client()


def test_make_client_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
    monkeypatch.setattr(extract_recos, "load_dotenv", lambda *a, **k: None)
    fake_anthropic = MagicMock()
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)
    extract_recos.make_anthropic_client()
    fake_anthropic.Anthropic.assert_called_once_with(api_key="fake-key")


def test_make_openai_client_with_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setattr(extract_recos, "load_dotenv", lambda *a, **k: None)
    fake_openai = MagicMock()
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    extract_recos.make_openai_client()
    fake_openai.OpenAI.assert_called_once_with(api_key="fake-key")


# ===== M4 : index de run partagé (_RunIndex) ================================
def test_new_run_index_returns_runindex(tmp_source):
    ri = new_run_index(tmp_source.source_id)
    assert isinstance(ri, _RunIndex)
    assert ri.next_index == 1
    assert ri.existing_map == {}


def test_persist_recos_shared_run_index_not_rebuilt(tmp_source, monkeypatch):
    """M4 — avec un run_index fourni, _persist_recos NE reconstruit PAS l'index
    (aucune relecture des recos) et le compteur avance d'un épisode à l'autre."""
    ri = new_run_index(tmp_source.source_id)
    assert ri.next_index == 1

    build_calls = {"n": 0}

    def _spy_build(sid):
        build_calls["n"] += 1
        return {}

    monkeypatch.setattr(extract_recos, "_build_existing_index", _spy_build)

    _persist_recos(tmp_source.source_id, "G1",
                   [{"title": "A", "type": "film"}], "anthropic", run_index=ri)
    _persist_recos(tmp_source.source_id, "G2",
                   [{"title": "B", "type": "film"}], "anthropic", run_index=ri)

    assert build_calls["n"] == 0          # jamais reconstruit
    assert ri.next_index == 3             # 2 recos créées → 1 → 3
    files = sorted(p.name for p in tmp_source.recos_dir.glob("*.json"))
    assert files == ["0001.json", "0002.json"]


def test_persist_recos_builds_index_when_none(tmp_source, monkeypatch):
    """Chemin standalone (run_index=None) : l'index est construit sur place."""
    build_calls = {"n": 0}
    real_build = extract_recos._build_existing_index

    def _spy_build(sid):
        build_calls["n"] += 1
        return real_build(sid)

    monkeypatch.setattr(extract_recos, "_build_existing_index", _spy_build)
    _persist_recos(tmp_source.source_id, tmp_source.guid,
                   [{"title": "Solo", "type": "film"}], "anthropic")
    assert build_calls["n"] == 1


def test_extract_all_batch_builds_index_once(tmp_source, monkeypatch):
    """M4 — sur un run batch à 2 épisodes, _build_existing_index et
    _next_reco_index ne sont appelés QU'UNE fois (pas une fois par épisode :
    sinon O(épisodes × recos))."""
    # 2e épisode + sa transcription.
    ep2_guid = "EP002"
    ep2 = tmp_source.episode_path.parent / "0002.json"
    ep2.write_text(json.dumps({"guid": ep2_guid, "title": "Deux"}), encoding="utf-8")
    (tmp_source.transcript_path.parent / f"{ep2_guid}.txt").write_text(
        "Ligne A.\n", encoding="utf-8")

    calls = {"build": 0, "next": 0}
    real_build = extract_recos._build_existing_index
    real_next = extract_recos._next_reco_index

    def _spy_build(sid):
        calls["build"] += 1
        return real_build(sid)

    def _spy_next(sid):
        calls["next"] += 1
        return real_next(sid)

    monkeypatch.setattr(extract_recos, "_build_existing_index", _spy_build)
    monkeypatch.setattr(extract_recos, "_next_reco_index", _spy_next)

    client = MagicMock(spec=["messages"])
    client.messages.batches.create.return_value = SimpleNamespace(id="b")
    client.messages.batches.retrieve.return_value = SimpleNamespace(
        processing_status="ended")
    ok = _fake_anthropic_message({"recos": [{"title": "Mortel", "type": "serie"}]})
    client.messages.batches.results.return_value = [
        SimpleNamespace(custom_id="req-0", result=SimpleNamespace(
            type="succeeded", message=SimpleNamespace(content=ok.content))),
        SimpleNamespace(custom_id="req-1", result=SimpleNamespace(
            type="succeeded", message=SimpleNamespace(content=ok.content))),
    ]
    n = extract_all_batch(tmp_source.source_id,
                          [tmp_source.episode_path, ep2],
                          client=client, poll_seconds=0)
    assert n == 2
    assert calls["build"] == 1
    assert calls["next"] == 1
    # Les 2 recos ont des index distincts (compteur partagé qui avance).
    files = sorted(p.name for p in tmp_source.recos_dir.glob("*.json"))
    assert files == ["0001.json", "0002.json"]


def test_main_all_sync_builds_index_once(tmp_source, monkeypatch):
    """M4 — la boucle synchrone de main() construit aussi l'index UNE fois."""
    ep2 = tmp_source.episode_path.parent / "0002.json"
    ep2.write_text(json.dumps({"guid": "EP002", "title": "Deux"}), encoding="utf-8")
    (tmp_source.transcript_path.parent / "EP002.txt").write_text(
        "Ligne A.\n", encoding="utf-8")

    calls = {"n": 0}
    real_build = extract_recos._build_existing_index

    def _spy_build(sid):
        calls["n"] += 1
        return real_build(sid)

    monkeypatch.setattr(extract_recos, "_build_existing_index", _spy_build)
    fake_client = MagicMock(spec=["messages"])
    fake_client.messages.create.return_value = _fake_anthropic_message(
        {"recos": [{"title": "X", "type": "film"}]})
    monkeypatch.setattr(extract_recos, "make_anthropic_client", lambda: fake_client)
    _run_main(monkeypatch, [
        "extract_recos.py", "--source", tmp_source.source_id, "--all",
    ])
    assert calls["n"] == 1


# ===== L1 : erreur batch dans main() journalisée ===========================
def test_main_batch_failure_is_logged_not_raised(tmp_source, monkeypatch):
    """L1 (revue 2026-07-19) — une erreur d'extract_all_batch en mode --batch
    est journalisée et NON propagée (parité avec la boucle synchrone)."""
    fake_client = MagicMock(spec=["messages"])
    monkeypatch.setattr(extract_recos, "make_anthropic_client", lambda: fake_client)

    def boom(*a, **k):
        raise RuntimeError("batch boom")

    monkeypatch.setattr(extract_recos, "extract_all_batch", boom)
    # Ne doit PAS lever.
    _run_main(monkeypatch, [
        "extract_recos.py", "--source", tmp_source.source_id,
        "--all", "--batch", "--poll-interval", "0",
    ])


# ===== _make_extractor / aliases (couverture) ==============================
def test_make_extractor_unknown_provider_raises():
    with pytest.raises(ValueError, match="Provider LLM inconnu"):
        _make_extractor(MagicMock(), provider="gemini")  # type: ignore[arg-type]


def test_make_extractor_explicit_providers():
    assert isinstance(_make_extractor(MagicMock(), provider="anthropic"),
                      _AnthropicExtractor)
    assert isinstance(_make_extractor(MagicMock(), provider="openai"),
                      _OpenAIExtractor)


def test_make_extractor_fallback_openai_by_chat_attr():
    # MagicMock sans spec a un attribut .chat → détecté comme OpenAI.
    assert isinstance(_make_extractor(MagicMock()), _OpenAIExtractor)


def test_make_extractor_fallback_anthropic_default():
    # spec=["messages"] : pas d'attribut .chat, module non-openai → Anthropic.
    assert isinstance(_make_extractor(MagicMock(spec=["messages"])),
                      _AnthropicExtractor)


def test_call_anthropic_alias(tmp_source):
    client = MagicMock(spec=["messages"])
    client.messages.create.return_value = _fake_anthropic_message(
        {"recos": [{"title": "Z", "type": "film"}]})
    out = _call_anthropic(client, "m", "P", "hosts", "chunk")
    assert out == [{"title": "Z", "type": "film"}]


def test_call_openai_alias():
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_openai_response(
        {"recos": [{"title": "Y", "type": "film"}]})
    out = _call_openai(client, "gpt-4o-mini", "P", "hosts", "chunk")
    assert out == [{"title": "Y", "type": "film"}]


# ===== _poll_batch_until_done (couverture timeout / statut non-ended) ======
def test_poll_batch_until_done_timeout_raises():
    """timeout dépassé sans état terminal → TimeoutError."""
    client = MagicMock()
    client.messages.batches.retrieve.return_value = SimpleNamespace(
        processing_status="in_progress")
    with pytest.raises(TimeoutError, match="pas terminé"):
        _poll_batch_until_done(client, "b", poll_seconds=0, timeout_seconds=-1)


def test_poll_batch_until_done_non_ended_terminal_warns(caplog):
    """Statut terminal ≠ ended (errored/expired) → retour sans lever, warning."""
    client = MagicMock()
    client.messages.batches.retrieve.return_value = SimpleNamespace(
        processing_status="errored")
    _poll_batch_until_done(client, "b", poll_seconds=0)  # ne lève pas


# ===== main() : verrou serveur occupé ======================================
def test_main_server_lock_busy_exits(tmp_source, monkeypatch):
    """Le review_server tient le verrou → main() log et sort (exit 1)."""
    import review_lock

    def busy(force=False):
        raise review_lock.ServerLockBusy("serveur actif")

    monkeypatch.setattr(extract_recos, "acquire_pipeline_lock", busy)
    with pytest.raises(SystemExit):
        _run_main(monkeypatch, [
            "extract_recos.py", "--source", tmp_source.source_id,
            "--guid", tmp_source.guid, "--dry-run",
        ])
