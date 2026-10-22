"""
banc_modeles.py — mesurer un modele d'extraction avant de l'adopter.

POURQUOI
--------
Changer de modele change ce que la chaine trouve (cf. `modeles_llm.py`). Avant
de toucher a `RECO_MODELE_EXTRACTION`, on rejoue l'extraction sur des episodes
DEJA RELUS et on compare a la relecture humaine, comme le 2026-09-17 :

- retrouvees : recos validees que le modele propose (le rappel — une reco
  manquee est perdue, la relecture ne la rattrape pas) ;
- deja ecartees : propositions que la relecture avait refusees (du bruit) ;
- autres : propositions absentes du corpus (bruit, ou vraie reco jamais vue) ;
- cout par episode, aux tarifs publics.

Meme decoupage, meme consigne et meme effort que `extract_recos.py`. Rien n'est
ecrit dans le corpus : le rapport va dans `tools/output/banc_modeles/`.

Usage (sur venus, ou se trouvent transcriptions et cle) :
    python banc_modeles.py --source un-bon-moment --modeles claude-opus-5 claude-opus-5-5
    python banc_modeles.py --source un-bon-moment --plan   # nombre d'appels, sans rien appeler

Chaque appel coute : environ 0,56 $ par episode et par modele avec Opus 5.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common
import extraction_mesures
import modeles_llm
import telemetry
from common import (
    atomic_write_text,
    list_episode_files,
    load_source,
    read_json,
    recos_dir_for,
    transcript_path_for,
)
from extract_recos import (
    _chunk_transcript,
    _dedupe,
    _intervenants,
    _norm,
    _normalize_reco,
    _parse_recos_from_content,
    _request_params,
)
from telemetry import llm
from transcription_mesures import saison

log = logging.getLogger("reco.banc")

SEUIL_RESSEMBLANCE = 0.85
RELUS = {"validated", "discarded"}


@dataclass
class Resultat:
    modele: str
    episodes: int = 0
    candidats: int = 0
    a_retrouver: int = 0
    retrouvees: int = 0
    ecartees_reproposees: int = 0
    autres: int = 0
    jetons_entree: int = 0
    jetons_sortie: int = 0
    secondes: float = 0.0
    manquees: list[str] = field(default_factory=list)

    @property
    def cout(self) -> float | None:
        return modeles_llm.cout(self.modele, self.jetons_entree, self.jetons_sortie)


def meme_titre(a: str, b: str) -> bool:
    """Titres equivalents : egaux une fois normalises, tres proches, ou l'un
    contenant TOUS les mots de l'autre et au moins la moitie des siens
    (« Fleabag » / « Fleabag (serie) », mais pas « Alien » / « Aliens vs
    Predator »)."""
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb or SequenceMatcher(None, na, nb).ratio() >= SEUIL_RESSEMBLANCE:
        return True
    court, long_ = sorted((set(na.split()), set(nb.split())), key=len)
    return court <= long_ and len(court) * 2 >= len(long_)


def _recos_relues(source_id: str) -> dict[str, list[dict[str, Any]]]:
    par_episode: dict[str, list[dict[str, Any]]] = {}
    for chemin in sorted(recos_dir_for(source_id).glob("*.json")):
        reco = read_json(chemin)
        par_episode.setdefault(reco.get("episodeGuid", ""), []).append(reco)
    return par_episode


def episodes_relus(source_id: str, nombre: int) -> list[dict[str, Any]]:
    """Les `nombre` episodes les plus recents entierement relus et transcrits."""
    recos = _recos_relues(source_id)
    candidats = []
    for chemin in list_episode_files(source_id):
        episode = read_json(chemin)
        siennes = recos.get(episode["guid"], [])
        if (siennes and all(r.get("status") in RELUS for r in siennes)
                and any(r.get("status") == "validated" for r in siennes)
                and transcript_path_for(source_id, episode["guid"]).exists()):
            candidats.append(episode)
    candidats.sort(key=lambda e: str(e.get("date") or e.get("pubDate") or ""), reverse=True)
    return candidats[:nombre]


def comparer(propositions: list[dict[str, Any]], relues: list[dict[str, Any]],
             resultat: Resultat) -> None:
    validees = [r for r in relues if r.get("status") == "validated"]
    ecartees = [r for r in relues if r.get("status") == "discarded"]
    titres = [p.get("title", "") for p in propositions]
    resultat.candidats += len(propositions)
    resultat.a_retrouver += len(validees)
    for reco in validees:
        if any(meme_titre(reco.get("title", ""), t) for t in titres):
            resultat.retrouvees += 1
        else:
            resultat.manquees.append(reco.get("title", ""))
    for titre in titres:
        if any(meme_titre(titre, r.get("title", "")) for r in validees):
            continue
        if any(meme_titre(titre, r.get("title", "")) for r in ecartees):
            resultat.ecartees_reproposees += 1
        else:
            resultat.autres += 1


def extraire(client: Any, modele: str, source: dict[str, Any], episode: dict[str, Any],
             texte: str, resultat: Resultat) -> list[dict[str, Any]]:
    """Meme requete que la chaine, mais rien n'est ecrit : on garde l'usage."""
    titre = source.get("title", source.get("id", ""))
    hotes = _intervenants(source, episode)
    brutes: list[dict[str, Any]] = []
    morceaux = _chunk_transcript(texte)
    for index, morceau in enumerate(morceaux):
        params = _request_params(modele, titre, hotes, morceau)
        with llm.chunk(index, len(morceaux), len(morceau)), \
                llm.appel("anthropic", modele, request=llm.requete(params),
                          client=client) as appel:
            message = client.messages.create(**params)
            appel.reponse(message)
            resultat.jetons_entree += message.usage.input_tokens
            resultat.jetons_sortie += message.usage.output_tokens
            recos = _parse_recos_from_content(message.content)
            appel.candidats(len(recos))
        brutes.extend(recos)
    return _dedupe([r for r in (_normalize_reco(b) for b in brutes) if r])


def mesurer(client: Any, source_id: str, modeles: list[str],
            episodes: list[dict[str, Any]], *, horloge=time.monotonic) -> list[Resultat]:
    source = load_source(source_id)
    relues = _recos_relues(source_id)
    resultats = []
    for modele in modeles:
        modeles_llm.noter_capacites(client, modele)
        resultat = Resultat(modele)
        debut = horloge()
        for episode in episodes:
            texte = transcript_path_for(source_id, episode["guid"]).read_text(encoding="utf-8")
            # Une expérience : jamais mêlée aux passes nominales des métriques.
            with telemetry.stage("extract", source_id=source_id, command="banc_modeles",
                                 episode_guid=episode["guid"], season=saison(episode),
                                 intent="experiment",
                                 **extraction_mesures.champs_etape("anthropic", modele, "sync")
                                 ) as etape:
                propositions = extraire(client, modele, source, episode, texte, resultat)
                etape.measure("unique_candidates", len(propositions), "count")
            comparer(propositions, relues.get(episode["guid"], []), resultat)
            resultat.episodes += 1
        resultat.secondes = horloge() - debut
        resultats.append(resultat)
    return resultats


def tableau(resultats: list[Resultat]) -> str:
    lignes = ["| Modèle | $/épisode | Candidats | Retrouvées | Déjà écartées | Autres |",
              "|---|---|---|---|---|---|"]
    for r in resultats:
        par_episode = (f"{r.cout / r.episodes:.2f}" if r.cout is not None and r.episodes
                       else "inconnu")
        lignes.append(f"| {r.modele} | {par_episode} | {r.candidats} | "
                      f"{r.retrouvees} / {r.a_retrouver} | {r.ecartees_reproposees} | {r.autres} |")
    return "\n".join(lignes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", required=True)
    parser.add_argument("--modeles", nargs="+",
                        help="Défaut : le modèle configuré et son secours.")
    parser.add_argument("--episodes", type=int, default=3,
                        help="Épisodes relus les plus récents (défaut : %(default)s).")
    parser.add_argument("--plan", action="store_true",
                        help="Affiche les appels prévus, sans rien appeler.")
    args = parser.parse_args(argv)

    modeles = args.modeles or [m for m in (modeles_llm.modele_extraction(),
                                           modeles_llm.modele_secours()) if m]
    episodes = episodes_relus(args.source, args.episodes)
    if not episodes:
        log.error("Aucun épisode entièrement relu et transcrit pour %s.", args.source)
        return 1
    morceaux = sum(len(_chunk_transcript(
        transcript_path_for(args.source, e["guid"]).read_text(encoding="utf-8")))
        for e in episodes)
    log.info("%d épisode(s) : %s", len(episodes), ", ".join(e.get("title", e["guid"])
                                                           for e in episodes))
    log.info("%d appel(s) par modèle, %d modèle(s).", morceaux, len(modeles))
    if args.plan:
        return 0

    from common import make_anthropic_client
    with telemetry.workflow_run(args.source, trigger="cli", command="banc_modeles",
                                intent="experiment",
                                config={"modeles": modeles,
                                        "episodes": [e["guid"] for e in episodes]}):
        resultats = mesurer(make_anthropic_client(), args.source, modeles, episodes)
    rapport = tableau(resultats)
    print(rapport)
    horodatage = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    # Lu a l'appel : un chemin fige a l'import ecrirait dans le vrai dossier
    # meme quand les tests le redirigent.
    cible = common.OUTPUT_DIR / "banc_modeles" / f"{horodatage}.json"
    cible.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(cible, json.dumps({
        "source": args.source,
        "episodes": [e["guid"] for e in episodes],
        "resultats": [asdict(r) | {"cout": r.cout} for r in resultats],
    }, ensure_ascii=False, indent=2) + "\n")
    log.info("Rapport : %s", cible)
    return 0


if __name__ == "__main__":
    sys.exit(main())
