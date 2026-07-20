"""seal_cross_stack_fixtures.py — Régénère les fixtures cross-stack.

À lancer **manuellement** après une évolution intentionnelle des codecs ou
du schéma Zod. Le test `tests/test_repository_cross_stack.py` est
read-only et échoue tant que ce script n'a pas été re-lancé.

Usage:
    python scripts/seal_cross_stack_fixtures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Permet l'import direct depuis `tools/`.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))

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


_ITEMS_DIR = _ROOT / "src" / "content" / "items" / "__cross_stack_fixture__"
_MENTIONS_DIR = _ROOT / "src" / "content" / "mentions" / "__cross_stack_fixture__"


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


def main() -> int:
    _ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    _MENTIONS_DIR.mkdir(parents=True, exist_ok=True)

    item = _ref_item()
    mention = _ref_mention()

    item_payload = (
        json.dumps(item_to_dict(item), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )
    mention_payload = (
        json.dumps(mention_to_dict(mention), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    )

    item_path = _ITEMS_DIR / f"{item.id}.json"
    mention_path = _MENTIONS_DIR / f"{mention.id}.json"

    item_path.write_text(item_payload, encoding="utf-8")
    mention_path.write_text(mention_payload, encoding="utf-8")

    print(f"Scellé: {item_path}")
    print(f"Scellé: {mention_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
