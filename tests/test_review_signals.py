"""Tests de `tools/review_signals.py` — l'encadré « À vérifier »."""
from __future__ import annotations

import review_render as rr
import review_signals as rsig
from _html_helpers import find_input, is_checked, parse
from review_guests import collect_guests, partial_match, render_guests_panel

HOSTS = ["Kyan Khojandi", "Navo"]
EP = {"guid": "yt-x", "guestsParsed": ["Carla de Coignac", "Félix Radu"],
      "audioDuration": 3600}


def kinds(r: dict, ep: dict = EP) -> list[str]:
    return [s.kind for s in rsig.reco_signals(r, ep, HOSTS)]


def base(**kw) -> dict:
    r = {"id": "r", "title": "Brazil", "quote": "Allez voir Brazil.",
         "timestamp": "00:10:00", "status": "draft"}
    r.update(kw)
    return r


def test_nothing_to_flag():
    assert kinds(base(recommendedBy="Navo")) == []


def test_first_name_of_a_guest_gets_a_one_click_fix():
    [s] = rsig.reco_signals(base(recommendedBy="Carla"), EP, HOSTS)
    assert s.kind == "who-partial"
    assert (s.fix_from, s.fix_to) == ("Carla", "Carla de Coignac")


def test_first_name_of_a_host_too():
    [s] = rsig.reco_signals(base(recommendedBy="Kyan"), EP, HOSTS)
    assert s.fix_to == "Kyan Khojandi"


def test_ambiguous_first_name_is_unknown_not_fixed():
    ep = {**EP, "guestsParsed": ["Carla de Coignac", "Carla Bruni"]}
    [s] = rsig.reco_signals(base(recommendedBy="Carla"), ep, HOSTS)
    assert s.kind == "who-unknown" and not s.fix_to


def test_stranger_is_flagged():
    assert kinds(base(recommendedBy="Fabrice Éboué")) == ["who-unknown"]


def test_names_compare_without_accents_or_case():
    assert kinds(base(recommendedBy="felix radu & NAVO")) == []


def test_excluded_and_placeholder_guests_are_not_people():
    ep = {**EP, "guestsExcluded": ["Félix Radu"],
          "guests": ["invité non spécifié"]}
    people = rsig.episode_people(ep, HOSTS)
    assert "Félix Radu" not in people
    assert all("spécifié" not in p for p in people)
    assert people[:2] == HOSTS


def test_parsed_fallback_when_no_snapshot():
    ep = {"guid": "g"}
    assert rsig.episode_people(ep, [], parsed=["Babor"]) == ["Babor"]


def test_creator_who_is_a_guest():
    r = base(creator="Félix Radu", recommendedBy="Navo")
    assert kinds(r) == ["creator-is-guest"]


def test_creator_flag_respects_word_boundaries_and_decisions():
    ep = {**EP, "guestsParsed": ["Seb"]}
    assert kinds(base(creator="Sébastien Tellier"), ep) == []
    assert kinds(base(creator="Félix Radu", guestWork=True)) == []
    assert kinds(base(creator="Félix Radu", kind="citation")) == []
    assert kinds(base(creator="")) == []


def test_season_in_quote_but_not_in_title():
    [s] = rsig.reco_signals(base(title="Bref", quote="la saison 2 de Bref"), EP, HOSTS)
    assert s.kind == "number-mismatch"
    assert "saison 2" in s.message and "n'en dit rien" in s.message


def test_season_disagreement_names_both():
    [s] = rsig.reco_signals(
        base(title="Fargo saison 3", quote="Fargo, saison IV"), EP, HOSTS)
    assert "saison 4" in s.message and "saison 3" in s.message


def test_numbers_that_agree_are_fine():
    assert kinds(base(title="Étincelle 2", quote="le volume 2")) == []
    assert kinds(base(title="Loki saison 2", quote="la saison deux, saison 2")) == []
    assert kinds(base(title="Dune tome II", quote="le tome 2 de Dune")) == []
    assert kinds(base(quote="saison xyz")) == []
    assert kinds(base(quote="saison xx")) == []  # chiffre romain hors table


def test_missing_quote_and_timestamp():
    assert kinds(base(quote="  ", timestamp=None)) == ["no-quote", "no-timestamp"]


def test_timestamp_beyond_the_end():
    assert kinds(base(timestamp="02:00:00")) == ["timestamp-out"]
    assert kinds(base(timestamp="02:00:00"), {"guid": "g"}) == []


def test_discarded_recos_are_never_flagged():
    assert kinds(base(status="discarded", quote="", recommendedBy="X")) == []


def test_render_signals_html():
    assert rsig.render_signals([]) == ""
    out = rsig.render_signals([
        rsig.Signal("who-partial", "« Carla » <b>", "Carla", "Carla de Coignac"),
        rsig.Signal("creator-is-guest", "msg"),
        rsig.Signal("no-quote", "Pas de citation."),
    ])
    assert "À vérifier" in out
    assert 'data-fix-to="Carla de Coignac"' in out
    assert 'data-fix-action="guest-work"' in out
    assert "&lt;b&gt;" in out  # échappé
    assert out.count('class="verif-fix"') == 2


# ===== Prénom seul : le panneau des invités suit l'encadré ==================
# Cas réel : invités « Babor » et « Jenny Letellier », une reco attribuée à
# « Jenny ». L'encadré dit « sans doute Jenny Letellier » ; le panneau des
# invités ne doit pas en faire une 3ᵉ invitée — mais la carte de CETTE reco
# doit garder la case « Jenny » cochée (sinon « Valider » l'effacerait).
JENNY_EP = {"guid": "g", "title": "Ep",
            "guestsParsed": ["Babor", "Jenny Letellier"]}


def test_partial_match_is_the_signal_rule():
    people = ["Babor", "Jenny Letellier"]
    assert partial_match("jénny", people) == "Jenny Letellier"
    assert partial_match("LETELLIER", people) == "Jenny Letellier"
    assert partial_match("Babor", people) == ""  # nom d'un seul mot : connu tel quel
    assert partial_match("Jenny Martin", people) == ""
    assert partial_match("", people) == ""
    assert rsig._partial_match is partial_match  # une seule implémentation


def test_first_name_of_a_full_name_guest_is_not_another_guest():
    recs = [{"recommendedBy": "Jenny"}, {"recommendedBy": "letellier & Babor"}]
    assert collect_guests(JENNY_EP, recs, []) == ["Babor", "Jenny Letellier"]
    panel = render_guests_panel("g", JENNY_EP, recs, [])
    assert 'value="Jenny"' not in panel
    assert "Invités de l'épisode (2)" in panel


def test_first_name_of_a_host_is_not_a_guest():
    recs = [{"recommendedBy": "Kyan"}]
    assert collect_guests({"guid": "g"}, recs, HOSTS) == []


def test_first_name_filter_uses_parsed_fallback():
    ep = {"guid": "g"}
    assert collect_guests(ep, [{"recommendedBy": "Jenny"}], [],
                          parsed=["Jenny Letellier"]) == ["Jenny Letellier"]


def test_first_name_is_kept_when_ambiguous_unknown_or_manual():
    two = {**JENNY_EP, "guestsParsed": ["Jenny Letellier", "Jenny Martin"]}
    assert "Jenny" in collect_guests(two, [{"recommendedBy": "Jenny"}], [])
    assert "Zoé" in collect_guests(JENNY_EP, [{"recommendedBy": "Zoé"}], [])
    assert "Jenny Martin" in collect_guests(
        JENNY_EP, [{"recommendedBy": "Jenny Martin"}], [])
    # Ajout manuel : jamais filtré.
    manual = {**JENNY_EP, "guests": ["Jenny"]}
    assert collect_guests(manual, [], []) == ["Jenny", "Babor", "Jenny Letellier"]
    # Nom complet exclu : il ne couvre plus le prénom.
    excl = {**JENNY_EP, "guestsExcluded": ["Jenny Letellier"]}
    assert collect_guests(excl, [{"recommendedBy": "Jenny"}], []) == ["Babor", "Jenny"]


def _who(card: str) -> dict[str, bool]:
    soup = parse(card)
    return {i["value"]: is_checked(i)
            for i in soup.find_all("input", {"name": "who"})}


def test_card_keeps_its_own_first_name_checked_next_to_the_full_name():
    """INVARIANT : la case « Jenny » reste cochée sur SA carte, à côté de
    « Jenny Letellier » — « Corriger en … » décoche l'une, coche l'autre, et
    « Valider » (qui reconstruit recommendedBy depuis les cases) ne perd rien."""
    r1 = {"id": "a", "title": "T", "types": ["film"], "status": "draft",
          "recommendedBy": "Jenny & Babor"}
    r2 = {"id": "b", "title": "U", "types": ["film"], "status": "draft",
          "recommendedBy": "Babor"}
    card1 = rr._reco_card(r1, JENNY_EP, [], "src", siblings=[r1, r2])
    who1 = _who(card1)
    assert who1["Jenny"] is True and who1["Babor"] is True
    assert who1["Jenny Letellier"] is False
    assert {n for n, on in who1.items() if on} == {"Jenny", "Babor"}
    fix = parse(card1).find("button", {"class": "verif-fix"})
    assert (fix["data-fix-from"], fix["data-fix-to"]) == ("Jenny", "Jenny Letellier")
    # Les AUTRES cartes ne proposent pas « Jenny » comme une invitée de plus.
    card2 = rr._reco_card(r2, JENNY_EP, [], "src", siblings=[r1, r2])
    assert "Jenny" not in _who(card2)
    assert "Jenny Letellier" in _who(card2)


def test_card_still_drops_placeholders_and_excluded_names():
    ep = {**JENNY_EP, "guestsExcluded": ["Truc"]}
    r = {"id": "a", "title": "T", "types": ["film"], "status": "draft",
         "recommendedBy": "non spécifié & truc & Babor & Babor"}
    names = rr._reco_candidates(r, ep, [], [r])
    assert names == ["Babor", "Jenny Letellier"]
    assert find_input(parse(rr._reco_checkboxes(names, r["recommendedBy"])),
                      "who", "Babor") is not None
