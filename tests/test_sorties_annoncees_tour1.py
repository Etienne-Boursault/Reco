"""Tests de `tools/sorties_annoncees.py` ajoutés au tour 1 de revue de la PR #227.

Pannes git et Matrix, recos illisibles, aperçu sans fetch, propositions refermées. Même banc que
`test_sorties_annoncees.py` (git réel, `origin` nu local ; passes, publication, Matrix et horloge
remplacés) : le fichier d'origine est à son plafond de 500 lignes.
"""
from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

import common
import publication as pub
import sorties_annoncees as sa
import sorties_plan as sp
import sorties_propositions as spr
import test_sorties_annoncees as base
from publication import ErreurGit
from test_sorties_annoncees import CHEMIN, CLE, ENV, URL_A, URL_B, Banc, Passe, _ecrire_reco, _git

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
    monkeypatch.setattr(spr, "branche_distante_presente", casse)
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


# --- une proposition refermée ou fusionnée autrement ne reste pas « en attente » ---------------

BRANCHE = "contenu/sorties-2026-11-26"
JETON = {**ENV, "RECO_GITHUB_TOKEN": "jeton-d-essai"}


def _proposition_en_attente(banc, depot, urls=(URL_A,), externes=None) -> str:
    """Une branche de contenu poussée, jamais fusionnée, et sa proposition dans l'état."""
    _git(depot, "checkout", "-q", "-b", BRANCHE)
    _ecrire_reco(depot, CHEMIN, links=[{"url": u, "label": "Deezer", "kind": "streaming"} for u in urls])
    _git(depot, "commit", "-qam", "liens")
    sha = _git(depot, "rev-parse", "HEAD")
    _git(depot, "push", "-q", "origin", BRANCHE)
    _git(depot, "checkout", "-q", "main")
    sp.ecrire_etat(banc.chemin_etat, sp.noter_proposition(sp.etat_vide(), CLE, BRANCHE, sha, list(urls), externes))
    return sha


class Github:
    """Remplace la lecture de l'API REST : rend ce qu'on lui donne, et note les appels."""

    def __init__(self, reponse=None, erreur: Exception | None = None) -> None:
        self.reponse, self.erreur, self.appels = reponse, erreur, []

    def __call__(self, url: str, jeton: str):
        self.appels.append((url, jeton))
        if self.erreur:
            raise self.erreur
        return self.reponse


@pytest.fixture
def github_distant(monkeypatch):
    monkeypatch.setattr(pub.Git, "url_distante", lambda self: "git@github.com:o/d.git")


def test_une_fusion_par_squash_ferme_la_proposition_par_les_adresses(banc, depot):
    # Le commit de la branche n'est jamais ancêtre de main, mais ses adresses y sont.
    _proposition_en_attente(banc, depot)
    _ecrire_reco(depot, CHEMIN, links=[{"url": URL_A, "label": "Deezer", "kind": "streaming"}])
    _git(depot, "commit", "-qam", "squash")
    _git(depot, "push", "-q", "origin", "main")
    passe = Passe(URL_B)
    banc.lancer([("musique", passe)])
    assert passe.appels == 1


def test_sans_jeton_une_pr_refermee_sans_fusion_reste_en_attente(banc, depot):
    _proposition_en_attente(banc, depot)
    passe = Passe(URL_B)
    banc.lancer([("musique", passe)])
    assert passe.appels == 0  # l'ancienne règle : branche présente, commit pas ancêtre


def test_une_pr_refermee_sans_fusion_rend_la_reco_relancable_avec_les_seules_adresses_nouvelles(
        banc, depot, github_distant):
    _proposition_en_attente(banc, depot)
    github = Github([{"state": "closed", "merged_at": None}])
    assert banc.lancer([("musique", Passe(URL_A, URL_B))], env=JETON, lire=github) == 0
    [(url, jeton)] = github.appels
    assert jeton == "jeton-d-essai"
    adresse = urlsplit(url)
    assert adresse.path == "/repos/o/d/pulls"
    assert parse_qs(adresse.query) == {"head": ["o:" + BRANCHE], "state": ["all"]}
    ecrit = json.loads((banc.publieur.dossier / CHEMIN).read_text(encoding="utf-8"))
    assert [lien["url"] for lien in ecrit["links"]] == [URL_B]


def test_une_pr_encore_ouverte_garde_la_reco_en_attente(banc, depot, github_distant):
    _proposition_en_attente(banc, depot)
    passe = Passe(URL_B)
    banc.lancer([("musique", passe)], env=JETON, lire=Github([{"state": "open"}]))
    assert passe.appels == 0


@pytest.mark.parametrize("github", [Github(erreur=OSError("API coupée")), Github([])])
def test_sans_reponse_utile_de_l_api_l_ancienne_regle_s_applique(banc, depot, github_distant, github):
    _proposition_en_attente(banc, depot)
    passe = Passe(URL_B)
    banc.lancer([("musique", passe)], env=JETON, lire=github)
    assert passe.appels == 0 and len(github.appels) == 1


def test_seules_les_propositions_des_recos_dans_leur_fenetre_sont_testees(banc, depot, github_distant):
    _proposition_en_attente(banc, depot)
    github = Github([{"state": "open"}])
    banc.maintenant = datetime(2026, 12, 21, 8, 0, tzinfo=UTC)  # J+31 : fenêtre fermée
    banc.lancer([("musique", Passe(URL_B))], env=JETON, lire=github)
    assert github.appels == []


def test_la_lecture_de_l_api_par_defaut_envoie_le_jeton_et_lit_la_liste(monkeypatch):
    vu = {}

    class Reponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

    def ouvrir(requete, timeout):
        vu.update(url=requete.full_url, auth=requete.get_header("Authorization"), delai=timeout)
        return Reponse(b'[{"state": "closed"}]')

    monkeypatch.setattr(spr.urllib.request, "urlopen", ouvrir)
    assert spr._lire_api("https://api.github.com/repos/o/d/pulls?state=all", "jeton") == [{"state": "closed"}]
    assert vu["auth"] == "Bearer jeton" and vu["delai"] == pub.DELAI_API


# --- les identifiants refusés ne reviennent pas ----------------------------------------------

class PasseAvecIdentifiant(Passe):
    """Comme `Passe`, mais la reco gagne aussi un `externalIds`."""

    def __call__(self, source: str, ids: set[str]) -> None:
        super().__call__(source, ids)
        for rid in ids:
            chemin = common.RECOS_DIR / source / f"{rid}.json"
            doc = json.loads(chemin.read_text(encoding="utf-8"))
            doc["externalIds"] = {"deezerAlbum": "123"}
            chemin.write_text(json.dumps(doc), encoding="utf-8")


def test_la_proposition_garde_les_identifiants_poses(banc):
    banc.lancer([("musique", PasseAvecIdentifiant(URL_A))])
    assert banc.etat()["propositions"][CLE]["externalIds"] == {"deezerAlbum": "123"}
    ecrit = json.loads((banc.publieur.dossier / CHEMIN).read_text(encoding="utf-8"))
    assert ecrit["externalIds"] == {"deezerAlbum": "123"}


def test_un_identifiant_deja_propose_ne_revient_pas_avec_une_autre_adresse(banc):
    sp.ecrire_etat(banc.chemin_etat, sp.noter_proposition(
        sp.etat_vide(), CLE, BRANCHE, "abc", [URL_A], {"deezerAlbum": "123"}))
    banc.lancer([("musique", PasseAvecIdentifiant(URL_A, URL_B))])
    ecrit = json.loads((banc.publieur.dossier / CHEMIN).read_text(encoding="utf-8"))
    assert [lien["url"] for lien in ecrit["links"]] == [URL_B] and "externalIds" not in ecrit


def test_un_identifiant_different_de_celui_refuse_est_propose(banc):
    sp.ecrire_etat(banc.chemin_etat, sp.noter_proposition(
        sp.etat_vide(), CLE, BRANCHE, "abc", [URL_A], {"deezerAlbum": "999"}))
    banc.lancer([("musique", PasseAvecIdentifiant(URL_A, URL_B))])
    ecrit = json.loads((banc.publieur.dossier / CHEMIN).read_text(encoding="utf-8"))
    assert ecrit["externalIds"] == {"deezerAlbum": "123"}


# --- le sablier ne part pas si l'éditeur a posé un lien -------------------------------------

def _jusqu_a_la_fermeture(banc) -> None:
    banc.lancer([("musique", Passe())])  # première relance : aucun lien trouvé
    banc.maintenant = datetime(2026, 12, 21, 8, 0, tzinfo=UTC)  # J+31


def test_le_sablier_part_quand_la_reco_n_a_pas_change(banc):
    _jusqu_a_la_fermeture(banc)
    banc.lancer([("musique", Passe())])
    assert [m for m in banc.messages if m.startswith("⏳")]


def test_le_sablier_ne_part_pas_si_l_editeur_a_pose_un_lien_a_la_main(banc, depot):
    _jusqu_a_la_fermeture(banc)
    _ecrire_reco(depot, CHEMIN, links=[{"url": URL_B, "label": "Apple Music", "kind": "streaming"}])
    _git(depot, "commit", "-qam", "lien posé à la main")
    _git(depot, "push", "-q", "origin", "main")
    banc.lancer([("musique", Passe())])
    assert not [m for m in banc.messages if m.startswith("⏳")]
