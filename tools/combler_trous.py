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
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

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
# Huit lignes identiques d'affilée signalent une boucle à relire. Sur les 113
# transcriptions du dépôt (inventaire du 2026-11-01), les suites de 5 à 7 lignes
# sont 59, presque toutes de vraies répétitions parlées de quelques secondes
# (« Bonne année ! », « ça va ? ») : les signaler noierait les vraies boucles.
BOUCLE_MIN = 8
# Une suite de 8 à 14 lignes reste ambiguë ; on la signale sans la remplacer.
BOUCLE_REPARATION_MIN = 15
BOUCLE_CONTEXTE = 20.0
# Mots que la réécoute d'une fenêtre doit entendre en plus pour qu'une fenêtre
# non comblée soit signalée. Sur S6-E07 (rejoué le 2026-11-01), les trois faux
# « passages muets » avaient de -61 à +1 mot de plus ; les autres fenêtres, de
# +8 à +71. Celle à +8 (« le dieu de l'arrache », 00:56) n'avait rien perdu
# d'utile, selon la réécoute de l'éditeur du 2026-10-30.
ECART_A_SIGNALER = 10
# Morceaux d'une même boucle coupée par de vraies phrases (cf. `zones_de_boucle`).
FRAGMENT_MIN = 4
FRAGMENT_ECART = 20.0
# Une phrase de quatre mots répétée huit fois en 25 s peut échapper au repérage
# des lignes identiques (S6-E07, 00:19). Elle est signalée, sans fusion auto.
REPETITION_PHRASE_MIN = 8
REPETITION_PHRASE_FENETRE = 25.0
# Génériques de sous-titrage que Whisper invente sur la musique ou le silence,
# appris de ses données d'entraînement : personne ne les prononce dans
# l'émission. Relevés dans le dépôt le 2026-11-01 : « Sous-titrage Société
# Radio-Canada » (8), « Sous-titrage ST' 501 » (9), « Sous-titres par Jérémy
# Diaz » (2). La ligne entière doit correspondre : « il est sous-titré en
# anglais » reste une parole.
GENERIQUE = re.compile(
    r"^[\s–—-]*(?:sous-titrage\s+(?:soci[ée]t[ée]\s+radio-canada|st'\s?501)"
    r"|sous-titres?\s+(?:r[ée]alis[ée]s\s+)?par\s+(?:la\s+communaut[ée]\s+d'amara\.org"
    r"|(?-i:[A-ZÉÈ][\w-]+\s+[A-ZÉÈ][\w-]+)))[\s.!]*$",
    re.IGNORECASE,
)

Entree = tuple[float, str]
# Reçoit `clip_timestamps` ([début, fin] ou [début] jusqu'au bout de l'audio),
# rend les segments (début absolu en secondes, texte).
Reecoute = Callable[[list[float]], Sequence[Entree]]


@dataclass
class Bilan:
    candidats: int = 0
    combles: int = 0
    mots_ajoutes: int = 0
    # Fenêtres que la réécoute entend plus longues sans savoir les recaler, ou
    # qu'elle n'a pas pu réécouter, en (début, plus long silence dedans),
    # secondes. Sur S6-E03, celle de 01:11:58 cachait une reco, et personne
    # n'avait de quoi savoir où tendre l'oreille. L'éditeur les reçoit par
    # Matrix. Celles où la réécoute n'entend rien de plus n'y sont pas : sur
    # S6-E07, c'étaient les trois faux « passages muets » du 2026-10-30.
    non_combles: list[tuple[float, float]] = field(default_factory=list)
    # Début et nombre de lignes de chaque boucle, corrigée ou laissée à relire.
    boucles_reparees: list[tuple[float, int]] = field(default_factory=list)
    boucles_non_reparees: list[tuple[float, int]] = field(default_factory=list)
    # Début, fin, occurrences et exemple du motif, hors boucles déjà signalées.
    repetitions_suspectes: list[tuple[float, float, int, str]] = field(default_factory=list)
    # Début de chaque générique inventé retiré de la transcription.
    generiques_retires: list[float] = field(default_factory=list)


def sans_generiques(entrees: Sequence[Entree]) -> tuple[list[Entree], list[float]]:
    """Retire les génériques inventés ; rend les lignes gardées et les débuts retirés.

    Le retrait laisse un saut horodaté là où Whisper a cessé d'écouter : le
    repérage des trous le voit ensuite, et la réécoute peut y retrouver une
    parole couverte (S6-E07, 00:39:50, pendant le blind test).
    """
    gardees = [(d, t) for d, t in entrees if not GENERIQUE.match(t)]
    return gardees, [d for d, t in entrees if GENERIQUE.match(t)]


def candidats(entrees: Sequence[Entree]) -> list[int]:
    """Indices des lignes suivies d'un saut suspect."""
    return [
        i for i in range(len(entrees) - 1)
        if entrees[i + 1][0] - entrees[i][0] >= SAUT_MIN
        and len(entrees[i][1]) < LONGUEUR_MAX_TEXTE
    ]


def _suites(entrees: Sequence[Entree], minimum: int) -> list[tuple[int, int, str]]:
    """Plages [début, fin) d'au moins `minimum` lignes au texte identique, et ce texte."""
    trouvees = []
    i = 0
    while i < len(entrees):
        cle = _cle(entrees[i][1])
        j = i + 1
        while cle and j < len(entrees) and _cle(entrees[j][1]) == cle:
            j += 1
        if cle and j - i >= minimum:
            trouvees.append((i, j, cle))
        i = j
    return trouvees


def zones_de_boucle(entrees: Sequence[Entree]) -> list[tuple[int, int, int]]:
    """Boucles, morceaux réunis : plages [début, fin) et nombre de lignes répétées.

    Une boucle peut être coupée par de vraies phrases. Sur S6-E07, « Frère. »
    revenait 7 fois, puis 12 lignes de parole, puis 30 fois : la seule suite de
    30 lignes laissait les 7 premières, trop courtes pour être signalées. Des
    suites du même texte, d'au moins `FRAGMENT_MIN` lignes et séparées de moins
    de `FRAGMENT_ECART` secondes, forment donc une seule zone.
    """
    zones: list[list] = []
    for i, j, cle in _suites(entrees, FRAGMENT_MIN):
        if (zones and zones[-1][3] == cle
                and entrees[i][0] - entrees[zones[-1][1] - 1][0] <= FRAGMENT_ECART):
            zones[-1][1] = j
            zones[-1][2] += j - i
        else:
            zones.append([i, j, j - i, cle])
    return [(i, j, n) for i, j, n, _cle_zone in zones if n >= BOUCLE_MIN]


def repetitions_de_phrases(entrees: Sequence[Entree]) -> list[tuple[float, float, int, str]]:
    """Repère les boucles de phrases que les lignes identiques ne voient pas."""
    mots = [(debut, mot) for debut, texte in entrees
            for mot in re.findall(r"\w+", texte.casefold())]
    occurrences: dict[tuple[str, ...], list[float]] = defaultdict(list)
    for i in range(len(mots) - 3):
        phrase = tuple(mot for _debut, mot in mots[i:i + 4])
        if len(set(phrase)) > 1:
            occurrences[phrase].append(mots[i][0])

    candidats_repetition = []
    for phrase, instants in occurrences.items():
        gauche = 0
        meilleur = None
        for droite, instant in enumerate(instants):
            while instant - instants[gauche] > REPETITION_PHRASE_FENETRE:
                gauche += 1
            nombre = droite - gauche + 1
            if nombre >= REPETITION_PHRASE_MIN and (meilleur is None or nombre > meilleur[2]):
                meilleur = (instants[gauche], instant, nombre, " ".join(phrase))
        if meilleur is not None:
            candidats_repetition.append(meilleur)

    plages_exactes = [(entrees[i][0], entrees[j][0] if j < len(entrees) else float("inf"))
                     for i, j, _n in zones_de_boucle(entrees)]
    candidats_repetition = [c for c in candidats_repetition
                            if not any(c[0] < fin and c[1] >= debut
                                       for debut, fin in plages_exactes)]
    uniques = []
    for candidat in sorted(candidats_repetition):
        if uniques and candidat[0] <= uniques[-1][1] + 2:
            if candidat[2] > uniques[-1][2]:
                uniques[-1] = candidat
        else:
            uniques.append(candidat)
    return uniques


def _ancre_commune(reference: str, candidat: str) -> int:
    a = re.findall(r"\w+", reference.casefold())
    b = re.findall(r"\w+", candidat.casefold())
    return max((bloc.size for bloc in difflib.SequenceMatcher(
        None, a, b, autojunk=False).get_matching_blocks()), default=0)


def _reprend_la_parole(zone: Sequence[Entree], nouvelles: Sequence[Entree]) -> bool:
    """Les vraies phrases prises dans une zone doivent survivre à son remplacement.

    Une zone en morceaux contient de la parole entre ses répétitions : la
    réécoute ne la remplace que si elle en reprend l'essentiel.
    """
    repetes = Counter(_cle(t) for _d, t in zone).most_common(1)[0][0]
    parole = [_cle(m) for _d, t in zone if _cle(t) != repetes for m in t.split()]
    parole = [m for m in parole if re.search(r"\w", m)]
    if not parole:
        return True
    neufs = [_cle(m) for _d, t in nouvelles for m in t.split()]
    repris = sum(bloc.size for bloc in difflib.SequenceMatcher(
        None, parole, neufs, autojunk=False).get_matching_blocks())
    return repris / len(parole) >= RECOUVREMENT_MIN


def reparer_boucles(entrees: Sequence[Entree], reecouter: Reecoute,
                    duree_audio: float | None = None,
                    ) -> tuple[list[Entree], list[tuple[float, int]], list[tuple[float, int]]]:
    """Remplace une boucle seulement si la réécoute retrouve ses deux bords.

    On conserve les lignes d'origine si le nouveau texte ne s'aligne pas avant
    ET après la boucle. Cela évite de recopier une hallucination ou une vraie
    répétition parlée simplement parce que la seconde passe diffère.
    """
    lignes = list(entrees)
    reparees, non_reparees = [], []
    for i, j, nombre in reversed(zones_de_boucle(lignes)):
        debut = lignes[i][0]
        # Sans une ligne des deux côtés, le remplacement ne peut pas être calé.
        if nombre < BOUCLE_REPARATION_MIN or i == 0 or j == len(lignes):
            non_reparees.append((debut, nombre))
            continue
        fin = lignes[j][0]
        clip = [max(0.0, debut - BOUCLE_CONTEXTE), fin + BOUCLE_CONTEXTE]
        if duree_audio is not None:
            clip[1] = min(clip[1], duree_audio)
        try:
            rendues = sorted(sans_generiques(reecouter(clip))[0])
        except Exception as exc:  # noqa: BLE001 — la transcription d'origine reste intacte.
            log.warning("Réécoute d'une boucle impossible vers %s : %s",
                        format_timestamp(debut), exc)
            non_reparees.append((debut, nombre))
            continue
        avant = " ".join(t for _d, t in lignes[max(0, i - 2):i])
        apres = " ".join(t for _d, t in lignes[j:j + 2])
        ancres_avant = [k for k, (d, t) in enumerate(rendues)
                         if d <= debut + 1 and _ancre_commune(avant, t) >= 2]
        ancres_apres = [k for k, (d, t) in enumerate(rendues)
                         if d >= fin - 2 and _ancre_commune(apres, t) >= 3]
        if not ancres_avant or not ancres_apres:
            non_reparees.append((debut, nombre))
            continue
        premiere = ancres_avant[-1] + 1
        derniere = next((k for k in ancres_apres if k > premiere), None)
        if derniere is None:
            non_reparees.append((debut, nombre))
            continue
        nouvelles = [(d, t.strip()) for d, t in rendues[premiere:derniere]
                     if debut - 1 <= d < fin and t.strip()]
        mots = sum(_mots(t.split()) for _d, t in nouvelles)
        if (len(nouvelles) < 2 or mots < max(5, nombre // 2)
                or zones_de_boucle(nouvelles)
                or [d for d, _t in nouvelles] != sorted(d for d, _t in nouvelles)
                or not _reprend_la_parole(lignes[i:j], nouvelles)):
            non_reparees.append((debut, nombre))
            continue
        lignes[i:j] = nouvelles
        reparees.append((debut, nombre))
        log.info("Boucle de %d lignes réparée vers %s : %d mots réécoutés.",
                 nombre, format_timestamp(debut), mots)
    return lignes, list(reversed(reparees)), list(reversed(non_reparees))


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

    repris_idx = {x for bloc in blocs for x in range(bloc.a, bloc.a + bloc.size)}
    # La borne de fin d'une fenêtre est posée sur un DÉBUT de ligne : la dernière
    # ligne comparée peut n'avoir qu'une fraction de seconde avant la fin de
    # l'audio réécouté, et la réécoute ne la rend alors pas du tout. Mesuré sur
    # S6-E03 (2026-10-02) : « C'est beau ce que tu dis. », commencée 1 s avant la
    # borne, pesait 6 mots sur 23 et faisait tomber le recouvrement à 0,57 — la
    # réécoute, qui contenait pourtant la reco perdue (« toujours les pieds sur
    # terre, Sonia Kronlund… »), était jetée. Une dernière ligne dont RIEN n'est
    # repris est donc tenue pour hors de portée et non pour un désaccord. Les
    # autres continuent de compter : une réécoute vraiment hors sujet n'en reprend
    # aucune et reste refusée.
    derniere = len(lignes) - 1
    indices_derniere = {i for i, (k, _j) in enumerate(anciens) if k == derniere}
    hors_de_portee = bool(derniere and indices_derniere and not indices_derniere & repris_idx)
    a_reprendre = _mots([j for i, (k, j) in enumerate(anciens)
                         if not (hors_de_portee and k == derniere)])
    repris = _mots([anciens[x][1] for x in repris_idx])
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


def combler(entrees: Sequence[Entree], reecouter: Reecoute,
            reecouter_boucle: Reecoute | None = None,
            duree_audio: float | None = None) -> tuple[list[Entree], Bilan]:
    """Rend les entrées avec les passages perdus retrouvés, dans l'ordre."""
    entrees, retires = sans_generiques(entrees)
    if retires:
        log.info("Génériques inventés retirés : %s.",
                 ", ".join(format_timestamp(d) for d in retires))
    suspects = candidats(entrees)
    bilan = Bilan(candidats=len(suspects), generiques_retires=retires)
    lignes = list(entrees)
    # Les fenêtres laissées telles quelles sont nommées : sans elles, le journal
    # disait « 14 candidat(s), 7 comblé(s) » sans dire lesquels, et il a fallu
    # rejouer la réécoute à la main pour retrouver la reco perdue de S6-E03.
    sans_suite: list[str] = []
    for debut, fin in fenetres(entrees, suspects):
        debuts = [d for d, _t in lignes]
        a = bisect.bisect_left(debuts, debut)
        b = len(lignes) if fin is None else bisect.bisect_left(debuts, fin)
        silence = max((lignes[k + 1][0] - lignes[k][0]
                       for k in range(a, min(b, len(lignes)) - 1)), default=0.0)
        try:
            rendues = reecouter([debut] if fin is None else [debut, fin])
        except Exception as exc:  # noqa: BLE001 — un trou non comblé ne perd pas l'épisode.
            log.warning("Réécoute impossible à partir de %s : %s", format_timestamp(debut), exc)
            bilan.non_combles.append((debut, silence))
            sans_suite.append(f"{format_timestamp(debut)} (+{silence:.0f} s)")
            continue
        rendues, _retires = sans_generiques(rendues)
        completees, ajoutes = completer(lignes[a:b], [t for _d, t in sorted(rendues)])
        if ajoutes:
            lignes[a:b] = completees
            bilan.combles += 1
            bilan.mots_ajoutes += ajoutes
            log.info("Passage perdu retrouvé vers %s : %d mot(s).",
                     format_timestamp(debut), ajoutes)
        else:
            sans_suite.append(f"{format_timestamp(debut)} (+{silence:.0f} s)")
            en_plus = (sum(_mots(t.split()) for _d, t in rendues)
                       - sum(_mots(t.split()) for _d, t in lignes[a:b]))
            # Seule une réécoute qui entend nettement plus vaut l'oreille de
            # l'éditeur ; le saut le plus long dit où tendre l'oreille.
            if en_plus >= ECART_A_SIGNALER:
                bilan.non_combles.append((debut, silence))
    log.info("Trous de transcription : %d candidat(s), %d comblé(s), %d mot(s) retrouvé(s).",
             bilan.candidats, bilan.combles, bilan.mots_ajoutes)
    if sans_suite:
        log.info("Fenêtres laissées telles quelles : %s.", ", ".join(sans_suite))
    if reecouter_boucle is not None:
        lignes, bilan.boucles_reparees, bilan.boucles_non_reparees = reparer_boucles(
            lignes, reecouter_boucle, duree_audio)
    bilan.repetitions_suspectes = repetitions_de_phrases(lignes)
    return lignes, bilan
