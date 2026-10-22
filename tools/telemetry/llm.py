"""
llm.py — un appel fournisseur RÉEL = une ligne de `llm_calls`.

    with llm.chunk(index=0, count=3, chars=24_000):
        with llm.appel("anthropic", model, request=llm.requete(params)) as appel:
            message = client.messages.create(**params)
            appel.reponse(message)            # usage relevé AVANT d'en extraire les recos
            appel.candidats(len(recos))

L'adaptateur continue de rendre ses recos ; la télémétrie part de côté, dans
l'étape courante. Hors étape, rien n'est écrit.

Usage. Les jetons viennent de la réponse (`usage_source = provider`). Une
réponse sans usage donne des jetons `NULL` et `usage_source = unavailable` —
jamais 0. Une requête qui échoue :
  - refusée par le fournisseur (4xx) : `failed`, rien de facturé ;
  - sinon (délai, coupure, 5xx) : `billing_uncertain`, coût inconnu.

Ce qui n'est jamais écrit : le prompt rempli, la transcription, le corps de la
réponse. `provider_usage_json` ne garde que les compteurs de l'objet `usage`.
"""
from __future__ import annotations

import contextlib
import hashlib
import logging
import time
import uuid
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any

from telemetry import pricing
from telemetry.context import StageHandle, current_stage, now_iso

COST_OWNERS = frozenset({"user_byok", "reco_managed", "local_machine", "unknown"})
#: Marque posée sur un client à sa création, selon d'où vient sa clé
#: (`common.make_anthropic_client` : clé de l'opérateur -> `reco_managed`).
ATTRIBUT_PROPRIETAIRE = "reco_cost_owner"

_CHUNK: ContextVar[dict[str, int] | None] = ContextVar("reco_telemetry_chunk", default=None)
_APPEL: ContextVar[Appel | None] = ContextVar("reco_telemetry_appel", default=None)


def prompt_sha256(*templates: str) -> str:
    """Empreinte des GABARITS (système + consigne), jamais du prompt rempli."""
    h = hashlib.sha256()
    for gabarit in templates:
        h.update(gabarit.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def cost_owner(client: Any) -> str:
    """Qui paie les jetons, déduit du client : sa clé dit à qui elle est.

    Un client sans marque (doublure de test, client construit ailleurs) donne
    `unknown`, jamais une supposition.
    """
    proprietaire = getattr(client, ATTRIBUT_PROPRIETAIRE, None)
    return proprietaire if isinstance(proprietaire, str) and proprietaire in COST_OWNERS \
        else "unknown"


@contextlib.contextmanager
def chunk(index: int, count: int, chars: int) -> Iterator[None]:
    jeton = _CHUNK.set({"chunk_index": index, "chunk_count": count, "chars_in_chunk": chars})
    try:
        yield
    finally:
        _CHUNK.reset(jeton)


def requete(params: dict[str, Any]) -> dict[str, Any]:
    """Les réglages d'une requête qui pèsent sur le coût — sans son contenu."""
    return {"max_tokens": params.get("max_tokens"),
            "effort": (params.get("output_config") or {}).get("effort"),
            "temperature": params.get("temperature")}


def _scalaires(objet: Any, profondeur: int = 2) -> Any:
    """Compteurs d'un objet `usage` (SDK ou dict), sans rien d'autre."""
    if objet is None or isinstance(objet, bool | int | float | str):
        return objet
    if profondeur == 0:
        return None
    if hasattr(objet, "model_dump"):
        objet = objet.model_dump()
    elif not isinstance(objet, dict):
        objet = {k: v for k, v in vars(objet).items() if not k.startswith("_")}
    sortie = {k: _scalaires(v, profondeur - 1) for k, v in objet.items()}
    return {k: v for k, v in sortie.items() if v is not None}


def _texte(valeur: Any) -> str | None:
    return valeur if isinstance(valeur, str) else None


def _entier(valeur: Any) -> int | None:
    return valeur if isinstance(valeur, int) and not isinstance(valeur, bool) else None


def usage_anthropic(message: Any) -> dict[str, Any]:
    usage = getattr(message, "usage", None)
    return {
        "input_tokens": _entier(getattr(usage, "input_tokens", None)),
        "output_tokens": _entier(getattr(usage, "output_tokens", None)),
        "cache_read_input_tokens": _entier(getattr(usage, "cache_read_input_tokens", None)),
        "cache_write_input_tokens": _entier(getattr(usage, "cache_creation_input_tokens", None)),
        # Anthropic compte le raisonnement dans la sortie, sans le détailler.
        "reasoning_tokens": None,
        "provider_request_id": _texte(getattr(message, "id", None)),
        "provider_usage_json": _scalaires(usage) or {},
    }


def usage_openai(reponse: Any) -> dict[str, Any]:
    usage = getattr(reponse, "usage", None)
    entree = getattr(usage, "prompt_tokens_details", None)
    sortie = getattr(usage, "completion_tokens_details", None)
    return {
        "input_tokens": _entier(getattr(usage, "prompt_tokens", None)),
        "output_tokens": _entier(getattr(usage, "completion_tokens", None)),
        "cache_read_input_tokens": _entier(getattr(entree, "cached_tokens", None)),
        "cache_write_input_tokens": None,
        "reasoning_tokens": _entier(getattr(sortie, "reasoning_tokens", None)),
        "provider_request_id": _texte(getattr(reponse, "id", None)),
        "provider_usage_json": _scalaires(usage) or {},
    }


_LECTEURS = {"anthropic": usage_anthropic, "openai": usage_openai}


class Appel:
    def __init__(self, provider: str, model: str, transport: str,
                 request: dict[str, Any] | None, client: Any = None) -> None:
        self.provider, self.model, self.transport = provider, model, transport
        self.cost_owner = cost_owner(client)
        self.request = dict(request or {})
        self.usage: dict[str, Any] = {}
        self.status = "succeeded"
        self.error_code: str | None = None
        self.parse_status: str | None = None
        self.candidates: int | None = None
        self.elapsed_ms: int | None = None

    def reponse(self, objet: Any) -> None:
        """Relève l'usage. Une réponse de forme inattendue laisse l'usage inconnu :
        une mesure ne casse jamais une extraction."""
        try:
            self.usage = _LECTEURS[self.provider](objet)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("reco.telemetry").warning(
                "Usage illisible (%s) : jetons inconnus.", type(exc).__name__)
            self.usage = {}

    def candidats(self, nombre: int) -> None:
        self.candidates = nombre
        if self.parse_status is None:
            self.parse_status = "json" if nombre else "empty"

    def echec(self, exc: BaseException) -> None:
        code = getattr(exc, "status_code", None)
        refuse = isinstance(code, int) and 400 <= code < 500
        self.status = "failed" if refuse else "billing_uncertain"
        self.error_code = str(code) if code is not None else type(exc).__name__


def enregistrer(etape: StageHandle, appel: Appel, *, extra: dict[str, Any] | None = None) -> bool:
    """Écrit l'appel dans `etape`, avec son coût s'il est fondé."""
    if not etape.id:
        return False
    usage = {k: appel.usage.get(k) for k in (
        "input_tokens", "output_tokens", "cache_read_input_tokens",
        "cache_write_input_tokens", "reasoning_tokens")}
    connu = usage["input_tokens"] is not None and usage["output_tokens"] is not None
    a_quand = now_iso()
    tarif = pricing.tarif(appel.provider, appel.model, appel.transport, a_quand) if connu else None
    montant = pricing.cout(tarif, usage) if appel.status == "succeeded" else None
    etape.calls += 1
    if not connu:
        etape.calls_without_usage += 1
    ligne = {
        "id": str(uuid.uuid4()), "stage_attempt_id": etape.id, "provider": appel.provider,
        "model": appel.model, "transport": appel.transport,
        **(_CHUNK.get() or {}), **(extra or {}),
        "provider_request_id": appel.usage.get("provider_request_id"),
        "status": appel.status, "parse_status": appel.parse_status,
        "candidates_raw": appel.candidates, "elapsed_ms": appel.elapsed_ms, **usage,
        "usage_source": "provider" if connu else "unavailable",
        "request_json": appel.request,
        "pricing_snapshot_id": pricing.snapshot_id(tarif) if montant is not None else None,
        "cost_decimal": str(montant) if montant is not None else None,
        "cost_currency": tarif["currency"] if montant is not None else None,
        "cost_owner": appel.cost_owner, "error_code": appel.error_code, "recorded_at": a_quand,
        "provider_usage_json": appel.usage.get("provider_usage_json") or {},
    }
    return etape.recorder.record_llm_call(ligne)


@contextlib.contextmanager
def appel(provider: str, model: str, *, transport: str = "sync",
          request: dict[str, Any] | None = None, client: Any = None) -> Iterator[Appel]:
    """Chronomètre un appel synchrone et l'écrit dans l'étape courante."""
    courant = Appel(provider, model, transport, request, client)
    jeton = _APPEL.set(courant)
    debut = time.perf_counter_ns()
    try:
        yield courant
    except Exception as exc:
        courant.echec(exc)
        raise
    finally:
        _APPEL.reset(jeton)
        courant.elapsed_ms = (time.perf_counter_ns() - debut) // 1_000_000
        enregistrer(current_stage(), courant)


def parse_echouee() -> None:
    """La réponse de l'appel en cours n'était pas du JSON exploitable."""
    courant = _APPEL.get()
    if courant is not None:
        courant.parse_status = "non_json"
