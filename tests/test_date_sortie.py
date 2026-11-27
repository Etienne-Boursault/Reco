"""Tests de `date_sortie` : le validateur de la date de sortie annoncée (R4 B, 27/11/2026).

Pur : aucune horloge, aucun réseau. « Aujourd'hui » est toujours passé en paramètre ;
le seul test qui touche au fuseau remplace `ZoneInfo`, car le poste Windows n'a pas
`tzdata` (le vrai fuseau se vérifie sur le LLM).
"""
from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta, tzinfo
from pathlib import Path

import pytest

import date_sortie as ds
from date_sortie import DateSortieInvalide

AUJOURDHUI = date(2026, 11, 27)


# --- le format et le calendrier --------------------------------------------------

def test_analyse_une_date_valide():
    assert ds.analyser_date_sortie("2026-11-20") == date(2026, 11, 20)


@pytest.mark.parametrize(
    "texte",
    ["2026-02-30", "2026-13-01", "2026-00-10", "2026-11-31"],
)
def test_refuse_un_jour_qui_n_existe_pas(texte):
    with pytest.raises(DateSortieInvalide, match="calendrier"):
        ds.analyser_date_sortie(texte)


@pytest.mark.parametrize(
    "texte",
    ["20261120", "20/11/2026", "2026-1-5", "2026-11-20T10:00", " 2026-11-20", "2026-11-20\n", "", "demain"],
)
def test_refuse_un_format_qui_n_est_pas_aaaa_mm_jj(texte):
    with pytest.raises(DateSortieInvalide, match="AAAA-MM-JJ"):
        ds.analyser_date_sortie(texte)


@pytest.mark.parametrize("valeur", [None, 20261120, 2026.0, ["2026-11-20"]])
def test_refuse_ce_qui_n_est_pas_une_chaine(valeur):
    with pytest.raises(DateSortieInvalide, match="AAAA-MM-JJ"):
        ds.analyser_date_sortie(valeur)


def test_le_29_fevrier_d_une_annee_bissextile_passe():
    assert ds.analyser_date_sortie("2028-02-29") == date(2028, 2, 29)
    with pytest.raises(DateSortieInvalide):
        ds.analyser_date_sortie("2027-02-29")


# --- l'horizon de 3 ans ---------------------------------------------------------

def test_valider_rend_la_chaine_d_origine():
    assert ds.valider_date_sortie("2026-12-04", AUJOURDHUI) == "2026-12-04"


def test_une_date_passee_est_acceptee():
    # Un album sorti hier, ou il y a dix ans, reste une date vraie.
    assert ds.valider_date_sortie("2026-11-26", AUJOURDHUI) == "2026-11-26"
    assert ds.valider_date_sortie("2016-05-01", AUJOURDHUI) == "2016-05-01"


def test_trois_ans_pile_passent_et_le_lendemain_est_refuse():
    assert ds.valider_date_sortie("2029-11-27", AUJOURDHUI) == "2029-11-27"
    with pytest.raises(DateSortieInvalide, match="3 ans"):
        ds.valider_date_sortie("2029-11-28", AUJOURDHUI)


def test_l_horizon_d_un_29_fevrier_tombe_le_28():
    # 29/02/2028 + 3 ans : 2031 n'est pas bissextile, la limite est le 28/02/2031.
    jour = date(2028, 2, 29)
    assert ds.valider_date_sortie("2031-02-28", jour) == "2031-02-28"
    with pytest.raises(DateSortieInvalide, match="3 ans"):
        ds.valider_date_sortie("2031-03-01", jour)


def test_valider_propage_le_refus_de_format():
    with pytest.raises(DateSortieInvalide, match="AAAA-MM-JJ"):
        ds.valider_date_sortie("2026-02-30x", AUJOURDHUI)


# --- la fenêtre de relance -------------------------------------------------------

SORTIE = date(2026, 11, 20)


@pytest.mark.parametrize(
    ("decalage", "attendu"),
    [(-1, False), (0, True), (30, True), (31, False)],
)
def test_fenetre_la_veille_le_jour_j_plus_30_et_plus_31(decalage, attendu):
    assert ds.dans_la_fenetre(SORTIE, SORTIE + timedelta(days=decalage)) is attendu


@pytest.mark.parametrize(
    ("decalage", "attendu"),
    [(-1, False), (0, False), (30, False), (31, True), (400, True)],
)
def test_fenetre_fermee_des_j_plus_31(decalage, attendu):
    assert ds.fenetre_fermee(SORTIE, SORTIE + timedelta(days=decalage)) is attendu


# --- les types servis ------------------------------------------------------------

@pytest.mark.parametrize("type_", ["album", "musique", "livre", "jeu"])
def test_les_types_de_la_v1_sont_servis(type_):
    assert ds.type_servi([type_]) is True


@pytest.mark.parametrize("type_", ["film", "serie", "artiste", "bd", "podcast", "autre"])
def test_les_autres_types_ne_sont_pas_servis(type_):
    assert ds.type_servi([type_]) is False


def test_une_reco_multitype_est_servie_si_un_type_l_est():
    assert ds.type_servi(["film", "livre"]) is True
    assert ds.type_servi([]) is False


def test_les_types_de_la_v1_restent_servis_par_les_passes():
    """Garde contre la dérive : un type retiré d'une passe ne doit pas rester promis."""
    import boutique_matching as bm
    import music_links_matching as mm

    assert set(ds.TYPES_V1) <= set(mm.SUPPORTED_TYPES) | set(bm.TYPES_SERVIS)


# --- minuit à Paris --------------------------------------------------------------

class _FauxFuseau(tzinfo):
    """Remplace `ZoneInfo` : Paris en hiver, UTC+1."""

    def __init__(self, nom):
        assert nom == "Europe/Paris"

    def utcoffset(self, _dt):
        return timedelta(hours=1)

    def dst(self, _dt):
        return timedelta(0)

    def tzname(self, _dt):
        return "CET"


def test_le_jour_est_celui_de_paris_pas_celui_d_utc(monkeypatch):
    monkeypatch.setattr(ds, "ZoneInfo", _FauxFuseau)
    # 23 h 30 UTC le 26 = 0 h 30 à Paris le 27.
    maintenant = datetime(2026, 11, 26, 23, 30, tzinfo=UTC)
    assert ds.jour_a_paris(maintenant) == date(2026, 11, 27)
    # 22 h 59 UTC : Paris n'a pas encore changé de jour.
    assert ds.jour_a_paris(datetime(2026, 11, 26, 22, 59, tzinfo=UTC)) == date(2026, 11, 26)


def test_sans_tzdata_le_jour_est_celui_d_utc(monkeypatch):
    from zoneinfo import ZoneInfoNotFoundError

    def _absent(_nom):
        raise ZoneInfoNotFoundError("Europe/Paris")

    monkeypatch.setattr(ds, "ZoneInfo", _absent)
    maintenant = datetime(2026, 11, 26, 23, 30, tzinfo=UTC)
    assert ds.jour_a_paris(maintenant) == date(2026, 11, 26)


def test_une_heure_sans_fuseau_est_refusee():
    with pytest.raises(ValueError, match="fuseau"):
        ds.jour_a_paris(datetime(2026, 11, 26, 23, 30))


def test_la_liste_des_types_servis_du_site_suit_celle_de_python():
    # Tour 1 de revue, PR #227 : `sortieAnnoncee.ts` garde sa propre copie de TYPES_V1.
    source = (Path(__file__).resolve().parent.parent / "src/utils/sortieAnnoncee.ts").read_text(encoding="utf-8")
    trouve = re.search(r"TYPES_SERVIS = \[([^\]]*)\]", source)
    assert trouve, "TYPES_SERVIS introuvable dans sortieAnnoncee.ts"
    assert tuple(re.findall(r"'([^']+)'", trouve.group(1))) == ds.TYPES_V1
