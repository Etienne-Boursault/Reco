"""Tests de la saisie de la date de sortie annoncée (R4 B, 27/11/2026, tranche B).

Plan : `_shared/docs/reco-v1/plans/pr-sorties-annoncees.md`, § 2. Le suivi par git est éprouvé
avec le vrai git, sur un dépôt temporaire ; l'horloge est toujours injectée.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

import review_edit_sortie
from review_edit import apply_edit, render_edit_form
from review_edit_sortie import (
    appliquer_sortie,
    champ_sortie,
    fichier_suivi_par_git,
)

MAINTENANT = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def _git(dossier: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=dossier, check=True, capture_output=True)


def _ecrire(chemin: Path, **champs) -> Path:
    reco = {"id": "r1", "episodeGuid": "ep-1", "title": "Old", "types": ["album"],
            "sourceId": "src", "status": "draft"}
    reco.update(champs)
    chemin.write_text(json.dumps(reco), encoding="utf-8")
    return chemin


def _lire(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


@pytest.fixture
def reco_libre(tmp_path):
    """Une reco dans un dépôt git où elle n'est pas encore suivie."""
    _git(tmp_path, "init", "-q")
    return _ecrire(tmp_path / "r1.json")


@pytest.fixture
def reco_suivie(reco_libre):
    _git(reco_libre.parent, "add", "r1.json")
    return reco_libre


# ---- fichier_suivi_par_git -------------------------------------------------
def test_fichier_non_suivi(reco_libre):
    assert fichier_suivi_par_git(reco_libre) is False


def test_fichier_suivi(reco_suivie):
    assert fichier_suivi_par_git(reco_suivie) is True


def test_hors_depot_git_compte_comme_non_suivi(tmp_path, monkeypatch):
    # Hors de tout dépôt (git rend 128), rien n'est publié par git : le champ reste ouvert.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    assert fichier_suivi_par_git(_ecrire(tmp_path / "r1.json")) is False


def test_git_introuvable_compte_comme_suivi(reco_libre, monkeypatch):
    # Prudence : si l'on ne sait pas, on ne propose pas d'écrire.
    def _absent(*_a, **_k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(review_edit_sortie.subprocess, "run", _absent)
    assert fichier_suivi_par_git(reco_libre) is True


# ---- appliquer_sortie ------------------------------------------------------
def test_pose_la_date_et_l_annee(reco_libre):
    reco = _lire(reco_libre)
    msg = appliquer_sortie(reco, {"releaseDate": ["2026-12-04"]}, reco_libre, MAINTENANT)
    assert msg is None
    assert reco["releaseDate"] == "2026-12-04"
    assert reco["year"] == 2026


def test_ne_touche_pas_a_year_existant(reco_libre):
    reco = _lire(reco_libre)
    reco["year"] = 2025
    appliquer_sortie(reco, {"releaseDate": ["2026-12-04"]}, reco_libre, MAINTENANT)
    assert reco["year"] == 2025


def test_champ_absent_ne_change_rien(reco_libre):
    reco = _lire(reco_libre)
    assert appliquer_sortie(reco, {}, reco_libre, MAINTENANT) is None
    assert "releaseDate" not in reco


def test_champ_vide_retire_la_date(reco_libre):
    reco = _lire(reco_libre)
    reco["releaseDate"] = "2026-12-04"
    assert appliquer_sortie(reco, {"releaseDate": ["  "]}, reco_libre, MAINTENANT) is None
    assert "releaseDate" not in reco


def test_champ_vide_sans_date_ne_fait_rien(reco_libre):
    reco = _lire(reco_libre)
    assert appliquer_sortie(reco, {"releaseDate": [""]}, reco_libre, MAINTENANT) is None


@pytest.mark.parametrize("valeur, attendu", [
    ("2026-02-30", "date ignorée : 2026-02-30 n'existe pas dans le calendrier"),
    ("demain", "date ignorée : format attendu : AAAA-MM-JJ"),
    ("2030-01-01", "date ignorée : 2030-01-01 est à plus de 3 ans"),
])
def test_date_invalide_est_ignoree_avec_un_message(reco_libre, valeur, attendu):
    reco = _lire(reco_libre)
    assert appliquer_sortie(reco, {"releaseDate": [valeur]}, reco_libre, MAINTENANT) == attendu
    assert "releaseDate" not in reco
    assert "year" not in reco


def test_date_invalide_garde_l_ancienne_date(reco_libre):
    reco = _lire(reco_libre)
    reco["releaseDate"] = "2026-12-04"
    appliquer_sortie(reco, {"releaseDate": ["nawak"]}, reco_libre, MAINTENANT)
    assert reco["releaseDate"] == "2026-12-04"


def test_type_hors_v1_refuse(reco_libre):
    reco = _lire(reco_libre)
    reco["types"] = ["film"]
    msg = appliquer_sortie(reco, {"releaseDate": ["2026-12-04"]}, reco_libre, MAINTENANT)
    assert msg.startswith("date ignorée : ")
    assert "album" in msg and "film" not in msg
    assert "releaseDate" not in reco


def test_fichier_suivi_refuse_la_date(reco_suivie):
    reco = _lire(reco_suivie)
    msg = appliquer_sortie(reco, {"releaseDate": ["2026-12-04"]}, reco_suivie, MAINTENANT)
    assert msg == "date ignorée : après publication, passer par une PR de contenu"
    assert "releaseDate" not in reco


def test_l_horloge_injectee_fixe_l_horizon(reco_libre):
    reco = _lire(reco_libre)
    tard = datetime(2029, 1, 1, tzinfo=timezone.utc)
    assert appliquer_sortie(reco, {"releaseDate": ["2030-01-01"]}, reco_libre, tard) is None
    assert reco["releaseDate"] == "2030-01-01"


# ---- apply_edit ------------------------------------------------------------
def test_apply_edit_enregistre_le_reste_malgre_une_date_invalide(reco_libre):
    avis: list[str] = []
    ok, guid = apply_edit(reco_libre, {"title": ["Neuf"], "types": ["album"],
                                       "releaseDate": ["2026-02-30"]},
                          maintenant=MAINTENANT, avertissements=avis)
    assert (ok, guid) == (True, "ep-1")
    assert avis == ["date ignorée : 2026-02-30 n'existe pas dans le calendrier"]
    reco = _lire(reco_libre)
    assert reco["title"] == "Neuf"
    assert "releaseDate" not in reco


def test_apply_edit_pose_la_date(reco_libre):
    avis: list[str] = []
    apply_edit(reco_libre, {"title": ["Neuf"], "types": ["album"],
                            "releaseDate": ["2026-12-04"]},
               maintenant=MAINTENANT, avertissements=avis)
    assert avis == []
    assert _lire(reco_libre)["releaseDate"] == "2026-12-04"


def test_apply_edit_juge_le_type_apres_l_edition(reco_libre):
    # Le type vient d'être changé vers un type servi : la date passe.
    reco = _lire(reco_libre)
    reco["types"] = ["film"]
    reco_libre.write_text(json.dumps(reco), encoding="utf-8")
    avis: list[str] = []
    apply_edit(reco_libre, {"title": ["X"], "types": ["livre"],
                            "releaseDate": ["2026-12-04"]},
               maintenant=MAINTENANT, avertissements=avis)
    assert avis == []
    assert _lire(reco_libre)["releaseDate"] == "2026-12-04"


def test_apply_edit_sans_champ_ni_liste_d_avis(reco_libre):
    ok, _ = apply_edit(reco_libre, {"title": ["X"], "types": ["album"]})
    assert ok is True
    assert "releaseDate" not in _lire(reco_libre)


def test_apply_edit_sans_horloge_ni_liste_utilise_le_jour_de_paris(reco_libre):
    # Un défaut sert « aujourd'hui » ; une date lointaine reste refusée sans lever.
    ok, _ = apply_edit(reco_libre, {"title": ["X"], "types": ["album"],
                                    "releaseDate": ["9999-01-01"]})
    assert ok is True
    assert "releaseDate" not in _lire(reco_libre)


# ---- champ_sortie et formulaire ---------------------------------------------
@pytest.fixture
def chemin_de(monkeypatch):
    """Fait résoudre le chemin d'une reco vers un fichier choisi par le test."""
    def _poser(chemin):
        monkeypatch.setattr(review_edit_sortie, "_chemin_de_reco", lambda _r: chemin)
    return _poser


def test_champ_present_pour_un_album_non_suivi(reco_libre, chemin_de):
    chemin_de(reco_libre)
    out = champ_sortie({"types": ["album"]})
    assert 'name="releaseDate"' in out
    assert "album" in out and "livre" in out and "jeu" in out  # il dit ce qu'il sert


def test_champ_prerempli_et_echappe(reco_libre, chemin_de):
    chemin_de(reco_libre)
    out = champ_sortie({"types": ["album"], "releaseDate": '"><script>'})
    assert "<script>" not in out
    assert "&quot;&gt;&lt;script&gt;" in out


def test_champ_absent_pour_un_type_hors_v1(reco_libre, chemin_de):
    chemin_de(reco_libre)
    assert champ_sortie({"types": ["film"]}) == ""


def test_champ_absent_si_la_reco_est_introuvable(chemin_de):
    chemin_de(None)
    assert champ_sortie({"types": ["album"]}) == ""


def test_mention_pour_un_fichier_suivi(reco_suivie, chemin_de):
    chemin_de(reco_suivie)
    out = champ_sortie({"types": ["album"], "releaseDate": "2026-12-04"})
    assert 'name="releaseDate"' not in out
    assert "après publication : PR de contenu" in out
    assert "2026-12-04" in out


def test_mention_sans_date_connue(reco_suivie, chemin_de):
    chemin_de(reco_suivie)
    out = champ_sortie({"types": ["album"]})
    assert "après publication : PR de contenu" in out


def test_chemin_de_reco_passe_par_le_cache_du_serveur(monkeypatch, tmp_path):
    import review_handler_base
    monkeypatch.setattr(review_handler_base, "_reco_path",
                        lambda source, rid: tmp_path / f"{source}-{rid}.json")
    assert review_edit_sortie._chemin_de_reco(
        {"sourceId": "s", "id": "a"}) == tmp_path / "s-a.json"


def test_le_formulaire_porte_le_champ(reco_libre, chemin_de):
    chemin_de(reco_libre)
    html = render_edit_form({"id": "r1", "title": "T", "types": ["album"]},
                            {"guid": "g"})
    assert 'name="releaseDate"' in html


def test_le_formulaire_sans_champ_pour_un_film(reco_libre, chemin_de):
    chemin_de(reco_libre)
    html = render_edit_form({"id": "r1", "title": "T", "types": ["film"]},
                            {"guid": "g"})
    assert 'name="releaseDate"' not in html


# ---- route : le message ------------------------------------------------------
def test_la_route_dit_la_date_ignoree(reco_libre, monkeypatch):
    import review_routes

    class _Faux(review_routes.Handler):
        source_id = "src"

        def __init__(self):  # pas de socket
            pass

        def _referer_path(self):
            return "/ep"

    cible = _Faux()
    monkeypatch.setattr(review_routes, "refresh_reco_in_cache", lambda *_a: None)
    guid, flash, kind = cible._dispatch_edit(
        reco_libre, "r1", {"title": ["T"], "types": ["album"], "releaseDate": ["nawak"]})
    assert guid == "ep-1"
    assert "Modifications enregistrées" in flash
    assert "date ignorée : format attendu : AAAA-MM-JJ" in flash
    assert kind == "warning"


# ---- tour 1 de revue, PR #227 : l'année déduite de la date, et le type qui n'est plus servi ----
def test_l_annee_deduite_suit_la_date_quand_elle_change(reco_libre):
    reco = _lire(reco_libre)
    appliquer_sortie(reco, {"releaseDate": ["2026-12-04"]}, reco_libre, MAINTENANT)
    assert reco["year"] == 2026
    appliquer_sortie(reco, {"releaseDate": ["2027-01-15"]}, reco_libre, MAINTENANT)
    assert reco["releaseDate"] == "2027-01-15" and reco["year"] == 2027


def test_une_annee_qui_ne_venait_pas_de_la_date_n_est_jamais_touchee(reco_libre):
    reco = _lire(reco_libre)
    reco.update(releaseDate="2026-12-04", year=1999)
    appliquer_sortie(reco, {"releaseDate": ["2027-01-15"]}, reco_libre, MAINTENANT)
    assert reco["year"] == 1999


def test_une_annee_posee_avant_la_date_reste_quand_la_date_est_retiree(reco_libre):
    reco = _lire(reco_libre)
    reco.update(releaseDate="2026-12-04", year=2026)
    assert appliquer_sortie(reco, {"releaseDate": [""]}, reco_libre, MAINTENANT) is None
    assert "releaseDate" not in reco and reco["year"] == 2026


def test_une_annee_etrangere_reste_quand_la_date_disparait(reco_libre):
    reco = _lire(reco_libre)
    reco.update(releaseDate="2026-12-04", year=1999)
    appliquer_sortie(reco, {"releaseDate": [""]}, reco_libre, MAINTENANT)
    assert "releaseDate" not in reco and reco["year"] == 1999


def test_un_type_qui_n_est_plus_servi_fait_retirer_la_date(reco_libre):
    # Le champ n'est plus au formulaire pour un type hors V1 : la date posée avant resterait.
    reco = _lire(reco_libre)
    reco.update(types=["film"], releaseDate="2026-12-04", year=2026)
    msg = appliquer_sortie(reco, {}, reco_libre, MAINTENANT)
    assert msg == "date de sortie retirée : type non servi"
    assert "releaseDate" not in reco and reco["year"] == 2026


def test_un_type_non_servi_sans_date_ne_dit_rien(reco_libre):
    reco = _lire(reco_libre)
    reco["types"] = ["film"]
    assert appliquer_sortie(reco, {}, reco_libre, MAINTENANT) is None


def test_apply_edit_retire_la_date_quand_le_type_change_vers_un_type_non_servi(reco_libre):
    reco = _lire(reco_libre)
    reco["releaseDate"] = "2026-12-04"
    reco_libre.write_text(json.dumps(reco), encoding="utf-8")
    avis: list[str] = []
    apply_edit(reco_libre, {"title": ["X"], "types": ["film"]},
               maintenant=MAINTENANT, avertissements=avis)
    assert avis == ["date de sortie retirée : type non servi"]
    assert "releaseDate" not in _lire(reco_libre)
