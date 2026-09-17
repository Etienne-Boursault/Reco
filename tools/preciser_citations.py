"""
preciser_citations.py — réécoute les quelques secondes d'où vient chaque citation,
en soufflant à Whisper les noms que l'extraction a reconnus.

La citation d'une reco est reprise TELLE QUELLE de la transcription et s'affiche
sur le site. Or Whisper écorche les noms propres : « Straumai » pour Stromae,
« Scret » pour Skread. Le modèle d'extraction, lui, rétablit le nom correct dans
le titre et le créateur de la reco — il sait donc ce que la transcription a raté.

On retranscrit alors la fenêtre d'où vient la citation (15 s avant l'horodatage,
25 s après) en donnant ces noms en indices (`hotwords`). Mesuré le 2026-09-17 :
sur un extrait, une liste de noms JUSTE fait apparaître « Skread » cinq fois là
où aucun autre réglage ne le trouvait ; et les extraits courts ponctuent bien,
alors qu'un épisode entier dérive au fil des fenêtres.

Garde-fous — la citation n'est remplacée que si les deux conditions tiennent :
  - le nouveau texte parle bien du même passage (similarité ≥ 0,45) ;
  - il rétablit au moins un nom que l'ancienne citation n'avait pas.
Sans `--apply`, rien n'est écrit.

Usage :
    cd tools
    python preciser_citations.py --source un-bon-moment --guid yt-XXXX [--apply] [--json]
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from common import (
    find_episode_by_guid,
    load_source,
    log,
    read_json,
    recos_dir_for,
    write_json_if_changed,
)

FENETRE_AVANT = 15.0
FENETRE_APRES = 25.0
SIMILARITE_MIN = 0.45
MODELE = "large-v3-turbo"

Transcripteur = Callable[[Path, float, float, str], list[str]]


@dataclass
class Precision:
    reco_id: str
    ancienne: str
    nouvelle: str
    noms_repares: list[str]


@dataclass
class Bilan:
    guid: str
    examinees: int = 0
    precisees: list[Precision] = field(default_factory=list)
    inchangees: int = 0
    sans_horodatage: list[str] = field(default_factory=list)
    erreurs: list[str] = field(default_factory=list)


def _norm(texte: str) -> str:
    texte = unicodedata.normalize("NFD", (texte or "").lower())
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", texte).strip()


def _secondes(horodatage: str | None) -> float | None:
    if not isinstance(horodatage, str):
        return None
    morceaux = horodatage.strip().split(":")
    if not all(m.isdigit() for m in morceaux) or not 2 <= len(morceaux) <= 3:
        return None
    valeurs = [int(m) for m in morceaux]
    while len(valeurs) < 3:
        valeurs.insert(0, 0)
    return valeurs[0] * 3600 + valeurs[1] * 60 + valeurs[2]


def noms_de(reco: dict[str, Any], source: dict[str, Any]) -> list[str]:
    """Les noms que l'extraction a reconnus, plus les animateurs."""
    candidats = [reco.get("title"), reco.get("creator"), reco.get("recommendedBy")]
    noms = []
    for valeur in [*candidats, *source.get("hosts", [])]:
        if isinstance(valeur, str) and valeur.strip() and valeur.strip() not in noms:
            noms.append(valeur.strip())
    return noms


def indices_de(noms: list[str]) -> str:
    return ", ".join(noms) + "."


def _meilleure_portion(segments: list[str], ancienne: str) -> tuple[str, float]:
    """Portion du nouveau texte qui correspond le mieux à l'ancienne citation.

    On part du segment le plus ressemblant, puis on étend tant que la
    ressemblance monte : une citation tient souvent sur deux ou trois segments.
    """
    if not segments:
        return "", 0.0
    cible = _norm(ancienne)

    def score(texte: str) -> float:
        return difflib.SequenceMatcher(None, cible, _norm(texte)).ratio()

    debut = max(range(len(segments)), key=lambda i: score(segments[i]))
    fin = debut
    meilleur = score(segments[debut])
    progresse = True
    while progresse:
        progresse = False
        for nouveau_debut, nouvelle_fin in ((debut - 1, fin), (debut, fin + 1)):
            if nouveau_debut < 0 or nouvelle_fin >= len(segments):
                continue
            candidat = score(" ".join(segments[nouveau_debut:nouvelle_fin + 1]))
            if candidat > meilleur:
                debut, fin, meilleur, progresse = nouveau_debut, nouvelle_fin, candidat, True
    return " ".join(segments[debut:fin + 1]).strip(), meilleur


def _transcripteur_whisper(model_name: str = MODELE,
                           compute_type: str = "int8") -> Transcripteur:
    modele: dict[str, Any] = {}

    def transcrire(audio: Path, debut: float, fin: float, indices: str) -> list[str]:
        if "m" not in modele:
            from faster_whisper import WhisperModel
            modele["m"] = WhisperModel(model_name, device="cpu", compute_type=compute_type)
        segments, _ = modele["m"].transcribe(
            str(audio), language="fr", beam_size=5, vad_filter=True,
            hotwords=indices, clip_timestamps=[debut, fin],
        )
        return [s.text.strip() for s in segments]

    return transcrire


def preciser_episode(source_id: str, guid: str, *, apply: bool = False,
                     transcripteur: Transcripteur | None = None,
                     audio: Path | None = None) -> Bilan:
    bilan = Bilan(guid)
    source = load_source(source_id)
    recos = []
    dossier = recos_dir_for(source_id)
    for chemin in sorted(dossier.glob("*.json")) if dossier.is_dir() else []:
        reco = read_json(chemin)
        if reco.get("episodeGuid") == guid and reco.get("status") != "discarded":
            recos.append((chemin, reco))
    if not recos:
        bilan.erreurs.append(f"aucune reco à préciser pour l'épisode {guid}")
        return bilan

    a_faire = [(c, r) for c, r in recos if _secondes(r.get("timestamp")) is not None and r.get("quote")]
    ids_a_faire = {r["id"] for _chemin, r in a_faire}
    bilan.sans_horodatage = sorted(r["id"] for _chemin, r in recos if r["id"] not in ids_a_faire)
    if not a_faire:
        return bilan

    if audio is None:
        from transcribe import _resolve_audio
        audio, _source_utilisee = _resolve_audio(source_id, read_json(find_episode_by_guid(source_id, guid)))
    if transcripteur is None:
        transcripteur = _transcripteur_whisper()

    for chemin, reco in a_faire:
        bilan.examinees += 1
        instant = _secondes(reco["timestamp"])
        noms = noms_de(reco, source)
        try:
            segments = transcripteur(audio, max(0.0, instant - FENETRE_AVANT),
                                     instant + FENETRE_APRES, indices_de(noms))
        except Exception as exc:  # noqa: BLE001 — une reco ratée n'arrête pas les autres.
            bilan.erreurs.append(f"{reco['id']} : {type(exc).__name__}: {str(exc)[:120]}")
            continue
        nouvelle, similarite = _meilleure_portion(segments, reco["quote"])
        ancienne_norm, nouvelle_norm = _norm(reco["quote"]), _norm(nouvelle)
        repares = [n for n in noms if _norm(n) and _norm(n) in nouvelle_norm
                   and _norm(n) not in ancienne_norm]
        if similarite < SIMILARITE_MIN or not repares:
            bilan.inchangees += 1
            continue
        bilan.precisees.append(Precision(reco["id"], reco["quote"], nouvelle, repares))
        if apply:
            write_json_if_changed(chemin, {**reco, "quote": nouvelle})
    return bilan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", required=True)
    parser.add_argument("--guid", required=True)
    parser.add_argument("--apply", action="store_true", help="Écrit ; sinon simulation.")
    parser.add_argument("--json", action="store_true", help="Bilan en JSON sur stdout.")
    parser.add_argument("--force", action="store_true",
                        help="Ignore le verrou du review_server.")
    args = parser.parse_args(argv)

    if args.apply:
        from review_lock import LockBusy, acquire_pipeline_lock
        try:
            with acquire_pipeline_lock(force=args.force):
                bilan = preciser_episode(args.source, args.guid, apply=True)
        except LockBusy as exc:
            log.error("%s", exc)
            return 2
    else:
        bilan = preciser_episode(args.source, args.guid)

    if args.json:
        print(json.dumps(asdict(bilan), ensure_ascii=False))
    for precision in bilan.precisees:
        log.info("%s : %s", precision.reco_id, ", ".join(precision.noms_repares))
        log.info("   avant : %s", precision.ancienne)
        log.info("   après : %s", precision.nouvelle)
    for erreur in bilan.erreurs:
        log.error("%s", erreur)
    log.info("%s — %d citation(s) examinée(s), %d précisée(s), %d inchangée(s)%s",
             "Écrit" if args.apply else "Simulation", bilan.examinees,
             len(bilan.precisees), bilan.inchangees,
             f", {len(bilan.sans_horodatage)} sans horodatage" if bilan.sans_horodatage else "")
    return 2 if bilan.erreurs and not bilan.examinees else 0


if __name__ == "__main__":
    sys.exit(main())
