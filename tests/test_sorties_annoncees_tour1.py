"""Tests de `tools/sorties_annoncees.py` ajoutés au tour 1 de revue de la PR #227.

Pannes git et Matrix, recos illisibles, aperçu sans fetch, propositions refermées. Même banc que
`test_sorties_annoncees.py` (git réel, `origin` nu local ; passes, publication, Matrix et horloge
remplacés) : le fichier d'origine est à son plafond de 500 lignes.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import sorties_annoncees as sa
import sorties_plan as sp
import test_sorties_annoncees as base
from publication import ErreurGit
from test_sorties_annoncees import CLE, URL_A, Banc, _ecrire_reco, _git

# Les fixtures du banc, reprises telles quelles (un import par nom ferait « redéfinir » le paramètre).
depot, banc, paris = base.depot, base.banc, base.paris


# --- tour 1 de revue, PR #227 : pannes, aperçu ---------------------------------------------

def _avec_origine_cassee(monkeypatch, commande: str) -> None:
    """Fait échouer une commande git précise (`diff`, `show`…), les autres restent réelles."""
    reel = sa.Git._git

    def casse(self, *args, **kw):
        if args and args[0] == commande:
            raise ErreurGit(f"{commande} cassé")
        return reel(self, *args, **kw)
    monkeypatch.setattr(sa.Git, "_git", casse)


def test_un_fetch_reussi_efface_la_panne_git_d_avant(banc):
    etat, _ = sp.noter_erreur(sp.etat_vide(), "git", "fetch coupé")
    sp.ecrire_etat(banc.chemin_etat, etat)
    banc.lancer()
    assert "git" not in banc.etat()["erreurs"]


def test_une_panne_dont_le_message_n_est_pas_parti_n_est_pas_notee(tmp_path):
    vide = tmp_path / "vide"
    vide.mkdir()
    _git(vide, "init", "-b", "main")
    banc = Banc(vide, tmp_path)

    def casse(_texte):
        raise OSError("Matrix coupé")
    assert banc.lancer(notify=casse) == 1
    assert banc.etat()["erreurs"] == {}  # signalée au prochain passage, pas perdue
    assert banc.lancer() == 1 and len(banc.messages) == 1


@pytest.mark.parametrize("commande", ["diff", "show"])
def test_une_erreur_git_apres_le_fetch_se_signale_rend_1_et_ne_note_pas_le_jour(banc, monkeypatch, commande):
    _avec_origine_cassee(monkeypatch, commande)
    assert banc.lancer() == 1
    assert len(banc.messages) == 1 and banc.messages[0].startswith("⚠️ Relance des sorties annoncées, git")
    etat = banc.etat()
    assert etat["dernier_jour"] is None and "git" in etat["erreurs"]


def test_un_ls_remote_qui_echoue_se_signale_comme_une_panne_git(banc, monkeypatch):
    sp.ecrire_etat(banc.chemin_etat, sp.noter_proposition(sp.etat_vide(), CLE, "contenu/x", "abc", [URL_A]))

    def casse(_racine, _nom):
        raise ErreurGit("ls-remote coupé")
    monkeypatch.setattr(sa, "branche_distante_presente", casse)
    assert banc.lancer() == 1
    assert "ls-remote coupé" in banc.messages[0] and banc.etat()["dernier_jour"] is None


def test_une_reco_illisible_sur_origin_est_sautee_et_signalee_une_fois(banc, depot):
    (depot / "src/content/recos/un-bon-moment/ubm-3.json").write_text('{"releaseDate": "2026-11-20", ', encoding="utf-8")
    _git(depot, "add", ".")
    _git(depot, "commit", "-m", "reco cassée")
    _git(depot, "push", "origin", "main")
    assert banc.lancer() == 0
    assert len(banc.publieur.appels) == 1  # ubm-1 est passée malgré ubm-3
    illisibles = [m for m in banc.messages if "illisible" in m]
    assert len(illisibles) == 1 and "ubm-3.json" in illisibles[0]
    banc.maintenant += timedelta(days=1)
    banc.lancer()
    assert len([m for m in banc.messages if "illisible" in m]) == 1


def test_une_reco_redevenue_lisible_efface_sa_panne(banc, depot):
    fichier = depot / "src/content/recos/un-bon-moment/ubm-3.json"
    fichier.write_text("{pas du json releaseDate", encoding="utf-8")
    _git(depot, "add", ".")
    _git(depot, "commit", "-m", "reco cassée")
    _git(depot, "push", "origin", "main")
    banc.lancer()
    assert any(c.startswith("reco ") for c in banc.etat()["erreurs"])
    _ecrire_reco(depot, "src/content/recos/un-bon-moment/ubm-3.json", releaseDate="2026-11-20")
    _git(depot, "commit", "-am", "réparée")
    _git(depot, "push", "origin", "main")
    banc.maintenant += timedelta(days=1)
    banc.lancer()
    assert not any(c.startswith("reco ") for c in banc.etat()["erreurs"])


def test_la_panne_d_une_passe_ne_s_efface_que_si_une_passe_a_tourne(banc):
    etat, _ = sp.noter_erreur(sp.etat_vide(), "passe musique", "API muette")
    sp.ecrire_etat(banc.chemin_etat, etat)
    banc.maintenant = datetime(2027, 6, 1, 8, 0, tzinfo=UTC)  # plus aucune reco dans sa fenêtre
    banc.lancer()
    assert "passe musique" in banc.etat()["erreurs"]
    banc.maintenant = datetime(2026, 11, 28, 8, 0, tzinfo=UTC)  # ubm-1 est relancée
    banc.lancer()
    assert "passe musique" not in banc.etat()["erreurs"]


def test_apercu_ne_fait_pas_de_fetch_et_lit_l_origin_main_local(banc, monkeypatch):
    commandes = []
    reel = sa.Git._git

    def espion(self, *args, **kw):
        commandes.append(args[0])
        return reel(self, *args, **kw)
    monkeypatch.setattr(sa.Git, "_git", espion)
    banc.lancer(apercu=True)
    assert "fetch" not in commandes and "grep" in commandes
    commandes.clear()
    banc.lancer()
    assert "fetch" in commandes
