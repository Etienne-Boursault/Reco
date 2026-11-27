"""review_edit_sortie.py — saisie de la date de sortie annoncée dans « Corriger ».

Décision « R4 B », 27/11/2026 (plan `_shared/docs/reco-v1/plans/pr-sorties-annoncees.md`,
§ 2 et remarques 3, 4 et 11 de la relecture) : l'éditeur seul note `releaseDate` sur une
reco, avant sa publication. La validation est celle de `date_sortie` ; ce module n'y
ajoute que les deux gardes propres à la saisie :
- le fichier ne doit pas être suivi par git : après la publication, le clone de la chaîne
  ne doit pas être modifié à la main, la date passe par une PR de contenu ;
- le type doit être servi en V1 (album, musique, livre, jeu).

Une date refusée n'empêche jamais d'enregistrer le reste de la reco : on rend un message
« date ignorée : … » que la route affiche.
"""
from __future__ import annotations

import html
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from common import log
from date_sortie import (
    TYPES_V1,
    DateSortieInvalide,
    jour_a_paris,
    type_servi,
    valider_date_sortie,
)

_APRES_PUBLICATION = "après publication : PR de contenu"
_TYPES_SERVIS = ", ".join(TYPES_V1)


def fichier_suivi_par_git(chemin: Path) -> bool:
    """Vrai si git suit ce fichier (reco déjà publiée).

    Hors de tout dépôt, rien n'est publié : non suivi. Si git est introuvable, on ne sait
    pas : on répond « suivi » pour ne pas proposer d'écrire sur un fichier publié.
    """
    try:
        fini = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", chemin.name],
            cwd=chemin.parent, capture_output=True, check=False,
        )
    except OSError as exc:
        log.warning("git introuvable, %s compté comme suivi : %s", chemin.name, exc)
        return True
    return fini.returncode == 0


def appliquer_sortie(reco: dict, data: dict, chemin: Path,
                     maintenant: datetime | None = None) -> str | None:
    """Pose, retire ou refuse `releaseDate` sur `reco` ; rend le message de refus ou None.

    `maintenant` est l'horloge injectée (aware) ; sans elle, l'instant présent. Le jour
    retenu est celui de Paris. `year` est posé à l'année de la date s'il manque.
    """
    if "releaseDate" not in data:
        return None
    if fichier_suivi_par_git(chemin):
        return "date ignorée : après publication, passer par une PR de contenu"
    valeur = (data["releaseDate"] or [""])[0].strip()
    if not valeur:
        reco.pop("releaseDate", None)
        return None
    if not type_servi(reco.get("types") or []):
        return f"date ignorée : seuls {_TYPES_SERVIS} sont servis"
    aujourdhui = jour_a_paris(maintenant or datetime.now(timezone.utc))
    try:
        reco["releaseDate"] = valider_date_sortie(valeur, aujourdhui)
    except DateSortieInvalide as exc:
        return f"date ignorée : {exc}"
    if reco.get("year") is None:
        reco["year"] = int(reco["releaseDate"][:4])
    return None


def _chemin_de_reco(r: dict) -> Path | None:
    """Fichier de la reco, par le cache du serveur (import tardif : pas de cycle)."""
    from review_handler_base import _reco_path
    return _reco_path(r.get("sourceId", ""), r.get("id", ""))


def champ_sortie(r: dict) -> str:
    """Bloc du formulaire : le champ, ou la mention « après publication », ou rien.

    Rien pour un type hors de la V1 ou une reco dont le fichier est introuvable.
    """
    if not type_servi(r.get("types") or []):
        return ""
    chemin = _chemin_de_reco(r)
    if chemin is None:
        return ""
    valeur = html.escape(r.get("releaseDate", "") or "")
    if fichier_suivi_par_git(chemin):
        return (f'<p class="ext"><span>Sortie annoncée le {valeur or "—"} '
                f'<em>({_APRES_PUBLICATION})</em></span></p>')
    return (
        '<label class="ext"><span>Sortie annoncée le '
        f'<em>(albums, musique, livres et jeux seulement)</em></span>'
        f'<input type="text" name="releaseDate" value="{valeur}" '
        'placeholder="AAAA-MM-JJ" inputmode="numeric"></label>'
    )
