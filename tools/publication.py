"""
publication.py — pousser sur GitHub un épisode relu, sans personne devant.

Jusqu'ici la publication était manuelle : copier les fichiers de venus vers le
poste de l'éditeur, commiter, ouvrir la PR. Ce module fait les trois premiers
gestes depuis venus, avec une clé de dépôt en écriture.

CE QUI REND CETTE ÉTAPE DÉLICATE
--------------------------------
Le clone de venus est sur `main`, et `tick.sh` fait `git pull --ff-only` à chaque
passage. Un commit laissé sur `main` en local ferait échouer ce pull dès que la
PR est fusionnée, et la chaîne travaillerait sur une copie divergente. La séquence
est donc : commiter, pousser sur une BRANCHE, vérifier que la poussée a réussi,
puis ramener `main` sur `origin/main` et retirer les copies locales — que la
fusion de la PR ramènera, suivies par git.

`git reset --hard` est proscrit : il emporterait une validation en cours faite par
l'humain sur un autre épisode. On remet donc la référence (`reset --mixed`) puis on
supprime NOMMÉMENT les fichiers publiés. Et on refuse de travailler si le clone
porte la moindre modification hors du périmètre de l'épisode.

Conséquence assumée : entre la poussée et la fusion, l'épisode disparaît de la page
de validation. Sa relecture est terminée à ce stade, et le message le dit.

Une clé de dépôt permet de POUSSER, pas d'ouvrir une PR (il y faut l'API). Avec
`RECO_GITHUB_TOKEN`, la PR est ouverte ; sans lui, le message porte le lien de
comparaison, qui ouvre le formulaire prérempli.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import common
from common import log, read_json, recos_dir_for, slugify

#: Une branche par épisode, préfixée comme les branches de contenu faites à la main.
PREFIXE_BRANCHE = "contenu/"
API_GITHUB = "https://api.github.com"
DELAI_API = 20


@dataclass
class Publication:
    """Ce qu'un épisode a produit, pour le message et pour les tests."""

    guid: str
    branche: str = ""
    sha: str = ""
    lien: str = ""
    pr_ouverte: bool = False
    fichiers: int = 0
    deja_publie: bool = False
    refus: str = ""
    avertissements: list[str] = field(default_factory=list)

    @property
    def refuse(self) -> bool:
        return bool(self.refus)


class ErreurGit(RuntimeError):
    """Une commande git a échoué ; le message porte sa sortie d'erreur."""


class Git:
    """Les quelques commandes git dont la publication a besoin, et rien de plus.

    Aucune n'utilise de shell. Les tests s'en servent tel quel sur un dépôt
    temporaire avec un `origin` nu : c'est le vrai git qui est éprouvé, pas un
    double qui dirait oui à tout.
    """

    def __init__(self, racine: Path) -> None:
        self.racine = Path(racine)

    def _git(self, *args: str, verifier: bool = True) -> str:
        fini = subprocess.run(["git", *args], cwd=self.racine, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", check=False)
        if verifier and fini.returncode != 0:
            raise ErreurGit(f"git {' '.join(args)} → {fini.returncode} : "
                            f"{(fini.stderr or fini.stdout).strip()[:300]}")
        return (fini.stdout or "").strip()

    def modifications(self) -> list[str]:
        """Chemins que git voit modifiés, ajoutés ou non suivis (format porcelain).

        `-uall` est indispensable : sans lui, git annonce un DOSSIER entier quand
        il est neuf (« ?? src/content/ ») au lieu des fichiers, et le périmètre
        de l'épisode ne correspond alors à rien.
        """
        lignes = self._git("status", "--porcelain", "-z", "-uall").split("\0")
        chemins = []
        for ligne in lignes:
            if len(ligne) > 3:
                chemins.append(ligne[3:])
        return chemins

    def ajouter(self, chemins: Sequence[str]) -> None:
        self._git("add", "--", *chemins)

    def commiter(self, message: str) -> str:
        self._git("commit", "-m", message)
        return self.tete()

    def tete(self) -> str:
        return self._git("rev-parse", "HEAD")

    def pousser(self, branche: str) -> None:
        self._git("push", "origin", f"HEAD:refs/heads/{branche}")

    def sha_distant(self, branche: str) -> str:
        sortie = self._git("ls-remote", "origin", f"refs/heads/{branche}")
        return sortie.split()[0] if sortie else ""

    def revenir_sur_origin_main(self) -> None:
        """Ramène `main` sur `origin/main` en laissant les fichiers sur le disque.

        `--mixed` et non `--hard` : le second emporterait tout travail local, y
        compris une validation que l'humain serait en train de faire.
        """
        self._git("reset", "--mixed", "origin/main")

    def url_distante(self) -> str:
        return self._git("remote", "get-url", "origin")


def _recos_de(source_id: str, guid: str) -> list[tuple[Path, dict[str, Any]]]:
    dossier = recos_dir_for(source_id)
    if not dossier.is_dir():
        return []
    trouvees = []
    for chemin in sorted(dossier.glob("*.json")):
        reco = read_json(chemin)
        if reco.get("episodeGuid") == guid:
            trouvees.append((chemin, reco))
    return trouvees


def fichiers_episode(source_id: str, guid: str, chemin_episode: Path) -> list[Path]:
    """Les fichiers qu'un épisode publie : lui, ses recos, ses mentions, ses œuvres.

    Les œuvres sont atteintes par les mentions (`itemId`) et non par un plan de
    publication : au moment de publier, la conversion a déjà eu lieu, peut-être
    lors d'un passage précédent. Une œuvre réutilisée d'un autre épisode est déjà
    suivie par git : elle sera simplement sans changement à ajouter.
    """
    fichiers = [chemin_episode]
    mentions_dir = common.CONTENT_DIR / "mentions" / source_id
    items_dir = common.CONTENT_DIR / "items" / source_id
    for chemin, reco in _recos_de(source_id, guid):
        fichiers.append(chemin)
        mention = mentions_dir / f"{reco.get('id')}.json"
        if not mention.exists():
            continue
        fichiers.append(mention)
        item = read_json(mention).get("itemId")
        if item:
            oeuvre = items_dir / f"{item}.json"
            if oeuvre.exists():
                fichiers.append(oeuvre)
    return sorted(set(fichiers))


def _relatifs(racine: Path, fichiers: Sequence[Path]) -> list[str]:
    """Chemins relatifs à la racine du dépôt, avec des « / » comme git les écrit."""
    relatifs = []
    for fichier in fichiers:
        relatifs.append(Path(fichier).resolve().relative_to(Path(racine).resolve()).as_posix())
    return sorted(set(relatifs))


def depot_github(url: str) -> tuple[str, str]:
    """(propriétaire, dépôt) depuis une URL SSH ou HTTPS. Vide si ce n'est pas GitHub."""
    nu = url.strip().removesuffix(".git")
    for marque in ("github.com:", "github.com/"):
        if marque in nu:
            morceaux = nu.split(marque, 1)[1].strip("/").split("/")
            if len(morceaux) >= 2:
                return morceaux[0], morceaux[1]
    return "", ""


def lien_comparaison(proprietaire: str, depot: str, branche: str) -> str:
    return (f"https://github.com/{proprietaire}/{depot}/compare/main...{branche}"
            "?expand=1")


def ouvrir_pr(proprietaire: str, depot: str, branche: str, titre: str, corps: str,
              jeton: str, *, poster: Callable[..., dict[str, Any]] | None = None) -> str:
    """Ouvre la PR par l'API et rend son adresse. Lève si l'API refuse."""
    poster = poster or _poster_api
    reponse = poster(f"{API_GITHUB}/repos/{proprietaire}/{depot}/pulls", jeton,
                     {"title": titre, "head": branche, "base": "main", "body": corps})
    return str(reponse.get("html_url") or "")


def _poster_api(url: str, jeton: str, charge: dict[str, Any]) -> dict[str, Any]:
    requete = urllib.request.Request(  # noqa: S310 — URL construite ici, schéma https
        url, data=json.dumps(charge).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {jeton}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json",
                 "User-Agent": "reco-chaine-venus"})
    with urllib.request.urlopen(requete, timeout=DELAI_API) as reponse:  # noqa: S310
        return json.loads(reponse.read().decode("utf-8"))


def _corps_pr(titre: str, nb_recos: int) -> str:
    return (f"Publication automatique depuis venus, après relecture de « {titre} ».\n\n"
            f"{nb_recos} reco(s) relue(s), avec leurs œuvres et leurs mentions.\n\n"
            "La chaîne a posé ce qu'elle savait poser ; le reste à compléter à la main "
            "a été envoyé sur Matrix au moment de la finalisation.\n\n"
            "Fusionner cette PR met le site à jour.")


def publier_episode(source_id: str, guid: str, titre: str, chemin_episode: Path, *,
                    racine: Path | None = None, git: Git | None = None,
                    jeton: str = "", poster: Callable[..., dict[str, Any]] | None = None,
                    ) -> Publication:
    """Commite, pousse sur une branche, vérifie, puis nettoie le clone.

    Refuse plutôt que de forcer : une reco encore en brouillon, ou une
    modification du clone étrangère à l'épisode, arrête tout.
    """
    resultat = Publication(guid)
    racine = Path(racine) if racine is not None else common.PROJECT_ROOT
    git = git or Git(racine)

    recos = _recos_de(source_id, guid)
    if not recos:
        resultat.refus = "aucune reco pour cet épisode"
        return resultat
    brouillons = [r.get("id") for _c, r in recos if r.get("status", "draft") == "draft"]
    if brouillons:
        resultat.refus = f"{len(brouillons)} reco(s) encore en brouillon"
        return resultat

    fichiers = _relatifs(racine, fichiers_episode(source_id, guid, chemin_episode))
    resultat.fichiers = len(fichiers)
    perimetre = set(fichiers)
    etrangers = [c for c in git.modifications() if c not in perimetre]
    if etrangers:
        resultat.refus = ("le clone porte des modifications étrangères à l'épisode : "
                          + ", ".join(sorted(etrangers)[:5]))
        return resultat

    a_publier = [c for c in git.modifications() if c in perimetre]
    if not a_publier:
        # Rien de neuf sous git : l'épisode est déjà sur `main` (ou déjà poussé).
        resultat.deja_publie = True
        return resultat

    branche = f"{PREFIXE_BRANCHE}{slugify(guid)}"
    resultat.branche = branche
    git.ajouter(a_publier)
    resultat.sha = git.commiter(
        f"contenu: publier {_sans_accents(titre)}\n\n"
        f"Pousse par la chaine de venus apres relecture. "
        f"{len(recos)} reco(s), {len(a_publier)} fichier(s).")
    git.pousser(branche)
    if git.sha_distant(branche) != resultat.sha:
        resultat.refus = ("la branche distante ne porte pas le commit attendu ; "
                          "rien n'a été retiré du clone")
        return resultat

    proprietaire, depot = depot_github(git.url_distante())
    resultat.lien = (lien_comparaison(proprietaire, depot, branche)
                     if proprietaire else f"branche {branche}")
    if jeton and proprietaire:
        try:
            adresse = ouvrir_pr(proprietaire, depot, branche,
                                f"contenu: publier {titre}",
                                _corps_pr(titre, len(recos)), jeton, poster=poster)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            resultat.avertissements.append(
                f"PR non ouverte ({type(exc).__name__}) : le lien de comparaison reste valable")
        else:
            if adresse:
                resultat.lien, resultat.pr_ouverte = adresse, True

    _nettoyer(git, racine, a_publier, resultat)
    return resultat


def _nettoyer(git: Git, racine: Path, publies: Sequence[str],
              resultat: Publication) -> None:
    """Ramène `main` sur `origin/main` et retire les copies locales des fichiers poussés.

    Appelé UNIQUEMENT après une poussée vérifiée : le contenu est sur GitHub, et
    la fusion de la PR le ramènera suivi par git. Un échec ici ne remet pas la
    publication en cause, il se signale.
    """
    try:
        git.revenir_sur_origin_main()
        for relatif in publies:
            (Path(racine) / relatif).unlink(missing_ok=True)
    except (ErreurGit, OSError) as exc:
        resultat.avertissements.append(
            f"clone non nettoyé ({type(exc).__name__}) : le prochain « git pull » peut échouer")


def _sans_accents(texte: str) -> str:
    """Messages de commit en ASCII, comme le reste de l'historique du dépôt."""
    import unicodedata
    decompose = unicodedata.normalize("NFD", texte)
    return "".join(c for c in decompose if unicodedata.category(c) != "Mn")


def message(titre: str, resultat: Publication) -> str:
    """Ce que l'éditeur reçoit sur Matrix."""
    quoi = "PR ouverte" if resultat.pr_ouverte else "à ouvrir en deux clics"
    avertissement = ("Cet épisode n'apparaît plus sur la page de validation jusqu'à la "
                     "fusion : sa relecture est terminée.")
    lignes = [f"📦 {titre} : publié sur GitHub ({resultat.fichiers} fichier(s)), {quoi}.",
              resultat.lien, avertissement]
    lignes += [f"⚠️ {a}" for a in resultat.avertissements]
    return "\n".join(lignes)


def publier_les_episodes(source_id: str, pending: Sequence[tuple[Path, dict[str, Any]]],
                         notify: Callable[[str], None], state: dict[str, Any], *,
                         rapporter: Callable[..., None], oublier: Callable[..., None],
                         racine: Path | None = None, git: Git | None = None,
                         jeton: str | None = None,
                         poster: Callable[..., dict[str, Any]] | None = None) -> int:
    """Publie les épisodes en attente. Une panne n'emporte ni l'état, ni les suivants."""
    if jeton is None:
        jeton = os.environ.get("RECO_GITHUB_TOKEN", "")
    for chemin, episode in pending:
        guid = episode["guid"]
        titre = episode.get("title") or guid
        cle = f"publication:{guid}"
        try:
            resultat = publier_episode(source_id, guid, titre, chemin, racine=racine,
                                       git=git, jeton=jeton, poster=poster)
        except Exception as exc:  # noqa: BLE001 — l'épisode suivant doit passer quand même.
            rapporter(state, cle, f"⚠️ Publication impossible pour « {titre} » : {exc}", notify)
            continue
        if resultat.refuse:
            rapporter(state, cle, f"⚠️ Publication refusée pour « {titre} » : {resultat.refus}",
                      notify)
            continue
        oublier(state, cle)
        state.setdefault("published", []).append(guid)
        if resultat.deja_publie:
            log.info("%s : rien à pousser, déjà sur main.", guid)
            continue
        notify(message(titre, resultat))
    return 0
