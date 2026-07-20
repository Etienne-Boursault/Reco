"""Tests TDD pour `RecommendedByConsistencyRule` (C3/H4/H8/L11)."""
from __future__ import annotations

from lint.rules.base import LintContext, Severity
from lint.rules.recommendedby_consistency import RecommendedByConsistencyRule
from tools.config.schema import SourceConfig


_HOST_CFG = SourceConfig(
    id="ubm", title="UBM", reco_prefix="ubm", hosts=("Alice",),
)


def _ctx(*, recos=(), episodes=(), cfg=_HOST_CFG, overrides=()):
    return LintContext(
        source_id="ubm", recos=recos, episodes=episodes,
        source_config=cfg, overrides=tuple(overrides),
    )


def test_recommendedby_matching_host_is_clean():
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-1", "recommendedBy": "Alice", "episodeGuid": "g"}
    ep = {"guid": "g", "guestsParsed": ["Bob"]}
    assert list(rule.check(_ctx(recos=(reco,), episodes=(ep,)))) == []


def test_recommendedby_matching_guest_is_clean():
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-2", "recommendedBy": "Bob", "episodeGuid": "g"}
    ep = {"guid": "g", "guestsParsed": ["Bob"]}
    assert list(rule.check(_ctx(recos=(reco,), episodes=(ep,)))) == []


def test_recommendedby_case_insensitive():
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-3", "recommendedBy": "  alice  ", "episodeGuid": "g"}
    ep = {"guid": "g"}
    assert list(rule.check(_ctx(recos=(reco,), episodes=(ep,)))) == []


def test_recommendedby_unknown_person_flagged_warning():
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-4", "recommendedBy": "Eve", "episodeGuid": "g"}
    ep = {"guid": "g", "guestsParsed": ["Bob"]}
    issues = list(rule.check(_ctx(recos=(reco,), episodes=(ep,))))
    flags = [i for i in issues if i.rule == "recommendedby_consistency"]
    assert len(flags) == 1
    assert flags[0].severity == Severity.WARNING
    assert flags[0].field == "recommendedBy"


def test_recommendedby_none_is_silent():
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-5", "episodeGuid": "g"}
    ep = {"guid": "g", "guestsParsed": ["Bob"]}
    assert list(rule.check(_ctx(recos=(reco,), episodes=(ep,)))) == []


def test_non_string_name_in_guests_is_ignored():
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-x", "recommendedBy": "Alice", "episodeGuid": "g"}
    ep = {"guid": "g", "guestsParsed": [None, 42, "Alice"]}
    assert list(rule.check(_ctx(recos=(reco,), episodes=(ep,)))) == []


def test_no_known_names_does_not_false_positive():
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-6", "recommendedBy": "Eve", "episodeGuid": "g"}
    ep = {"guid": "g"}
    ctx = LintContext(
        source_id="ubm", recos=(reco,), episodes=(ep,), source_config=None,
    )
    assert list(rule.check(ctx)) == []


# ---------------------------------------------------------------------------
# C3 — sentinels whitelistés
# ---------------------------------------------------------------------------


def test_sentinel_inconnu_is_silent():
    rule = RecommendedByConsistencyRule()
    for sentinel in ("Inconnu", "Invité", "Invitée", "Plusieurs invités",
                     "Tout le monde", "intervenant"):
        reco = {
            "id": f"ubm-sent-{sentinel}",
            "recommendedBy": sentinel, "episodeGuid": "g",
        }
        ep = {"guid": "g", "guestsParsed": ["Bob"]}
        issues = list(rule.check(_ctx(recos=(reco,), episodes=(ep,))))
        assert not any(i.rule == "recommendedby_consistency" for i in issues), \
            f"sentinel {sentinel!r} aurait dû être silencieux"


# ---------------------------------------------------------------------------
# C3 — co-recos split
# ---------------------------------------------------------------------------


def test_co_reco_with_ampersand_finds_member():
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-co1", "recommendedBy": "Alice & Bob", "episodeGuid": "g"}
    ep = {"guid": "g", "guestsParsed": ["Bob"]}
    assert list(rule.check(_ctx(recos=(reco,), episodes=(ep,)))) == []


def test_co_reco_with_comma_finds_member():
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-co2", "recommendedBy": "Eve, Alice", "episodeGuid": "g"}
    ep = {"guid": "g"}
    # Alice = host de la config
    assert list(rule.check(_ctx(recos=(reco,), episodes=(ep,)))) == []


def test_co_reco_with_et_finds_member():
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-co3", "recommendedBy": "Eve et Alice", "episodeGuid": "g"}
    ep = {"guid": "g"}
    assert list(rule.check(_ctx(recos=(reco,), episodes=(ep,)))) == []


def test_co_reco_all_unknown_flagged():
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-co4", "recommendedBy": "Eve & Mallory", "episodeGuid": "g"}
    ep = {"guid": "g"}
    issues = list(rule.check(_ctx(recos=(reco,), episodes=(ep,))))
    assert any(i.rule == "recommendedby_consistency" for i in issues)


# ---------------------------------------------------------------------------
# H8 — Unicode normalization
# ---------------------------------------------------------------------------


def test_nfkc_normalization_handles_nfd_vs_nfc():
    import unicodedata
    rule = RecommendedByConsistencyRule()
    nfd = unicodedata.normalize("NFD", "Mélanie Doutey")
    nfc = unicodedata.normalize("NFC", "Mélanie Doutey")
    assert nfd != nfc  # confirme la différence binaire
    reco = {"id": "ubm-uni", "recommendedBy": nfd, "episodeGuid": "g"}
    ep = {"guid": "g", "guestsParsed": [nfc]}
    assert list(rule.check(_ctx(recos=(reco,), episodes=(ep,)))) == []


# ---------------------------------------------------------------------------
# L11 — orphan episode ref
# ---------------------------------------------------------------------------


def test_orphan_episode_ref_emits_info():
    """L11 : guid présent mais épisode introuvable → INFO `orphan_episode_ref`."""
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-orph", "recommendedBy": "Alice", "episodeGuid": "missing"}
    issues = list(rule.check(_ctx(recos=(reco,), episodes=())))
    orphan = [i for i in issues if i.rule == "orphan_episode_ref"]
    assert orphan
    assert orphan[0].severity == Severity.INFO
    assert orphan[0].field == "episodeGuid"


# ---------------------------------------------------------------------------
# H4 — overrides
# ---------------------------------------------------------------------------


def test_empty_recommendedby_after_split_is_silent():
    """Cas tordu : ``recommendedBy="  &  "`` → tous les splits vides."""
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-emp", "recommendedBy": " & ", "episodeGuid": "g"}
    ep = {"guid": "g", "guestsParsed": ["Bob"]}
    # Devrait être silencieux car la string n'est pas blank mais
    # tous les membres splittés le sont.
    assert list(rule.check(_ctx(recos=(reco,), episodes=(ep,)))) == []


def test_override_silences_recommendedby_warning():
    rule = RecommendedByConsistencyRule()
    reco = {"id": "ubm-ov", "recommendedBy": "Eve", "episodeGuid": "g"}
    ep = {"guid": "g", "guestsParsed": ["Bob"]}
    overrides = [{"entity_id": "ubm-ov", "field": "recommendedBy", "ignore": True}]
    issues = list(rule.check(_ctx(recos=(reco,), episodes=(ep,), overrides=overrides)))
    assert not any(i.rule == "recommendedby_consistency" for i in issues)
