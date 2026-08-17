"""Tests de tools/fill_guest_creators.py.

Ce que ces tests défendent avant tout : le REFUS de deviner. Face à deux
invités, rien dans la donnée ne dit lequel a écrit l'œuvre — trancher au hasard
produirait une attribution fausse, c'est-à-dire exactement le défaut que
l'outil répare. Le cas ambigu est donc traité comme un résultat à part entière,
pas comme un échec silencieux.
"""
from __future__ import annotations

import json

import pytest

import fill_guest_creators as fgc


@pytest.fixture(autouse=True)
def _source_temporaire(tmp_path, monkeypatch):
    """Une source avec deux animateurs, dans un dossier JETABLE.

    Le chemin est substitué par la FONCTION `sources_dir`, jamais par une
    constante : une constante figée à l'import a déjà résisté au monkeypatch
    d'une suite de tests, qui a modifié 29 fichiers du vrai corpus.
    """
    dossier = tmp_path / "sources"
    dossier.mkdir()
    (dossier / "ubm.json").write_text(
        json.dumps({"id": "ubm", "hosts": ["Kyan Khojandi", "Navo"]}),
        encoding="utf-8")
    monkeypatch.setattr(fgc, "sources_dir", lambda: dossier)
    fgc._hosts_bruts.cache_clear()
    fgc.AMBIGUS.clear()
    yield
    fgc._hosts_bruts.cache_clear()


def _reco(**kw):
    d = {"id": "ubm-1", "title": "Une œuvre", "sourceId": "ubm",
         "guestWork": True, "status": "validated"}
    d.update(kw)
    return d


# ---------------------------------------------------------------------------
# Ce que l'outil déduit
# ---------------------------------------------------------------------------
def test_un_seul_invite_donne_le_createur():
    reco = _reco(recommendedBy="Natoo")
    changes = fgc.transform(reco)
    assert reco["creator"] == "Natoo"
    assert len(changes) == 1 and changes[0].field == "creator"
    assert changes[0].before is None


def test_les_animateurs_sont_retires_du_calcul():
    """« Kyan Khojandi & Clément Cotentin » → l'auteur est l'INVITÉ."""
    reco = _reco(recommendedBy="Kyan Khojandi & Clément Cotentin")
    fgc.transform(reco)
    assert reco["creator"] == "Clément Cotentin"


@pytest.mark.parametrize("brut", [
    "Kyan Khojandi & Jessé",
    "Kyan Khojandi, Jessé",
    "Kyan Khojandi et Jessé",
])
def test_les_trois_separateurs_du_corpus(brut):
    reco = _reco(recommendedBy=brut)
    fgc.transform(reco)
    assert reco["creator"] == "Jessé"


def test_animateurs_seuls_l_oeuvre_est_la_leur():
    """« Bref 2 », présenté par Kyan et Navo : c'est BIEN leur œuvre."""
    reco = _reco(recommendedBy="Kyan Khojandi & Navo")
    fgc.transform(reco)
    assert reco["creator"] == "Kyan Khojandi & Navo"


def test_animateur_seul():
    reco = _reco(recommendedBy="Kyan Khojandi")
    fgc.transform(reco)
    assert reco["creator"] == "Kyan Khojandi"


def test_l_animateur_est_reconnu_malgre_accents_et_casse():
    """Les noms sont saisis à la main : « KYAN KHOJANDI » reste un animateur."""
    reco = _reco(recommendedBy="KYAN  KHOJANDI & Rosa Bursztein")
    fgc.transform(reco)
    assert reco["creator"] == "Rosa Bursztein"


# ---------------------------------------------------------------------------
# Ce que l'outil REFUSE de deviner
# ---------------------------------------------------------------------------
def test_deux_invites_ne_sont_JAMAIS_tranches():
    """Le cœur de l'outil. Rien ne dit lequel des deux a écrit l'œuvre."""
    reco = _reco(recommendedBy="Bun Hay Mean & Alexandre Kominek")
    assert fgc.transform(reco) == []
    assert "creator" not in reco


def test_un_cas_ambigu_est_SIGNALE_et_non_avale():
    """Un refus muet serait indistinguable d'un « rien à faire »."""
    reco = _reco(id="ubm-9", recommendedBy="Tom Baldetti & Yassir")
    fgc.transform(reco)
    assert len(fgc.AMBIGUS) == 1
    assert fgc.AMBIGUS[0]["id"] == "ubm-9"
    assert fgc.AMBIGUS[0]["invites"] == ["Tom Baldetti", "Yassir"]


def test_un_cas_deductible_n_est_PAS_signale():
    fgc.transform(_reco(recommendedBy="Natoo"))
    assert fgc.AMBIGUS == []


# ---------------------------------------------------------------------------
# Ce que l'outil ne touche pas
# ---------------------------------------------------------------------------
def test_un_createur_deja_renseigne_est_intact():
    """L'outil COMBLE, il ne corrige pas : réécrire écraserait une donnée
    vérifiée à la main par une déduction."""
    reco = _reco(creator="Quelqu'un d'autre", recommendedBy="Natoo")
    assert fgc.transform(reco) == []
    assert reco["creator"] == "Quelqu'un d'autre"


def test_une_reco_sans_guestWork_est_ignoree():
    """Sans `guestWork`, `recommendedBy` désigne qui RECOMMANDE — pas l'auteur.
    Les confondre attribuerait chaque film à qui en a parlé."""
    reco = _reco(guestWork=False, recommendedBy="Natoo")
    assert fgc.transform(reco) == []
    assert "creator" not in reco


@pytest.mark.parametrize("rb", [None, "", "   ", 42])
def test_recommendedBy_inexploitable(rb):
    reco = _reco(recommendedBy=rb)
    assert fgc.transform(reco) == []
    assert "creator" not in reco


def test_un_createur_vide_est_traite_comme_absent():
    reco = _reco(creator="   ", recommendedBy="Natoo")
    fgc.transform(reco)
    assert reco["creator"] == "Natoo"


# ---------------------------------------------------------------------------
# Sources introuvables ou malformées
# ---------------------------------------------------------------------------
def test_source_inconnue_rend_l_outil_PLUS_prudent():
    """Sans animateurs connus, tout le monde passe pour un invité : deux noms
    deviennent donc un cas ambigu, écarté — jamais une attribution au hasard."""
    reco = _reco(sourceId="jamais-vue", recommendedBy="Kyan Khojandi & Natoo")
    assert fgc.transform(reco) == []
    assert "creator" not in reco


def test_source_inconnue_un_seul_nom_reste_deductible():
    reco = _reco(sourceId="jamais-vue", recommendedBy="Natoo")
    fgc.transform(reco)
    assert reco["creator"] == "Natoo"


def test_source_illisible_ne_leve_pas(tmp_path, monkeypatch):
    dossier = tmp_path / "cassees"
    dossier.mkdir()
    (dossier / "ubm.json").write_text("{ ceci n'est pas du JSON", encoding="utf-8")
    monkeypatch.setattr(fgc, "sources_dir", lambda: dossier)
    fgc._hosts_bruts.cache_clear()
    reco = _reco(recommendedBy="Natoo")
    fgc.transform(reco)
    assert reco["creator"] == "Natoo"


def test_sourceId_en_reference_objet():
    """Le schéma porte tantôt `"ubm"`, tantôt `{"id": "ubm"}`."""
    reco = _reco(sourceId={"id": "ubm"}, recommendedBy="Kyan Khojandi & Natoo")
    fgc.transform(reco)
    assert reco["creator"] == "Natoo"


def test_sourceId_absent():
    reco = _reco(sourceId=None, recommendedBy="Natoo")
    fgc.transform(reco)
    assert reco["creator"] == "Natoo"


# ---------------------------------------------------------------------------
# Fonctions exposées
# ---------------------------------------------------------------------------
def test_personnes_decoupe_et_nettoie():
    assert fgc.personnes("A & B,  C et D") == ["A", "B", "C", "D"]
    assert fgc.personnes(None) == []


def test_fold_replie_accents_casse_et_espaces():
    assert fgc.fold("  Éléonore   COSTES ") == "eleonore costes"
    assert fgc.fold(None) == ""


def test_hosts_de_source_absente():
    assert fgc.hosts_de("aucune-source") == set()


def test_createur_deduit_est_pur():
    """Il RENVOIE le créateur sans muter la reco : c'est ce qui permet de
    l'appeler dans un rapport sans effet de bord."""
    reco = _reco(recommendedBy="Natoo")
    assert fgc.createur_deduit(reco) == "Natoo"
    assert "creator" not in reco


def test_build_parser_expose_les_options_communes():
    args = fgc.build_parser().parse_args([])
    assert args.apply is False          # dry-run par défaut
    assert args.source is None


def test_sources_dir_pointe_dans_le_corpus(monkeypatch):
    """La fonction NON substituée doit viser `src/content/sources`.

    Les autres tests la remplacent par un dossier jetable ; sans ce test, le
    vrai chemin ne serait jamais évalué — et une faute de frappe y passerait
    inaperçue jusqu'à l'exécution réelle.
    """
    monkeypatch.undo()
    chemin = fgc.sources_dir()
    assert chemin.name == "sources"
    assert chemin.parent.name == "content"


def test_createur_deduit_refuse_sans_guestWork():
    assert fgc.createur_deduit(_reco(guestWork=False, recommendedBy="Natoo")) is None


def test_createur_deduit_refuse_un_createur_deja_la():
    assert fgc.createur_deduit(_reco(creator="Déjà", recommendedBy="Natoo")) is None


def test_createur_deduit_refuse_un_recommendedBy_vide():
    assert fgc.createur_deduit(_reco(recommendedBy="  ")) is None


def test_createur_deduit_refuse_deux_invites():
    assert fgc.createur_deduit(_reco(recommendedBy="Alice & Bob")) is None


def test_createur_deduit_rend_les_animateurs_seuls():
    assert fgc.createur_deduit(_reco(recommendedBy="Kyan Khojandi & Navo")) == "Kyan Khojandi & Navo"
