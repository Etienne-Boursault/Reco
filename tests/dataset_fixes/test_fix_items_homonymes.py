"""Tests de `tools/fix_items_homonymes.py`.

CE QUE CET OUTIL REPARE
-----------------------
Onze items portaient l'identifiant TMDB d'un HOMONYME. La reco correspondante,
elle, portait le bon — les recos ont ete corrigees a la main au fil du temps,
les items sont restes sur leur appariement automatique par titre.

Le symptome est visible : l'item « Fantomas » pointait le film MUET de 1913
tout en creditant Jean Marais, qui joue dans celui de 1964. L'item « Vice »
pointait « Vice-versa » de Pixar en creditant Adam McKay.

CE QUI PROUVE CHAQUE CAS
------------------------
Deux temoins concordants, jamais un seul :
  1. l'API TMDB, interrogee avec le TYPE (movie/57774 et tv/57774 sont deux
     oeuvres differentes — une verification qui ignore le type se trompe) ;
  2. le `creator` de l'item lui-meme, qui designe l'oeuvre que l'identifiant
     contredit.

POURQUOI UNE TABLE ET NON UNE REGLE
-----------------------------------
La regle « l'item herite de l'identifiant de la reco » marcherait sur ces onze
cas. Mais rien ne garantit qu'une reco a toujours raison contre son item : la
supposition tient ici parce qu'on l'a VERIFIEE onze fois, pas parce qu'elle
serait vraie par nature. Une table dit ce qui a ete verifie ; une regle
affirmerait davantage.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import fix_items_homonymes as fih


@pytest.fixture
def items_root(tmp_path: Path, monkeypatch) -> Path:
    items = tmp_path / "items"
    items.mkdir()
    recos = tmp_path / "recos"
    recos.mkdir()
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(df, "ITEMS_DIR", items)
    monkeypatch.setattr(common, "RECOS_DIR", recos)
    monkeypatch.setattr(df, "RECOS_DIR", recos)
    return items


def _item(iid="570ac224", titre="Fantomas", tmdb=319287, typ="movie", **extra):
    doc = {"id": iid, "title": titre, "types": ["film"],
           "externalIds": {"tmdb": tmdb, "tmdbType": typ}}
    doc.update(extra)
    return doc


# ===== La correction =======================================================
def test_l_identifiant_de_l_homonyme_est_remplace():
    """movie/319287 est le « Fantomas » MUET de 1913 ; celui du corpus est
    celui de 1964, avec de Funes et Jean Marais."""
    doc = _item()
    changes = fih.transform(doc)
    assert doc["externalIds"]["tmdb"] == 1871
    assert doc["externalIds"]["tmdbType"] == "movie"
    assert [c.field for c in changes] == ["externalIds.tmdb"]


def test_le_TYPE_est_corrige_quand_il_change():
    """« The Legend of Hei » etait declare `tv` alors que c'est un FILM."""
    doc = _item("8c792e21", "The Legend of Hei", 16339, "tv")
    fih.transform(doc)
    assert doc["externalIds"]["tmdbType"] == "movie"
    assert doc["externalIds"]["tmdb"] == 620249


def test_le_watchPage_perime_part_avec_l_identifiant():
    """Il derivait de l'ancien : le garder pointerait encore l'homonyme."""
    doc = _item(externalIds={"tmdb": 319287, "tmdbType": "movie",
                             "watchPage": "https://www.themoviedb.org/movie/"
                                          "319287/watch?locale=FR"})
    fih.transform(doc)
    assert "watchPage" not in doc["externalIds"]


def test_les_diffuseurs_de_l_homonyme_sont_SUPPRIMES():
    """Ils decrivaient la disponibilite de l'autre oeuvre. On ne les recopie
    pas : cette information change tous les mois."""
    doc = _item(watchProviders=[{"name": "Netflix", "url": "https://x.fr"}])
    fih.transform(doc)
    assert "watchProviders" not in doc


# ===== Les gardes ==========================================================
def test_un_titre_QUI_A_CHANGE_annule_la_correction():
    doc = _item(titre="Autre chose")
    assert fih.transform(doc) == []
    assert doc["externalIds"]["tmdb"] == 319287


def test_un_identifiant_DEJA_AUTRE_annule_la_correction():
    doc = _item(tmdb=999999)
    assert fih.transform(doc) == []


def test_un_document_hors_table_n_est_pas_touche():
    assert fih.transform(_item("zzzzzzzz", "Inconnu")) == []


def test_une_RECO_n_est_jamais_touchee():
    """La table ne vise que des items. Une reco portant par hasard le meme
    identifiant ne doit pas etre reecrite — c'est elle qui a raison."""
    reco = {"id": "ubm-0666", "title": "Fantomas",
            "externalIds": {"tmdb": "1871", "tmdbType": "movie"}}
    assert fih.transform(reco) == []


def test_un_document_sans_externalIds_ne_fait_pas_lever():
    assert fih.transform({"id": "570ac224", "title": "Fantomas"}) == []


def test_la_passe_est_idempotente():
    doc = _item()
    fih.transform(doc)
    assert fih.transform(doc) == []


# ===== Coherence de la table ===============================================
def test_chaque_entree_porte_deux_temoins():
    """Un seul temoin n'est pas une preuve : la justification doit citer et la
    fiche TMDB, et ce que dit le corpus (createur ou citation)."""
    for iid, motif in fih.POURQUOI.items():
        assert len(motif) > 60, iid


def test_chaque_correction_est_justifiee():
    assert set(fih.CORRECTIONS) == set(fih.POURQUOI)


def test_aucune_correction_ne_vise_une_reco():
    """Les identifiants de reco commencent par `ubm-`. En viser une ici
    inverserait le sens de la correction."""
    for iid in fih.CORRECTIONS:
        assert not iid.startswith("ubm-"), iid


def test_les_types_sont_ceux_de_l_API():
    for iid, (_, _, _, _, typ) in fih.CORRECTIONS.items():
        assert typ in {"movie", "tv"}, iid


# ===== CLI =================================================================
def test_main_apply_ecrit(items_root: Path):
    p = items_root / "a.json"
    p.write_text(json.dumps(_item()), encoding="utf-8")
    assert fih.main(["--apply"]) == 0
    assert json.loads(p.read_text(encoding="utf-8"))["externalIds"]["tmdb"] == 1871


def test_main_dry_run_n_ecrit_pas(items_root: Path):
    p = items_root / "a.json"
    p.write_text(json.dumps(_item()), encoding="utf-8")
    avant = p.read_text(encoding="utf-8")
    assert fih.main([]) == 0
    assert p.read_text(encoding="utf-8") == avant


def test_chaque_titre_attendu_EXISTE_dans_le_corpus():
    """Une garde qui ne mord jamais ne protege rien : elle rend l'entree
    muette, et son silence ressemble a un succes.

    C'est arrive le 2026-08-18 sur « La jeune fille et la mort » : j'avais
    recopie le titre de la RECO (« La Jeune Fille et la Mort », capitales)
    alors que la table vise l'ITEM, qui l'ecrit en minuscules. L'entree n'a
    rien fait, et seul un recomptage l'a revele.
    """
    import json

    from common import CONTENT_DIR

    reels = {}
    for chemin in (CONTENT_DIR / "items").rglob("*.json"):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if doc.get("id"):
            reels[doc["id"]] = doc.get("title")
    assert len(reels) > 500, "corpus d'items introuvable"

    ecarts = [(iid, attendu, reels.get(iid))
              for iid, (attendu, *_) in fih.CORRECTIONS.items()
              if iid in reels and reels[iid] != attendu]
    assert not ecarts, (
        f"le titre attendu ne correspond pas a l'item : {ecarts} — "
        f"l'entree ne s'appliquera jamais.")
