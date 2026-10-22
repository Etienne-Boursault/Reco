"""
reports.py — couverture, résumés et export pour un futur estimateur.

Règles :
  - `null` = non mesuré, `0` = mesuré à zéro ; une somme sur des valeurs
    absentes est `null`, jamais 0 ;
  - le nominal (première passe qualifiée) et le surcoût (reprises,
    retraitements, expériences, migrations, rattrapages, inconnu) ne se
    mélangent jamais ;
  - un ratio (coût par heure d'audio…) n'est calculé que sur une cohorte
    qualifiée, avec sa taille d'échantillon ;
  - un coût n'est additionné que dans sa devise ; les appels sans coût connu
    sont comptés à part.
"""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from telemetry.donnees import Donnees, instant

SCHEMA_VERSION = 1
AVERTISSEMENTS = [
    "Les métriques absentes ne sont pas converties en zéro : null = non mesuré.",
    ("Les épisodes traités avant la télémétrie ne sont pas reconstruits : seul leur état "
     "final (catalogue) est rapporté."),
    ("Le temps humain repose sur des battements (15 s, inactivité 60 s) à calibrer contre "
     "une relecture chronométrée avant tout usage dans l'estimateur."),
]


def _ratio(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def _somme(valeurs: Iterable[int | None]) -> int | None:
    """Somme de valeurs TOUTES connues ; une seule absente rend la somme inconnue."""
    total = 0
    vues = 0
    for valeur in valeurs:
        if valeur is None:
            return None
        total += valeur
        vues += 1
    return total if vues else None


def temps_actif_ms(battements: list[dict[str, Any]]) -> int | None:
    """Union des intervalles ]t - intervalle, t] : deux onglets ne comptent pas double."""
    if not battements:
        return None
    intervalles = sorted(
        (instant(b["received_at"]) - timedelta(milliseconds=b["interval_ms"]),
         instant(b["received_at"])) for b in battements)
    total, (debut, fin) = timedelta(0), intervalles[0]
    for d, f in intervalles[1:]:
        if d <= fin:
            fin = max(fin, f)
        else:
            total += fin - debut
            debut, fin = d, f
    total += fin - debut
    return int(total.total_seconds() * 1000)


def couts(appels: list[dict[str, Any]]) -> dict[str, Any]:
    """Coût connu par devise, appels sans coût, et couverture tarifaire."""
    par_devise: dict[str, Decimal] = defaultdict(Decimal)
    inconnus = 0
    for appel in appels:
        if appel.get("cost_decimal") is not None:
            par_devise[appel["cost_currency"]] += Decimal(appel["cost_decimal"])
        else:
            inconnus += 1
    return {"known": {d: str(m.quantize(Decimal("0.000001"))) for d, m in par_devise.items()}
            or None,
            "unknownCostCalls": inconnus, "pricingCoverage": _ratio(len(appels) - inconnus,
                                                                     len(appels))}


def couverture(donnees: Donnees) -> dict[str, Any]:
    tentatives = donnees.attempts
    reussies = [t for t in tentatives if t["status"] == "succeeded"]
    transcriptions = [t for t in reussies if t["stage"] == "transcribe"]
    humains = [e for e in donnees.events if e["actor_kind"] == "human"]
    sessions = {b["session_id"] for b in donnees.activity}
    avec_usage = sum(1 for a in donnees.calls if a["usage_source"] == "provider")
    statuts = Counter((t["stage"], t["status"]) for t in tentatives)
    return {
        "sourceId": donnees.source_id, "schemaVersion": donnees.schema_version,
        "runs": len(donnees.runs), "stageAttempts": len(tentatives),
        "llmCalls": len(donnees.calls), "reviewEvents": len(donnees.events),
        "activityBeats": len(donnees.activity),
        "attemptsByStageAndStatus": {f"{e}:{s}": n for (e, s), n in sorted(statuts.items())},
        "attemptsByIntent": dict(sorted(Counter(t["intent"] for t in tentatives).items())),
        "startedNotFinished": sum(1 for t in tentatives if t["status"] == "started"),
        "lostObservations": _somme(r.get("lost_observations") for r in donnees.runs
                                   if r["status"] != "started"),
        "coverage": {
            "tokens": _ratio(avec_usage, len(donnees.calls)),
            "duration": _ratio(sum(1 for t in transcriptions
                                   if t.get("media_duration_ms") is not None),
                               len(transcriptions)),
            "mediaOrigin": _ratio(sum(1 for t in transcriptions if t.get("media_origin")),
                                  len(transcriptions)),
            "humanTime": _ratio(sum(1 for e in humains if e.get("review_session_id") in sessions),
                                len(humains)),
            "pricing": couts(donnees.calls)["pricingCoverage"],
            "complete": _ratio(sum(1 for t in reussies if t["telemetry_complete"]), len(reussies)),
        },
    }


def _bloc(tentatives: list[dict[str, Any]], appels: dict[str, list[dict[str, Any]]]
          ) -> dict[str, Any]:
    siens = [a for t in tentatives for a in appels.get(t["id"], [])]
    par_etape: dict[str, list[int | None]] = defaultdict(list)
    for t in tentatives:
        par_etape[t["stage"]].append(t.get("elapsed_ms"))
    return {
        "attempts": len(tentatives),
        "episodes": len({t["episode_guid"] for t in tentatives if t.get("episode_guid")}),
        "byStatus": dict(sorted(Counter(t["status"] for t in tentatives).items())),
        "elapsedMsByStage": {e: _somme(v) for e, v in sorted(par_etape.items())},
        "llmCalls": len(siens),
        "llmCallsByTransport": dict(sorted(Counter(a["transport"] for a in siens).items())),
        "llmCallsByModel": dict(sorted(Counter(f"{a['provider']}:{a['model']}"
                                               for a in siens).items())),
        "inputTokens": _somme(a.get("input_tokens") for a in siens),
        "outputTokens": _somme(a.get("output_tokens") for a in siens),
        "cost": couts(siens),
    }


def resume(donnees: Donnees, cohorte: dict[str, Any] | None = None) -> dict[str, Any]:
    """Nominal (cohorte, ou toutes les premières passes) et surcoût, séparés."""
    appels = donnees.appels_de()
    retenus = set((cohorte or {}).get("includedEpisodes") or [])
    if cohorte is not None:
        nominal = [t for t in donnees.attempts if t.get("episode_guid") in retenus
                   and t["intent"] == "standard_first_pass"]
    else:
        nominal = [t for t in donnees.attempts if t["intent"] == "standard_first_pass"]
    surcout: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in donnees.attempts:
        if t["intent"] != "standard_first_pass":
            surcout[t["intent"]].append(t)
    evenements = [e for e in donnees.events if cohorte is None or e.get("episode_guid") in retenus]
    corrections = Counter(c for e in evenements if e["actor_kind"] == "human"
                          for c in _liste(e.get("derived_categories_json")))
    return {
        "nominal": _bloc(nominal, appels),
        "operationalOverhead": {i: _bloc(t, appels) for i, t in sorted(surcout.items())},
        "review": {
            "actionsByActor": dict(sorted(Counter(e["actor_kind"] for e in evenements).items())),
            "actionsByType": dict(sorted(Counter(e["action"] for e in evenements).items())),
            "humanCorrectionCategories": dict(corrections.most_common()),
            "humanActiveMs": temps_actif_ms(
                [b for b in donnees.activity if cohorte is None
                 or b.get("episode_guid") in retenus]),
        },
    }


def _liste(valeur: Any) -> list[str]:
    import json
    try:
        return list(json.loads(valeur or "[]"))
    except ValueError:
        return []


def _observe(donnees: Donnees, cohorte: dict[str, Any]) -> dict[str, Any]:
    retenus = set(cohorte["includedEpisodes"])
    vide = {k: None for k in ("processingElapsedMs", "humanActiveMs", "llmInputTokens",
                              "llmOutputTokens", "costKnown", "costCurrency",
                              "uniqueCandidates", "reviewActions", "audioDurationMs")}
    if not retenus:
        return vide
    appels = donnees.appels_de()
    nominales = [t for t in donnees.attempts if t.get("episode_guid") in retenus
                 and t["intent"] == "standard_first_pass" and t["status"] == "succeeded"]
    extractions = [t for t in nominales if t["stage"] == "extract"]
    siens = [a for t in extractions for a in appels.get(t["id"], [])]
    cout = couts(siens)
    devise = next(iter(cout["known"])) if cout["known"] and len(cout["known"]) == 1 else None
    humains = [e for e in donnees.events if e["actor_kind"] == "human"
               and e.get("episode_guid") in retenus]
    return {
        "processingElapsedMs": _somme(t.get("elapsed_ms") for t in nominales),
        "humanActiveMs": temps_actif_ms([b for b in donnees.activity
                                         if b.get("episode_guid") in retenus]),
        "llmInputTokens": _somme(a.get("input_tokens") for a in siens),
        "llmOutputTokens": _somme(a.get("output_tokens") for a in siens),
        "costKnown": cout["known"][devise] if devise else None,
        "costCurrency": devise,
        "uniqueCandidates": _somme(t["measurements"].get("unique_candidates")
                                   for t in extractions),
        "reviewActions": len(humains),
        "audioDurationMs": _somme(t.get("media_duration_ms") for t in nominales
                                  if t["stage"] == "transcribe"),
    }


def _derive(observe: dict[str, Any], cohorte: dict[str, Any],
            donnees: Donnees) -> dict[str, Any]:
    """Ratios d'une cohorte QUALIFIÉE seulement ; sinon tous null."""
    nuls = {k: None for k in ("costPerAudioHour", "candidatesPerAudioHour",
                              "humanMinutesPerReviewAction", "reviewMinutesPerCandidate",
                              "manualReworkRate")}
    heures = (observe["audioDurationMs"] or 0) / 3_600_000
    if not cohorte["isQualified"] or not heures:
        return {**nuls, "sampleSize": cohorte["includedEpisodeCount"]}
    retenus = set(cohorte["includedEpisodes"])
    humains = [e for e in donnees.events if e["actor_kind"] == "human"
               and e.get("episode_guid") in retenus]
    examinees = {e["reco_id"] for e in humains}
    retouchees = {e["reco_id"] for e in humains if e["action"] in {"edit", "merge"}}
    cout = observe["costKnown"]
    return {
        "costPerAudioHour": str(Decimal(cout) / Decimal(str(heures))) if cout else None,
        "candidatesPerAudioHour": (round(observe["uniqueCandidates"] / heures, 3)
                                   if observe["uniqueCandidates"] is not None else None),
        "humanMinutesPerReviewAction": (
            round(observe["humanActiveMs"] / 60_000 / observe["reviewActions"], 3)
            if observe["humanActiveMs"] is not None and observe["reviewActions"] else None),
        # Plusieurs fiches sont relues ensemble : pas de minute par candidat.
        "reviewMinutesPerCandidate": None,
        "manualReworkRate": _ratio(len(retouchees), len(examinees)),
        "sampleSize": cohorte["includedEpisodeCount"],
    }


def export(donnees: Donnees, cohorte: dict[str, Any], *,
           maintenant: datetime | None = None) -> dict[str, Any]:
    """Export pour l'estimateur, au format de la spécification (`schemaVersion` 1)."""
    observe = _observe(donnees, cohorte)
    cov = couverture(donnees)["coverage"]
    return {
        "schemaVersion": SCHEMA_VERSION, "sourceId": donnees.source_id,
        "generatedAt": (maintenant or datetime.now(UTC)).isoformat(timespec="seconds"),
        "cohort": {k: cohorte[k] for k in ("selector", "workflowProfile",
                                          "includedEpisodeCount", "isQualified", "status")}
        | {"excluded": [{"reason": e["reason"], "count": e["count"]} for e in cohorte["excluded"]],
           "reference": cohorte["reference"]},
        "coverage": {"llmUsage": cov["tokens"], "audioDuration": cov["duration"],
                     "humanActiveTime": cov["humanTime"], "pricing": cov["pricing"]},
        "observed": observe,
        "derived": _derive(observe, cohorte, donnees),
        "overhead": resume(donnees)["operationalOverhead"],
        "warnings": list(AVERTISSEMENTS),
    }


_FORME: dict[str, Any] = {
    "schemaVersion": int, "sourceId": str, "generatedAt": str,
    "cohort": {"selector": str, "includedEpisodeCount": int, "excluded": list,
               "isQualified": bool, "status": str},
    "coverage": {"llmUsage": (float, int, type(None)), "audioDuration": (float, int, type(None)),
                 "humanActiveTime": (float, int, type(None)), "pricing": (float, int, type(None))},
    "observed": {k: (int, str, type(None)) for k in (
        "processingElapsedMs", "humanActiveMs", "llmInputTokens", "llmOutputTokens",
        "costKnown", "costCurrency", "uniqueCandidates", "reviewActions")},
    "warnings": list,
}


def valider(objet: Any, forme: Any = None, chemin: str = "export") -> list[str]:
    """Contrôle de forme de l'export ; rend la liste des écarts (vide = conforme)."""
    forme = _FORME if forme is None else forme
    if isinstance(forme, dict):
        if not isinstance(objet, dict):
            return [f"{chemin} : objet attendu"]
        erreurs = []
        for cle, sous in forme.items():
            if cle not in objet:
                erreurs.append(f"{chemin}.{cle} : absent")
            else:
                erreurs += valider(objet[cle], sous, f"{chemin}.{cle}")
        return erreurs
    types = forme if isinstance(forme, tuple) else (forme,)
    if isinstance(objet, bool) and bool not in types:  # bool est un int en Python
        return [f"{chemin} : booléen inattendu"]
    return [] if isinstance(objet, types) else [f"{chemin} : type {type(objet).__name__}"]


def lignes_csv(donnees: Donnees) -> str:
    """Une ligne par tentative : de quoi recouper dans un tableur."""
    colonnes = ["started_at", "workflow_run_id", "episode_guid", "season", "stage", "intent",
                "status", "skip_reason", "elapsed_ms", "cpu_time_ms", "media_origin",
                "media_duration_ms", "provider", "model", "telemetry_complete",
                "llm_calls", "input_tokens", "output_tokens", "cost_known"]
    appels = donnees.appels_de()
    sortie = io.StringIO()
    ecrivain = csv.DictWriter(sortie, fieldnames=colonnes, extrasaction="ignore",
                              lineterminator="\n")
    ecrivain.writeheader()
    for t in sorted(donnees.attempts, key=lambda t: t["started_at"]):
        siens = appels.get(t["id"], [])
        cout = couts(siens)["known"]
        ecrivain.writerow({**t, "llm_calls": len(siens),
                           "input_tokens": _somme(a.get("input_tokens") for a in siens),
                           "output_tokens": _somme(a.get("output_tokens") for a in siens),
                           "cost_known": ";".join(f"{m} {d}" for d, m in (cout or {}).items())})
    return sortie.getvalue()


def _montants(connus: dict[str, str] | None) -> str:
    return ", ".join(f"{m} {d}" for d, m in connus.items()) if connus else "aucun"


def _ms(valeur: int | None) -> str:
    return "non mesuré" if valeur is None else f"{valeur / 60_000:.1f} min"


def markdown(couverture_: dict[str, Any], resume_: dict[str, Any],
             cohorte: dict[str, Any]) -> str:
    """Résumé lisible : temps machine / humain, modèles, coûts, couverture, cohorte."""
    nominal, review = resume_["nominal"], resume_["review"]
    entete = (f"Cohorte `{cohorte['selector']}` : **{cohorte['status']}** — "
              f"{cohorte['includedEpisodeCount']} épisode(s) retenu(s) sur "
              f"{cohorte['candidateEpisodeCount']} candidat(s).")
    lignes = [f"# Métriques — {couverture_['sourceId']}", "", entete, ""]
    for e in cohorte["excluded"]:
        lignes.append(f"- exclus `{e['reason']}` : {e['count']}")
    lignes += ["", "## Temps", "",
               "| | Valeur |", "|---|---|"]
    for etape, ms in nominal["elapsedMsByStage"].items():
        lignes.append(f"| traitement `{etape}` (nominal) | {_ms(ms)} |")
    lignes += [f"| relecture active (humain) | {_ms(review['humanActiveMs'])} |", "",
               "## Modèles et coûts (nominal)", ""]
    for modele, n in nominal["llmCallsByModel"].items():
        lignes.append(f"- `{modele}` : {n} appel(s)")
    cout = _montants(nominal["cost"]["known"])
    inconnus = nominal["cost"]["unknownCostCalls"]
    lignes += [f"- coût connu : {cout} ; appels sans coût connu : {inconnus}", "",
               "## Surcoût opérationnel", ""]
    for intention, bloc in resume_["operationalOverhead"].items():
        lignes.append(f"- `{intention}` : {bloc['attempts']} tentative(s), {bloc['llmCalls']} "
                      f"appel(s), coût connu {_montants(bloc['cost']['known'])}")
    lignes += ["", "## Relecture", "",
               f"- actions : {review['actionsByActor'] or 'aucune'}",
               f"- corrections humaines : {review['humanCorrectionCategories'] or 'aucune'}",
               "", "## Couverture", ""]
    for cle, valeur in couverture_["coverage"].items():
        lignes.append(f"- {cle} : {'non mesuré' if valeur is None else f'{valeur:.0%}'}")
    return "\n".join(lignes) + "\n"
