"""Tests : la liste seenGuids est bornée à MAX_SEEN_GUIDS (LRU)."""
from __future__ import annotations

from rss.state import MAX_SEEN_GUIDS, PollingState


def test_seen_guids_capped_to_max():
    s = PollingState(source_id="x")
    # On simule N runs successifs.
    new_guids = [f"g{i}" for i in range(MAX_SEEN_GUIDS + 50)]
    s2 = s.with_observed(guids=new_guids, checked_at="t")
    assert len(s2.seen_guids) == MAX_SEEN_GUIDS


def test_lru_evicts_oldest_first():
    # On simule un état déjà à la capacité, puis on ajoute 5 GUIDs nouveaux.
    seed = tuple(f"old{i}" for i in range(MAX_SEEN_GUIDS))
    s = PollingState(source_id="x", seen_guids=seed)
    s2 = s.with_observed(guids=["new0", "new1", "new2"], checked_at="t")
    assert len(s2.seen_guids) == MAX_SEEN_GUIDS
    # Les 3 plus vieux sont évincés.
    assert "old0" not in s2.seen_guids
    assert "old2" not in s2.seen_guids
    # Les anciens "récents" sont préservés (le DERNIER non-évincé est juste
    # avant les 3 nouveaux : on a évincé old0..old2, donc la queue =
    # old3..old9999, new2, new1, new0). `[-4]` = `old9999` (dernier ancien).
    assert s2.seen_guids[-4] == f"old{MAX_SEEN_GUIDS - 1}"
    # Les nouveaux sont en queue.
    assert s2.seen_guids[-3:] == ("new2", "new1", "new0")
