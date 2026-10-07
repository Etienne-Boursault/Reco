"""
caler_citations.py — après l'extraction, cale chaque citation sur la transcription.

Deux défauts mesurés le 2026-10-07 sur les 1 259 recos publiées :

- LE MINUTAGE. Le modèle d'extraction le recopie depuis les `[hh:mm:ss]` de la
  transcription, et rien ne vérifiait qu'il pointe sur la citation : 45 recos
  à plus de 30 s (souvent une minute pile de trop ou de moins), 4 à 00:00:00.
  Ici, le code retrouve la citation dans la transcription et prend le minutage
  de sa ligne : d'abord près du minutage annoncé (±60 s), sinon ailleurs dans
  l'épisode si la phrase n'y est qu'une fois. Un écart de 10 s ou moins est
  laissé tel quel ; une citation introuvable aussi.

- LES NOMS. La citation reprend la transcription mot pour mot, et Whisper
  écorche les noms propres (« Camelot » pour Kaamelott) — environ une citation
  sur cinq. Le modèle d'extraction, lui, a écrit le nom juste dans le titre et
  le créateur : le passage qui transcrit mal ce nom en prend la graphie.
  Rien ne trie ici avant d'écrire, d'où des garde-fous plus stricts que la
  passe faite à la main sur le corpus :
    * le passage ressemble au nom (≥ 0,72 : « Camelot » et Kaamelott
      sont à 0,75) et compte autant de mots pleins (un de plus pour un nom
      d'un seul mot : « Aurel San ») ;
    * chaque mot du passage répond, dans l'ordre, à un mot du nom (« Jason
      Seagal » répond à Jason Segel ; « demi de Fellini » ne répond pas à
      Federico Fellini) ;
    * le passage n'est pas un mot courant de l'épisode (« franchement » pour
      *L'attachement*, « musique » pour *Muse*) ;
    * le nom n'est pas un titre descriptif (parenthèse, plus de six mots).

Chaque correction est rendue au message de validation (ancien → nouveau) : la
relecture tranche, comme pour la réécoute de `preciser_citations.py`, qui
passe avant et travaille sur l'audio.

Usage :
    cd tools
    python caler_citations.py --source un-bon-moment --guid yt-XXXX [--apply]
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common import log, read_json, recos_dir_for, transcript_path_for, write_json_if_changed

FENETRE = 60          # s autour du minutage annoncé
TOLERANCE = 10        # s : un écart plus petit n'est pas corrigé
SEUIL_PRES = 0.75     # ressemblance pour retrouver la citation près du minutage
SEUIL_AILLEURS = 0.80  # … et ailleurs dans l'épisode
SEUIL_RIVAL = 0.75    # un second endroit aussi ressemblant rend la phrase ambiguë
SEUIL_NOM = 0.72
MOT_COURANT = 4       # occurrences dans l'épisode au-delà desquelles un mot est courant
MOTS_VIDES = frozenset(
    "le la les l un une des de du d et a au aux the of en sur pour par".split())
MOT = re.compile(r"[^\W_]+", re.UNICODE)

Ligne = tuple[int, list[str]]


@dataclass
class Bilan:
    guid: str
    minutages: list[tuple[str, str, str]] = field(default_factory=list)  # id, avant, après
    noms: list[tuple[str, str, str]] = field(default_factory=list)       # id, ancien, nouveau
    erreurs: list[str] = field(default_factory=list)


# ===== texte =================================================================
def _mot(mot: str) -> str:
    return unicodedata.normalize("NFKD", mot).encode("ascii", "ignore").decode().lower()


def mots(texte: str | None) -> list[str]:
    return [m for m in (_mot(x) for x in MOT.findall(texte or "")) if m]


def secondes(horodatage: str | None) -> int | None:
    if not isinstance(horodatage, str):
        return None
    morceaux = horodatage.strip().split(":")
    if not 2 <= len(morceaux) <= 3 or not all(m.isdigit() for m in morceaux):
        return None
    valeurs = [int(m) for m in morceaux]
    while len(valeurs) < 3:
        valeurs.insert(0, 0)
    return valeurs[0] * 3600 + valeurs[1] * 60 + valeurs[2]


def horodatage(total: int) -> str:
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def lire_transcription(chemin: Path) -> list[Ligne]:
    lignes = []
    for brute in chemin.read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"\[(\d\d):(\d\d):(\d\d)\]\s*(.*)", brute)
        if m and mots(m[4]):
            lignes.append((int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]), mots(m[4])))
    return lignes


# ===== minutage ==============================================================
def _fenetres(lignes: list[Ligne], i: int, n: int) -> Iterator[str]:
    """Textes qui commencent à la ligne i, de 0,6 à 1,4 fois la longueur de la citation."""
    acc: list[str] = []
    for j in range(i, min(i + max(40, 2 * n), len(lignes))):
        acc += lignes[j][1]
        if len(acc) >= n * 0.6:
            yield " ".join(acc[: int(n * 1.4) + 1])
        if len(acc) > n * 1.4:
            return


def _departs(citation: list[str], lignes: list[Ligne],
             autour: tuple[int, int] | None = None) -> list[tuple[float, int]]:
    """(ressemblance, seconde) des meilleurs départs, du meilleur au moins bon."""
    cible = " ".join(citation)
    if autour:
        indices = [i for i, (t, _m) in enumerate(lignes) if autour[0] <= t <= autour[1]]
    else:
        voc = set(citation)
        communs = []
        for i in range(len(lignes)):
            fen: set[str] = set()
            for j in range(i, min(i + 4, len(lignes))):
                fen.update(lignes[j][1])
            communs.append((len(voc & fen), i))
        indices = [i for _n, i in sorted(communs, reverse=True)[:25]]
    scores = []
    for i in indices:
        meilleur = max((difflib.SequenceMatcher(None, cible, f, autojunk=False).ratio()
                        for f in _fenetres(lignes, i, len(citation))), default=0.0)
        scores.append((meilleur, lignes[i][0]))
    return sorted(scores, reverse=True)


def recaler(citation: str | None, annonce: str | None, lignes: list[Ligne]) -> int | None:
    """Seconde où la citation est dite, si elle diffère nettement du minutage annoncé."""
    texte = mots(citation)
    if len(texte) < 3 or not lignes:
        return None
    avant = secondes(annonce) or None  # 00:00:00 ne désigne rien
    trouve = None
    if avant is not None:
        pres = _departs(texte, lignes, (avant - FENETRE, avant + FENETRE))
        if pres and pres[0][0] >= SEUIL_PRES:
            meilleur = pres[0][0]
            if any(abs(t - avant) <= TOLERANCE and s >= meilleur - 0.05 for s, t in pres):
                return None
            trouve = pres[0][1]
    if trouve is None:
        partout = _departs(texte, lignes)
        if not partout or partout[0][0] < SEUIL_AILLEURS:
            return None
        trouve = partout[0][1]
        if any(abs(t - trouve) > 30 and s >= SEUIL_RIVAL for s, t in partout[1:]):
            return None
    if avant is not None and abs(trouve - avant) <= TOLERANCE:
        return None
    return trouve


# ===== noms ==================================================================
def _ressemblance(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def _recollages(morceau: list[tuple[str, ...]], n: int) -> Iterator[list[tuple[str, ...]]]:
    """Le passage ramené à n mots en recollant des mots voisins (chaque mot garde ses morceaux).

    Whisper coupe les noms : « Blond Red Dead » (Blonde Redhead), « Get Down
    Service » (Getdown Services), « Aurel San » (Orelsan).
    """
    if len(morceau) == n:
        yield morceau
    elif len(morceau) > n:
        for m in range(len(morceau) - 1):
            yield from _recollages([*morceau[:m], morceau[m] + morceau[m + 1], *morceau[m + 2:]], n)


def _repond(morceaux: tuple[str, ...], mot: str) -> bool:
    """Un mot (éventuellement recollé) répond à un mot du nom.

    Un recollage doit rapprocher du nom plus que chacun de ses morceaux, et
    chaque morceau en reprendre un bout : « Roi Lion ! Je » ne devient pas
    « lionje » pour répondre à « lion », ni « René avait » à « Resnais ».
    """
    colle = "".join(morceaux)
    r = _ressemblance(colle, mot)
    if r < 0.6:
        return False
    if len(morceaux) == 1:
        return True
    return (r > max(_ressemblance(x, mot) for x in morceaux)
            and all(_commun(x, mot) >= min(3, len(x)) for x in morceaux))


def _commun(a: str, b: str) -> int:
    return difflib.SequenceMatcher(None, a, b).find_longest_match().size


def _mot_a_mot(morceau: list[str], pleins: list[str]) -> bool:
    """Chaque mot du passage répond à un mot du nom, dans l'ordre, et le passage diffère.

    « Jason Seagal » répond à Jason Segel ; « demi Fellini » ne répond pas à
    Federico Fellini, et « 8 et demi de Fellini » n'est donc pas une faute.
    """
    if morceau == pleins:
        return False
    return any(all(_repond(a, b) for a, b in zip(r, pleins, strict=True))
               for r in _recollages([(w,) for w in morceau], len(pleins)))


def _sans_article(nom: str) -> str:
    """« The Typhoon » -> « Typhoon » : quand la citation porte déjà son propre article."""
    for m in MOT.finditer(nom):
        if _mot(m.group()) not in MOTS_VIDES:
            return nom[m.start():]
    return nom


def _passage(nom: str, citation: str, courants: set[str]) -> tuple[int, int, str] | None:
    """Début, fin et remplaçant du passage de la citation qui transcrit mal `nom`."""
    nm = mots(nom)
    if not nm or len(nm) > 6 or "(" in nom:
        return None
    jetons = [(m.start(), m.end(), _mot(m.group())) for m in MOT.finditer(citation)]
    jetons = [j for j in jetons if j[2]]
    texte = [j[2] for j in jetons]
    if f" {' '.join(nm)} " in f" {' '.join(texte)} ":
        return None
    pleins = [w for w in nm if w not in MOTS_VIDES] or nm
    cible = " ".join(pleins)
    # Fenêtres de mots pleins consécutifs ; les mots vides entre eux suivent.
    places = [k for k, w in enumerate(texte) if w not in MOTS_VIDES]
    meilleur: tuple[float, int, int] = (0.0, 0, 0)
    for taille in range(len(pleins), len(pleins) + 3):
        for s in range(len(places) - taille + 1):
            choisis = places[s:s + taille]
            if choisis[-1] - choisis[0] > 2 * taille:
                continue
            if not _mot_a_mot([texte[k] for k in choisis], pleins):
                continue
            r = difflib.SequenceMatcher(None, cible, " ".join(texte[k] for k in choisis)).ratio()
            if r > meilleur[0]:
                meilleur = (r, choisis[0], choisis[-1] + 1)
    r, i, j = meilleur
    if r < SEUIL_NOM or len(" ".join(texte[i:j])) < 4:
        return None
    if all(w in courants for w in texte[i:j]):
        return None
    # Les mots du nom qui encadrent déjà le passage en font partie (« Les » Clés…).
    debut, fin = 0, len(nm)
    while i > 0 and debut < len(nm) and texte[i - 1] == nm[debut] and nm[debut] in MOTS_VIDES:
        i -= 1
        debut += 1
    while j < len(jetons) and fin > 0 and texte[j] == nm[fin - 1] and nm[fin - 1] in MOTS_VIDES:
        j += 1
        fin -= 1
    remplacant = nom
    if nm[debut] in MOTS_VIDES and i > 0 and texte[i - 1] in MOTS_VIDES:
        remplacant = _sans_article(nom)  # « Le Typhon » -> « Le Typhoon », pas « Le The Typhoon »
    return jetons[i][0], jetons[j - 1][1], remplacant


def corriger_noms(citation: str, noms: list[str],
                  courants: set[str] = frozenset()) -> tuple[str, list[tuple[str, str]]]:
    """La citation où chaque nom mal transcrit prend la graphie de la fiche."""
    corrections: list[tuple[str, str]] = []
    for nom in noms:
        place = _passage(nom, citation, set(courants))
        if place is None:
            continue
        debut, fin, remplacant = place
        ancien = citation[debut:fin]
        if any(mots(ancien) == mots(posé) for _a, posé in corrections):
            continue  # un nom déjà rétabli ne se réécrit pas sous la graphie d'un autre
        if any(f" {' '.join(mots(autre))} " in f" {' '.join(mots(ancien))} "
               for autre in noms if autre != nom):
            continue  # titre et créateur qui écrivent la même personne autrement
        citation = citation.replace(ancien, remplacant)
        corrections.append((ancien, remplacant))
    return citation, corrections


def noms_de(reco: dict[str, Any]) -> list[str]:
    noms = [reco.get("title")]
    noms += re.split(r",|&| et ", reco.get("creator") or "")
    return [n.strip() for n in noms if isinstance(n, str) and n.strip()]


def mots_courants(lignes: list[Ligne]) -> set[str]:
    compte = Counter(w for _t, ws in lignes for w in ws)
    return {w for w, n in compte.items() if n >= MOT_COURANT}


# ===== épisode ===============================================================
def caler_episode(source_id: str, guid: str, *, apply: bool = False) -> Bilan:
    bilan = Bilan(guid)
    chemin = transcript_path_for(source_id, guid)
    if not chemin.exists():
        bilan.erreurs.append(f"pas de transcription pour {guid}")
        return bilan
    lignes = lire_transcription(chemin)
    courants = mots_courants(lignes)
    dossier = recos_dir_for(source_id)
    for fichier in sorted(dossier.glob("*.json")) if dossier.is_dir() else []:
        reco = read_json(fichier)
        if reco.get("episodeGuid") != guid or reco.get("status") == "discarded":
            continue
        nouvelle = dict(reco)
        citation, corrections = corriger_noms(reco.get("quote") or "", noms_de(reco), courants)
        if corrections:
            nouvelle["quote"] = citation
            bilan.noms += [(reco["id"], a, n) for a, n in corrections]
        seconde = recaler(reco.get("quote"), reco.get("timestamp"), lignes)
        if seconde is not None:
            nouvelle["timestamp"] = horodatage(seconde)
            bilan.minutages.append((reco["id"], reco.get("timestamp") or "", nouvelle["timestamp"]))
        if apply and nouvelle != reco:
            write_json_if_changed(fichier, nouvelle)
    return bilan


def resume(bilan: Bilan) -> str:
    """Lignes du message de validation ; vide s'il n'y a rien à relire."""
    lignes = []
    if bilan.noms:
        lignes.append("Noms rétablis dans les citations : "
                      + " ; ".join(f"{a} → {n}" for _i, a, n in bilan.noms) + ".")
    if bilan.minutages:
        lignes.append(f"{len(bilan.minutages)} minutage(s) recalé(s) sur la citation.")
    return "\n".join(lignes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", required=True)
    parser.add_argument("--guid", required=True)
    parser.add_argument("--apply", action="store_true", help="écrire (sinon : à blanc)")
    args = parser.parse_args(argv)
    bilan = caler_episode(args.source, args.guid, apply=args.apply)
    for reco_id, ancien, nouveau in bilan.noms:
        log.info("%s : « %s » → « %s »", reco_id, ancien, nouveau)
    for reco_id, avant, apres in bilan.minutages:
        log.info("%s : %s → %s", reco_id, avant, apres)
    for erreur in bilan.erreurs:
        log.warning(erreur)
    if not args.apply:
        log.info("À blanc : rien n'est écrit (--apply pour écrire).")
    return 1 if bilan.erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
