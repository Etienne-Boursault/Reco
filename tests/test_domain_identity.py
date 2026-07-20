"""Tests de `tools.domain.services.identity` — couverture 100%."""
from __future__ import annotations

import re

import pytest

from domain.item import ItemType
from domain.services.identity import ItemIdentityService, canonical_key


# ---------------------------------------------------------------------------
# canonical_key
# ---------------------------------------------------------------------------


def test_canonical_key_deterministic():
    k1 = canonical_key("Le Comte de Monte-Cristo", "Alexandre Dumas", (ItemType.BOOK,))
    k2 = canonical_key("Le Comte de Monte-Cristo", "Alexandre Dumas", (ItemType.BOOK,))
    assert k1 == k2


def test_canonical_key_strips_diacritics():
    k = canonical_key("Léa", "Émile", (ItemType.BOOK,))
    assert "é" not in k
    assert "lea" in k
    assert "emile" in k


def test_canonical_key_lowercases():
    a = canonical_key("DRIVE", "REFN", (ItemType.FILM,))
    b = canonical_key("drive", "refn", (ItemType.FILM,))
    assert a == b


def test_canonical_key_collapses_whitespace():
    a = canonical_key("Le   Comte", "Dumas", (ItemType.BOOK,))
    b = canonical_key("Le Comte", "Dumas", (ItemType.BOOK,))
    assert a == b


def test_canonical_key_strips_punctuation():
    a = canonical_key("Drive!", "Refn.", (ItemType.FILM,))
    b = canonical_key("Drive", "Refn", (ItemType.FILM,))
    assert a == b


def test_canonical_key_types_ignored_post_adr_0002():
    # Cf. ADR 0002 : les types ne participent plus à la clé.
    a = canonical_key("X", None, (ItemType.FILM, ItemType.SERIES))
    b = canonical_key("X", None, (ItemType.SERIES, ItemType.FILM))
    c = canonical_key("X", None)  # types optionnels désormais
    d = canonical_key("X", None, (ItemType.BOOK,))  # autre type, même clé
    assert a == b == c == d


def test_canonical_key_creator_none():
    # Séparateur NUL byte (cf. _SEPARATOR), creator vide => clé finit par NUL.
    k = canonical_key("Drive", None, (ItemType.FILM,))
    assert "\x00" in k
    assert k == "drive\x00"


def test_canonical_key_format():
    k = canonical_key("Drive", "Refn", (ItemType.FILM,))
    # title\x00creator (cf. ADR 0002 : pas de section types)
    parts = k.split("\x00")
    assert len(parts) == 2
    assert parts[0] == "drive"
    assert parts[1] == "refn"


def test_canonical_key_separator_invariant_no_pipe_no_nul_in_normalized():
    """Senior H4 : invariant que `_normalize_text` n'introduit jamais
    le séparateur NUL ni de pipe (pour rétro-compat lecture)."""
    k = canonical_key("a|b|c\x00d", "e\x00f|g", (ItemType.FILM,))
    parts = k.split("\x00")
    # Exactement 2 segments : title et creator (chacun sans NUL interne).
    assert len(parts) == 2
    assert "\x00" not in parts[0]
    assert "\x00" not in parts[1]


def test_canonical_key_empty_title_raises():
    with pytest.raises(ValueError, match="title"):
        canonical_key("", "Refn", (ItemType.FILM,))


def test_canonical_key_blank_title_raises():
    with pytest.raises(ValueError, match="title"):
        canonical_key("   ", "Refn", (ItemType.FILM,))


def test_canonical_key_non_str_title_raises():
    with pytest.raises(ValueError, match="title"):
        canonical_key(42, "Refn", (ItemType.FILM,))  # type: ignore[arg-type]


def test_canonical_key_title_only_punctuation_raises():
    with pytest.raises(ValueError, match="normalisation"):
        canonical_key("!!!", "X", (ItemType.FILM,))


def test_canonical_key_empty_types_now_ok_post_adr_0002():
    # Cf. ADR 0002 : types est déprécié et optionnel. () ne lève plus.
    k = canonical_key("Drive", "Refn", ())
    assert k == "drive\x00refn"


def test_canonical_key_types_none_ok():
    # Le param types est optionnel (default None).
    k = canonical_key("Drive", "Refn")
    assert k == "drive\x00refn"


def test_canonical_key_non_tuple_types_still_validated_if_provided():
    # Si fourni, on continue à valider qu'il s'agit bien d'un tuple
    # (évite qu'un appelant legacy passe n'importe quoi sans bruit).
    with pytest.raises(ValueError, match="types"):
        canonical_key("Drive", "Refn", [ItemType.FILM])  # type: ignore[arg-type]


def test_canonical_key_non_item_type_still_validated_if_provided():
    with pytest.raises(ValueError, match="types"):
        canonical_key("Drive", "Refn", ("film",))  # type: ignore[arg-type]


def test_canonical_key_blank_creator_treated_as_empty():
    # blank → normalize_text("   ") == "" → equivalent à None
    a = canonical_key("Drive", "   ", (ItemType.FILM,))
    b = canonical_key("Drive", None, (ItemType.FILM,))
    assert a == b


# ---------------------------------------------------------------------------
# ItemIdentityService.generate_id
# ---------------------------------------------------------------------------


_ID_RE = re.compile(r"^[a-f0-9]{8}(-\d+)?$")


def test_generate_id_stable():
    key = canonical_key("Drive", "Refn", (ItemType.FILM,))
    a = ItemIdentityService.generate_id(key, frozenset())
    b = ItemIdentityService.generate_id(key, frozenset())
    assert a == b


def test_generate_id_format_no_collision():
    key = canonical_key("Drive", "Refn", (ItemType.FILM,))
    id_ = ItemIdentityService.generate_id(key, frozenset())
    assert _ID_RE.match(id_), id_
    assert "-" not in id_  # pas de suffixe sans collision


def test_generate_id_resolves_collision_dash_1():
    key = canonical_key("Drive", "Refn", (ItemType.FILM,))
    base = ItemIdentityService.generate_id(key, frozenset())
    id_ = ItemIdentityService.generate_id(key, frozenset({base}))
    assert id_ == f"{base}-1"


def test_generate_id_resolves_collision_dash_2():
    key = canonical_key("Drive", "Refn", (ItemType.FILM,))
    base = ItemIdentityService.generate_id(key, frozenset())
    id_ = ItemIdentityService.generate_id(key, frozenset({base, f"{base}-1"}))
    assert id_ == f"{base}-2"


def test_generate_id_skips_existing_suffixes():
    key = canonical_key("Drive", "Refn", (ItemType.FILM,))
    base = ItemIdentityService.generate_id(key, frozenset())
    id_ = ItemIdentityService.generate_id(
        key, frozenset({base, f"{base}-1", f"{base}-2", f"{base}-3"})
    )
    assert id_ == f"{base}-4"


def test_generate_id_empty_canonical_raises():
    with pytest.raises(ValueError, match="canonical"):
        ItemIdentityService.generate_id("", frozenset())


def test_generate_id_non_str_canonical_raises():
    with pytest.raises(ValueError, match="canonical"):
        ItemIdentityService.generate_id(42, frozenset())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ItemIdentityService.find_match
# ---------------------------------------------------------------------------


def test_find_match_exact_returns_id():
    key = canonical_key("Drive", "Refn", (ItemType.FILM,))
    existing = {"abc12345": (key, (ItemType.FILM,))}
    match = ItemIdentityService.find_match(key, (ItemType.FILM,), existing)
    assert match == "abc12345"


def test_find_match_canonical_differs_returns_none():
    key_a = canonical_key("Drive", "Refn", (ItemType.FILM,))
    key_b = canonical_key("Other", "X", (ItemType.FILM,))
    existing = {"abc12345": (key_a, (ItemType.FILM,))}
    assert ItemIdentityService.find_match(key_b, (ItemType.FILM,), existing) is None


def test_find_match_disjoint_types_returns_none():
    key = canonical_key("Drive", "Refn", (ItemType.FILM,))
    existing = {"abc12345": (key, (ItemType.SERIES,))}
    match = ItemIdentityService.find_match(key, (ItemType.FILM,), existing)
    assert match is None


def test_find_match_overlapping_types_returns_id():
    key = canonical_key("Drive", "Refn", (ItemType.FILM,))
    existing = {"abc12345": (key, (ItemType.FILM, ItemType.SERIES))}
    match = ItemIdentityService.find_match(
        key, (ItemType.SERIES, ItemType.ALBUM), existing
    )
    assert match == "abc12345"


def test_find_match_empty_existing_returns_none():
    key = canonical_key("Drive", None, (ItemType.FILM,))
    assert ItemIdentityService.find_match(key, (ItemType.FILM,), {}) is None


def test_find_match_empty_candidate_types_raises():
    key = canonical_key("Drive", None, (ItemType.FILM,))
    with pytest.raises(ValueError, match="candidate_types"):
        ItemIdentityService.find_match(key, (), {})


def test_find_match_non_tuple_candidate_types_raises():
    key = canonical_key("Drive", None, (ItemType.FILM,))
    with pytest.raises(ValueError, match="candidate_types"):
        ItemIdentityService.find_match(key, [ItemType.FILM], {})  # type: ignore[arg-type]


def test_find_match_returns_first_match():
    key = canonical_key("Drive", "Refn", (ItemType.FILM,))
    # dict garde l'ordre d'insertion en 3.7+
    existing = {
        "first": (key, (ItemType.FILM,)),
        "second": (key, (ItemType.FILM,)),
    }
    match = ItemIdentityService.find_match(key, (ItemType.FILM,), existing)
    assert match == "first"


# ---------------------------------------------------------------------------
# A2 — IdentityRegistry.seed
# ---------------------------------------------------------------------------


def test_seed_idempotent():
    """Seedez la même paire deux fois → no-op."""
    from domain.services.identity import IdentityRegistry
    reg = IdentityRegistry()
    reg.seed("canon", "abc12345")
    reg.seed("canon", "abc12345")
    assert reg.reserve_id("canon") == "abc12345"


def test_seed_conflict_raises():
    """Seedez deux ids différents pour la même canonical → ValueError."""
    from domain.services.identity import IdentityRegistry
    reg = IdentityRegistry()
    reg.seed("canon", "abc12345")
    with pytest.raises(ValueError, match="conflit"):
        reg.seed("canon", "def67890")


def test_seed_then_reserve_id_returns_seeded():
    """Une fois seedée, reserve_id renvoie l'id pré-attribué."""
    from domain.services.identity import IdentityRegistry
    reg = IdentityRegistry()
    reg.seed("canon", "custom-id-1")
    assert reg.reserve_id("canon") == "custom-id-1"


def test_seed_marks_id_used_for_future_collisions():
    """Un id seedé est considéré comme utilisé : un canonical sans
    attribution préalable qui aurait naturellement choisi le même hash
    obtient un suffixe à la place."""
    from domain.services.identity import IdentityRegistry, generate_item_id
    reg = IdentityRegistry()
    # Pré-attribue l'id qui serait naturellement généré pour "other".
    natural_id = generate_item_id("other", frozenset())
    reg.seed("seeded-canonical", natural_id)
    # "other" est désormais en collision → suffixe.
    other_id = reg.reserve_id("other")
    assert other_id != natural_id
    assert other_id.startswith(natural_id)


def test_seed_rejects_empty_canonical():
    from domain.services.identity import IdentityRegistry
    reg = IdentityRegistry()
    with pytest.raises(ValueError, match="canonical"):
        reg.seed("", "abc12345")


def test_seed_rejects_empty_item_id():
    from domain.services.identity import IdentityRegistry
    reg = IdentityRegistry()
    with pytest.raises(ValueError, match="item_id"):
        reg.seed("canon", "")
