"""
branche_de_contenu.py — pousser un commit de contenu sans jamais toucher au clone vivant.

R4 B, 27/11/2026 (PR « sorties annoncées », plan § 3 et remarque 1 de la relecture).

Le clone de venus est celui de l'éditeur : il y valide des recos pendant que la chaîne
tourne, et `tick.sh` y fait `git pull --ff-only`. `publication.py` commite dans ce clone
puis le remet en ordre (reset, suppression de fichiers) ; cela convient à une étape où
l'éditeur a fini. Une relance quotidienne, elle, peut tomber pendant une validation :
elle ne doit ni écrire dans le clone, ni déplacer `HEAD`, ni toucher à l'index.

La séquence tient donc dans un dossier à part :
  1. `git worktree add --detach <tmp> origin/main` ;
  2. l'appelant y écrit ses fichiers (`ecrire(dossier)`), on commite ;
  3. on pousse sur `<base>`, ou `<base>-2`, `-3`… si le nom est pris (jamais de poussée
     forcée) ;
  4. on vérifie la branche distante (famille F11) : sans le commit attendu, c'est une
     erreur ;
  5. on ouvre la PR si l'on a un jeton, sinon on donne le lien de comparaison ;
  6. le dossier temporaire est TOUJOURS supprimé (`worktree remove`, puis `prune`), même
     en cas d'échec. Une poussée ratée ne laisse rien : l'appelant reprend le lendemain.

`ouvrir_pr`, `lien_comparaison`, `depot_github` et `Git` viennent de `publication.py`.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common import log
from publication import ErreurGit, Git, depot_github, lien_comparaison, ouvrir_pr


@dataclass
class BrancheDeContenu:
    """Ce que la poussée a produit, pour le message Matrix et pour l'état de la relance."""

    nom: str
    sha: str
    lien: str = ""
    pr_ouverte: bool = False
    avertissements: list[str] = field(default_factory=list)


def branche_distante_presente(racine: Path, nom: str) -> bool:
    """La branche existe-t-elle sur `origin` ? (`ls-remote`, sans toucher au clone.)"""
    return bool(Git(racine).sha_distant(nom))


def est_ancetre_de_origin_main(racine: Path, sha: str) -> bool:
    """Le commit est-il déjà dans `origin/main` ? Un commit inconnu compte pour non."""
    fini = subprocess.run(["git", "merge-base", "--is-ancestor", sha, "origin/main"],
                          cwd=racine, capture_output=True, check=False)
    return fini.returncode == 0


def _nom_libre(racine: Path, base: str) -> str:
    nom, numero = base, 1
    while branche_distante_presente(racine, nom):
        numero += 1
        nom = f"{base}-{numero}"
    return nom


def publier_branche(racine: Path, base: str, ecrire: Callable[[Path], object], message: str, *,
                    titre: str, corps: str, jeton: str = "",
                    poster: Callable[..., dict[str, Any]] | None = None,
                    ) -> BrancheDeContenu | None:
    """Commite ce que `ecrire(dossier)` change sur `origin/main`, pousse et ouvre la PR.

    Rend `None` s'il n'y a rien à commiter. Lève `ErreurGit` si une commande git échoue
    ou si la branche distante ne porte pas le commit ; l'exception de `ecrire` remonte
    telle quelle. Une fois la poussée faite, une vérification impossible ou une PR qui
    n'ouvre pas ne perdent pas la branche : le résultat porte un avertissement (PR #227,
    tour 1). Dans tous les cas le dossier temporaire a disparu.
    """
    racine = Path(racine)
    parent = Path(tempfile.mkdtemp(prefix="reco-contenu-"))
    arbre = parent / "arbre"
    try:
        Git(racine)._git("worktree", "add", "--detach", str(arbre), "origin/main")
        ecrire(arbre)
        dans_l_arbre = Git(arbre)
        dans_l_arbre._git("add", "-A")
        if not dans_l_arbre.modifications():
            return None
        sha = dans_l_arbre.commiter(message)
        nom = _nom_libre(racine, base)
        dans_l_arbre.pousser(nom)
        # Tour 1 de revue (PR #227) : une fois la branche partie, aucune erreur ne doit en perdre
        # le nom, sinon l'appelant ne note pas la proposition et repousse les mêmes adresses.
        resultat = BrancheDeContenu(nom, sha, lien=f"branche {nom}")
        try:
            distant = Git(racine).sha_distant(nom)
        except ErreurGit as exc:
            log.warning("branche %s poussée, vérification impossible : %s", nom, exc)
            resultat.avertissements.append(f"branche non vérifiée après la poussée ({exc})")
        else:
            if distant != sha:
                raise ErreurGit(f"la branche distante {nom} ne porte pas le commit attendu")
        try:
            _ouvrir_la_pr(racine, resultat, titre, corps, jeton, poster)
        except Exception as exc:  # noqa: BLE001 — la branche est partie : on garde son nom.
            log.warning("PR non ouverte pour %s : %s", nom, exc)
            resultat.avertissements.append(
                f"PR non ouverte ({type(exc).__name__}) : le lien de comparaison reste valable")
        return resultat
    finally:
        Git(racine)._git("worktree", "remove", "--force", str(arbre), verifier=False)
        Git(racine)._git("worktree", "prune", verifier=False)
        shutil.rmtree(parent, ignore_errors=True)


def _ouvrir_la_pr(racine: Path, resultat: BrancheDeContenu, titre: str, corps: str,
                  jeton: str, poster: Callable[..., dict[str, Any]] | None) -> None:
    proprietaire, depot = depot_github(Git(racine).url_distante())
    if not proprietaire:
        return
    resultat.lien = lien_comparaison(proprietaire, depot, resultat.nom)
    if not jeton:
        return
    try:
        adresse = ouvrir_pr(proprietaire, depot, resultat.nom, titre, corps, jeton, poster=poster)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.warning("PR non ouverte pour %s : %s", resultat.nom, exc)
        resultat.avertissements.append(
            f"PR non ouverte ({type(exc).__name__}) : le lien de comparaison reste valable")
        return
    if adresse:
        resultat.lien, resultat.pr_ouverte = adresse, True
