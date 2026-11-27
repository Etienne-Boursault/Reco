"""Tests de `tools/branche_de_contenu.py` : une branche de contenu sans toucher au clone vivant.

R4 B, 27/11/2026 (PR « sorties annoncées », tranche C). Le git est RÉEL : un dépôt
temporaire, son `origin` nu, une vraie poussée. Aucun test ne touche au dépôt Reco ni
au réseau : l'ouverture de PR passe par un poseur injecté.

Ce qui compte : l'éditeur peut modifier un fichier du clone pendant l'opération, et
ni ce fichier, ni `HEAD`, ni l'index ne doivent bouger (remarque 1 de la relecture).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import branche_de_contenu as bdc
import publication as pub


def _git(racine: Path, *args: str) -> str:
    fini = subprocess.run(["git", *args], cwd=racine, capture_output=True, text=True,
                          encoding="utf-8", check=True)
    return (fini.stdout or "").strip()


@pytest.fixture
def depot(tmp_path):
    """Un clone sur `main` avec un fichier suivi, et son `origin` nu."""
    origine = tmp_path / "origine.git"
    racine = tmp_path / "clone"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origine))
    racine.mkdir()
    _git(racine, "init", "-b", "main")
    _git(racine, "remote", "add", "origin", str(origine))
    _git(racine, "config", "user.name", "Reco (essai)")
    _git(racine, "config", "user.email", "essai@example.test")
    (racine / "reco.json").write_text('{"liens": []}\n', encoding="utf-8")
    _git(racine, "add", "reco.json")
    _git(racine, "commit", "-m", "depart")
    _git(racine, "push", "-u", "origin", "main")
    return racine


def _ecrire_enrichi(dossiers: list[Path] | None = None):
    def ecrire(dossier: Path) -> None:
        if dossiers is not None:
            dossiers.append(dossier)
        (dossier / "reco.json").write_text('{"liens": ["https://exemple.test/a"]}\n',
                                           encoding="utf-8")
    return ecrire


def _publier(racine: Path, ecrire=None, **kwargs):
    return bdc.publier_branche(racine, "contenu/sorties-2026-11-27",
                               ecrire or _ecrire_enrichi(), "contenu: un lien de plus",
                               titre="contenu: un lien de plus", corps="Corps.", **kwargs)


def _arbres(racine: Path) -> list[str]:
    return [ligne for ligne in _git(racine, "worktree", "list").splitlines() if ligne]


def test_a_file_edited_in_the_live_clone_during_the_operation_stays_intact(depot):
    (depot / "reco.json").write_text('{"liens": ["à la main"]}\n', encoding="utf-8")
    (depot / "neuf.json").write_text("{}\n", encoding="utf-8")
    tete, index = _git(depot, "rev-parse", "HEAD"), _git(depot, "ls-files", "-s")
    etat = _git(depot, "status", "--porcelain")

    def ecrire(dossier: Path) -> None:
        _ecrire_enrichi()(dossier)
        # L'éditeur sauvegarde pendant la relance.
        (depot / "reco.json").write_text('{"liens": ["encore à la main"]}\n', encoding="utf-8")

    resultat = _publier(depot, ecrire)

    assert resultat is not None
    assert (depot / "reco.json").read_text(encoding="utf-8") == '{"liens": ["encore à la main"]}\n'
    assert _git(depot, "rev-parse", "HEAD") == tete
    assert _git(depot, "ls-files", "-s") == index
    assert _git(depot, "status", "--porcelain") == etat
    assert _git(depot, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_the_commit_reaches_the_remote_branch_and_main_does_not_move(depot):
    principale = _git(depot, "rev-parse", "origin/main")

    resultat = _publier(depot)

    assert resultat.nom == "contenu/sorties-2026-11-27"
    assert _git(depot, "ls-remote", "origin", f"refs/heads/{resultat.nom}").split()[0] == resultat.sha
    assert _git(depot, "show", f"{resultat.sha}:reco.json") == '{"liens": ["https://exemple.test/a"]}'
    assert _git(depot, "log", "-1", "--format=%s", resultat.sha) == "contenu: un lien de plus"
    assert _git(depot, "rev-parse", "origin/main") == principale
    assert _git(depot, "rev-parse", "main") == principale


def test_the_temporary_folder_is_always_removed(depot):
    dossiers: list[Path] = []

    _publier(depot, _ecrire_enrichi(dossiers))

    assert not dossiers[0].exists()
    assert len(_arbres(depot)) == 1


def test_a_failed_push_leaves_no_folder_and_no_branch(depot, monkeypatch):
    dossiers: list[Path] = []

    def refuse(self, branche):
        raise pub.ErreurGit("poussée refusée")

    monkeypatch.setattr(pub.Git, "pousser", refuse)

    with pytest.raises(pub.ErreurGit, match="poussée refusée"):
        _publier(depot, _ecrire_enrichi(dossiers))

    assert not dossiers[0].exists()
    assert len(_arbres(depot)) == 1
    assert _git(depot, "ls-remote", "origin", "refs/heads/contenu/*") == ""


def test_a_remote_branch_without_our_commit_is_an_error(depot, monkeypatch):
    dossiers: list[Path] = []
    monkeypatch.setattr(pub.Git, "pousser", lambda self, branche: None)

    with pytest.raises(pub.ErreurGit, match="ne porte pas le commit attendu"):
        _publier(depot, _ecrire_enrichi(dossiers))

    assert not dossiers[0].exists()


def test_a_failure_while_writing_also_removes_the_folder(depot):
    dossiers: list[Path] = []

    def ecrire(dossier: Path) -> None:
        dossiers.append(dossier)
        raise RuntimeError("passe en panne")

    with pytest.raises(RuntimeError, match="passe en panne"):
        _publier(depot, ecrire)

    assert not dossiers[0].exists()
    assert len(_arbres(depot)) == 1


def test_a_taken_name_gives_a_numbered_one_and_never_forces(depot):
    premiere = _publier(depot)
    deuxieme = _publier(depot)
    troisieme = _publier(depot)

    assert [premiere.nom, deuxieme.nom, troisieme.nom] == [
        "contenu/sorties-2026-11-27", "contenu/sorties-2026-11-27-2",
        "contenu/sorties-2026-11-27-3"]
    assert bdc.branche_distante_presente(depot, premiere.nom)
    assert not bdc.branche_distante_presente(depot, "contenu/sorties-2026-11-27-4")


def test_nothing_to_commit_pushes_nothing(depot):
    def ecrire(dossier: Path) -> None:
        (dossier / "reco.json").write_text('{"liens": []}\n', encoding="utf-8")

    assert _publier(depot, ecrire) is None
    assert _git(depot, "ls-remote", "origin", "refs/heads/contenu/*") == ""
    assert len(_arbres(depot)) == 1


def test_a_commit_is_an_ancestor_of_origin_main_only_once_merged(depot):
    resultat = _publier(depot)
    assert not bdc.est_ancetre_de_origin_main(depot, resultat.sha)

    _git(depot, "fetch", "origin", resultat.nom)
    _git(depot, "push", "origin", f"{resultat.sha}:refs/heads/main")
    _git(depot, "fetch", "origin", "main")

    assert bdc.est_ancetre_de_origin_main(depot, resultat.sha)


def test_an_unknown_commit_is_not_an_ancestor(depot):
    assert not bdc.est_ancetre_de_origin_main(depot, "0" * 40)


def test_without_a_token_the_result_carries_the_comparison_link(depot):
    resultat = _publier(depot)

    assert not resultat.pr_ouverte
    assert resultat.lien == f"branche {resultat.nom}"  # origine locale : pas GitHub


def test_with_a_token_the_pull_request_is_opened(depot, monkeypatch):
    monkeypatch.setattr(pub.Git, "url_distante", lambda self: "git@github.com:o/d.git")
    appels = []

    def poster(url, jeton, charge):
        appels.append((url, jeton, charge))
        return {"html_url": "https://github.com/o/d/pull/7"}

    resultat = _publier(depot, jeton="jeton-essai", poster=poster)

    assert resultat.pr_ouverte
    assert resultat.lien == "https://github.com/o/d/pull/7"
    assert appels[0][0] == "https://api.github.com/repos/o/d/pulls"
    assert appels[0][2]["head"] == resultat.nom
    assert appels[0][2]["title"] == "contenu: un lien de plus"
    assert appels[0][2]["body"] == "Corps."


def test_a_refused_pull_request_falls_back_on_the_comparison_link(depot, monkeypatch):
    monkeypatch.setattr(pub.Git, "url_distante", lambda self: "git@github.com:o/d.git")
    def poster(*_a, **_k):
        raise OSError("réseau coupé")

    resultat = _publier(depot, jeton="jeton-essai", poster=poster)

    assert not resultat.pr_ouverte
    assert resultat.lien == pub.lien_comparaison("o", "d", resultat.nom)
    assert "PR non ouverte (OSError)" in resultat.avertissements[0]
