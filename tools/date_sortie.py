"""Date de sortie annoncée d'une reco : validateur, fenêtre de relance, types servis.

Décision « R4 B », 27/11/2026 : l'éditeur note sur la reco la date de sortie annoncée
d'une œuvre pas encore publiée (`releaseDate`, `AAAA-MM-JJ`), et la chaîne relance la
recherche de liens chaque jour, du jour de la sortie à J+30. Plan :
`_shared/docs/reco-v1/plans/pr-sorties-annoncees.md`, § 2.

C'est LE validateur Python de ce champ (le schéma Zod de `src/content.config.ts` est
son pendant côté site). Pur : aucune horloge, aucun réseau, aucun disque. « Aujourd'hui »
est toujours un paramètre, pour qu'un test fixe le jour.

À noter pour la suite :
- **Jamais de date inventée** (`DATA_SCHEMA.md`, règle 4) : seul l'éditeur la remplit.
- **Types servis en V1** : album, musique, livre, jeu, ceux que servent
  `music_links_matching` et `boutique_matching` (vérifié le 27/11 ; un test garde la
  dérive). Les films, séries et artistes en sont exclus.
- **Le jour est celui de Paris.** Si `tzdata` manque (poste Windows, image sans paquet),
  on retombe sur l'heure UTC, documenté dans le plan (remarque 10 de la relecture).
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

#: Types dont la recherche de liens est relancée (V1). Doit rester inclus dans ce que
#: servent `music_links_matching.SUPPORTED_TYPES` et `boutique_matching.TYPES_SERVIS`.
TYPES_V1: tuple[str, ...] = ("album", "musique", "livre", "jeu")

#: La relance dure du jour de la sortie à J+30 inclus.
FENETRE_JOURS = 30

#: Une date plus de 3 ans après aujourd'hui est une faute de frappe, pas une annonce.
HORIZON_ANS = 3

_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}")


class DateSortieInvalide(ValueError):
    """La date de sortie est refusée ; le message est lisible tel quel par l'éditeur."""


def analyser_date_sortie(valeur: object) -> date:
    """Lit `AAAA-MM-JJ` strict, jour de calendrier réel (30 février refusé)."""
    # fullmatch : `$` accepterait un retour à la ligne final.
    if not isinstance(valeur, str) or not _FORMAT.fullmatch(valeur):
        raise DateSortieInvalide("format attendu : AAAA-MM-JJ")
    try:
        return date(int(valeur[:4]), int(valeur[5:7]), int(valeur[8:]))
    except ValueError:
        raise DateSortieInvalide(f"{valeur} n'existe pas dans le calendrier") from None


def _plus_trois_ans(jour: date) -> date:
    try:
        return jour.replace(year=jour.year + HORIZON_ANS)
    except ValueError:  # 29 février vers une année non bissextile
        return jour.replace(year=jour.year + HORIZON_ANS, day=28)


def valider_date_sortie(valeur: object, aujourdhui: date) -> str:
    """Rend la date normalisée, ou lève `DateSortieInvalide`.

    Une date passée est acceptée (un album sorti hier garde sa date) ; une date à plus
    de 3 ans d'`aujourdhui` est refusée.
    """
    jour = analyser_date_sortie(valeur)
    if jour > _plus_trois_ans(aujourdhui):
        raise DateSortieInvalide(f"{valeur} est à plus de {HORIZON_ANS} ans")
    return jour.isoformat()


def dans_la_fenetre(sortie: date, aujourdhui: date) -> bool:
    """Vrai du jour de la sortie (J) à J+30 inclus ; faux la veille et à J+31."""
    return 0 <= (aujourdhui - sortie).days <= FENETRE_JOURS


def fenetre_fermee(sortie: date, aujourdhui: date) -> bool:
    """Vrai dès J+31 : la relance est finie, le signal « sans résultat » peut partir."""
    return (aujourdhui - sortie).days > FENETRE_JOURS


def type_servi(types: Iterable[str]) -> bool:
    """Vrai si l'un des types de la reco est servi en V1."""
    return any(t in TYPES_V1 for t in types)


def jour_a_paris(maintenant: datetime) -> date:
    """Le jour civil de Paris à cet instant ; repli sur UTC sans `tzdata`."""
    if maintenant.tzinfo is None:
        raise ValueError("l'heure doit porter un fuseau")
    try:
        fuseau = ZoneInfo("Europe/Paris")
    except ZoneInfoNotFoundError:
        fuseau = UTC
    return maintenant.astimezone(fuseau).date()
