"""graphies.py — Registre des graphies corrigées en relecture.

Décision R6 A d'Étienne, 2026-11-27 (« référencer les différentes corrections
qui sont trouvées pour les appliquer aux futurs épisodes ») : Whisper écrit les
noms au son (« Hilleret » pour Hillairet, « Gat Buzzy » pour Get Busy), la
relecture les corrige, puis la même faute revient à l'épisode suivant.

Trois temps :
  1. l'extraction garde le brouillon d'origine de chaque reco neuve
     (`garder_brouillon`), hors du contenu versionné ;
  2. la finalisation compare ce brouillon à la reco validée et note chaque
     nom propre corrigé (`enregistrer`) ;
  3. la relecture des épisodes suivants PROPOSE la correction (`propositions`,
     encadré « À vérifier »). Rien n'est jamais remplacé seul : « Navo » et
     « Bruno Muschio » sont la même personne, un remplacement aveugle casserait.

Le registre vit dans `tools/output/graphies/registre.json`, hors de Git : un
fichier suivi, modifié par la finalisation, ferait refuser la publication
suivante (« modifications étrangères à l'épisode »). Chemins résolus à l'appel,
pour qu'un test ne touche jamais le vrai registre.
"""
from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any

import common
from common import log, read_json, write_json_if_changed

# Les champs où Whisper laisse ses fautes. Les liens et les types n'en sont pas.
CHAMPS = ("title", "creator", "recommendedBy", "quote")
# Au-delà, c'est une réécriture, pas une graphie.
_MAX_MOTS = 3
# Sous ce seuil, ce n'est plus le même nom : une autre œuvre, une reformulation.
_SEUIL_RESSEMBLANCE = 0.6
_MOT = re.compile(r"\w+(?:[-'’]\w+)*")


def _dossier() -> Path:
    return common.OUTPUT_DIR / "graphies"


def _registre() -> Path:
    return _dossier() / "registre.json"


def _brouillon(source_id: str, reco_id: str) -> Path:
    return _dossier() / "brouillons" / source_id / f"{reco_id}.json"


# ----- 1. le brouillon d'origine --------------------------------------------

def garder_brouillon(source_id: str, reco: dict[str, Any]) -> None:
    """Garde les champs textuels d'une reco neuve, une seule fois.

    Une réextraction ne l'écrase pas : c'est la première version, celle que la
    relecture va corriger, qui sert de référence.
    """
    reco_id = reco.get("id")
    if not reco_id:
        return
    chemin = _brouillon(source_id, reco_id)
    if chemin.exists():
        return
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        write_json_if_changed(chemin, {k: reco[k] for k in CHAMPS if reco.get(k)})
    except OSError as exc:
        # L'extraction passe avant le registre : la reco est écrite, seul son
        # brouillon manquera à la comparaison.
        log.warning("Brouillon de %s non gardé (%s) : sa relecture n'alimentera pas "
                    "le registre des graphies.", reco_id, exc)


# ----- 2. ce que la relecture a corrigé ---------------------------------------

def _ressemble(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, a.casefold(), b.casefold()).ratio() >= _SEUIL_RESSEMBLANCE


def _nom_propre(mots: list[str]) -> bool:
    return all(m[:1].isupper() for m in mots)


def corrections(avant: dict[str, Any], apres: dict[str, Any]) -> list[dict[str, str]]:
    """Les noms corrigés entre le brouillon et la reco validée.

    Ne retient qu'un remplacement court (trois mots au plus de chaque côté),
    qui ressemble à ce qu'il remplace. Dans une citation, seuls les noms
    propres comptent : « drole » → « drôle » n'apprend rien sur Whisper.
    """
    trouvees: list[dict[str, str]] = []
    for champ in CHAMPS:
        mots_avant = _MOT.findall(avant.get(champ) or "")
        mots_apres = _MOT.findall(apres.get(champ) or "")
        blocs = difflib.SequenceMatcher(None, mots_avant, mots_apres, autojunk=False)
        for op, i1, i2, j1, j2 in blocs.get_opcodes():
            if op != "replace" or i2 - i1 > _MAX_MOTS or j2 - j1 > _MAX_MOTS:
                continue
            fausse = " ".join(mots_avant[i1:i2])
            juste = " ".join(mots_apres[j1:j2])
            if fausse.casefold() == juste.casefold() or not _ressemble(fausse, juste):
                continue
            if champ == "quote" and not _nom_propre(mots_apres[j1:j2]):
                continue
            trouvees.append({"fausse": fausse, "juste": juste, "champ": champ})
    return trouvees


def charger() -> list[dict[str, Any]]:
    """Les entrées du registre ; vide s'il est absent ou illisible."""
    chemin = _registre()
    if not chemin.exists():
        return []
    try:
        return list(read_json(chemin).get("entrees") or [])
    except (OSError, ValueError, AttributeError) as exc:
        log.warning("Registre des graphies illisible (%s) : ignoré. %s", chemin, exc)
        return []


def enregistrer(source_id: str, guid: str, recos: list[dict[str, Any]]) -> int:
    """Note les corrections d'un épisode finalisé. Renvoie le nombre de nouveautés.

    Idempotent : un épisode finalisé deux fois ne compte qu'une fois. Les recos
    écartées ne sont pas relues, et une reco sans brouillon gardé (antérieure au
    registre) ne dit rien.
    """
    entrees = charger()
    index = {(e["fausse"], e["juste"]): e for e in entrees}
    nouveautes = 0
    for reco in recos:
        if reco.get("status") != "validated" or not reco.get("id"):
            continue
        chemin = _brouillon(source_id, reco["id"])
        if not chemin.exists():
            continue
        for c in corrections(read_json(chemin), reco):
            entree = index.get((c["fausse"], c["juste"]))
            if entree is None:
                entree = {"fausse": c["fausse"], "juste": c["juste"], "champs": [],
                          "episodes": [], "vu": 0}
                index[(c["fausse"], c["juste"])] = entree
                entrees.append(entree)
            if c["champ"] not in entree["champs"]:
                entree["champs"].append(c["champ"])
            if guid not in entree["episodes"]:
                entree["episodes"].append(guid)
                entree["vu"] += 1
                nouveautes += 1
    if nouveautes:
        _dossier().mkdir(parents=True, exist_ok=True)
        write_json_if_changed(_registre(), {"version": 1, "entrees": entrees})
    return nouveautes


def noter_episode(source_id: str, guid: str, recos: list[dict[str, Any]]) -> int:
    """`enregistrer`, sans jamais bloquer la publication de l'épisode."""
    try:
        n = enregistrer(source_id, guid, recos)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.warning("Registre des graphies non mis à jour pour l'épisode %s : %s", guid, exc)
        return 0
    if n:
        log.info("Registre des graphies : %d correction(s) notée(s) pour %s.", n, guid)
    return n


# ----- 3. les propositions de la relecture ----------------------------------

def _contient(texte: str, forme: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(forme)}(?!\w)", texte, re.IGNORECASE) is not None


def propositions(reco: dict[str, Any],
                 registre: list[dict[str, Any]]) -> list[tuple[str, str, int]]:
    """(forme fausse, forme juste, fois vue) pour chaque faute connue présente.

    Pas de proposition quand le même champ porte déjà la bonne graphie : la
    citation peut citer les deux (« Hillairet, pas Hilleret »).
    """
    trouvees: list[tuple[str, str, int]] = []
    for entree in registre:
        fausse, juste = entree.get("fausse") or "", entree.get("juste") or ""
        if not fausse or not juste:
            continue
        for champ in CHAMPS:
            texte = reco.get(champ) or ""
            if _contient(texte, fausse) and not _contient(texte, juste):
                trouvees.append((fausse, juste, int(entree.get("vu") or 0)))
                break
    return trouvees
