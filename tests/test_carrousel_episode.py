"""Tests pour `tools/carrousel_episode.py` — remplissage des gabarits, sans rendu."""
from __future__ import annotations

import pytest

import carrousel_episode as ce

EP = {"numero": "S6 · E06", "titre": "Un titre", "invites": ["A", "B"], "lien": "https://unebonnere.co/x/",
      "recos": [{"type": "Film", "titre": "Court", "createur": "X", "citation": "« <b> »", "qui": "Navo",
                 "moment": "1:10"},
                {"type": "Série", "titre": "Un titre vraiment beaucoup trop long", "createur": "",
                 "citation": "c", "qui": "Kyan Khojandi", "moment": "2:00"}]}


def test_remplir_echappe_et_deroule_les_listes():
    corps = '<sc-for list="{{gens}}" as="g"><i>{{g.nom}}</i></sc-for>{{x}}'
    assert ce.remplir(corps, {"gens": [{"nom": "A&B"}], "x": "<y>"}) == "<i>A&amp;B</i>&lt;y&gt;"


def test_remplir_refuse_un_gabarit_incomplet():
    with pytest.raises(SystemExit):
        ce.remplir("{{x}} {{y.z}}", {"x": 1})


def test_taille_titre_reduit_les_titres_longs():
    assert ce.taille_titre("Court") == 190
    assert ce.taille_titre("Un titre de vingt-deux") == 160
    assert ce.taille_titre("Un titre vraiment beaucoup trop long") == 130


def test_pages_couverture_recos_fin(tmp_path):
    pages = ce.pages(EP, tmp_path)
    assert [p.name for p in pages] == ["01-couverture.html", "02-reco.html", "03-reco.html", "04-fin.html"]
    reco = pages[1].read_text(encoding="utf-8")
    assert "&lt;b&gt;" in reco and "Navo" in reco and "{{" not in reco
    assert "font-size: 130px" in pages[2].read_text(encoding="utf-8")


def test_textes_groupent_par_type_et_suivent_les_images(tmp_path):
    t = ce.textes(EP)
    assert t["instagram"].startswith("Les 2 recos d’Un Bon Moment S6·E06, avec A et B 🎙️\n\n🎬 Court\n📺 Un titre")
    assert "lien en bio" in t["instagram"] and "https://unebonnere.co/x/" in t["threads"]
    assert t["instagram"].endswith("Site de fan, non officiel.")
    assert len(t["alts"]) == len(ce.pages(EP, tmp_path)) == 4
    assert t["alts"][1] == "Reco 1 sur 2. Film : Court — X. « « <b> » » Reco de Navo, à 1:10."
    assert t["alts"][2].startswith("Reco 2 sur 2. Série : Un titre vraiment beaucoup trop long. «")
