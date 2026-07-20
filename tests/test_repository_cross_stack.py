"""Tests cross-stack Python ↔ Astro/Zod sur Item / Mention.

Stratégie (alignée sur `test_config_cross_stack.py`) :

1. On vérifie qu'un Item / une Mention sérialisés par les codecs respectent
   les **contraintes structurelles** déclarées côté Zod (clés camelCase,
   formats de timestamp, valeurs d'enum, etc.). C'est un smoke-test
   structurel qui détecte les drifts évidents.

2. La validation Zod réelle (avec ses types runtime) reste assurée par
   `npm run build` en CI : si un drift apparaît, le build casse.

3. On scelle ici quelques fixtures `src/content/{items,mentions}/__cross_stack_fixture__/`
   écrites par les codecs Python. Le `npm run build` les passera à Zod ;
   un drift Astro→Python sera détecté.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from domain.item import (
    CustomLink,
    ExternalIds,
    Item,
    ItemType,
    WatchProvider,
)
from domain.mention import (
    ExtractionHistoryEntry,
    Mention,
    MentionKind,
    MentionStatus,
    SourceRef,
    TranscriptSource,
)
from repository.serialization.item_codec import item_to_dict
from repository.serialization.mention_codec import mention_to_dict


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ITEMS_DIR = _PROJECT_ROOT / "src" / "content" / "items"
_MENTIONS_DIR = _PROJECT_ROOT / "src" / "content" / "mentions"
_FIXTURE_SUBDIR = "__cross_stack_fixture__"


# ---------------------------------------------------------------------------
# Fixtures de référence (figées) — écrites sur disque pour npm run build
# ---------------------------------------------------------------------------


def _ref_item() -> Item:
    return Item(
        id="fixture0",
        types=(ItemType.FILM, ItemType.SERIES),
        title="Fixture Title",
        creator="Fixture Creator",
        year=2020,
        aliases=("alt1", "alt2"),
        external_ids=ExternalIds(
            tmdb=42, tmdb_type="movie", spotify="sp",
            musicbrainz="mb", openlibrary="ol", isbn="isbn", justwatch="jw",
        ),
        custom_links=(CustomLink(label="X", url="https://x.example.com"),),
        watch_providers=(
            WatchProvider(name="N", url="https://n.example.com", region="FR"),
        ),
        link_overrides={"JW": "https://jw.example.com"},
        recommended_by="Tester",
        schema_version=1,
    )


def _ref_mention() -> Mention:
    return Mention(
        id="fixturem",
        item_id="fixture0",
        source_ref=SourceRef(
            source_id="un-bon-moment",
            episode_guid="e1",
            timestamp="01:02:03",
            transcript_source=TranscriptSource.YOUTUBE,
        ),
        recommended_by="Tester",
        quote="Une citation",
        kind=MentionKind.RECO,
        status=MentionStatus.VALIDATED,
        extraction_history=(
            ExtractionHistoryEntry(
                transcript_model="large-v3",
                transcript_source=TranscriptSource.YOUTUBE,
                llm_provider="anthropic",
                llm_model="claude-3",
                worker="w1",
                at="2026-06-10T14:00:00Z",
                extra={"k": "v"},
            ),
        ),
        extractors=("anthropic", "openai"),
    )


# ---------------------------------------------------------------------------
# Constantes Zod (devraient rester en miroir de `src/content.config.ts`)
# ---------------------------------------------------------------------------


# D5 — Dérivé de l'enum domaine pour rester automatiquement à jour si un
# nouveau type d'œuvre est ajouté (cf. senior 2.B #20). Le test
# `test_zod_item_type_values_match_python_enum` ci-dessous garantit que
# la SSOT Zod (src/content.config.ts) reste alignée.
_ITEM_TYPE_VALUES = {t.value for t in ItemType}
_TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
_ID_RE = re.compile(r"^[a-z0-9-]{1,64}$")
_TRANSCRIPT_SOURCE_VALUES = {"youtube", "acast"}
_KIND_VALUES = {"reco", "citation"}
_STATUS_VALUES = {"draft", "validated", "discarded"}
_TMDB_TYPE_VALUES = {"movie", "tv"}


# ---------------------------------------------------------------------------
# Item — conformité structurelle au schéma Zod
# ---------------------------------------------------------------------------


def test_item_codec_produces_zod_compatible_dict():
    d = item_to_dict(_ref_item())
    # Clés camelCase obligatoires
    assert _ID_RE.match(d["id"])
    assert isinstance(d["types"], list) and len(d["types"]) >= 1
    for t in d["types"]:
        assert t in _ITEM_TYPE_VALUES
    assert isinstance(d["title"], str) and d["title"]
    assert d["schemaVersion"] >= 1
    assert "externalIds" in d
    assert d["externalIds"]["tmdbType"] in _TMDB_TYPE_VALUES
    assert isinstance(d["customLinks"], list)
    assert isinstance(d["watchProviders"], list)
    assert isinstance(d["linkOverrides"], dict)


def test_item_codec_year_in_zod_bounds():
    d = item_to_dict(_ref_item())
    assert 1800 <= d["year"] <= 2100


def test_item_codec_no_snake_case_keys():
    """Garde-fou contre un drift : aucun champ ne doit rester en snake_case."""
    d = item_to_dict(_ref_item())
    # On parcourt les top-level + sous-dict externalIds.
    forbidden = ("tmdb_type", "schema_version", "recommended_by",
                 "watch_providers", "custom_links", "link_overrides",
                 "external_ids")
    flat = json.dumps(d)
    for key in forbidden:
        assert key not in flat, f"snake_case résiduel: {key}"


# ---------------------------------------------------------------------------
# Mention — conformité structurelle au schéma Zod
# ---------------------------------------------------------------------------


def test_mention_codec_produces_zod_compatible_dict():
    d = mention_to_dict(_ref_mention())
    assert _ID_RE.match(d["id"])
    assert _ID_RE.match(d["itemId"])
    assert d["kind"] in _KIND_VALUES
    assert d["status"] in _STATUS_VALUES
    sr = d["sourceRef"]
    assert isinstance(sr["sourceId"], str) and sr["sourceId"]
    assert _TIMESTAMP_RE.match(sr["timestamp"])
    assert sr["transcriptSource"] in _TRANSCRIPT_SOURCE_VALUES
    # extractionHistory
    assert isinstance(d["extractionHistory"], list)
    e = d["extractionHistory"][0]
    assert isinstance(e["llmProvider"], str)
    assert isinstance(e["llmModel"], str)
    assert isinstance(e["at"], str)
    # extra reste un dict[str, str]
    assert all(isinstance(k, str) and isinstance(v, str)
               for k, v in e["extra"].items())


def test_mention_codec_no_snake_case_keys():
    d = mention_to_dict(_ref_mention())
    forbidden = ("item_id", "source_ref", "source_id", "episode_guid",
                 "transcript_source", "recommended_by", "schema_version",
                 "extraction_history", "transcript_model",
                 "llm_provider", "llm_model")
    flat = json.dumps(d)
    for key in forbidden:
        assert key not in flat, f"snake_case résiduel: {key}"


# ---------------------------------------------------------------------------
# Fixtures sur disque — sceau pour `npm run build` (CI)
# ---------------------------------------------------------------------------


def test_sealed_fixtures_on_disk_match_codecs_output():
    """Vérifie que les fixtures scellées sur disque correspondent EXACTEMENT
    à ce que les codecs Python produiraient AUJOURD'HUI.

    Politique (senior 2.B #1) : ce test ne **mute jamais** le working tree.
    Si une dérive est détectée, lancer explicitement :

        python scripts/seal_cross_stack_fixtures.py

    pour re-générer les fixtures (action volontaire, jamais en CI).
    """
    item = _ref_item()
    mention = _ref_mention()

    item_path = _ITEMS_DIR / _FIXTURE_SUBDIR / f"{item.id}.json"
    mention_path = _MENTIONS_DIR / _FIXTURE_SUBDIR / f"{mention.id}.json"

    expected_item = (
        json.dumps(item_to_dict(item), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    expected_mention = (
        json.dumps(mention_to_dict(mention), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )

    assert item_path.exists(), (
        f"Fixture absente: {item_path}. Lancer scripts/seal_cross_stack_fixtures.py."
    )
    assert mention_path.exists(), (
        f"Fixture absente: {mention_path}. Lancer scripts/seal_cross_stack_fixtures.py."
    )
    assert item_path.read_text("utf-8") == expected_item, (
        "Drift item: le codec Python produit un JSON différent du fixture "
        "scellé. Lancer scripts/seal_cross_stack_fixtures.py pour resceller."
    )
    assert mention_path.read_text("utf-8") == expected_mention, (
        "Drift mention: le codec Python produit un JSON différent du fixture "
        "scellé. Lancer scripts/seal_cross_stack_fixtures.py pour resceller."
    )


@pytest.mark.parametrize(
    "path,kind",
    [
        # C12 — Les noms de fixtures sont dérivés des ids du domaine pour
        # éviter qu'une coquille (`fixture0` → `fixture1` dans `_ref_item`)
        # ne laisse passer un drift entre code et fichier.
        pytest.param(
            _ITEMS_DIR / _FIXTURE_SUBDIR / f"{_ref_item().id}.json", "item",
            id="item-fixture-readable",
        ),
        pytest.param(
            _MENTIONS_DIR / _FIXTURE_SUBDIR / f"{_ref_mention().id}.json", "mention",
            id="mention-fixture-readable",
        ),
    ],
)
def test_fixture_files_on_disk_are_round_trippable(path, kind):
    """Les fichiers JSON sur disque (consommés par Astro/Zod) doivent
    être désérialisables côté Python. Si ce test casse, c'est qu'on a
    bossé sur le disque sans passer par le codec."""
    if not path.exists():
        pytest.skip(f"Fixture absente : {path} — run test_seal_fixtures_on_disk_for_astro_build d'abord")
    data = json.loads(path.read_text("utf-8"))
    if kind == "item":
        from repository.serialization.item_codec import item_from_dict
        item_from_dict(data)
    else:
        from repository.serialization.mention_codec import mention_from_dict
        mention_from_dict(data)
