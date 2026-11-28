"""Tests de `tools/rappel_dimanche.py` : le message Matrix du dimanche soir.

Tableau de bord, R2 B du 27/11/2026 ; TB-1 C et TB-2 B du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 7 ; PR 4, tranche 4a). L'horloge est injectée, le fuseau
est fixé à UTC+1 (le poste Windows n'a pas `tzdata`), Matrix est un faux, et
`rafraichir` est remplacé : aucun appel réseau, aucune écriture hors du dossier temporaire.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import bord_afaire
import bord_contenu
import bord_distant
import bord_github
import bord_reseaux
import rappel_dimanche as rd
import review_render
import review_render_page

# Dimanche 29/11/2026, 20 h 05 à Paris (UTC+1) : semaine ISO 2026-W48.
DIMANCHE_20H05 = datetime(2026, 11, 29, 19, 5, tzinfo=UTC)
EP12 = {"guid": "yt-12", "title": "Douze", "season": 6, "number": 12}
AUDIENCE = {"etat": "ok", "lu": "2026-11-29T19:00:00+00:00",
            "donnees": {"signalements": {"etat": "lu", "enAttente": [{"id": "s1"}]}}}
PR_SORTIES = {"numero": 7, "titre": "Sorties", "branche": "contenu/sorties-x",
              "groupe": "sorties", "date": "2026-11-28T08:00:00Z",
              "adresse": "https://github.com/a/b/pull/7"}
GITHUB = {"etat": "ok", "lu": "2026-11-29T19:00:00+00:00",
          "donnees": {"depot": "a/b", "fusionnees": [],
                      "ouvertes": {"episodes": [], "sorties": [PR_SORTIES], "coupee": False}}}
CONTENU = {"liens": {"date": "2026-11-23", "age": 6, "ancien": False, "morts": 3}}


class FauxSender:
    def __init__(self, ok: bool = True):
        self.ok, self.envoyes = ok, []

    def send(self, payload: dict) -> bool:
        self.envoyes.append(payload)
        return self.ok


@pytest.fixture
def monde(tmp_path, monkeypatch):
    """Un dimanche soir ordinaire : tout est lu, il reste des choses à faire."""
    m = SimpleNamespace(
        sender=FauxSender(), audience=AUDIENCE, github=GITHUB, contenu=CONTENU,
        groups={"yt-12": [{"status": "draft"}] * 14}, rafraichis=[],
        etat=tmp_path / "bord" / "rappel.json")
    monkeypatch.setenv("RECO_BORD_DIR", str(tmp_path / "bord"))
    monkeypatch.setenv("RECO_RAPPEL_DIMANCHE", "1")
    monkeypatch.delenv("RECO_REVIEW_URL", raising=False)
    monkeypatch.setattr(rd, "_fuseau", lambda: timezone(timedelta(hours=1)))
    monkeypatch.setattr(rd, "_sender", lambda: m.sender)
    monkeypatch.setattr(bord_distant, "rafraichir", lambda **kw: m.rafraichis.append("audience") or "ok")
    monkeypatch.setattr(bord_github, "rafraichir", lambda **kw: m.rafraichis.append("github") or "ok")
    monkeypatch.setattr(bord_distant, "lire", lambda **kw: m.audience)
    monkeypatch.setattr(bord_github, "lire", lambda **kw: m.github)
    monkeypatch.setattr(bord_contenu, "lire", lambda source_id, **kw: m.contenu)
    monkeypatch.setattr(review_render, "_load_groups",
                        lambda source_id: ({}, {"yt-12": EP12}, m.groups))
    monkeypatch.setattr(review_render_page, "_pipeline_state", lambda source_id: {"x": 1})
    monkeypatch.setattr(bord_reseaux, "episodes_recents", lambda *a: [])
    return m


def _lancer(*argv: str, maintenant: datetime = DIMANCHE_20H05) -> int:
    return rd.main(["--notifier", "matrix", *argv], maintenant=maintenant)


def _corps(monde) -> str:
    [envoye] = monde.sender.envoyes
    assert envoye["msgtype"] == "m.text"
    return envoye["body"]


def test_le_dimanche_a_20h_le_message_part_et_la_semaine_est_marquee(monde):
    assert _lancer() == 0
    corps = _corps(monde)
    assert corps.startswith("🗒️ Il te reste : relire ")
    assert "(14 recos)" in corps
    assert "1 signalement en attente" in corps and "3 liens morts" in corps
    assert "fusionner la PR des sorties : Sorties (#7)" in corps
    assert " · " in corps
    assert json.loads(monde.etat.read_text(encoding="utf-8"))["semaine"] == "2026-W48"
    assert monde.rafraichis == ["audience", "github"]


def test_le_texte_reprend_les_lignes_de_la_colonne_a_faire(monde):
    items = bord_afaire.a_faire_depuis(
        episodes={"yt-12": EP12}, groups=monde.groups, recents=[], coches={},
        audience=AUDIENCE, github=GITHUB, contenu=CONTENU)
    assert _lancer() == 0
    assert _corps(monde) == "🗒️ Il te reste : " + " · ".join(i["texte"] for i in items)


@pytest.mark.parametrize("quand", [
    datetime(2026, 11, 28, 19, 5, tzinfo=UTC),    # samedi soir
    datetime(2026, 11, 30, 19, 5, tzinfo=UTC),    # lundi : pas de rattrapage
    datetime(2026, 11, 29, 18, 59, tzinfo=UTC),   # dimanche 19 h 59 à Paris
])
def test_un_mauvais_jour_ou_avant_20h_rien_ne_part(monde, quand):
    assert _lancer(maintenant=quand) == 0
    assert monde.sender.envoyes == [] and monde.rafraichis == []
    assert not monde.etat.exists()


def test_a_20h00_pile_le_message_part(monde):
    assert _lancer(maintenant=datetime(2026, 11, 29, 19, 0, tzinfo=UTC)) == 0
    assert len(monde.sender.envoyes) == 1


def test_sans_l_interrupteur_le_script_reste_inerte(monde, monkeypatch):
    monkeypatch.delenv("RECO_RAPPEL_DIMANCHE")
    assert _lancer() == 0
    assert monde.sender.envoyes == [] and monde.rafraichis == []
    monkeypatch.setenv("RECO_RAPPEL_DIMANCHE", "0")
    assert _lancer() == 0 and monde.sender.envoyes == []


def test_une_seconde_fois_la_meme_semaine_rien_ne_part(monde):
    assert _lancer() == 0 and _lancer() == 0
    assert len(monde.sender.envoyes) == 1
    # La semaine suivante, le message repart.
    assert _lancer(maintenant=DIMANCHE_20H05 + timedelta(days=7)) == 0
    assert len(monde.sender.envoyes) == 2


def test_rien_a_dire_n_envoie_rien_et_ne_marque_pas_la_semaine(monde):
    monde.groups, monde.audience = {}, {**AUDIENCE, "donnees": {"signalements": {
        "etat": "lu", "enAttente": []}}}
    monde.github = {**GITHUB, "donnees": {**GITHUB["donnees"], "ouvertes": {
        "episodes": [], "sorties": [], "coupee": False}}}
    monde.contenu = {"liens": {"date": "2026-11-23", "age": 6, "ancien": False, "morts": 0}}
    assert _lancer() == 0
    assert monde.sender.envoyes == [] and not monde.etat.exists()


def test_des_lignes_inconnues_seules_envoient_un_message_qui_ne_dit_pas_rien_a_faire(monde, monkeypatch):
    # Revue, M1 : se taire se lirait « rien à faire » (F22). Le message part, sous une autre forme.
    monkeypatch.setenv("RECO_REVIEW_URL", "https://relecture.example")
    monde.groups, monde.audience, monde.github, monde.contenu = {}, None, None, None
    assert _lancer() == 0
    corps = _corps(monde)
    assert corps.startswith("🗒️ Rien de sûr cette semaine : ")
    assert "signalements : inconnu" in corps and "Il te reste" not in corps
    assert corps.endswith("\nhttps://relecture.example/bord")
    assert json.loads(monde.etat.read_text(encoding="utf-8"))["semaine"] == "2026-W48"


def test_une_ligne_inconnue_se_dit_dans_un_message_qui_part_pour_une_vraie_tache(monde):
    monde.audience = None
    assert _lancer() == 0
    assert "signalements : inconnu" in _corps(monde)
    assert "(données du" not in _corps(monde)  # jamais lue : pas de date à citer


@pytest.mark.parametrize("contenu", ["{pas du json", '["pas", "un", "objet"]', '{"semaine": 48}'])
def test_un_etat_illisible_n_envoie_rien_n_ecrit_rien_et_sort_en_erreur(monde, contenu):
    monde.etat.parent.mkdir(parents=True)
    monde.etat.write_text(contenu, encoding="utf-8")
    assert _lancer() == 1
    assert monde.sender.envoyes == [] and monde.rafraichis == []
    assert monde.etat.read_text(encoding="utf-8") == contenu


def test_un_envoi_rate_ne_marque_pas_la_semaine_et_sort_en_erreur(monde):
    monde.sender = FauxSender(ok=False)
    assert _lancer() == 1
    assert len(monde.sender.envoyes) == 1 and not monde.etat.exists()


def test_sans_matrix_configure_l_envoi_compte_comme_rate(monde):
    monde.sender = None
    assert _lancer() == 1
    assert not monde.etat.exists()


def test_une_ecriture_d_etat_impossible_sort_en_erreur(monde, monkeypatch):
    def refuse(*a, **kw):
        raise OSError("disque plein")

    monkeypatch.setattr(rd.common, "atomic_write_text", refuse)
    assert _lancer() == 1
    assert len(monde.sender.envoyes) == 1


def test_des_donnees_distantes_perimees_disent_inconnu_avec_leur_date(monde):
    monde.audience = {"etat": "panne", "lu": "2026-11-27T22:30:00+00:00",
                      "donnees": AUDIENCE["donnees"]}
    monde.github = {"etat": "limite", "lu": "2026-11-26T08:00:00+00:00",
                    "donnees": GITHUB["donnees"]}
    assert _lancer() == 0
    corps = _corps(monde)
    assert "signalements : inconnu (données du 27/11)" in corps
    assert "sorties : inconnu (données du 26/11)" in corps


def test_une_ligne_inconnue_d_une_source_ok_n_a_pas_de_date(monde):
    # Revue, F2 : un bloc en panne isolée (source `ok`) ne porte pas la date du jour.
    monde.audience = {**AUDIENCE, "donnees": {"signalements": {"etat": "erreur"}}}
    assert _lancer() == 0
    corps = _corps(monde)
    assert "signalements : inconnu" in corps and "(données du" not in corps


def test_la_date_des_donnees_se_lit_a_paris(monde):
    # 23 h 30 UTC le 27 est déjà le 28 à 0 h 30 à Paris (UTC+1 forcé ici).
    monde.audience = {"etat": "panne", "lu": "2026-11-27T23:30:00+00:00", "donnees": None}
    assert _lancer() == 0
    assert "signalements : inconnu (données du 28/11)" in _corps(monde)


def test_un_cache_des_cases_illisible_dit_reseaux_inconnu(monde, tmp_path):
    (tmp_path / "bord").mkdir()
    (tmp_path / "bord" / "reseaux.json").write_text("{abîmé", encoding="utf-8")
    assert _lancer() == 0
    assert "réseaux : inconnu" in _corps(monde)


def test_le_lien_de_la_page_vient_de_reco_review_url(monde, monkeypatch):
    monkeypatch.setenv("RECO_REVIEW_URL", "https://relecture.example/")
    assert _lancer() == 0
    assert _corps(monde).endswith("\nhttps://relecture.example/bord")


def test_sans_reco_review_url_le_message_n_a_pas_de_lien(monde):
    assert _lancer() == 0
    assert "http" not in _corps(monde) and "\n" not in _corps(monde)


def test_un_rafraichissement_en_erreur_ne_coupe_ni_l_autre_ni_le_message(monde, monkeypatch):
    def casse(**kw):
        raise RuntimeError("clé secrète dans le message")

    monkeypatch.setattr(bord_distant, "rafraichir", casse)
    assert _lancer() == 0
    assert monde.rafraichis == ["github"] and len(monde.sender.envoyes) == 1


def test_le_rafraichissement_journalise_le_type_jamais_le_message(monde, monkeypatch, caplog):
    def casse(**kw):
        raise RuntimeError("clé secrète dans le message")

    monkeypatch.setattr(bord_github, "rafraichir", casse)
    assert _lancer() == 0
    assert "RuntimeError" in caplog.text and "clé secrète" not in caplog.text


def test_le_script_ne_reconfigure_pas_le_journal_racine(monde, monkeypatch):
    # Revue, F4 : `basicConfig` doublait chaque ligne (le journal `reco` a déjà sa sortie).
    racine = logging.getLogger()
    monkeypatch.setattr(racine, "handlers", [])
    assert _lancer() == 0
    assert racine.handlers == []


def test_apercu_affiche_sans_envoyer_ni_ecrire_et_ignore_jour_heure_et_interrupteur(
        monde, monkeypatch, capsys):
    monkeypatch.delenv("RECO_RAPPEL_DIMANCHE")
    monde.etat.parent.mkdir(parents=True)
    monde.etat.write_text("{illisible", encoding="utf-8")
    samedi = datetime(2026, 11, 28, 10, 0, tzinfo=UTC)
    assert rd.main(["--apercu"], maintenant=samedi) == 0
    sortie = capsys.readouterr().out
    assert sortie.startswith("🗒️ Il te reste : ") and "3 liens morts" in sortie
    assert monde.sender.envoyes == []
    assert monde.etat.read_text(encoding="utf-8") == "{illisible"


def test_apercu_dit_quand_il_n_y_a_rien_a_dire(monde, capsys):
    monde.groups, monde.contenu = {}, {"liens": {"date": "2026-11-23", "age": 6, "ancien": False, "morts": 0}}
    monde.audience = {**AUDIENCE, "donnees": {"signalements": {"etat": "lu", "enAttente": []}}}
    monde.github = {**GITHUB, "donnees": {**GITHUB["donnees"], "ouvertes": {
        "episodes": [], "sorties": [], "coupee": False}}}
    assert rd.main(["--apercu"], maintenant=DIMANCHE_20H05) == 0
    assert "rien à dire" in capsys.readouterr().out


def test_apercu_montre_le_message_de_rien_de_sur(monde, capsys):
    monde.groups, monde.audience, monde.github, monde.contenu = {}, None, None, None
    assert rd.main(["--apercu"], maintenant=DIMANCHE_20H05) == 0
    assert capsys.readouterr().out.startswith("🗒️ Rien de sûr cette semaine : ")
    assert not monde.etat.exists()


def _instantane(dossier):
    return {str(f.relative_to(dossier)): (f.stat().st_size, f.stat().st_mtime_ns)
            for f in dossier.rglob("*")}


def test_apercu_ne_rafraichit_rien_et_n_ecrit_aucun_fichier(monde, monkeypatch, capsys):
    # Revue, F1 (famille F19) : l'aperçu lit le cache seulement, sans réseau ni écriture.
    dossier = monde.etat.parent
    dossier.mkdir(parents=True)
    (dossier / "distant.json").write_text("{}", encoding="utf-8")
    avant, relancer = _instantane(dossier), []
    for module, donnees in ((bord_distant, monde.audience), (bord_github, monde.github)):
        monkeypatch.setattr(module, "lire", lambda d=donnees, **kw: relancer.append(kw.get("relancer")) or d)
    assert rd.main(["--apercu"], maintenant=DIMANCHE_20H05) == 0
    assert capsys.readouterr().out.startswith("🗒️ Il te reste : ")
    assert monde.rafraichis == []
    assert relancer == [False, False]
    assert _instantane(dossier) == avant


def test_sans_notifier_ni_apercu_le_script_refuse(monde):
    with pytest.raises(SystemExit) as exc:
        rd.main([], maintenant=DIMANCHE_20H05)
    assert exc.value.code == 2


def test_l_envoi_passe_par_matrix_et_dit_non_configure_sans_ses_variables(monkeypatch):
    for nom in ("RECO_MATRIX_HOMESERVER", "RECO_MATRIX_TOKEN", "RECO_MATRIX_ROOM"):
        monkeypatch.delenv(nom, raising=False)
    assert rd._sender() is None
    monkeypatch.setenv("RECO_MATRIX_HOMESERVER", "https://matrix.invalid")
    monkeypatch.setenv("RECO_MATRIX_TOKEN", "faux")
    monkeypatch.setenv("RECO_MATRIX_ROOM", "!faux:matrix.invalid")
    assert rd._sender() is not None
