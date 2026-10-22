"""
extraction_mesures.py — ce que la télémétrie retient d'une extraction LLM.

Séparé d'`extract_recos.py`, qui ne porte que des points de mesure d'une
ligne. Deux chemins :

  - synchrone : une tentative `extract` par épisode, un appel par chunk
    (`telemetry.llm.appel`, posé dans les adaptateurs) ;
  - lot (Message Batches API) : une tentative par épisode, ouvertes ensemble.
    La correspondance `custom_id` -> épisode est écrite AVANT de scruter le lot,
    pour qu'un lot interrompu reste attribuable ; chaque résultat est rangé dans
    l'épisode de SA requête, une seule fois (index unique). L'attente du lot est
    mesurée sur le lot, jamais répartie entre épisodes.

Candidats : bruts par appel (`llm_calls.candidates_raw`), puis par épisode
uniques après normalisation et déduplication (`unique_candidates`), puis
fiches créées et mises à jour. Les candidats répétés d'un chunk à l'autre ne
s'additionnent pas en œuvres distinctes.
"""
from __future__ import annotations

import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import telemetry
from common import read_json
from telemetry import llm
from transcription_mesures import ms_depuis, saison

PROMPT_VERSION = "recos-extraction-v1"
RECIPE_VERSION = "cultural-recommendations-v1"


def configuration(provider: str, model: str, transport: str) -> dict[str, Any]:
    """Paramètres fonctionnels de l'extraction ; lus à l'appel dans `extract_recos`."""
    import extract_recos as er
    effort = er.EFFORT if provider == "anthropic" and er.accepte_effort(model) else None
    return {
        "provider": provider, "model": model, "transport": transport,
        "max_tokens": er.MAX_TOKENS_RAISONNEMENT if effort else er.MAX_TOKENS,
        "effort": effort, "temperature": None,  # défaut du fournisseur, non fixé
        "chunk_chars": er.CHUNK_CHARS, "chunk_overlap_chars": er.CHUNK_OVERLAP_CHARS,
        "prompt_version": PROMPT_VERSION, "prompt_sha256": empreinte_prompt(),
        "recipe_version": RECIPE_VERSION,
    }


def empreinte_prompt() -> str:
    import extract_recos as er
    return llm.prompt_sha256(er.SYSTEM_PROMPT, er.USER_TEMPLATE)


def champs_etape(provider: str, model: str, transport: str) -> dict[str, Any]:
    return {"config": configuration(provider, model, transport), "provider": provider,
            "model": model, "prompt_version": PROMPT_VERSION,
            "prompt_sha256": empreinte_prompt(), "recipe_version": RECIPE_VERSION}


def mesurer_episode(texte: str, chunks: list[str]) -> None:
    etape = telemetry.current_stage()
    etape.measure("transcript_chars", len(texte), "chars")
    etape.measure("chunk_count", len(chunks), "count")
    etape.set(transcript_id_or_hash=_empreinte(texte))


def _empreinte(texte: str) -> str:
    from transcription_mesures import empreinte_texte
    return empreinte_texte(texte)


def mesurer_ecritures(uniques: int, creees: int, mises_a_jour: int) -> None:
    etape = telemetry.current_stage()
    etape.measure("unique_candidates", uniques, "count")
    etape.measure("recos_created", creees, "count")
    etape.measure("recos_updated", mises_a_jour, "count")


class SuiviLot:
    """Les tentatives d'un lot multi-épisodes, et l'attribution de ses résultats."""

    def __init__(self, source_id: str, provider: str, model: str,
                 episode_paths: Iterable[Path], guids: list[str],
                 meta: dict[str, dict[str, Any]]) -> None:
        self.provider, self.model, self.meta = provider, model, meta
        self.run = telemetry.current_run()
        self.batch_id: str | None = None
        self.etapes: dict[str, telemetry.StageHandle] = {}
        self.echecs: dict[str, int] = {}
        self._fin_soumission: int | None = None
        episodes = {}
        for path in episode_paths:
            try:
                ep = read_json(path)
            except (OSError, ValueError):
                continue
            episodes[ep.get("guid")] = ep
        for guid in guids:
            if self.run is not None:
                self.etapes[guid] = self.run.open_stage(
                    "extract", episode_guid=guid, season=saison(episodes.get(guid, {})),
                    **champs_etape(provider, model, "batch"))

    def etape(self, guid: str) -> telemetry.StageHandle:
        return self.etapes.get(guid) or telemetry.current_stage()

    def soumis(self, batch_id: str, debut_ns: int) -> None:
        """Lot accepté : on écrit le lot et la correspondance avant de scruter."""
        self.batch_id = batch_id
        self._fin_soumission = time.perf_counter_ns()
        if self.run is None:
            return
        recorder = self.run.recorder
        recorder.record_batch({
            "id": batch_id, "provider": self.provider, "model": self.model,
            "workflow_run_id": self.run.id, "request_count": len(self.meta),
            "submitted_at": telemetry.now_iso(), "submit_elapsed_ms": ms_depuis(debut_ns),
            "last_status": "submitted"})
        recorder.map_batch_requests(
            {"batch_id": batch_id, "custom_id": cid, "stage_attempt_id": self.etapes[m["guid"]].id,
             "episode_guid": m["guid"], "chunk_index": m["chunk_index"],
             "chunk_count": m["chunk_count"], "chars_in_chunk": m["chars_in_chunk"]}
            for cid, m in self.meta.items() if m["guid"] in self.etapes)

    def statut(self, status: str) -> None:
        if self.run is not None and self.batch_id:
            self.run.recorder.update_batch(self.batch_id, {"last_status": status})

    def attente_terminee(self) -> None:
        """Fin de l'attente côté fournisseur : ni CPU local, ni durée d'un épisode."""
        self._debut_resultats = time.perf_counter_ns()
        if self.run is not None and self.batch_id and self._fin_soumission is not None:
            self.run.recorder.update_batch(self.batch_id, {
                "ended_at": telemetry.now_iso(), "wait_ms": ms_depuis(self._fin_soumission)})

    def entree(self, entry: Any, candidats: int | None) -> None:
        """Un résultat du lot, rangé dans l'épisode de sa requête."""
        m = self.meta.get(entry.custom_id)
        if m is None or m["guid"] not in self.etapes:
            return
        appel = llm.Appel(self.provider, self.model, "batch", None)
        if entry.result.type == "succeeded":
            appel.reponse(entry.result.message)
            if candidats is not None:
                appel.candidats(candidats)
        else:
            # errored / canceled / expired : non facturé selon le fournisseur,
            # mais l'usage n'est pas rendu — il reste inconnu.
            appel.status, appel.error_code = "failed", entry.result.type
            self.echecs[m["guid"]] = self.echecs.get(m["guid"], 0) + 1
        llm.enregistrer(self.etapes[m["guid"]], appel, extra={
            "batch_id": self.batch_id, "batch_custom_id": entry.custom_id,
            "chunk_index": m["chunk_index"], "chunk_count": m["chunk_count"],
            "chars_in_chunk": m["chars_in_chunk"]})

    def fermer(self, exc: BaseException | None = None) -> None:
        if self.run is None:
            return
        if self.batch_id and getattr(self, "_debut_resultats", None) is not None:
            self.run.recorder.update_batch(self.batch_id, {
                "result_processing_ms": ms_depuis(self._debut_resultats)})
        for guid, etape in self.etapes.items():
            if exc is None and self.echecs.get(guid):
                etape.fail(f"{self.echecs[guid]} requête(s) du lot en échec")
            self.run.close_stage(etape, exc)
