"""
sorties_annoncees.py — relancer chaque jour la recherche de liens d'un album ou d'un livre
dont la sortie était annoncée.

R4 B, 27/11/2026 (PR « sorties annoncées » ; plan `_shared/docs/reco-v1/plans/pr-sorties-annoncees.md`,
§ 3). L'éditeur note `releaseDate` sur une reco dont l'œuvre n'est pas encore sortie. Du jour
de la sortie à J+30, cette étape relance les passes de liens, et propose ce qu'elle trouve par
une PR de contenu : l'éditeur décide en fusionnant.

Ce que cette étape ne fait JAMAIS : écrire dans le clone vivant, y commiter, le remettre en
ordre. Elle lit les recos sur `origin/main` (`git show`), cherche sur une copie, et commite dans
un worktree détaché (`branche_de_contenu.publier_branche`). Une reco modifiée dans le clone est
sautée (sa PR ferait échouer le prochain `pull --ff-only`). Une poussée ratée ne laisse rien : la
reco est reprise le lendemain. Un lien de `linksRejected` ne revient jamais (`fusionner`).
Une PR qui n'attend plus (fusionnée, même par squash, ou refermée) : `sorties_propositions.py`.

Cadence : une fois par jour, au premier passage à partir de 6 h à Paris (repli UTC, à partir de
5 h, sans `tzdata`). Sans `RECO_SORTIES_ANNONCEES=1`, l'étape s'arrête aussitôt. `--apercu`
ignore la cadence et la variable, cherche sur la copie et affiche ; il n'écrit rien (ni état, ni
commit, ni poussée, pas même un `git fetch` : il lit l'`origin/main` déjà récupéré) et n'envoie
aucun message. Les passes retenues sont celles des types servis
(`date_sortie.TYPES_V1`) : musique, boutique, jeux, YouTube Music. Les décisions de l'état et des
messages vivent dans `sorties_plan.py`.

Appel : `python tools/sorties_annoncees.py --notifier matrix` (depuis `tick.sh`, après « publier »).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common
import sorties_plan as sp
from branche_de_contenu import publier_branche
from common import write_json_if_changed
from date_sortie import jour_a_paris
from liens_avant_relecture import _passes_par_defaut, _travailler_sur_copie, _urls, fusionner
from publication import ErreurGit, Git
from sorties_propositions import Lire, propositions_en_attente

log = logging.getLogger("sorties_annoncees")

Notify = Callable[[str], None]
Passe = Callable[[str, set[str]], Any]

VARIABLE = "RECO_SORTIES_ANNONCEES"
#: Passes des types servis en V1 (album, musique, livre, jeu) ; les autres ne trouveraient rien.
PASSES_RETENUES = ("musique", "boutique", "jeux", "YouTube Music")
RECOS_REL = "src/content/recos"


def etat_path() -> Path:
    return common.OUTPUT_DIR / "pipeline" / "sorties-annoncees.json"


def _ouvert(maintenant: datetime) -> bool:
    """6 h passées à Paris ; sans `tzdata`, 5 h passées en UTC (6 h l'hiver, 7 h l'été)."""
    try:
        return maintenant.astimezone(ZoneInfo("Europe/Paris")).hour >= 6
    except ZoneInfoNotFoundError:
        return maintenant.astimezone(UTC).hour >= 5


def _recos_sur_origin(git: Git, source: str) -> tuple[dict[str, tuple[str, dict[str, Any]]], list[str]]:
    """`({clé: (chemin, reco)}, chemins illisibles)` des recos de `origin/main` qui portent une
    `releaseDate`. Un JSON illisible est sauté et rendu à part : il ne fait pas tomber l'étape."""
    sortie = git._git("grep", "-l", "-z", "-e", "releaseDate", "origin/main", "--",
                      f"{RECOS_REL}/{source}", verifier=False)
    recos: dict[str, tuple[str, dict[str, Any]]] = {}
    illisibles = []
    for brut in filter(None, sortie.split("\0")):
        chemin = brut.removeprefix("origin/main:")
        try:
            doc = json.loads(git._git("show", f"origin/main:{chemin}"))
            recos[sp.cle_de(doc)] = (chemin, doc)
        except (ValueError, AttributeError):  # JSON faux, ou pas un objet
            log.error("reco illisible sur origin/main : %s", chemin)
            illisibles.append(chemin)
    return recos, illisibles


def _chercher(source: str, docs: dict[str, dict[str, Any]], passes: Sequence[tuple[str, Passe]],
              etat: dict[str, Any]) -> list[tuple[str, dict[str, Any], list[str]]]:
    """`(clé, reco enrichie, adresses nouvelles)` pour chaque reco qui gagne un lien jamais proposé."""
    copies = _travailler_sur_copie(source, {d["id"]: d for d in docs.values()}, [], passes)
    trouvees = []
    for cle, doc in docs.items():
        fusion = fusionner(copies[doc["id"]], doc, doc)
        if fusion is None:
            continue
        nouvelles = sp.adresses_nouvelles(etat, cle, set(_urls(fusion)) - set(_urls(doc)))
        if nouvelles:
            fusion["links"] = [lien for lien in fusion["links"]
                               if lien["url"] in nouvelles or lien["url"] in _urls(doc)]
            # Un identifiant déjà proposé (PR refusée) ne revient pas avec une autre adresse.
            refuses = sp.identifiants_deja_proposes(etat, cle)
            gardes = {k: v for k, v in _ids_nouveaux(fusion, doc).items() if refuses.get(k) != v}
            fusion["externalIds"] = {**(doc.get("externalIds") or {}), **gardes}
            if not fusion["externalIds"]:
                del fusion["externalIds"]
            trouvees.append((cle, fusion, nouvelles))
    return trouvees


def _ids_nouveaux(fusion: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    """Les `externalIds` que la recherche a ajoutés à la reco d'origine."""
    avant = doc.get("externalIds") or {}
    return {k: v for k, v in (fusion.get("externalIds") or {}).items() if k not in avant}


def _surveiller(passes: Sequence[tuple[str, Passe]], pannes: dict[str, str]) -> list[tuple[str, Passe]]:
    """Même passes, qui notent leur panne avant de la relancer (la copie la journalise et passe)."""
    def envelopper(nom: str, passe: Passe) -> Passe:
        def appel(source: str, ids: set[str]) -> Any:
            try:
                return passe(source, ids)
            except Exception as exc:
                pannes[nom] = f"{type(exc).__name__}: {str(exc)[:160]}"
                raise
        return appel
    return [(nom, envelopper(nom, passe)) for nom, passe in passes]




def _envoyer(notify: Notify) -> Callable[[str], bool]:
    """Un message Matrix qui échoue ne fait pas échouer l'étape : on le journalise, et on dit non."""
    def envoyer(texte: str) -> bool:
        try:
            notify(texte)
        except Exception as exc:  # noqa: BLE001 — l'état doit s'écrire malgré Matrix.
            log.error("message non envoyé (%s) : %s", type(exc).__name__, texte[:80])
            return False
        return True
    return envoyer


def relancer(racine: Path, *, source: str = "un-bon-moment", notify: Notify, chemin_etat: Path,
             env: Mapping[str, str] = os.environ, apercu: bool = False,
             maintenant: Callable[[], datetime] = lambda: datetime.now(UTC),
             passes: Sequence[tuple[str, Passe]] | None = None,
             publier: Callable[..., Any] = publier_branche,
             poster: Callable[..., dict[str, Any]] | None = None,
             lire: Lire | None = None, afficher: Notify = print) -> int:
    """Le passage du jour. Rend 0, ou 1 si l'état, git ou la publication a échoué."""
    if not apercu and env.get(VARIABLE) != "1":
        log.info("étape inactive (%s absent)", VARIABLE)
        return 0
    instant = maintenant()
    if not apercu and not _ouvert(instant):
        return 0
    jour = jour_a_paris(instant)
    try:
        etat = sp.lire_etat(chemin_etat)
    except sp.EtatIllisible as exc:  # F22 : on n'écrase rien
        log.error("état illisible, étape arrêtée : %s", exc)
        return 1
    if not apercu and sp.jour_deja_traite(etat, jour):
        return 0
    envoyer = (lambda _texte: False) if apercu else _envoyer(notify)
    git = Git(racine)
    try:
        if not apercu:  # « n'écrit rien » : l'aperçu lit l'origin/main de la dernière récupération
            git._git("fetch", "origin")
        recos, illisibles = _recos_sur_origin(git, source)
        # Pas `git.modifications()` : `_git` retire l'espace de tête de « ␣M chemin » et fausse le premier chemin.
        changees = set(git._git("diff", "--name-only", "-z", "HEAD").split("\0"))
        en_attente = propositions_en_attente(racine, git, etat, recos, jour,
                                             jeton=env.get("RECO_GITHUB_TOKEN", ""), lire=lire)
    except ErreurGit as exc:  # le jour n'est pas noté : on réessaie au passage suivant
        return _fin(apercu, chemin_etat, _panne(etat, "git", str(exc), envoyer), 1)
    etat = sp.effacer_erreur(sp.noter_jour(etat, jour), "git")
    etat = _signaler_illisibles(etat, illisibles, envoyer)
    modifiees = {cle for cle, (chemin, _) in recos.items() if chemin in changees}
    docs = [doc for _, doc in recos.values()]
    plan = sp.plan_du_jour(docs, jour, etat, sur_origin=set(recos), modifiees=modifiees,
                           en_attente=en_attente)
    etat = sp.noter_relance(etat, (sp.cle_de(d) for d in plan.a_relancer),
                            {sp.cle_de(d): _urls(d) for d in plan.a_relancer})
    for doc in plan.modifiees:
        if envoyer(sp.message_modifiee(doc)):
            etat = sp.noter_signal(etat, "sautee", sp.cle_de(doc))
    for doc in sp.sabliers(docs, jour, etat):
        if envoyer(sp.message_sablier(doc)):
            etat = sp.noter_signal(etat, "sablier", sp.cle_de(doc))
    for cle, texte in sp.annonces_en_attente(etat).items():  # un message 🗓️ qui n'était pas parti
        if envoyer(texte):
            etat = sp.noter_annonce_envoyee(etat, cle)
    if passes is None:
        passes = [p for p in _passes_par_defaut() if p[0] in PASSES_RETENUES]
    pannes: dict[str, str] = {}
    trouvees = _chercher(source, {sp.cle_de(d): d for d in plan.a_relancer},
                         _surveiller(passes, pannes), etat) if plan.a_relancer else []
    for nom, _ in passes if plan.a_relancer else ():  # sans passe tournée, une panne n'est ni neuve ni réparée
        if nom in pannes:
            etat = _panne(etat, f"passe {nom}", pannes[nom], envoyer)
        else:
            etat = sp.effacer_erreur(etat, f"passe {nom}")
    if apercu:
        for cle, _fusion, nouvelles in trouvees:
            afficher(f"{cle} : {', '.join(nouvelles)}")
        afficher(f"{len(plan.a_relancer)} reco(s) cherchée(s), {len(trouvees)} avec des liens nouveaux.")
        return 0
    code = 0
    if trouvees:
        etat, code = _proposer(racine, jour, trouvees, recos, etat, envoyer, publier, poster, env)
    return _fin(apercu, chemin_etat, etat, code)


def _panne(etat: dict[str, Any], cle: str, message: str,
           envoyer: Callable[[str], bool]) -> dict[str, Any]:
    """Note la panne et la signale une seule fois par clé : un message qui n'est pas parti ne la
    marque pas signalée, le passage suivant le renvoie."""
    neuf, premiere = sp.noter_erreur(etat, cle, message)
    if not premiere or envoyer(sp.message_panne(cle, message)):
        return neuf
    return etat


def _signaler_illisibles(etat: dict[str, Any], illisibles: list[str],
                         envoyer: Callable[[str], bool]) -> dict[str, Any]:
    """Une reco JSON illisible sur origin/main est signalée une fois, jusqu'à ce qu'elle se relise."""
    for chemin in illisibles:
        etat = _panne(etat, f"reco {chemin}", "JSON illisible sur origin/main, reco sautée", envoyer)
    for cle in [c for c in etat["erreurs"] if c.startswith("reco ") and c[5:] not in illisibles]:
        etat = sp.effacer_erreur(etat, cle)
    return etat


def _fin(apercu: bool, chemin: Path, etat: dict[str, Any], code: int) -> int:
    if not apercu:
        sp.ecrire_etat(chemin, etat)
    return code


def _proposer(racine: Path, jour: date, trouvees: list[tuple[str, dict[str, Any], list[str]]],
              recos: dict[str, tuple[str, dict[str, Any]]], etat: dict[str, Any],
              envoyer: Callable[[str], bool], publier: Callable[..., Any],
              poster: Callable[..., dict[str, Any]] | None,
              env: Mapping[str, str]) -> tuple[dict[str, Any], int]:
    """Pousse la branche de contenu, note les propositions, puis annonce chaque trouvaille."""
    def ecrire(dossier: Path) -> None:
        for cle, fusion, _ in trouvees:
            write_json_if_changed(dossier / recos[cle][0], fusion)

    titres = [recos[cle][1]["title"] for cle, _, _ in trouvees]
    resume = f"liens trouvés après la sortie annoncée de {', '.join(titres)}"
    lignes = [f"- « {recos[cle][1]['title']} » : {', '.join(adr)}" for cle, _, adr in trouvees]
    corps = ("Liens trouvés par la relance des sorties annoncées (R4 B, 27/11/2026) :\n"
             + "\n".join(lignes) + "\n\nLa PR ne change que les recos. À relire avant de fusionner.")
    try:
        resultat = publier(racine, f"contenu/sorties-{jour.isoformat()}", ecrire, f"contenu: {resume}",
                           titre=f"contenu: {resume}", corps=corps,
                           jeton=env.get("RECO_GITHUB_TOKEN", ""), poster=poster)
    except Exception as exc:  # noqa: BLE001 — rien n'est parti : reprise demain.
        log.error("publication de la branche de contenu impossible : %s", exc)
        return _panne(etat, "publication", f"{type(exc).__name__}: {str(exc)[:160]}", envoyer), 1
    etat = sp.effacer_erreur(etat, "publication")
    if resultat is None:
        return etat, 0
    annonces = {}
    for cle, fusion, adresses in trouvees:
        labels = [lien.get("label") or lien["url"] for lien in fusion["links"] if lien["url"] in adresses]
        annonces[cle] = "\n".join([sp.message_trouvaille(recos[cle][1], labels, resultat.lien),
                                   *resultat.avertissements])
    for cle, fusion, adresses in trouvees:  # d'abord l'état (avec l'annonce à retenter), ensuite Matrix
        etat = sp.noter_proposition(etat, cle, resultat.nom, resultat.sha, adresses,
                                    _ids_nouveaux(fusion, recos[cle][1]), annonces[cle])
    for cle in annonces:
        if envoyer(annonces[cle]):
            etat = sp.noter_annonce_envoyee(etat, cle)
    return etat, 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Relance la recherche de liens des recos dont la sortie était annoncée.")
    parser.add_argument("--source", default="un-bon-moment")
    parser.add_argument("--notifier", choices=("matrix", "none"), default="none")
    parser.add_argument("--apercu", action="store_true",
                        help="cherche sur une copie et affiche : ni commit, ni poussée, ni message, ni état")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from traiter_nouveaux_episodes import build_notify
    return relancer(common.PROJECT_ROOT, source=args.source, notify=build_notify(args.notifier),
                    chemin_etat=etat_path(), apercu=args.apercu)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
