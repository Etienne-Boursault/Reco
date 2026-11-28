"""Tests de `tools/bord_systeme.py` : coûts, modèles et image du tableau de bord (tranche 3b).

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026 (relecture du plan R20 :
« inconnu » au lieu de 0 $). La base de test a le vrai schéma de la télémétrie (`MIGRATIONS`),
dans un dossier temporaire ; aucun réseau. Un champ illisible se dit « inconnu » (`None`), les
autres restent lus.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

import bord_systeme
from telemetry.schema import MIGRATIONS

SOURCE = "un-bon-moment"
MAINTENANT = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)


@pytest.fixture
def monde(tmp_path, monkeypatch):
    """Base de télémétrie, compose.yml et variables d'environnement temporaires."""
    import common
    monkeypatch.setattr(common, "TOOLS_DIR", tmp_path / "tools")
    monkeypatch.setenv("RECO_METRICS_DB", str(tmp_path / "base.sqlite"))
    monkeypatch.delenv("RECO_MODELE_EXTRACTION", raising=False)
    monkeypatch.delenv("RECO_MODELE_SECOURS", raising=False)
    return tmp_path


def _base(tmp, tentatives=(), appels=()):
    conn = sqlite3.connect(tmp / "base.sqlite")
    for script in MIGRATIONS:
        conn.executescript(script)
    for i, (source, etape, statut, modele, fin) in enumerate(tentatives):
        conn.execute(
            "INSERT INTO stage_attempts (id, workflow_run_id, source_id, stage, intent, status,"
            " started_at, ended_at, model) VALUES (?, 'r', ?, ?, 'nominal', ?, 't', ?, ?)",
            [f"a{i}", source, etape, statut, fin, modele])
    for i, (tentative, modele, cout, devise, il_y_a) in enumerate(appels):
        conn.execute(
            "INSERT INTO llm_calls (id, stage_attempt_id, provider, model, transport, status,"
            " usage_source, cost_decimal, cost_currency, recorded_at)"
            " VALUES (?, ?, 'anthropic', ?, 'sync', 'succeeded', 'provider', ?, ?, ?)",
            [f"c{i}", tentative, modele, cout, devise,
             (MAINTENANT - il_y_a).isoformat(timespec="milliseconds")])
    conn.commit()
    conn.close()


def _compose(tmp, texte):
    chemin = tmp / "deploy" / "venus" / "compose.yml"
    chemin.parent.mkdir(parents=True)
    chemin.write_text(texte, encoding="utf-8")


def _lire(**options):
    return bord_systeme.lire(SOURCE, maintenant=MAINTENANT, **options)


JOUR = timedelta(days=1)


# --- coûts -----------------------------------------------------------------------------------

def test_les_couts_se_separent_en_semaine_en_cours_et_semaine_precedente(monde):
    _base(monde, [(SOURCE, "extract", "succeeded", "m", "t")], [
        ("a0", "m", "1.5", "USD", 2 * JOUR), ("a0", "m", "0.25", "USD", 6 * JOUR),
        ("a0", "m", "4", "USD", 8 * JOUR), ("a0", "m", "9", "USD", 15 * JOUR)])
    couts = _lire()["couts"]
    assert couts["semaine"]["cout"]["known"] == {"USD": "1.750000"}
    assert couts["semaine"]["appels"] == 2
    assert couts["precedente"]["cout"]["known"] == {"USD": "4.000000"}
    assert couts["precedente"]["appels"] == 1


def test_une_semaine_sans_appel_est_mesuree_a_zero_appel_sans_cout_invente(monde):
    _base(monde, [(SOURCE, "extract", "succeeded", "m", "t")], [])
    semaine = _lire()["couts"]["semaine"]
    assert semaine["appels"] == 0
    assert semaine["cout"]["known"] is None and semaine["cout"]["unknownCostCalls"] == 0


def test_des_appels_sans_cout_ne_font_jamais_zero_dollar(monde):
    _base(monde, [(SOURCE, "extract", "succeeded", "m", "t")], [
        ("a0", "m", None, None, JOUR), ("a0", "m", "1", "USD", JOUR)])
    cout = _lire()["couts"]["semaine"]["cout"]
    assert cout["known"] == {"USD": "1.000000"}
    assert cout["unknownCostCalls"] == 1
    assert cout["pricingCoverage"] == 0.5


def test_un_cout_sans_devise_compte_comme_inconnu(monde):
    _base(monde, [(SOURCE, "extract", "succeeded", "m", "t")], [("a0", "m", "3", None, JOUR)])
    cout = _lire()["couts"]["semaine"]["cout"]
    assert cout["known"] is None and cout["unknownCostCalls"] == 1


def test_les_couts_se_rangent_par_modele(monde):
    _base(monde, [(SOURCE, "extract", "succeeded", "m", "t")], [
        ("a0", "opus", "2", "USD", JOUR), ("a0", "opus", "1", "USD", JOUR),
        ("a0", "haiku", None, None, JOUR)])
    modeles = _lire()["couts"]["semaine"]["par_modele"]
    assert modeles["opus"]["known"] == {"USD": "3.000000"}
    assert modeles["haiku"]["known"] is None and modeles["haiku"]["unknownCostCalls"] == 1


def test_les_couts_d_une_autre_source_ne_comptent_pas(monde):
    _base(monde, [("autre", "extract", "succeeded", "m", "t")], [("a0", "m", "5", "USD", JOUR)])
    assert _lire()["couts"]["semaine"]["appels"] == 0


def test_sans_base_les_couts_sont_inconnus_et_le_reste_se_lit(monde):
    _compose(monde, "  image: reco-atelier:1\n")
    etat = _lire()
    assert etat["couts"] == {"semaine": None, "precedente": None}
    assert etat["image"] == "reco-atelier:1"
    assert etat["modeles"]["extraction"]["source"] == "env"


def test_une_base_illisible_rend_les_couts_inconnus_sans_lever(monde):
    (monde / "base.sqlite").write_bytes(b"pas une base sqlite" * 100)
    etat = _lire()
    assert etat["couts"] == {"semaine": None, "precedente": None}
    assert etat["modeles"]["extraction"]["source"] == "env"


def test_une_base_sans_les_tables_rend_les_couts_inconnus(monde):
    sqlite3.connect(monde / "base.sqlite").close()
    assert _lire()["couts"] == {"semaine": None, "precedente": None}


def test_un_cout_mal_forme_rend_les_couts_inconnus_et_laisse_les_modeles(monde):
    _base(monde, [(SOURCE, "extract", "succeeded", "claude-x", "2026-11-27T10:00:00+00:00")],
          [("a0", "m", "pas un nombre", "USD", JOUR)])
    etat = _lire()
    assert etat["couts"] == {"semaine": None, "precedente": None}
    assert etat["modeles"]["extraction"]["nom"] == "claude-x"


def test_sans_horloge_donnee_les_couts_suivent_l_heure_courante(monde):
    _base(monde, [(SOURCE, "extract", "succeeded", "m", "t")], [])
    assert bord_systeme.lire(SOURCE)["couts"]["semaine"]["appels"] == 0


# --- modèles ---------------------------------------------------------------------------------

def test_le_modele_d_extraction_est_celui_de_la_derniere_extraction_reussie(monde):
    _base(monde, [
        (SOURCE, "extract", "succeeded", "ancien", "2026-11-20T10:00:00+00:00"),
        (SOURCE, "extract", "succeeded", "recent", "2026-11-27T10:00:00+00:00"),
        (SOURCE, "extract", "failed", "echec", "2026-11-28T10:00:00+00:00"),
        (SOURCE, "transcribe", "succeeded", "whisper", "2026-11-28T11:00:00+00:00"),
        ("autre", "extract", "succeeded", "ailleurs", "2026-11-28T11:00:00+00:00")])
    extraction = _lire()["modeles"]["extraction"]
    assert extraction == {"nom": "recent", "source": "mesure",
                          "date": "2026-11-27T10:00:00+00:00"}


def test_sans_extraction_mesuree_le_modele_vient_de_l_environnement(monde, monkeypatch):
    monkeypatch.setenv("RECO_MODELE_EXTRACTION", "claude-test-1")
    _base(monde, [(SOURCE, "extract", "succeeded", None, "2026-11-27T10:00:00+00:00"),
                  (SOURCE, "extract", "succeeded", "", "2026-11-27T11:00:00+00:00")])
    assert _lire()["modeles"]["extraction"] == {"nom": "claude-test-1", "source": "env",
                                                "date": None}


def test_le_modele_de_secours_vient_de_l_environnement(monde, monkeypatch):
    monkeypatch.setenv("RECO_MODELE_SECOURS", "claude-secours-2")
    assert _lire()["modeles"]["secours"] == {"nom": "claude-secours-2", "source": "env"}


def test_un_secours_coupe_se_dit_aucun_nom_et_non_inconnu(monde, monkeypatch):
    monkeypatch.setenv("RECO_MODELE_SECOURS", "aucun")
    assert _lire()["modeles"]["secours"] == {"nom": None, "source": "env"}


# --- image -----------------------------------------------------------------------------------

def test_l_image_est_lue_dans_compose_yml(monde):
    _compose(monde, "x-atelier: &atelier\n  # image: ancienne\n"
                    "  image: reco-atelier:2026-11-14-pillow13  # repli\n  build:\n")
    assert _lire()["image"] == "reco-atelier:2026-11-14-pillow13"


def test_sans_compose_yml_l_image_est_inconnue(monde):
    assert _lire()["image"] is None


def test_un_compose_yml_sans_ligne_image_donne_une_image_inconnue(monde):
    _compose(monde, "services:\n  review:\n    build: .\n")
    assert _lire()["image"] is None


def test_un_compose_yml_illisible_donne_une_image_inconnue(monde):
    chemin = monde / "deploy" / "venus" / "compose.yml"
    chemin.parent.mkdir(parents=True)
    chemin.write_bytes(b"\xff\xfe\x00 image: x")
    assert _lire()["image"] is None


def test_les_chemins_se_resolvent_a_l_appel_et_non_a_l_import(monde):
    """Le compose.yml suit `common.TOOLS_DIR` du moment, jamais le dépôt réel."""
    _compose(monde, "  image: reco-atelier:temoin\n")
    assert _lire()["image"] == "reco-atelier:temoin"
