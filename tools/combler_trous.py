"""
combler_trous.py — retrouve les passages que la transcription longue a perdus.

Sur un épisode entier, faster-whisper peut sauter un passage parlé sans rien
signaler. S6-E01 (2026-09-18) : après 01:16:31, la seule phrase qui nommait le
livre promu (« un livre des scripts de Bref 2 ») manquait ; l'extraction ne
pouvait pas la deviner, la reco a été ratée. Réécoutée seule, la fenêtre redonne
le texte, avec ou sans filtre de silence : c'est la transcription longue.

Repérage : une ligne courte suivie d'un saut d'au moins 9 s jusqu'à la suivante.
Sur S6-E01, 11 candidats : 8 cachaient des phrases perdues (313 mots en tout),
dont celle du livre ; les 3 autres ont été laissés tels quels.

Fusion au mot près, et non par horodatage. Près d'un trou, la transcription
longue décale ses horodatages de plusieurs secondes (mesuré le 2026-09-21) :
remplacer « les lignes de la fenêtre » par la réécoute recopiait du texte déjà
présent d'un côté et en coupait de l'autre. On aligne donc les mots de la
réécoute sur ceux des lignes de la fenêtre, on cale le tout sur des ancres
(plusieurs mots identiques d'affilée), et on n'ajoute que les morceaux absents
entre la première et la dernière ancre. Rien de ce qui existe n'est déplacé ;
les lignes gardent leur horodatage, donc l'ordre.

Les lignes voisines, hors fenêtre, ne sont PAS comparées : une phrase répétée
juste avant (« je suis sur un premier script » / « t'es sur un premier
script ») y attirait l'alignement et faisait perdre des mots — mesuré sur S6-E01.

La réécoute doit reprendre l'essentiel des lignes de la fenêtre, sinon on la
croit hors sujet (musique, hallucination) et on n'y touche pas. On ne cherche
ni avant la première ligne ni après la dernière : aucun saut ne s'y mesure.
"""

from __future__ import annotations

import bisect
import difflib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from common import format_timestamp, log

# Saut minimal entre deux débuts de ligne pour soupçonner un trou (secondes).
SAUT_MIN = 9.0
# Au-delà, une ligne est assez longue pour expliquer le saut à elle seule. Les
# 110 caractères mesurés comptaient l'horodatage « [HH:MM:SS] » (11).
LONGUEUR_MAX_TEXTE = 110 - 11
# Durée minimale réécoutée : celle qui a retrouvé le passage de S6-E01.
FENETRE_MIN = 20.0
# Mots identiques d'affilée pour caler la réécoute sur l'existant.
ANCRE = 3
# Un écart plus court entre les deux versions est une variante, pas un oubli.
AJOUT_MIN = 3
# Part des mots de la fenêtre que la réécoute doit reprendre pour être crue.
RECOUVREMENT_MIN = 0.6

Entree = tuple[float, str]
# Reçoit `clip_timestamps` ([début, fin] ou [début] jusqu'au bout de l'audio),
# rend les segments (début absolu en secondes, texte).
Reecoute = Callable[[list[float]], Sequence[Entree]]


@dataclass
class Bilan:
    candidats: int = 0
    combles: int = 0
    mots_ajoutes: int = 0


def candidats(entrees: Sequence[Entree]) -> list[int]:
    """Indices des lignes suivies d'un saut suspect."""
    return [
        i for i in range(len(entrees) - 1)
        if entrees[i + 1][0] - entrees[i][0] >= SAUT_MIN
        and len(entrees[i][1]) < LONGUEUR_MAX_TEXTE
    ]


def fenetres(entrees: Sequence[Entree],
             suspects: Sequence[int]) -> list[tuple[float, float | None]]:
    """Fenêtres [début, fin) à réécouter, bords posés sur des débuts de lignes ;
    fin à None : jusqu'au bout de l'audio. Les fenêtres qui se chevauchent
    sont fusionnées."""
    plages: list[tuple[int, int]] = []
    for i in suspects:
        limite = entrees[i][0] + FENETRE_MIN
        j = next((k for k in range(i + 1, len(entrees)) if entrees[k][0] >= limite),
                 len(entrees))
        if plages and i < plages[-1][1]:
            plages[-1] = (plages[-1][0], max(plages[-1][1], j))
        else:
            plages.append((i, j))
    return [(entrees[i][0], entrees[j][0] if j < len(entrees) else None) for i, j in plages]


def _cle(jeton: str) -> str:
    return re.sub(r"\W+", "", jeton.lower()) or jeton


def _mots(jetons: Sequence[str]) -> int:
    """Une ponctuation isolée (« ? » à la française) n'est pas un mot."""
    return sum(1 for jeton in jetons if re.search(r"\w", jeton))


def completer(lignes: Sequence[Entree], textes: Sequence[str]) -> tuple[list[Entree], int]:
    """Ajoute aux lignes d'une fenêtre les morceaux que sa réécoute a en plus.

    Rend les lignes complétées et le nombre de mots ajoutés (0 : rien de sûr,
    les lignes sont rendues telles quelles).
    """
    anciens = [(k, jeton) for k, (_debut, texte) in enumerate(lignes)
               for jeton in texte.split()]
    nouveaux = [jeton for texte in textes for jeton in texte.split()]
    cles_a, cles_n = [_cle(j) for _k, j in anciens], [_cle(j) for j in nouveaux]
    blocs = difflib.SequenceMatcher(None, cles_a, cles_n, autojunk=False).get_matching_blocks()

    a_reprendre = _mots([j for _k, j in anciens])
    repris = _mots([anciens[x][1] for bloc in blocs for x in range(bloc.a, bloc.a + bloc.size)])
    # La fenêtre et sa réécoute commencent et finissent aux mêmes instants : si
    # elles commencent (ou finissent) par les mêmes mots, c'est une ancre, même
    # courte — une ligne n'a parfois qu'un mot (« Ouais. », « Salut. »).
    ancres = [bloc for bloc in blocs if bloc.size and (
        bloc.size >= ANCRE
        or (bloc.a == 0 and bloc.b == 0)
        or (bloc.a + bloc.size == len(cles_a) and bloc.b + bloc.size == len(cles_n)))]
    if not a_reprendre or repris / a_reprendre < RECOUVREMENT_MIN or not ancres:
        return list(lignes), 0

    # Entre la première et la dernière ancre, la réécoute est calée sur
    # l'existant ; au-delà, on ne saurait pas où placer ce qu'elle ajoute.
    lo_a, lo_n = ancres[0].a, ancres[0].b
    hi_a, hi_n = ancres[-1].a + ancres[-1].size, ancres[-1].b + ancres[-1].size
    jetons: list[list[str]] = [[] for _ in lignes]
    for k, jeton in anciens[:lo_a]:
        jetons[k].append(jeton)
    ligne, ajoutes = anciens[lo_a][0], 0
    operations = difflib.SequenceMatcher(
        None, cles_a[lo_a:hi_a], cles_n[lo_n:hi_n], autojunk=False).get_opcodes()
    for _tag, a1, a2, n1, n2 in operations:
        vieux, neufs = anciens[lo_a + a1:lo_a + a2], nouveaux[lo_n + n1:lo_n + n2]
        gain = _mots(neufs) - _mots([j for _k, j in vieux])
        if gain >= AJOUT_MIN:
            # Un passage oublié : la réécoute prend la place de ce qu'elle
            # recouvre, dans la ligne où il commence.
            ligne = vieux[0][0] if vieux else ligne
            jetons[ligne].extend(neufs)
            ajoutes += gain
        else:
            for k, jeton in vieux:
                jetons[k].append(jeton)
                ligne = k
    for k, jeton in anciens[hi_a:]:
        jetons[k].append(jeton)
    if not ajoutes:
        return list(lignes), 0
    return [(lignes[k][0], " ".join(j)) for k, j in enumerate(jetons) if j], ajoutes


def combler(entrees: Sequence[Entree], reecouter: Reecoute) -> tuple[list[Entree], Bilan]:
    """Rend les entrées avec les passages perdus retrouvés, dans l'ordre."""
    suspects = candidats(entrees)
    bilan = Bilan(candidats=len(suspects))
    lignes = list(entrees)
    for debut, fin in fenetres(entrees, suspects):
        try:
            rendues = reecouter([debut] if fin is None else [debut, fin])
        except Exception as exc:  # noqa: BLE001 — un trou non comblé ne perd pas l'épisode.
            log.warning("Réécoute impossible à partir de %s : %s", format_timestamp(debut), exc)
            continue
        debuts = [d for d, _t in lignes]
        a = bisect.bisect_left(debuts, debut)
        b = len(lignes) if fin is None else bisect.bisect_left(debuts, fin)
        completees, ajoutes = completer(lignes[a:b], [t for _d, t in sorted(rendues)])
        if ajoutes:
            lignes[a:b] = completees
            bilan.combles += 1
            bilan.mots_ajoutes += ajoutes
            log.info("Passage perdu retrouvé vers %s : %d mot(s).",
                     format_timestamp(debut), ajoutes)
    log.info("Trous de transcription : %d candidat(s), %d comblé(s), %d mot(s) retrouvé(s).",
             bilan.candidats, bilan.combles, bilan.mots_ajoutes)
    return lignes, bilan
