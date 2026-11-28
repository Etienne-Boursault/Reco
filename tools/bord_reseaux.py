"""bord_reseaux.py — les cases des réseaux du tableau de bord, cochées à la main.

Décision : tableau de bord, R2 B du 27/11/2026 et TB-1 C du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 4, relecture R3).

Six cases par épisode (Instagram, Threads, Spotify, Deezer, SensCritique,
commentaire YouTube), gardées dans `<RECO_BORD_DIR>/reseaux.json` (par défaut
`tools/output/bord/`, hors de Git), sous la forme `{guid: {réseau: date}}`.

POURQUOI LES 3 DERNIERS DE `published`, ET PAS LES ÉPISODES DU CLONE
-------------------------------------------------------------------
Après la poussée, `publication._nettoyer` retire le fichier de l'épisode du
clone tant que sa PR n'est pas fusionnée : c'est justement la semaine où l'on
coche les réseaux. Le guid se valide donc par l'état de la chaîne, et le titre
se lit sur la branche `origin/contenu/<slug>` (`git show`), ou manque.

Un fichier de cases illisible n'est jamais réécrit (F22) : `lire` et `cocher`
lèvent `EtatIllisible`, la page le signale et la case est refusée.

LA FENÊTRE DE PUBLICATION (revue globale du tableau de bord, E1, 28/11/2026)
----------------------------------------------------------------------------
Les cases restent sur les 3 derniers, mais « fusionner la PR » regarde les `N_PUBLICATION` (10)
derniers publiés : venus pousse `contenu/<slug>` sans ouvrir de PR, et un épisode non fusionné
au-delà des 3 derniers n'apparaissait plus nulle part. Plus ancien que la fenêtre, un épisode
absent du clone est compté par `non_verifies` (un épisode revenu dans le clone est fusionné).
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import common
from common import log, slugify
from publication import PREFIXE_BRANCHE

#: La liste fixe, dans l'ordre d'affichage.
RESEAUX = ("instagram", "threads", "spotify", "deezer", "senscritique", "youtube")
LIBELLES = {"instagram": "Instagram", "threads": "Threads", "spotify": "Spotify",
            "deezer": "Deezer", "senscritique": "SensCritique",
            "youtube": "commentaire YouTube"}
N_RECENTS = 3
#: Les derniers publiés dont la PR est vérifiée (revue globale, E1) ; les cases n'en prennent que 3.
N_PUBLICATION = 10
# Le serveur de relecture n'a qu'un fil : un git bloqué ne doit pas le figer.
_DELAI_GIT = 5


class EtatIllisible(Exception):
    """`reseaux.json` existe mais ne se lit pas : on ne l'écrase pas."""


def dossier() -> Path:
    """Le dossier du tableau de bord, résolu à l'appel (les tests le déplacent)."""
    return Path(os.environ.get("RECO_BORD_DIR") or common.OUTPUT_DIR / "bord")


def _chemin() -> Path:
    return dossier() / "reseaux.json"


def lire() -> dict[str, dict[str, str]]:
    """Les cases cochées ; `{}` sans fichier ; `EtatIllisible` s'il est abîmé."""
    chemin = _chemin()
    if not chemin.exists():
        return {}
    try:
        donnees = common.read_json(chemin)
    except (OSError, ValueError) as exc:
        raise EtatIllisible(f"{chemin.name} illisible ({type(exc).__name__})") from exc
    if not (isinstance(donnees, dict) and all(
            isinstance(v, dict) and all(isinstance(d, str) for d in v.values())
            for v in donnees.values())):
        raise EtatIllisible(f"{chemin.name} n'a pas la forme {{guid: {{réseau: date}}}}")
    return donnees


def _publies(state: dict[str, Any] | None) -> list[str]:
    """Tous les guid publiés, du plus récent au plus ancien."""
    return list(dict.fromkeys((state or {}).get("published") or []))[::-1]


def guids_recents(state: dict[str, Any] | None, n: int = N_RECENTS) -> list[str]:
    """Les `n` derniers guid publiés (3 par défaut), du plus récent au plus ancien."""
    return _publies(state)[:n]


def non_verifies(state: dict[str, Any] | None, episodes: dict[str, dict]) -> int:
    """Les publiés plus anciens que la fenêtre de publication et absents du clone (`episodes`).

    Leur PR n'est pas regardée : l'« À faire d'abord » le dit (F23). Un ancien épisode revenu
    dans le clone est fusionné, il ne compte pas.
    """
    return sum(1 for g in _publies(state)[N_PUBLICATION:] if g not in episodes)


def cocher(state: dict[str, Any] | None, guid: str, reseau: str, fait: bool, *,
           maintenant: datetime | None = None) -> dict[str, dict[str, str]]:
    """Pose (`fait`) ou retire une case, puis l'écrit en atomique ; rend le nouvel état.

    `ValueError` pour un réseau hors de la liste ou un guid hors des 3 derniers
    publiés ; `EtatIllisible` si le fichier existant ne se lit pas.
    """
    if reseau not in RESEAUX:
        raise ValueError(f"réseau inconnu : {reseau[:40]!r}")
    if guid not in guids_recents(state):
        raise ValueError(f"épisode hors des {N_RECENTS} derniers publiés : {guid[:60]!r}")
    cases = lire()
    if fait:
        quand = (maintenant or datetime.now(UTC)).isoformat(timespec="seconds")
        cases.setdefault(guid, {}).setdefault(reseau, quand)
    else:
        cases.get(guid, {}).pop(reseau, None)
        if not cases.get(guid, True):
            del cases[guid]
    common.write_json_if_changed(_chemin(), cases)
    return cases


def branche_de(guid: str) -> str:
    """La branche que `publication.py` pousse pour cet épisode : `contenu/<slugify(guid)>`."""
    return f"{PREFIXE_BRANCHE}{slugify(guid)}"


def _episode_sur_la_branche(source_id: str, guid: str) -> dict[str, Any] | None:
    """Le JSON de l'épisode tel que poussé sur `origin/contenu/<slug>`, ou None."""
    slug = slugify(guid)
    racine = Path(common.PROJECT_ROOT)
    try:
        relatif = (common.episodes_dir_for(source_id) / f"{slug}.json").relative_to(racine)
        fini = subprocess.run(
            ["git", "show", f"origin/{PREFIXE_BRANCHE}{slug}:{relatif.as_posix()}"],
            cwd=racine, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_DELAI_GIT, check=False)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        log.warning("bord : titre de %s non lu sur sa branche (%s)", guid, type(exc).__name__)
        return None
    if fini.returncode != 0:
        # Branche fusionnée puis supprimée, ou pas encore rapatriée : le guid suffit.
        return None
    try:
        episode = json.loads(fini.stdout)
    except ValueError:
        log.warning("bord : épisode %s illisible sur sa branche", guid)
        return None
    return episode if isinstance(episode, dict) else None


def episodes_recents(source_id: str, state: dict[str, Any] | None,
                     episodes: dict[str, dict], n: int = N_RECENTS) -> list[dict[str, Any]] | None:
    """Les `n` derniers publiés (3 par défaut) : `{"guid", "fusionne", "episode"}`, ou None sans état.

    `fusionne` : l'épisode est revenu dans le clone (`episodes`, ceux de
    `_load_groups`), donc sa PR est fusionnée. Sinon, `episode` vient de sa
    branche, ou vaut None.
    """
    if state is None:
        return None
    recents = []
    for guid in guids_recents(state, n):
        fusionne = guid in episodes
        episode = episodes[guid] if fusionne else _episode_sur_la_branche(source_id, guid)
        recents.append({"guid": guid, "fusionne": fusionne, "episode": episode})
    return recents
