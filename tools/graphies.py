"""graphies.py — Registre des graphies corrigées en relecture.

Décision R6 A d'Étienne, 2026-11-27 (« référencer les différentes corrections
qui sont trouvées pour les appliquer aux futurs épisodes ») : Whisper écrit les
noms au son (« Hilleret » pour Hillairet, « Gat Buzzy » pour Get Busy), la
relecture les corrige, puis la même faute revient à l'épisode suivant.

Trois temps :
  1. en fin de traitement d'un épisode (`garder_brouillons_episode`), une fois
     la réécoute et le calage des citations passés, on garde le brouillon de
     chaque reco encore en brouillon, hors du contenu versionné. Plus tôt, les
     réécritures automatiques des citations passeraient pour des corrections
     de relecture. Un nouveau passage écrase le brouillon, tant que la reco
     n'est pas relue ;
  2. la finalisation compare ce brouillon à la reco validée et note chaque
     nom propre corrigé (`enregistrer`). Le brouillon porte le guid de
     l'épisode : les identifiants de reco sont réutilisés après une
     suppression, un brouillon d'un autre épisode est ignoré ;
  3. la relecture des épisodes suivants PROPOSE la correction (`propositions`,
     encadré « À vérifier », sur les recos encore à relire). Rien n'est jamais
     remplacé seul : « Navo » et « Bruno Muschio » sont la même personne, un
     remplacement aveugle casserait.

Limites connues, voulues ou hors de portée :
  - une forme fautive de moins de 4 signes, comme « Léa », n'entre pas au
    registre (compromis voulu : elle signalerait presque toutes les cartes) ;
  - une extraction lancée à la main par `extract_recos.py`, hors de la chaîne,
    ne garde pas de brouillon ;
  - une reco corrigée sans être validée, puis réextraite, prend son texte
    corrigé comme brouillon.

Un registre qui existe mais ne se lit pas n'est jamais réécrit : la publication
suivante le laisse intact au lieu de l'écraser avec les seules nouveautés.

Les petits mots courants n'entrent jamais au registre (« Le » → « Les » dans
« Le Misérables ») : une forme fautive de moins de 4 signes, ou faite
uniquement de mots courants, signalerait presque toutes les cartes.

Le registre vit dans `tools/output/graphies/registre.json`, hors de Git : un
fichier suivi, modifié par la finalisation, ferait refuser la publication
suivante (« modifications étrangères à l'épisode »). Chemins résolus à l'appel,
pour qu'un test ne touche jamais le vrai registre. La relecture le lit pour
chaque carte : `charger` le garde en mémoire tant que le fichier ne change pas.
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
# Une forme fautive plus courte est trop banale pour être proposée.
_MIN_SIGNES = 4
# Articles, prépositions et conjonctions : « Le » → « Les » n'apprend rien.
_MOTS_COURANTS = frozenset({
    "le", "la", "les", "l", "de", "des", "du", "d", "un", "une", "et", "au", "aux",
    "en", "ou", "à", "a", "the", "an", "of", "and", "in", "on", "to",
})
_MOT = re.compile(r"\w+(?:[-'’]\w+)*")


def _dossier() -> Path:
    return common.OUTPUT_DIR / "graphies"


def _registre() -> Path:
    return _dossier() / "registre.json"


def _brouillon(source_id: str, reco_id: str) -> Path:
    return _dossier() / "brouillons" / source_id / f"{reco_id}.json"


# ----- 1. le brouillon d'origine --------------------------------------------

def garder_brouillon(source_id: str, reco: dict[str, Any]) -> bool:
    """Garde les champs textuels d'une reco encore en brouillon, en écrasant le précédent.

    Une reco relue (validée, écartée) n'écrase rien : son brouillon, déjà gardé,
    est la référence que la finalisation compare. Renvoie vrai si la reco était
    à garder (et non si le fichier a changé).
    """
    reco_id = reco.get("id")
    if not reco_id or reco.get("status", "draft") != "draft":
        return False
    chemin = _brouillon(source_id, reco_id)
    contenu = {k: reco[k] for k in CHAMPS if reco.get(k)}
    contenu["episodeGuid"] = reco.get("episodeGuid")
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        write_json_if_changed(chemin, contenu)
    except OSError as exc:
        # L'extraction passe avant le registre : la reco est écrite, seul son
        # brouillon manquera à la comparaison.
        log.warning("Brouillon de %s non gardé (source %s, fichier %s : %s) : sa relecture "
                    "n'alimentera pas le registre des graphies.", reco_id, source_id, chemin, exc)
    return True


def garder_brouillons_episode(source_id: str, guid: str) -> int:
    """Garde le brouillon de chaque reco encore en brouillon de l'épisode.

    À appeler quand l'épisode est traité en entier (après la réécoute et le
    calage des citations), jamais sur la sortie brute du modèle. Ne lève rien :
    la chaîne ne doit pas s'arrêter pour un registre. Renvoie le nombre de recos
    gardées.
    """
    gardees = 0
    try:
        chemins = sorted(common.recos_dir_for(source_id).glob("*.json"))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        log.warning("Brouillons de l'épisode %s (source %s) non gardés : dossier des recos "
                    "illisible (%s).", guid, source_id, exc)
        return 0
    for chemin in chemins:
        try:
            reco = read_json(chemin)
            if isinstance(reco, dict) and reco.get("episodeGuid") == guid:
                gardees += garder_brouillon(source_id, reco)
        except Exception as exc:  # noqa: BLE001 — jamais d'erreur vers la chaîne
            log.warning("Reco %s illisible ou inattendue (source %s, épisode %s : %s) : "
                        "son brouillon n'est pas gardé.", chemin, source_id, guid, exc)
    return gardees


# ----- 2. ce que la relecture a corrigé ---------------------------------------

def _ressemble(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, a.casefold(), b.casefold()).ratio() >= _SEUIL_RESSEMBLANCE


def _nom_propre(mots: list[str]) -> bool:
    return all(m[:1].isupper() for m in mots)


def _distinctive(mots: list[str]) -> bool:
    """Vrai si la forme n'est ni trop courte ni faite que de mots courants."""
    if len(" ".join(mots)) < _MIN_SIGNES:
        return False
    return any(m.casefold() not in _MOTS_COURANTS for m in mots)


def corrections(avant: dict[str, Any], apres: dict[str, Any]) -> list[dict[str, str]]:
    """Les noms corrigés entre le brouillon et la reco validée.

    Ne retient qu'un remplacement court (trois mots au plus de chaque côté),
    qui ressemble à ce qu'il remplace, dont la bonne graphie est un nom propre
    (dans tous les champs : « drole » → « drôle » n'apprend rien sur Whisper)
    et dont la forme fautive n'est pas un petit mot courant.
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
            if not _nom_propre(mots_apres[j1:j2]) or not _distinctive(mots_avant[i1:i2]):
                continue
            trouvees.append({"fausse": fausse, "juste": juste, "champ": champ})
    return trouvees


def _entree_valide(entree: Any) -> dict[str, Any] | None:
    """L'entrée du registre complétée de ses valeurs par défaut, ou rien si inutilisable."""
    if not isinstance(entree, dict):
        return None
    fausse, juste = entree.get("fausse"), entree.get("juste")
    if not (isinstance(fausse, str) and fausse and isinstance(juste, str) and juste):
        return None
    champs, episodes, vu = entree.get("champs"), entree.get("episodes"), entree.get("vu")
    return {**entree,
            "champs": champs if isinstance(champs, list) else [],
            "episodes": episodes if isinstance(episodes, list) else [],
            "vu": vu if isinstance(vu, int) and not isinstance(vu, bool) else 0}


class RegistreIllisible(Exception):
    """Le fichier du registre existe mais ne se lit pas : on n'y écrit rien."""


def _lire() -> tuple[list[dict[str, Any]], list[Any]]:
    """(entrées utilisables, entrées mal formées telles quelles), lues sans cache.

    Un registre absent vaut vide ; un registre qui existe sans se lire lève
    `RegistreIllisible`. Les entrées mal formées sont rendues pour qu'une
    réécriture les garde au lieu de les effacer sans trace.
    """
    chemin = _registre()
    if not chemin.exists():
        return [], []
    try:
        brutes = read_json(chemin).get("entrees")
    except (OSError, ValueError, AttributeError) as exc:
        raise RegistreIllisible(f"{chemin} illisible ({exc})") from exc
    if brutes is None:
        return [], []
    if not isinstance(brutes, list):
        raise RegistreIllisible(f"{chemin} : « entrees » n'est pas une liste")
    entrees = [e for e in map(_entree_valide, brutes) if e is not None]
    ecartees = [b for b in brutes if _entree_valide(b) is None]
    if ecartees:
        log.warning("Registre des graphies : %d entrée(s) mal formée(s) ignorée(s), "
                    "gardées telles quelles dans le fichier (%s).", len(ecartees), chemin)
    return entrees, ecartees


# Dernière lecture : (chemin, date de modification, taille) -> entrées.
_cache: dict[str, Any] = {"cle": None, "entrees": []}


def charger() -> list[dict[str, Any]]:
    """Les entrées du registre, pour la relecture : ne les modifiez pas.

    Les pages de relecture l'appellent pour chaque carte ; le fichier n'est relu
    que s'il a changé. `enregistrer`, qui modifie les entrées, passe par `_lire`.
    """
    chemin = _registre()
    try:
        stat = chemin.stat()
    except OSError:
        return []
    cle = (str(chemin), stat.st_mtime_ns, stat.st_size)
    if _cache["cle"] != cle:
        try:
            _cache["entrees"] = _lire()[0]
        except RegistreIllisible as exc:
            # Un échec de lecture ne se met jamais en cache : le prochain appel relit.
            _cache["cle"] = None
            log.warning("Registre des graphies ignoré pour la relecture : %s", exc)
            return []
        _cache["cle"] = cle
    return _cache["entrees"]


def enregistrer(source_id: str, guid: str, recos: list[dict[str, Any]]) -> int:
    """Note les corrections d'un épisode finalisé. Renvoie le nombre de nouveautés.

    Idempotent : un épisode finalisé deux fois ne compte qu'une fois. Les recos
    écartées ne sont pas relues, une reco sans brouillon gardé (antérieure au
    registre) ne dit rien, et un brouillon illisible ou d'un autre épisode
    (identifiant de reco réutilisé) est passé, sans toucher aux autres recos.
    """
    try:
        entrees, ecartees = _lire()
    except RegistreIllisible as exc:
        log.error("Registre des graphies non mis à jour (source %s, épisode %s) : %s ; "
                  "fichier laissé intact.", source_id, guid, exc)
        return 0
    index = {(e["fausse"], e["juste"]): e for e in entrees}
    nouveautes = 0
    for reco in recos:
        if reco.get("status") != "validated" or not reco.get("id"):
            continue
        brouillon = _brouillon_de(source_id, reco["id"], guid)
        if brouillon is None:
            continue
        reco = _champs_texte(reco, source_id, reco["id"], f"reco validée de l'épisode {guid}")
        for c in corrections(brouillon, reco):
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
        write_json_if_changed(_registre(), {"version": 1, "entrees": entrees + ecartees})
    return nouveautes


def _brouillon_de(source_id: str, reco_id: str, guid: str) -> dict[str, Any] | None:
    """Le brouillon gardé d'une reco, ou rien s'il manque, est illisible ou vient d'un autre épisode."""
    chemin = _brouillon(source_id, reco_id)
    if not chemin.exists():
        return None
    try:
        brouillon = read_json(chemin)
    except (OSError, ValueError) as exc:
        log.warning("Brouillon de %s illisible (source %s, fichier %s : %s) : cette reco "
                    "n'alimente pas le registre des graphies.", reco_id, source_id, chemin, exc)
        return None
    if not isinstance(brouillon, dict):
        log.warning("Brouillon de %s mal formé (source %s, fichier %s) : cette reco "
                    "n'alimente pas le registre des graphies.", reco_id, source_id, chemin)
        return None
    if brouillon.get("episodeGuid") != guid:
        log.warning("Brouillon de %s ignoré (source %s, fichier %s) : il vient de l'épisode %s, "
                    "pas de %s (identifiant de reco réutilisé).",
                    reco_id, source_id, chemin, brouillon.get("episodeGuid"), guid)
        return None
    return _champs_texte(brouillon, source_id, reco_id, f"brouillon {chemin}")


def _champs_texte(donnees: dict[str, Any], source_id: str, reco_id: str,
                  origine: str) -> dict[str, Any]:
    """Les données sans les champs textuels qui ne sont pas une chaîne (avertissement).

    Un fichier écrit à la main ou par une version future peut porter
    `"creator": 5` : le champ est ignoré pour cette reco, et les autres recos de
    l'épisode comptent quand même.
    """
    propres = dict(donnees)
    for champ in CHAMPS:
        if champ in propres and not isinstance(propres[champ], str):
            log.warning("Champ %s de %s ignoré (source %s, %s) : %s au lieu d'une chaîne.",
                        champ, reco_id, source_id, origine, type(propres[champ]).__name__)
            del propres[champ]
    return propres


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

def _contient(texte: str, forme: str, *, casse: bool = False) -> bool:
    """Vrai si la forme est dans le texte, mot entier. Avec `casse`, la forme telle
    quelle ou toute en capitales (« HILLERET »), jamais en minuscules."""
    formes = [forme, forme.upper()] if casse else [forme]
    motif = "|".join(map(re.escape, formes))
    return re.search(rf"(?<!\w)(?:{motif})(?!\w)", texte,
                     0 if casse else re.IGNORECASE) is not None


def propositions(reco: dict[str, Any],
                 registre: list[dict[str, Any]]) -> list[tuple[str, str, int]]:
    """(forme fausse, forme juste, fois vue) pour chaque faute connue présente.

    Pas de proposition quand un des champs porte déjà la bonne graphie : la
    citation peut citer les deux (« Hillairet, pas Hilleret »), et la fiche
    peut déjà avoir été corrigée dans un autre champ. Une forme fautive à
    majuscule se cherche avec sa casse, ou toute en capitales : « Les » n'est pas
    « les ». Une entrée trop courte ou banale, déjà au registre d'avant le filtre
    de `_distinctive`, n'est jamais proposée.
    """
    textes = [reco.get(champ) or "" for champ in CHAMPS]
    trouvees: list[tuple[str, str, int]] = []
    for entree in registre:
        fausse, juste = entree.get("fausse") or "", entree.get("juste") or ""
        if not fausse or not juste or not _distinctive(_MOT.findall(fausse)):
            continue
        if any(_contient(t, juste) for t in textes):
            continue
        casse = fausse[:1].isupper()
        if any(_contient(t, fausse, casse=casse) for t in textes):
            trouvees.append((fausse, juste, int(entree.get("vu") or 0)))
    return trouvees
