"""
invites_titre.py — les invités d'un épisode, lus dans son titre.

Les invités sont toujours dans le titre (consigne de l'éditeur, 2026-10-09), sous
deux formes :

- l'ancienne, Acast : « avec HAKIM JEMILI », « avec Laurie et Pablo » ;
- celle des vidéos YouTube (saisons 5 et 6) : les noms en tête, puis une phrase —
  « Félix Radu et Carla de Coignac mettent de la poésie partout (Un Bon Moment,
  S6-E04) », « Albert Dupontel, ce grand maître du cinéma (…) ».

Dans la seconde, les noms s'arrêtent au premier mot qui n'en est pas un : un mot
en minuscule (« mettent », « ce », « irremplaçables »), sauf une particule suivie
d'une majuscule (« Carla de Coignac »). L'ancienne heuristique coupait sur une
liste de verbes et laissait passer « Jenny Letellier irremplaçables », ou jetait
« Carla de Coignac mettent de la poésie partout », trop long pour un nom.

Mesuré le 2026-10-09 sur les 40 titres des saisons 5 et 6 dont les invités ont été
relus : voir `tests/test_invites_titre.py`.
"""

from __future__ import annotations

import re

# Mots qui commencent par une majuscule sans être un nom (début de phrase).
_PAS_DES_NOMS = frozenset(
    "le la les l un une des du de ce cette ces episode épisode special spécial "
    "best bonus live hors série extrait qui que quoi comment pourquoi quand "
    "invité invitée invités intervenant inconnu".split())
# Particules d'un nom, seulement suivies d'une majuscule (« Carla de Coignac »).
_PARTICULES = frozenset("de du des d la le von van di da del".split())
_SEPARATEURS = frozenset({"et", "&"})
_MAX_MOTS = 5


def _majuscule(mot: str) -> bool:
    return bool(mot) and mot[0].isalpha() and mot[0].isupper()


def _decouper(segment: str) -> list[str]:
    """Les noms en tête du segment, jusqu'au premier mot qui n'en est pas un."""
    mots = segment.split()
    noms: list[list[str]] = []
    courant: list[str] = []

    def clore() -> None:
        nonlocal courant
        if courant:
            noms.append(courant)
        courant = []

    for i, brut in enumerate(mots):
        mot = brut.rstrip(",;:!?.")
        virgule = brut.endswith(",")
        suivant = mots[i + 1] if i + 1 < len(mots) else ""
        if mot.casefold() in _SEPARATEURS:
            clore()
            continue
        if _majuscule(mot) and not (not courant and mot.casefold() in _PAS_DES_NOMS):
            courant.append(mot)
        elif courant and mot.casefold() in _PARTICULES and _majuscule(suivant):
            courant.append(mot)
        else:
            break
        if virgule or brut != mot:
            clore()
            if brut != mot and not virgule:
                break  # « ! », « ? », « : » : la phrase commence
    clore()
    return [" ".join(n) for n in noms if len(n) <= _MAX_MOTS]


def invites_du_titre(titre: str | None, animateurs: list[str] | tuple[str, ...]) -> list[str]:
    """Les invités nommés dans le titre, animateurs exclus, sans doublon."""
    t = (titre or "").strip()
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t)   # « (Un Bon Moment, S6-E04) » en fin de titre
    t = re.sub(r"\s*\([^)]*\)", "", t)          # « YVICK (MISTER V) et … » : on saute l'aparté
    m = re.search(r"\bavec\b(.+)", t, re.IGNORECASE)
    segment = m.group(1) if m else t
    if m:
        # « avec l'humoriste FADILY CAMARA » : la description précède le nom.
        mots = segment.split()
        while mots and not _majuscule(mots[0].split("'")[-1].split("’")[-1]):
            mots.pop(0)
        if mots and not _majuscule(mots[0]):
            mots[0] = re.split(r"['’]", mots[0])[-1]
        segment = " ".join(mots)
    lettres = [c for mot in segment.split() if mot.casefold() not in _SEPARATEURS
               for c in mot if c.isalpha()]
    if lettres and all(c.isupper() for c in lettres):
        # « avec HAKIM JEMILI », « YVICK et FREDDY GLADIEUX » ; « et » reste en minuscule.
        segment = " ".join(m if m.casefold() in _SEPARATEURS else m.title() for m in segment.split())

    a_ecarter = {a.casefold() for a in animateurs}
    invites: list[str] = []
    vus: set[str] = set()
    for nom in _decouper(segment):
        cle = nom.casefold()
        if cle not in a_ecarter and cle not in vus:
            vus.add(cle)
            invites.append(nom)
    return invites
