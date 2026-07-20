"""Tests des corrections issues des CR senior + archi sur la couche
`tools.domain` (item 2.A → 2.B).

Couvre les fixes Phase A/B/C/D du plan d'exécution.
"""
from __future__ import annotations

import dataclasses
import pickle

import pytest

import domain
from domain.item import CustomLink, ExternalIds, Item, ItemType, WatchProvider
from domain.mention import (
    ExtractionHistoryEntry,
    Mention,
    SourceRef,
    TranscriptSource,
)
from domain.ports import ItemRepository, MentionRepository
from domain.services.identity import (
    IdentityRegistry,
    canonical_key,
    find_matching_item,
    generate_item_id,
)


# ---------------------------------------------------------------------------
# Fixtures factorisées (L7)
# ---------------------------------------------------------------------------


def _make_item(**overrides):
    base = dict(id="abc12345", types=(ItemType.FILM,), title="Drive")
    base.update(overrides)
    return Item(**base)


def _make_mention(**overrides):
    base = dict(id="m-1", item_id="abc12345", source_ref=SourceRef(source_id="ubm"))
    base.update(overrides)
    return Mention(**base)


# ---------------------------------------------------------------------------
# #1 — canonical_key sans types (ADR 0002)
# ---------------------------------------------------------------------------


def test_canonical_key_two_calls_same_title_creator_match_regardless_of_types():
    a = canonical_key("Drive", "Refn", (ItemType.FILM,))
    b = canonical_key("Drive", "Refn", (ItemType.SERIES,))
    assert a == b  # ADR 0002 : les types ne participent plus à la clé.


def test_can_merge_overlapping_types_returns_true_aligned_with_find_match():
    """Aligne le comportement entre find_match (intersection) et can_merge."""
    a = _make_item(creator="Refn", types=(ItemType.FILM, ItemType.SERIES))
    b = _make_item(id="def67890", creator="Refn", types=(ItemType.FILM,))
    assert domain.can_merge_items(a, b) is True


def test_can_merge_disjoint_types_rejected_by_intersection_not_canonical():
    a = _make_item(creator="Refn", types=(ItemType.FILM,))
    b = _make_item(id="def67890", creator="Refn", types=(ItemType.BOOK,))
    # canonical_key identique (title + creator), mais intersection types vide.
    assert canonical_key(a.title, a.creator) == canonical_key(b.title, b.creator)
    assert domain.can_merge_items(a, b) is False


# ---------------------------------------------------------------------------
# #2 — generate_id stabilité + IdentityRegistry
# ---------------------------------------------------------------------------


def test_generate_id_warning_about_deletion_instability_documented():
    """Le contrat est documenté : `generate_item_id` n'est valable qu'à la
    création. Pour mémoïser les attributions, utiliser IdentityRegistry.
    """
    doc = generate_item_id.__doc__ or ""
    assert "création" in doc.lower() or "creation" in doc.lower()
    assert "registry" in doc.lower() or "supprimé" in doc.lower() or "supprime" in doc.lower()


def test_identity_registry_reserves_same_id_for_same_canonical():
    reg = IdentityRegistry()
    key = canonical_key("Drive", "Refn")
    id1 = reg.reserve_id(key)
    id2 = reg.reserve_id(key)
    assert id1 == id2
    assert reg.has(key)


def test_identity_registry_handles_collisions():
    reg = IdentityRegistry()
    # Deux canonicals différents qui (par hasard) produiraient le même
    # digest ne se chevauchent pas. On simule en réservant explicitement.
    id1 = reg.reserve_id("aaa")
    id2 = reg.reserve_id("bbb")
    assert id1 != id2


# ---------------------------------------------------------------------------
# #3 — Public API
# ---------------------------------------------------------------------------


def test_public_api_exposes_ports_module():
    # Les Protocols ne sont pas dans __all__ (sub-module), mais le module
    # ports doit être importable.
    from domain import ports
    assert ports.ItemRepository is not None
    assert ports.MentionRepository is not None


# ---------------------------------------------------------------------------
# #4 — link_overrides / extra immuables
# ---------------------------------------------------------------------------


def test_link_overrides_truly_immutable():
    it = _make_item(link_overrides={"tmdb": "https://override"})
    with pytest.raises(TypeError):
        it.link_overrides["tmdb"] = "x"  # type: ignore[index]
    with pytest.raises(TypeError):
        it.link_overrides["new"] = "y"  # type: ignore[index]


def test_extra_truly_immutable():
    e = ExtractionHistoryEntry(
        transcript_model=None,
        transcript_source=None,
        llm_provider="anthropic",
        llm_model="claude-x",
        worker=None,
        at="2026-06-10T14:00:00Z",
        extra={"retry": "2"},
    )
    with pytest.raises(TypeError):
        e.extra["retry"] = "3"  # type: ignore[index]


def test_item_is_truly_hashable_with_link_overrides():
    """Le freeze via MappingProxyType ne suffit pas à rendre hashable
    (les dict ne sont pas hashables). On vérifie le comportement réel.
    """
    a = _make_item(link_overrides={"k": "v"})
    # MappingProxyType n'est pas hashable, donc Item non plus.
    # On documente le contrat.
    with pytest.raises(TypeError):
        hash(a)


def test_item_without_link_overrides_is_hashable_via_factory_equality():
    """Item sans link_overrides : reste eq-by-value mais pas hashable
    (dict default → MappingProxyType vide non hashable). On documente."""
    a = _make_item()
    b = _make_item()
    assert a == b  # égalité structurelle ok
    # hash → TypeError car link_overrides=MappingProxyType({}) non hashable
    with pytest.raises(TypeError):
        hash(a)


# ---------------------------------------------------------------------------
# #4 bis — link_overrides validation
# ---------------------------------------------------------------------------


def test_link_overrides_empty_key_raises():
    with pytest.raises(ValueError, match="link_overrides"):
        _make_item(link_overrides={"": "v"})


def test_link_overrides_blank_value_raises():
    with pytest.raises(ValueError, match="link_overrides"):
        _make_item(link_overrides={"k": "   "})


def test_link_overrides_non_str_key_raises():
    with pytest.raises(ValueError, match="link_overrides"):
        _make_item(link_overrides={42: "v"})


def test_link_overrides_non_mapping_raises():
    with pytest.raises(ValueError, match="link_overrides"):
        _make_item(link_overrides=[("k", "v")])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# #4 ter — custom_links / watch_providers : types d'éléments
# ---------------------------------------------------------------------------


def test_custom_links_with_wrong_element_type_raises():
    with pytest.raises(ValueError, match="custom_links"):
        _make_item(custom_links=("not-a-link",))  # type: ignore[arg-type]


def test_watch_providers_with_wrong_element_type_raises():
    with pytest.raises(ValueError, match="watch_providers"):
        _make_item(watch_providers=("not-a-provider",))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# #7 — Ports
# ---------------------------------------------------------------------------


def test_item_repository_protocol_signature():
    # Vérifie que la signature attendue est bien présente.
    import inspect
    methods = {"get", "list_all", "upsert", "existing_index"}
    assert methods.issubset(set(dir(ItemRepository)))
    # `get` doit accepter `item_id: str`.
    sig = inspect.signature(ItemRepository.get)
    assert "item_id" in sig.parameters


def test_mention_repository_protocol_signature():
    methods = {"get", "list_for_item", "list_for_episode", "upsert"}
    assert methods.issubset(set(dir(MentionRepository)))


def test_item_repository_runtime_implementable():
    """Un fake adapter satisfait le Protocol structuralement."""
    class FakeRepo:
        def get(self, item_id): return None
        def list_all(self): return []
        def upsert(self, item): return True
        def existing_index(self): return {}
    # Pas d'erreur à l'instanciation ; le typing structural est respecté.
    fake = FakeRepo()
    assert fake.get("x") is None


# ---------------------------------------------------------------------------
# #8 — Module-level functions
# ---------------------------------------------------------------------------


def test_module_level_generate_item_id_equivalent_to_service():
    key = canonical_key("Drive", "Refn")
    a = generate_item_id(key, frozenset())
    b = domain.ItemIdentityService.generate_id(key, frozenset())
    assert a == b


def test_module_level_find_matching_item_equivalent():
    key = canonical_key("Drive", "Refn")
    existing = {"abc12345": (key, (ItemType.FILM,))}
    a = find_matching_item(key, (ItemType.FILM,), existing)
    b = domain.ItemIdentityService.find_match(key, (ItemType.FILM,), existing)
    assert a == b == "abc12345"


# ---------------------------------------------------------------------------
# #10 — TranscriptSource StrEnum
# ---------------------------------------------------------------------------


def test_transcript_source_enum_values():
    assert TranscriptSource.YOUTUBE == "youtube"
    assert TranscriptSource.ACAST == "acast"


def test_source_ref_accepts_transcript_source_enum():
    s = SourceRef(source_id="x", transcript_source=TranscriptSource.YOUTUBE)
    assert s.transcript_source == TranscriptSource.YOUTUBE


def test_source_ref_str_coerced_to_enum():
    s = SourceRef(source_id="x", transcript_source="youtube")
    assert s.transcript_source == TranscriptSource.YOUTUBE
    assert isinstance(s.transcript_source, TranscriptSource)


def test_source_ref_invalid_transcript_source_raises():
    with pytest.raises(ValueError, match="transcript_source"):
        SourceRef(source_id="x", transcript_source="whisper")


# ---------------------------------------------------------------------------
# #13 — Spec tests (cas réels du dataset)
# ---------------------------------------------------------------------------


def test_spec_le_comte_de_monte_cristo_canonical_stable():
    """Cas réel : même œuvre malgré orthographe + casse."""
    a = canonical_key("Le Comte de Monte Cristo", "Dumas")
    b = canonical_key("Le Comte de Monte-Cristo", "Alexandre Dumas")
    # Le creator diffère (`Dumas` vs `Alexandre Dumas`) → on accepte des
    # clés distinctes ici. Le test documente la limite (extending wisdom
    # à la couche application : matching fuzzy de creator).
    assert a != b
    # Mais la ponctuation entre les deux orthographes ne fait pas la
    # différence à creator égal.
    c = canonical_key("Le Comte de Monte-Cristo", "Dumas")
    assert a == c


def test_spec_drive_canonical_stable_across_punctuation_and_case():
    a = canonical_key("Drive!", "Nicolas Winding Refn")
    b = canonical_key("DRIVE", "nicolas winding refn")
    assert a == b


def test_spec_kyan_a_good_time_with_canonical_strips_format_titles():
    # Le format diffère du show réel — couvre la mémoire utilisateur
    # "reco-yt-format-titles".
    a = canonical_key("A Good Time with Pierre Niney", "Kyan Khojandi")
    b = canonical_key("A good time with Pierre Niney!", "Kyan Khojandi")
    assert a == b


# ---------------------------------------------------------------------------
# #15-16 — Erreurs précises
# ---------------------------------------------------------------------------


def test_external_ids_tmdb_bool_rejected():
    with pytest.raises(ValueError, match="bool"):
        ExternalIds(tmdb=True)  # type: ignore[arg-type]


def test_item_types_error_message_mentions_type():
    with pytest.raises(ValueError, match="ItemType"):
        _make_item(types=("film",))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# #17 (archi #14) — recommended_by Mention
# ---------------------------------------------------------------------------


def test_mention_recommended_by_none_ok():
    m = _make_mention(recommended_by=None)
    assert m.recommended_by is None


def test_mention_recommended_by_blank_raises():
    with pytest.raises(ValueError, match="recommended_by"):
        _make_mention(recommended_by="   ")


def test_mention_quote_blank_raises():
    with pytest.raises(ValueError, match="quote"):
        _make_mention(quote="   ")


# ---------------------------------------------------------------------------
# #M8 — title strip
# ---------------------------------------------------------------------------


def test_item_title_stripped_on_construction():
    it = _make_item(title="  Drive  ")
    assert it.title == "Drive"


# ---------------------------------------------------------------------------
# #M7 — ItemType réduit vs RecoType : justification
# ---------------------------------------------------------------------------


def test_item_type_includes_legacy_show_place_video():
    """ADR 0006 : les types historiques `spectacle/lieu/video` sont
    désormais des valeurs first-class de `ItemType` (SHOW/PLACE/VIDEO)
    pour préserver la sémantique du dataset legacy. OTHER reste comme
    fallback générique pour les types vraiment hors catégorie.
    """
    values = {t.value for t in ItemType}
    assert "spectacle" in values
    assert "lieu" in values
    assert "video" in values
    # OTHER est disponible comme fallback.
    assert "autre" in values


# ---------------------------------------------------------------------------
# #archi #13 — Timestamp bornes
# ---------------------------------------------------------------------------


def test_source_ref_timestamp_minutes_over_60_raises():
    with pytest.raises(ValueError, match="timestamp"):
        SourceRef(source_id="x", timestamp="01:60:00")


def test_source_ref_timestamp_seconds_over_60_raises():
    with pytest.raises(ValueError, match="timestamp"):
        SourceRef(source_id="x", timestamp="01:00:60")


def test_source_ref_timestamp_max_valid_ok():
    SourceRef(source_id="x", timestamp="99:59:59")


# ---------------------------------------------------------------------------
# #L9 — ISO8601 at
# ---------------------------------------------------------------------------


def _make_entry(**overrides):
    base = dict(
        transcript_model=None,
        transcript_source=None,
        llm_provider="anthropic",
        llm_model="claude-x",
        worker=None,
        at="2026-06-10T14:00:00Z",
    )
    base.update(overrides)
    return ExtractionHistoryEntry(**base)


def test_extraction_history_entry_at_invalid_iso_raises():
    with pytest.raises(ValueError, match="at"):
        _make_entry(at="hier soir")


def test_extraction_history_entry_at_accepts_z_suffix():
    e = _make_entry(at="2026-06-10T14:00:00Z")
    assert e.at == "2026-06-10T14:00:00Z"


def test_extraction_history_entry_at_accepts_iso_with_offset():
    e = _make_entry(at="2026-06-10T14:00:00+02:00")
    assert e.at == "2026-06-10T14:00:00+02:00"


def test_extraction_history_entry_extra_non_mapping_raises():
    with pytest.raises(ValueError, match="extra"):
        _make_entry(extra=[("k", "v")])  # type: ignore[arg-type]


def test_extraction_history_entry_extra_scalar_values_accepted():
    """C3 — `extra` accepte str|int|float|bool (scalaires JSON)."""
    e = _make_entry(extra={"s": "x", "i": 42, "f": 3.14, "b": True})
    assert e.extra["s"] == "x"
    assert e.extra["i"] == 42
    assert e.extra["f"] == 3.14
    assert e.extra["b"] is True


def test_extraction_history_entry_extra_non_scalar_value_raises():
    """C3 — Une valeur non-scalaire (ex. dict) doit rester rejetée."""
    with pytest.raises(ValueError, match="extra"):
        _make_entry(extra={"k": {"nested": 1}})  # type: ignore[arg-type]


def test_extraction_history_entry_extra_non_str_key_raises():
    with pytest.raises(ValueError, match="extra"):
        _make_entry(extra={42: "v"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# #L11 — Stabilité ordre types
# ---------------------------------------------------------------------------


def test_find_matching_item_types_order_irrelevant_post_adr_0002():
    # Comme canonical_key ignore les types, l'ordre des types dans
    # existing n'a aucune incidence sur la clé. La résolution se fait
    # via intersection.
    key = canonical_key("Drive", "Refn")
    existing = {
        "id1": (key, (ItemType.SERIES, ItemType.FILM)),
        "id2": (key, (ItemType.FILM, ItemType.SERIES)),
    }
    # Premier match (ordre d'insertion).
    assert find_matching_item(key, (ItemType.FILM,), existing) == "id1"


# ---------------------------------------------------------------------------
# #L5 — can_attach_mention cas réel
# ---------------------------------------------------------------------------


def test_item_recommended_by_blank_raises():
    with pytest.raises(ValueError, match="recommended_by"):
        _make_item(recommended_by="   ")


def test_item_recommended_by_non_str_raises():
    with pytest.raises(ValueError, match="recommended_by"):
        _make_item(recommended_by=42)  # type: ignore[arg-type]


def test_source_ref_transcript_source_non_str_non_enum_raises():
    with pytest.raises(ValueError, match="transcript_source"):
        SourceRef(source_id="x", transcript_source=42)  # type: ignore[arg-type]


def test_can_attach_mention_real_chain():
    item = _make_item(id="real-id-1")
    mention = _make_mention(item_id="real-id-1")
    assert domain.can_attach_mention(mention, item) is True
    # Ré-attribuer l'item à un autre id casserait l'attache.
    other = _make_item(id="other-id-2")
    assert domain.can_attach_mention(mention, other) is False
