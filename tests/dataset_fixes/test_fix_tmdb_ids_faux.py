"""Tests de `tools/fix_tmdb_ids_faux.py`.

CE QUE CET OUTIL REPARE
-----------------------
Quatre oeuvres du corpus portaient un identifiant TMDB designant une AUTRE
oeuvre. Ce n'est pas une imprecision de metadonnee : l'identifiant alimente le
lien « fiche », la page « où regarder » et la liste des diffuseurs. La page
« Drive » annoncait donc 19 diffuseurs, tous herites de « Mulholland Drive »,
et son `watchPage` disait litteralement `1018-mulholland-drive`.

Decouvertes le 2026-08-18 en preparant la fusion des items en double : c'est
la GARDE de `fusion_items_doublons` qui a refuse de fusionner « Drive » avec
« Mulholland Drive », revelant que les deux partageaient un identifiant.

POURQUOI DEUX SONT CORRIGES ET DEUX RETIRES
-------------------------------------------
Corriger suppose de connaitre le bon identifiant. Pour « Drive » et « Iris »,
il est etabli. Pour « Mortal » et « Bagarre », non — et inventer un
remplacement plausible serait pire que l'absence. On retire donc l'identifiant
faux sans en poser d'autre.

CE QUI N'EST PAS FIGE DANS LA TABLE
-----------------------------------
`watchProviders` est SUPPRIME, jamais recopie. La disponibilite d'une oeuvre
change tous les mois : un instantane code en dur pourrirait sur place. Le
`watchPage`, lui, se deduit de l'identifiant — il est donc reconstruit.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import fix_tmdb_ids_faux as ftf


@pytest.fixture
def racines(tmp_path: Path, monkeypatch):
    recos = tmp_path / "recos"
    items = tmp_path / "items"
    recos.mkdir()
    items.mkdir()
    monkeypatch.setattr(common, "RECOS_DIR", recos)
    monkeypatch.setattr(df, "RECOS_DIR", recos)
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(df, "ITEMS_DIR", items)
    return recos, items


def _drive(**extra):
    doc = {
        "id": "44695732", "title": "Drive",
        "externalIds": {"tmdb": 1018, "tmdbType": "movie",
                        "watchPage": "https://www.themoviedb.org/movie/"
                                     "1018-mulholland-drive/watch?locale=FR"},
        "watchProviders": [{"name": "Netflix", "url": "https://x.fr"}],
    }
    doc.update(extra)
    return doc


# ===== Correction ==========================================================
def test_drive_recoit_son_VRAI_identifiant():
    doc = _drive()
    ftf.transform(doc)
    assert doc["externalIds"]["tmdb"] == 64690


def test_le_watchPage_est_RECONSTRUIT_depuis_le_bon_identifiant():
    """Il disait `1018-mulholland-drive` sur la page « Drive »."""
    doc = _drive()
    ftf.transform(doc)
    assert doc["externalIds"]["watchPage"] == (
        "https://www.themoviedb.org/movie/64690/watch?locale=FR")


def test_les_diffuseurs_perimes_sont_SUPPRIMES_et_non_recopies():
    """Ils decrivaient la disponibilite de Mulholland Drive. Les recopier
    depuis une table figerait une information qui change tous les mois."""
    doc = _drive()
    ftf.transform(doc)
    assert "watchProviders" not in doc


def test_iris_passe_de_la_serie_coreenne_a_la_francaise():
    doc = {"id": "63c35f4b", "title": "Iris",
           "externalIds": {"tmdb": 31505, "tmdbType": "tv"}}
    ftf.transform(doc)
    assert doc["externalIds"]["tmdb"] == 271593


# ===== Retrait =============================================================
def test_un_identifiant_faux_SANS_remplacant_connu_est_retire():
    """« Mortal » portait `tv/90591` = « Pecado Mortal », telenovela
    bresilienne. Aucun remplacant n'est etabli : mieux vaut rien qu'un
    identifiant invente."""
    doc = {"id": "4856e2ad", "title": "Mortal",
           "externalIds": {"tmdb": 90591, "tmdbType": "tv"}}
    ftf.transform(doc)
    # `externalIds` disparait s'il devient vide (cf. le test suivant) : on
    # interroge donc sans supposer qu'il existe encore.
    assert "tmdb" not in (doc.get("externalIds") or {})
    assert "tmdbType" not in (doc.get("externalIds") or {})


def test_un_externalIds_devenu_vide_disparait():
    """Laisser `externalIds: {}` encombre le corpus sans rien porter."""
    doc = {"id": "4856e2ad", "title": "Mortal",
           "externalIds": {"tmdb": 90591, "tmdbType": "tv"}}
    ftf.transform(doc)
    assert "externalIds" not in doc


def test_les_autres_identifiants_survivent_au_retrait():
    doc = {"id": "4856e2ad", "title": "Mortal",
           "externalIds": {"tmdb": 90591, "tmdbType": "tv",
                           "instagram": "quelquun"}}
    ftf.transform(doc)
    assert doc["externalIds"] == {"instagram": "quelquun"}


# ===== Les gardes ==========================================================
def test_un_titre_QUI_A_CHANGE_annule_la_correction():
    doc = _drive(title="Autre chose")
    assert ftf.transform(doc) == []
    assert doc["externalIds"]["tmdb"] == 1018


def test_un_identifiant_DEJA_AUTRE_annule_la_correction():
    """Si quelqu'un est passe avant nous, on ne recrit pas par-dessus."""
    doc = _drive()
    doc["externalIds"]["tmdb"] = 99999
    assert ftf.transform(doc) == []
    assert doc["externalIds"]["tmdb"] == 99999


def test_un_document_hors_table_n_est_pas_touche():
    doc = {"id": "zzz", "title": "X", "externalIds": {"tmdb": 1018}}
    assert ftf.transform(doc) == []


def test_un_document_sans_externalIds_ne_fait_pas_lever():
    assert ftf.transform({"id": "44695732", "title": "Drive"}) == []


def test_la_passe_est_idempotente():
    doc = _drive()
    ftf.transform(doc)
    assert ftf.transform(doc) == []
    assert doc["externalIds"]["tmdb"] == 64690


# ===== Coherence de la table ===============================================
def test_mulholland_drive_n_est_PAS_dans_la_table():
    """C'est LUI qui porte legitimement movie/1018. Le corriger inverserait
    l'erreur."""
    assert "c9f6b3f4" not in ftf.CORRECTIONS
    assert "ubm-0968" not in ftf.CORRECTIONS


def test_bref_2_n_est_PAS_dans_la_table():
    """Verification faite : TMDB liste « bref. 2 » (2025) comme la SAISON 2
    de tv/60715. L'identifiant partage est donc correct — l'annoncer comme
    faux etait une erreur d'analyse."""
    for _, (_, ancien, _, _) in ftf.CORRECTIONS.items():
        assert ancien != 60715


def test_chaque_entree_porte_sa_justification():
    for cle, motif in ftf.POURQUOI.items():
        assert len(motif) > 40, cle


def test_chaque_correction_est_justifiee():
    assert set(ftf.CORRECTIONS) <= set(ftf.POURQUOI)


# ===== CLI =================================================================
def test_main_corrige_les_recos_ET_les_items(racines):
    recos, items = racines
    (recos / "a.json").write_text(json.dumps(
        {"id": "ubm-0187", "title": "Iris",
         "externalIds": {"tmdb": 31505, "tmdbType": "tv"}}), encoding="utf-8")
    (items / "b.json").write_text(json.dumps(_drive()), encoding="utf-8")
    assert ftf.main(["--apply"]) == 0
    assert json.loads((recos / "a.json").read_text(
        encoding="utf-8"))["externalIds"]["tmdb"] == 271593
    assert json.loads((items / "b.json").read_text(
        encoding="utf-8"))["externalIds"]["tmdb"] == 64690


def test_main_dry_run_n_ecrit_pas(racines):
    recos, items = racines
    (items / "b.json").write_text(json.dumps(_drive()), encoding="utf-8")
    avant = (items / "b.json").read_text(encoding="utf-8")
    assert ftf.main([]) == 0
    assert (items / "b.json").read_text(encoding="utf-8") == avant


def test_retirer_l_identifiant_emporte_le_watchPage_qui_en_derivait():
    """« Bagarre » portait un `watchPage` disant `49064-picture-snatcher` —
    un film de 1933 sans rapport avec le spectacle recommande. L'adresse se
    DEDUIT de l'identifiant : elle ne peut pas lui survivre."""
    doc = {"id": "44d74324", "title": "Bagarre",
           "externalIds": {"tmdb": 49064, "tmdbType": "movie",
                           "watchPage": "https://www.themoviedb.org/movie/"
                                        "49064-picture-snatcher/watch?locale=FR"},
           "watchProviders": [{"name": "X", "url": "https://x.fr"}]}
    ftf.transform(doc)
    assert "externalIds" not in doc
    assert "watchProviders" not in doc


# ===== Asymetrie des deux schemas ==========================================
def test_une_reco_garde_son_identifiant_en_CHAINE():
    """`content.config.ts` declare `tmdb: z.string()` cote RECO (ligne 203) et
    `z.number().int()` cote ITEM (ligne 322). Ecrire un entier dans une reco
    arrete le build — c'est arrive le 2026-08-18 sur ubm-0187.

    On preserve donc le TYPE d'origine plutot que d'en imposer un."""
    doc = {"id": "ubm-0187", "title": "Iris",
           "externalIds": {"tmdb": "31505", "tmdbType": "tv"}}
    ftf.transform(doc)
    assert doc["externalIds"]["tmdb"] == "271593"
    assert isinstance(doc["externalIds"]["tmdb"], str)


def test_un_item_garde_son_identifiant_en_NOMBRE():
    doc = {"id": "63c35f4b", "title": "Iris",
           "externalIds": {"tmdb": 31505, "tmdbType": "tv"}}
    ftf.transform(doc)
    assert doc["externalIds"]["tmdb"] == 271593
    assert isinstance(doc["externalIds"]["tmdb"], int)
