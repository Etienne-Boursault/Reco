"""
bord_chaine.py — le bloc « Chaîne » du tableau de bord d'admin.

Décision : tableau de bord, R2 B du 27/11/2026 et TB-1 C du 28/11/2026.

Rend, sans rien écrire :
  - l'épisode en cours : le plus récent des épisodes `yt-…` pas encore publiés
    et plus récent que le dernier publié (tour 1, M2) ; à défaut, le dernier
    publié, par date de fiche (sa fiche peut manquer : la publication la retire
    du clone jusqu'à la fusion de la PR, on n'a alors que son guid) ;
  - ses étapes, chacune avec son état, son heure et la source qui le dit ;
  - les dernières erreurs signalées par la chaîne ;
  - les derniers passages de `deploy/venus/tick.sh`, lus dans `passages.jsonl`, et le
    début du passage qui tourne, lu dans `en-cours` (tour 1, F8 repris, 28/11/2026 :
    `tick.sh` ne note un passage qu'à sa fin).

Relecture du plan, R7 (28/11/2026) : l'étape `detecter` n'est pas mesurée, donc
« Détecté » n'a jamais d'heure ; « Publié » vient de `published`, puis de la PR fusionnée
(`merged_at`, tour 1 de la PR 3, M2) : la route passe `fusionnees` (`{branche: date}`, lue une
seule fois dans `bord_github`), et un épisode dont la branche `contenu/<slug>` y figure est
publié à la date de fusion, même si l'état de la chaîne ou le clone ne le disent pas. Une
donnée absente donne « inconnu », jamais
« fait » ni « à venir ». Les heures viennent toutes de la télémétrie
(`stage_attempts`, dernière tentative réussie), lue en `mode=ro`.

Le dossier du bord (`tools/output/bord/`) se règle par `RECO_BORD_DIR`
(`bord_reseaux.dossier`), comme dans `tick.sh`, qui y écrit `passages.jsonl` et `en-cours`.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import common
from bord_reseaux import branche_de
from bord_reseaux import dossier as bord_dir

INCONNU = "inconnu"
_FICHE = "fiche de l'épisode"
_ETAT = "état de la chaîne"
_TELEMETRIE = "télémétrie"
_PR_FUSIONNEE = "PR fusionnée"
_TRANSCRIT = {"auto", "validated"}


def _lire_etat(source_id: str) -> dict[str, Any] | None:
    """Fichier d'état de `traiter_nouveaux_episodes`, ou None s'il manque ou est illisible."""
    path = common.OUTPUT_DIR / "pipeline" / f"{common.slugify(source_id)}.json"
    try:
        etat = common.read_json(path)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        common.log.warning("bord_chaine : état de la chaîne illisible (%s) : %s", path, exc)
        return None
    return etat if isinstance(etat, dict) else None


def _episodes_yt(source_id: str) -> list[dict[str, Any]]:
    out = []
    for path in common.list_episode_files(source_id):
        if not path.name.startswith("yt-"):
            continue
        try:
            episode = common.read_json(path)
        except (OSError, ValueError) as exc:
            common.log.warning("bord_chaine : fiche d'épisode illisible (%s) : %s", path, exc)
            continue
        if isinstance(episode, dict) and str(episode.get("guid", "")).startswith("yt-"):
            out.append(episode)
    return out


def _episode_en_cours(episodes: list[dict[str, Any]], etat: dict[str, Any] | None,
                      fusionnes: list[str]) -> tuple[str, dict[str, Any] | None] | None:
    """(guid, fiche ou None) de l'épisode à montrer, ou None s'il n'y en a aucun.

    `fusionnes` : les guids dont la PR est fusionnée, publiés même absents de `published`.
    """
    publies = [str(g) for g in (etat or {}).get("published") or []]
    publies += [g for g in fusionnes if g not in publies]
    fiches = {e["guid"]: e for e in episodes}

    def date(e: dict[str, Any]) -> str:
        return str(e.get("date") or "")

    # Tour 1, M2 : n'est « en cours » qu'un épisode plus récent que le dernier
    # publié connu ; un vieil épisode resté hors de `published` n'en est pas un.
    dernier = max((date(fiches[g]) for g in publies if g in fiches), default=None)
    en_cours = sorted((e for e in episodes if e["guid"] not in publies
                       and (dernier is None or date(e) > dernier)),
                      key=lambda e: (date(e), e["guid"]))
    if en_cours:
        return en_cours[-1]["guid"], en_cours[-1]
    if publies:
        # Le plus récent des publiés, par date de fiche : un publié sans fiche
        # (la publication l'a retirée du clone) est le plus récent, puis la position.
        guid = max(publies, key=lambda g: (g not in fiches, date(fiches.get(g, {})),
                                           publies.index(g)))
        return guid, fiches.get(guid)
    return None


def heures_etapes(db_path: Path, source_id: str, guid: str) -> dict[str, str]:
    """Fin de la dernière tentative réussie de chaque étape mesurée de l'épisode."""
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        try:
            lignes = conn.execute(
                "SELECT stage, MAX(ended_at) FROM stage_attempts WHERE source_id = ? "
                "AND episode_guid = ? AND status = 'succeeded' AND ended_at IS NOT NULL "
                "GROUP BY stage", [source_id, guid]).fetchall()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        common.log.warning("bord_chaine : télémétrie illisible (%s) pour %s : %s",
                           db_path, guid, exc)
        return {}
    return {stage: fin for stage, fin in lignes}


def _etape(cle: str, libelle: str, etat: str, heure: str | None, source: str) -> dict[str, Any]:
    return {"cle": cle, "libelle": libelle, "etat": etat, "heure": heure, "source": source}


def _selon_etat(cle: str, libelle: str, liste: str, guid: str, etat: dict[str, Any] | None,
                heure: str | None) -> dict[str, Any]:
    """Étape dite par une liste du fichier d'état ; la télémétrie supplée à l'état absent."""
    if etat is not None:
        fait = guid in (etat.get(liste) or [])
        return _etape(cle, libelle, "fait" if fait else "a_venir", heure, _ETAT)
    if heure:
        return _etape(cle, libelle, "fait", heure, _TELEMETRIE)
    return _etape(cle, libelle, INCONNU, None, INCONNU)


def etapes(guid: str, fiche: dict[str, Any] | None, etat: dict[str, Any] | None,
           heures: dict[str, str], fusion: str | None = None) -> list[dict[str, Any]]:
    """Les cinq étapes de l'épisode, de « Détecté » à « Publié » ; `fusion` : date de fusion de sa PR."""
    if fiche is not None:
        detecte = _etape("detecte", "Détecté", "fait", None, _FICHE)
        transcrit = fiche.get("transcriptStatus") in _TRANSCRIT
        transcription = _etape("transcrit", "Transcrit", "fait" if transcrit else "a_venir",
                               heures.get("transcribe"), _FICHE)
    else:  # seul un épisode publié est montré sans fiche : la publication l'a retirée
        detecte = _etape("detecte", "Détecté", "fait", None, _ETAT)
        transcription = _etape("transcrit", "Transcrit", "fait", heures.get("transcribe"), _ETAT)
    publie = _selon_etat("publie", "Publié", "published", guid, etat, None)
    if fusion and publie["etat"] != "fait":  # tour 1, M2 : la PR fusionnée suffit
        publie = _etape("publie", "Publié", "fait", fusion, _PR_FUSIONNEE)
    return [
        detecte,
        transcription,
        _selon_etat("extrait", "Extrait", "extracted", guid, etat, heures.get("extract")),
        _selon_etat("finalise", "Finalisé", "finalized", guid, etat, heures.get("finalize")),
        publie,
    ]


def lire_passages(path: Path, n: int) -> list[dict[str, Any]] | None:
    """Les `n` derniers passages, du plus récent au plus ancien ; None sans journal lisible."""
    try:
        lignes = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        common.log.warning("bord_chaine : journal des passages illisible (%s) : %s", path, exc)
        return None
    passages = []
    for ligne in reversed(lignes):
        try:
            passage = json.loads(ligne)
        except ValueError:
            continue  # ligne coupée par un passage interrompu : la suivante compte
        if isinstance(passage, dict):
            passages.append(passage)
            if len(passages) == n:
                break
    return passages


def lire_en_cours(path: Path) -> str | None:
    """Début du passage en cours (fichier écrit par `tick.sh`), ou None s'il manque ou est illisible."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        common.log.warning("bord_chaine : fichier du passage en cours illisible (%s) : %s", path, exc)
        return None


def etat_chaine(source_id: str, *, db_path: Path | None = None, nb_passages: int = 5,
                fusionnees: dict[str, Any] | None = None) -> dict[str, Any]:
    """Tout le bloc « Chaîne » : épisode en cours, étapes, erreurs, derniers passages.

    `fusionnees` : `{branche: date de fusion}` de `bord_afaire.branches_fusionnees` (M2).
    """
    etat = _lire_etat(source_id)
    fusions = fusionnees or {}
    fiches = _episodes_yt(source_id)
    fusionnes = [e["guid"] for e in fiches if branche_de(e["guid"]) in fusions]
    choix = _episode_en_cours(fiches, etat, fusionnes)
    if db_path is None:
        from telemetry.recorder import default_db_path
        db_path = default_db_path()
    episode, liste = None, []
    if choix is not None:
        guid, fiche = choix
        episode = {"guid": guid, "titre": (fiche or {}).get("title"),
                   "date": (fiche or {}).get("date")}
        liste = etapes(guid, fiche, etat, heures_etapes(db_path, source_id, guid),
                       fusions.get(branche_de(guid)))
    signalees = (etat or {}).get("lastErrors")
    # Toutes : l'état est écrit trié par clé, un plafond garderait les premières
    # par ordre alphabétique et cacherait la dernière (tour 1, M1).
    erreurs = [str(m) for m in signalees.values()] if isinstance(signalees, dict) else []
    # `etat_lu` : l'état a été lu, même sans épisode à montrer (tour 1, F3).
    return {"episode": episode, "etapes": liste, "erreurs": erreurs, "etat_lu": etat is not None,
            "passages": lire_passages(bord_dir() / "passages.jsonl", nb_passages),
            "en_cours": lire_en_cours(bord_dir() / "en-cours")}
