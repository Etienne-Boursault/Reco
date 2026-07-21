"""Tests pour tools/review_doubts.py — page /doutes (file de validation agent)."""
from __future__ import annotations

import pytest

import review_doubts
from review_doubts import LOW_CONFIDENCE, collect_doubts, render_doubts
from _html_helpers import parse


# ---- Fixtures ---------------------------------------------------------------
def _mk_groups(recos):
    """Construit le triple (source, episodes, groups) attendu par _load_groups."""
    source = {"title": "Un bon moment", "hosts": ["Kyan Khojandi", "Navo"]}
    episodes = {
        "g1": {"guid": "g1", "title": "Épisode Un", "season": 5, "number": 1},
    }
    groups = {"g1": recos}
    return source, episodes, groups


def _patch_groups(monkeypatch, recos):
    monkeypatch.setattr(
        review_doubts, "_load_groups", lambda source_id: _mk_groups(recos),
    )


def _reco(rid, status="draft", kind=None, recommended_by=None, agent=None):
    r = {"id": rid, "episodeGuid": "g1", "title": f"Œuvre {rid}",
         "types": ["film"], "status": status}
    if kind:
        r["kind"] = kind
    if recommended_by is not None:
        r["recommendedBy"] = recommended_by
    if agent is not None:
        r["agentReview"] = agent
    return r


# ---- collect_doubts ---------------------------------------------------------
def test_collect_via_monkeypatch_unsure(monkeypatch):
    _patch_groups(monkeypatch, [
        _reco("r1", status="draft",
              agent={"verdict": "unsure", "confidence": 0.4, "reason": "titre artefact"}),
    ])
    s = collect_doubts("src")
    assert [r["id"] for _, r in s["pending"]] == ["r1"]
    assert not s["recby"] and not s["lowconf"] and not s["flagged"]


def test_collect_validate_without_recby_goes_to_recby(monkeypatch):
    _patch_groups(monkeypatch, [
        _reco("r2", status="validated", kind="reco",
              agent={"verdict": "validate", "confidence": 0.9, "reason": "ok"}),
    ])
    s = collect_doubts("src")
    assert [r["id"] for _, r in s["recby"]] == ["r2"]


def test_collect_validate_with_recby_not_in_recby(monkeypatch):
    _patch_groups(monkeypatch, [
        _reco("r3", status="validated", kind="reco", recommended_by="Navo",
              agent={"verdict": "validate", "confidence": 0.9, "reason": "ok"}),
    ])
    s = collect_doubts("src")
    assert not s["recby"]


def test_collect_low_confidence_applied(monkeypatch):
    _patch_groups(monkeypatch, [
        _reco("r4", status="discarded",
              agent={"verdict": "discard", "confidence": 0.5, "reason": "borderline"}),
    ])
    s = collect_doubts("src")
    assert [r["id"] for _, r in s["lowconf"]] == ["r4"]


def test_collect_high_confidence_not_lowconf(monkeypatch):
    _patch_groups(monkeypatch, [
        _reco("r5", status="discarded",
              agent={"verdict": "discard", "confidence": 0.9, "reason": "sûr"}),
    ])
    s = collect_doubts("src")
    assert not s["lowconf"]


def test_collect_flags_go_to_flagged(monkeypatch):
    _patch_groups(monkeypatch, [
        _reco("r6", status="validated", kind="reco", recommended_by="Navo",
              agent={"verdict": "validate", "confidence": 0.9,
                     "reason": "ok", "flags": ["title_suspect"],
                     "note": "orthographe à vérifier"}),
    ])
    s = collect_doubts("src")
    assert [r["id"] for _, r in s["flagged"]] == ["r6"]


def test_collect_guestwork_without_recby_goes_to_recby(monkeypatch):
    # Une œuvre d'invité (guestWork, kind=reco) validée sans prescripteur doit
    # apparaître dans « Reco de » à compléter, comme une reco classique.
    r = _reco("r11", status="validated", kind="reco",
              agent={"verdict": "validate", "confidence": 0.9, "reason": "ok"})
    r["guestWork"] = True
    _patch_groups(monkeypatch, [r])
    s = collect_doubts("src")
    assert [x["id"] for _, x in s["recby"]] == ["r11"]


def test_collect_citation_without_recby_not_listed(monkeypatch):
    # Les citations sans recommendedBy sont normales (pas de prescripteur).
    _patch_groups(monkeypatch, [
        _reco("r7", status="validated", kind="citation",
              agent={"verdict": "citation", "confidence": 0.9, "reason": "ok"}),
    ])
    s = collect_doubts("src")
    assert not s["recby"]


def test_collect_ignores_recos_without_agent_review(monkeypatch):
    _patch_groups(monkeypatch, [
        _reco("r8", status="draft"),
        _reco("r9", status="validated", kind="reco"),
    ])
    s = collect_doubts("src")
    assert not any(s.values())


def test_collect_no_duplicate_between_sections(monkeypatch):
    # unsure + flags + basse confiance → une seule apparition (pending prime).
    _patch_groups(monkeypatch, [
        _reco("r10", status="draft",
              agent={"verdict": "unsure", "confidence": 0.3,
                     "reason": "?", "flags": ["title_suspect"]}),
    ])
    s = collect_doubts("src")
    ids = [r["id"] for sec in s.values() for _, r in sec]
    assert ids.count("r10") == 1
    assert [r["id"] for _, r in s["pending"]] == ["r10"]


# ---- render_doubts (V2 — groupé PAR TYPE, 2026-07-19) -----------------------
def test_render_grouped_by_type(monkeypatch):
    """La page est organisée PAR TYPE d'info à valider (une section par type),
    chaque reco portant une puce épisode — plus un bloc par épisode."""
    _patch_groups(monkeypatch, [
        _reco("r1", status="draft",
              agent={"verdict": "unsure", "confidence": 0.4, "reason": "titre artefact"}),
        _reco("r2", status="validated", kind="reco",
              agent={"verdict": "validate", "confidence": 0.9, "reason": "ok"}),
    ])
    out = render_doubts("src", ep="g1")
    # Sections par type via leurs ancres (markup, pas le CSS inliné) : pending
    # (r1) et recby (r2, validée sans prescripteur).
    assert 'id="sec-pending"' in out
    assert 'id="sec-recby"' in out
    # L'épisode est visible via une puce sur CHAQUE item → apparaît plusieurs
    # fois (une par section concernée), et pointe vers la page épisode.
    assert 'class="doubt-ep-tag"' in out
    assert out.count("Épisode Un") >= 2
    assert "/ep?guid=g1" in out
    assert 'data-reco-id="r1"' in out
    assert 'data-reco-id="r2"' in out
    # En-têtes de type (nouveaux libellés) + sommaire cliquable.
    assert "À trancher" in out
    assert "Qui recommande" in out
    assert 'class="doubt-summary"' in out


def test_render_types_ordered_within_episode(monkeypatch):
    """Refonte 2026-07-21 — dans la vue d'UN épisode, les sections restent dans
    l'ordre de priorité de _SECTIONS (pending avant lowconf)."""
    source = {"title": "Src", "hosts": []}
    episodes = {
        "g1": {"guid": "g1", "title": "Épisode Un", "season": 5, "number": 1},
    }
    r_low = _reco("rlow", status="discarded",
                  agent={"verdict": "discard", "confidence": 0.5, "reason": "l"})
    r_pending = _reco("rpend", status="draft",
                      agent={"verdict": "unsure", "confidence": 0.4, "reason": "p"})
    monkeypatch.setattr(
        review_doubts, "_load_groups",
        lambda source_id: (source, episodes, {"g1": [r_low, r_pending]}),
    )
    out = render_doubts("src", ep="g1")
    assert out.index('id="sec-pending"') < out.index('id="sec-lowconf"')
    assert 'data-reco-id="rpend"' in out and 'data-reco-id="rlow"' in out


def test_render_index_lists_episodes_recent_first(monkeypatch):
    """Refonte 2026-07-21 — /doutes (sans ep) rend un index LÉGER : la liste des
    épisodes à revoir, du plus récent au plus ancien, sans carte ni lecteur."""
    source = {"title": "Src", "hosts": []}
    episodes = {
        "old": {"guid": "old", "title": "Vieux", "date": "2020-01-01"},
        "new": {"guid": "new", "title": "Récent", "date": "2026-01-01"},
    }
    mk = lambda rid: _reco(rid, status="draft",
                           agent={"verdict": "unsure", "confidence": 0.4, "reason": "?"})
    r_old, r_new = mk("ro"), mk("rn")
    r_old["episodeGuid"], r_new["episodeGuid"] = "old", "new"
    monkeypatch.setattr(
        review_doubts, "_load_groups",
        lambda source_id: (source, episodes, {"old": [r_old], "new": [r_new]}),
    )
    out = render_doubts("src")
    # Index : liens vers chaque épisode, aucune carte, récent avant vieux.
    assert 'href="/doutes?ep=new"' in out and 'href="/doutes?ep=old"' in out
    assert out.index("Récent") < out.index("Vieux")
    # Aucune CARTE sur l'index (les data-reco-id des recos ne sont pas rendus ;
    # la chaîne générique existe dans le bundle JS, on cible donc les vrais id).
    assert 'data-reco-id="ro"' not in out and 'data-reco-id="rn"' not in out
    assert 'class="doubt-ep-list"' in out


def test_render_edit_button_targets_doutes(monkeypatch):
    """Sur /doutes, le bouton Éditer reste dans la file (/doutes?edit=) pour
    revenir à /doutes après save (#M3) — jamais vers /ep."""
    _patch_groups(monkeypatch, [
        _reco("r1", status="draft",
              agent={"verdict": "unsure", "confidence": 0.4, "reason": "?"}),
    ])
    out = render_doubts("src", ep="g1")
    assert 'btn-edit" href="/doutes?ep=g1&edit=r1"' in out
    assert 'btn-edit" href="/ep' not in out


def test_render_edit_id_renders_inline_form(monkeypatch):
    """render_doubts(edit_id=...) rend le formulaire d'édition inline (action
    /edit) au lieu de la carte normale ; sans edit_id, aucun formulaire /edit."""
    _patch_groups(monkeypatch, [
        _reco("r1", status="draft",
              agent={"verdict": "unsure", "confidence": 0.4, "reason": "?"}),
    ])
    assert 'action="/edit"' not in render_doubts("src", ep="g1")
    assert 'action="/edit"' in render_doubts("src", ep="g1", edit_id="r1")


def test_render_empty_state(monkeypatch):
    _patch_groups(monkeypatch, [])
    out = render_doubts("src")
    assert "Aucun doute" in out


def test_render_section_agent_block_inside_li(monkeypatch):
    """L1 — chaque bloc agent (.agent-review) est enveloppé dans un <li>,
    jamais enfant direct d'un <ul> (HTML invalide sinon)."""
    _patch_groups(monkeypatch, [
        _reco("r1", status="draft",
              agent={"verdict": "unsure", "confidence": 0.4, "reason": "?"}),
    ])
    out = render_doubts("src", ep="g1")
    soup = parse(out)
    blocks = soup.select(".agent-review")
    assert blocks  # au moins un bloc rendu
    for block in blocks:
        assert block.parent.name != "ul"
        assert block.find_parent("li") is not None


def test_render_includes_player_wrap(monkeypatch):
    """M2 — la page /doutes injecte le wrap player (data-player-wrap) pour que
    les liens timecode (target=ytplayer) jouent inline au lieu d'ouvrir un
    onglet."""
    _patch_groups(monkeypatch, [
        _reco("r1", status="draft",
              agent={"verdict": "unsure", "confidence": 0.4, "reason": "?"}),
    ])
    out = render_doubts("src")
    assert "data-player-wrap" in out


# ---- M1 : coercion défensive de confidence ----------------------------------
def test_section_for_coerces_string_confidence():
    """Une confidence en chaîne ('0.4') ne fait pas planter le tri : elle est
    coercée en float (< 0.7 → lowconf), et une valeur non numérique est ignorée."""
    from review_doubts import _section_for
    base = {"status": "validated", "kind": "reco", "recommendedBy": "X"}
    assert _section_for({**base, "agentReview": {"verdict": "v", "confidence": "0.4"}}) == "lowconf"
    assert _section_for({**base, "agentReview": {"verdict": "v", "confidence": "0.9"}}) is None
    assert _section_for({**base, "agentReview": {"verdict": "v", "confidence": "high"}}) is None
    assert _section_for({**base, "agentReview": {"verdict": "v", "confidence": None}}) is None


def test_render_string_confidence_does_not_crash(monkeypatch):
    """Intégration M1 — une reco à confidence textuelle ne fait pas tomber toute
    la page /doutes (la route n'a pas de try/except)."""
    _patch_groups(monkeypatch, [
        _reco("r1", status="validated", kind="reco", recommended_by="Kyan",
              agent={"verdict": "validate", "confidence": "0.4", "reason": "?"}),
    ])
    out = render_doubts("src", ep="g1")  # ne doit pas lever
    assert 'data-reco-id="r1"' in out


def test_section_for_non_string_recommendedby_no_crash():
    """m5 (revue 2026-07-19) — un recommendedBy non-string (liste, donnée agent
    malformée) ne fait pas planter le tri (str() défensif) ; _section_for tourne
    pour CHAQUE reco de l'index ET de /doutes."""
    from review_doubts import _section_for
    base = {"status": "validated", "kind": "reco",
            "agentReview": {"verdict": "validate", "confidence": 0.9}}
    # Liste non vide → traité comme « a un prescripteur » → pas recby, pas de crash.
    assert _section_for({**base, "recommendedBy": ["Kyan"]}) is None
    # Liste vide (falsy) → traité comme absent → recby.
    assert _section_for({**base, "recommendedBy": []}) == "recby"


def test_render_doubts_cancel_returns_to_doutes(monkeypatch):
    """M2 (rev-render) — le lien Annuler de l'édition inline sur /doutes revient
    à /doutes (pas /ep) : le save y retournait déjà, l'Annuler suit."""
    _patch_groups(monkeypatch, [
        _reco("r1", status="draft",
              agent={"verdict": "unsure", "confidence": 0.4, "reason": "?"}),
    ])
    out = render_doubts("src", ep="g1", edit_id="r1")
    assert 'href="/doutes?ep=g1">Annuler</a>' in out
    assert 'href="/ep?guid=g1">Annuler' not in out


def test_render_escapes_reason(monkeypatch):
    _patch_groups(monkeypatch, [
        _reco("r1", status="draft",
              agent={"verdict": "unsure", "confidence": 0.4,
                     "reason": '<script>alert(1)</script>'}),
    ])
    out = render_doubts("src")
    assert "<script>alert(1)</script>" not in out


def test_render_shows_confidence_and_reason(monkeypatch):
    _patch_groups(monkeypatch, [
        _reco("r1", status="draft",
              agent={"verdict": "unsure", "confidence": 0.42, "reason": "cas limite"}),
    ])
    out = render_doubts("src", ep="g1")
    assert "cas limite" in out
    assert "0.42" in out or "42" in out


def test_render_episode_link_carries_youtube_title_tooltip(monkeypatch):
    """L3 CR — le lien d'épisode de /doutes expose le youtubeTitle en tooltip
    quand il diffère du titre RSS (symétrie avec _ep_header)."""
    source = {"title": "Src", "hosts": []}
    episodes = {"g1": {"guid": "g1", "title": "Titre RSS",
                       "youtubeTitle": "English Format Title"}}
    recos = [_reco("r1", status="draft",
                   agent={"verdict": "unsure", "confidence": 0.4, "reason": "?"})]
    monkeypatch.setattr(
        review_doubts, "_load_groups",
        lambda source_id: (source, episodes, {"g1": recos}),
    )
    out = render_doubts("src", ep="g1")
    assert 'title="YouTube : English Format Title"' in out


# ---- rev-render m3 : bannière flash sur /doutes (retour non-JS) --------------
def test_render_doubts_flash_banner_shown(monkeypatch):
    """rev-render m3 (revue 2026-07-19) — un flash passé à render_doubts est
    rendu en bannière (flash-<kind>). Sans ça, le message d'un POST /save initié
    depuis /doutes (redirigé vers /doutes?flash=…) était PERDU sans JS."""
    _patch_groups(monkeypatch, [
        _reco("r1", status="draft",
              agent={"verdict": "unsure", "confidence": 0.4, "reason": "?"}),
    ])
    out = render_doubts("src", flash="Validée.", flash_kind="success")
    soup = parse(out)
    banner = soup.select_one(".flash.flash-success")
    assert banner is not None
    assert "Validée." in banner.get_text()


def test_render_doubts_flash_banner_on_empty_state(monkeypatch):
    """rev-render m3 — la bannière apparaît aussi sur l'état vide (0 doute)."""
    _patch_groups(monkeypatch, [])
    out = render_doubts("src", flash="Traité — reco suivante.",
                        flash_kind="success")
    assert "flash-success" in out
    assert "Traité — reco suivante." in out


def test_render_doubts_no_flash_no_banner(monkeypatch):
    """rev-render m3 — sans flash, aucune bannière parasite n'est rendue."""
    _patch_groups(monkeypatch, [
        _reco("r1", status="draft",
              agent={"verdict": "unsure", "confidence": 0.4, "reason": "?"}),
    ])
    out = render_doubts("src")
    assert 'class="flash' not in out


def test_render_doubts_flash_kind_sanitized(monkeypatch):
    """rev-render m3 — un flash_kind hors liste blanche retombe sur `info`
    (délégué à _flash_banner) : pas d'injection de classe CSS arbitraire."""
    _patch_groups(monkeypatch, [])
    out = render_doubts("src", flash="msg", flash_kind="evil onmouseover=x")
    assert "flash-info" in out
    assert "flash-evil" not in out


def test_agent_block_renders_flags_note_and_human_correction(monkeypatch):
    """Couvre les branches flags / note / humanCorrection de `_agent_block`
    (le paramètre `section_key` mort a été retiré — rev-render m6)."""
    _patch_groups(monkeypatch, [
        _reco("r1", status="draft", agent={
            "verdict": "unsure", "confidence": 0.4,
            "reason": "titre douteux",
            "flags": ["titre suspect", "lien à vérifier"],
            "note": "note interne agent",
            "humanCorrection": "corrigé par Kyan",
        }),
    ])
    out = render_doubts("src", ep="g1")
    assert "titre suspect" in out
    assert "lien à vérifier" in out
    assert "note interne agent" in out
    assert "corrigé par Kyan" in out
