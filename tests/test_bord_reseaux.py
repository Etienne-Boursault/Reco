"""Tests de `tools/bord_reseaux.py` — les cases des réseaux du tableau de bord.

L'état vit sous `RECO_BORD_DIR` (un dossier temporaire ici) : aucun test
n'écrit dans `tools/output/`. Le titre d'un épisode publié mais pas encore
fusionné se lit sur un VRAI dépôt git temporaire, comme dans
`test_publication.py`.
"""
from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

import bord_reseaux as br

MAINTENANT = datetime(2026, 11, 28, 9, 30, tzinfo=UTC)
ETAT = {"published": ["yt-a", "yt-b", "yt-c", "yt-d"]}


@pytest.fixture(autouse=True)
def bord(tmp_path, monkeypatch):
    d = tmp_path / "bord"
    monkeypatch.setenv("RECO_BORD_DIR", str(d))
    return d


def _contenu(bord: Path) -> dict:
    return json.loads((bord / "reseaux.json").read_text(encoding="utf-8"))


# ---- Les 3 derniers publiés ------------------------------------------------
def test_guids_recents_les_trois_derniers_du_plus_recent_au_plus_ancien():
    assert br.guids_recents(ETAT) == ["yt-d", "yt-c", "yt-b"]


def test_guids_recents_sans_etat_de_chaine():
    assert br.guids_recents(None) == []
    assert br.guids_recents({}) == []


# ---- Pose et retrait ------------------------------------------------------
def test_lire_sans_fichier_rend_un_etat_vide():
    assert br.lire() == {}


def test_cocher_pose_la_case_avec_sa_date(bord):
    br.cocher(ETAT, "yt-d", "deezer", True, maintenant=MAINTENANT)
    assert _contenu(bord) == {"yt-d": {"deezer": "2026-11-28T09:30:00+00:00"}}
    assert br.lire() == _contenu(bord)
    assert not list(bord.glob("*.tmp"))


def test_cocher_deux_fois_garde_la_premiere_date(bord):
    br.cocher(ETAT, "yt-d", "deezer", True, maintenant=MAINTENANT)
    br.cocher(ETAT, "yt-d", "deezer", True, maintenant=datetime(2026, 11, 29, tzinfo=UTC))
    assert _contenu(bord)["yt-d"]["deezer"].startswith("2026-11-28")


def test_cocher_retire_la_case_et_l_episode_vide(bord):
    br.cocher(ETAT, "yt-d", "deezer", True, maintenant=MAINTENANT)
    br.cocher(ETAT, "yt-d", "spotify", True, maintenant=MAINTENANT)
    br.cocher(ETAT, "yt-d", "deezer", False)
    assert _contenu(bord) == {"yt-d": {"spotify": "2026-11-28T09:30:00+00:00"}}
    br.cocher(ETAT, "yt-d", "spotify", False)
    assert _contenu(bord) == {}


def test_les_six_reseaux_sont_admis(bord):
    for reseau in ("instagram", "threads", "spotify", "deezer", "senscritique", "youtube"):
        br.cocher(ETAT, "yt-c", reseau, True, maintenant=MAINTENANT)
    assert set(_contenu(bord)["yt-c"]) == set(br.RESEAUX)
    assert len(br.RESEAUX) == 6


# ---- Refus ------------------------------------------------------------------
def test_un_reseau_inconnu_est_refuse(bord):
    with pytest.raises(ValueError):
        br.cocher(ETAT, "yt-d", "myspace", True)
    assert not (bord / "reseaux.json").exists()


def test_un_guid_hors_des_trois_derniers_publies_est_refuse(bord):
    with pytest.raises(ValueError):
        br.cocher(ETAT, "yt-a", "deezer", True)
    with pytest.raises(ValueError):
        br.cocher(ETAT, "yt-inconnu", "deezer", True)
    assert not (bord / "reseaux.json").exists()


def test_sans_etat_de_chaine_aucune_case_ne_se_coche(bord):
    with pytest.raises(ValueError):
        br.cocher(None, "yt-d", "deezer", True)
    assert not (bord / "reseaux.json").exists()


@pytest.mark.parametrize("texte", ["{pas du json", '["yt-d"]', '{"yt-d": ["deezer"]}',
                                   '{"yt-d": {"deezer": 3}}'])
def test_un_fichier_illisible_n_est_jamais_reecrit(bord, texte):
    bord.mkdir(parents=True)
    chemin = bord / "reseaux.json"
    chemin.write_text(texte, encoding="utf-8")
    with pytest.raises(br.EtatIllisible):
        br.lire()
    with pytest.raises(br.EtatIllisible):
        br.cocher(ETAT, "yt-d", "deezer", True)
    assert chemin.read_text(encoding="utf-8") == texte


# ---- Épisodes récents : fusionné, ou publié mais pas encore fusionné -------
def _git(racine: Path, *args: str) -> str:
    fini = subprocess.run(["git", *args], cwd=racine, capture_output=True, text=True,
                          encoding="utf-8", check=True)
    return (fini.stdout or "").strip()


@pytest.fixture
def clone(tmp_path, monkeypatch):
    """Un clone où `yt-AbC` a été poussé sur `contenu/yt-abc`, puis retiré du disque.

    C'est l'état que laisse `publication._nettoyer` tant que la PR n'est pas
    fusionnée : le fichier de l'épisode n'existe plus que sur la branche.
    """
    import common

    racine = tmp_path / "clone"
    racine.mkdir()
    _git(racine, "init", "-b", "main")
    _git(racine, "config", "user.name", "Reco (essai)")
    _git(racine, "config", "user.email", "essai@example.test")
    (racine / "LISEZMOI.md").write_text("essai\n", encoding="utf-8")
    _git(racine, "add", "LISEZMOI.md")
    _git(racine, "commit", "-m", "depart")
    _git(racine, "checkout", "-b", "contenu/yt-abc")
    episode = racine / "src/content/episodes/demo/yt-abc.json"
    episode.parent.mkdir(parents=True)
    episode.write_text(json.dumps({"guid": "yt-AbC", "title": "Épisode poussé",
                                   "season": 6, "number": 11}), encoding="utf-8")
    _git(racine, "add", "src")
    _git(racine, "commit", "-m", "contenu: publier")
    _git(racine, "update-ref", "refs/remotes/origin/contenu/yt-abc", "HEAD")
    _git(racine, "checkout", "main")
    assert not episode.exists()
    monkeypatch.setattr(common, "PROJECT_ROOT", racine)
    monkeypatch.setattr(common, "EPISODES_DIR", racine / "src/content/episodes")
    return racine


def test_publie_pas_encore_fusionne_le_titre_vient_de_la_branche(clone):
    etat = {"published": ["yt-AbC"]}
    recents = br.episodes_recents("demo", etat, episodes={})
    assert recents == [{"guid": "yt-AbC", "fusionne": False,
                        "episode": {"guid": "yt-AbC", "title": "Épisode poussé",
                                    "season": 6, "number": 11}}]
    # Le guid reste cochable : il est validé par `published`, pas par le clone.
    br.cocher(etat, "yt-AbC", "instagram", True, maintenant=MAINTENANT)
    assert "yt-AbC" in br.lire()


def test_publie_sans_branche_rapatriee_l_episode_est_inconnu(clone):
    recents = br.episodes_recents("demo", {"published": ["yt-absent"]}, episodes={})
    assert recents == [{"guid": "yt-absent", "fusionne": False, "episode": None}]


def test_hors_d_un_depot_git_l_episode_est_inconnu(tmp_path, monkeypatch):
    import common

    monkeypatch.setattr(common, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path / "episodes")
    recents = br.episodes_recents("demo", {"published": ["yt-x"]}, episodes={})
    assert recents[0]["episode"] is None


def test_fusionne_l_episode_vient_du_clone_sans_appeler_git(monkeypatch):
    def interdit(*_a, **_k):
        raise AssertionError("git ne doit pas être appelé pour un épisode fusionné")

    monkeypatch.setattr(br.subprocess, "run", interdit)
    ep = {"guid": "yt-a", "title": "Fusionné", "season": 6, "number": 10}
    recents = br.episodes_recents("demo", {"published": ["yt-a"]}, episodes={"yt-a": ep})
    assert recents == [{"guid": "yt-a", "fusionne": True, "episode": ep}]


def test_sans_etat_de_chaine_les_recents_sont_inconnus():
    assert br.episodes_recents("demo", None, episodes={}) is None


# ---- git qui échoue : le guid suffit, la page ne tombe pas -----------------
class _Fini:
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout, self.returncode = stdout, returncode


@pytest.mark.parametrize("comportement", [
    subprocess.TimeoutExpired("git", 5), FileNotFoundError("git"),
    _Fini("pas du json"), _Fini('["une", "liste"]')])
def test_un_git_en_panne_ou_une_branche_abimee_donne_un_episode_inconnu(
        clone, monkeypatch, comportement):
    def faux_run(*_a, **_k):
        if isinstance(comportement, Exception):
            raise comportement
        return comportement

    monkeypatch.setattr(br.subprocess, "run", faux_run)
    recents = br.episodes_recents("demo", {"published": ["yt-AbC"]}, episodes={})
    assert recents[0]["episode"] is None


def test_un_dossier_d_episodes_hors_du_depot_donne_un_episode_inconnu(tmp_path, monkeypatch):
    import common

    monkeypatch.setattr(common, "PROJECT_ROOT", tmp_path / "depot")
    monkeypatch.setattr(common, "EPISODES_DIR", tmp_path / "ailleurs")
    assert br.episodes_recents("demo", {"published": ["yt-x"]}, episodes={})[0]["episode"] is None
