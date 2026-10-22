"""
cohorts.py — quels épisodes forment une cohorte de référence, et pourquoi les autres non.

La saison 6 est une cohorte CANDIDATE : `season = 6` ne prouve pas que le
workflow y était stable. Chaque épisode du catalogue reçoit soit une place dans
la cohorte, soit un code d'exclusion. Zéro épisode retenu est un résultat
honnête (`insufficient_data`), pas une panne du rapport.

Un épisode est retenu si, pour CHAQUE étape requise (transcription, extraction) :
  1. sa saison est écrite dans le catalogue et vaut la saison demandée ;
  2. une tentative `standard_first_pass` a RÉUSSI (pas un saut, pas un cache) ;
  3. cette tentative a la configuration de référence : l'empreinte de
     configuration la plus fréquente parmi les candidats. Un profil déclaré
     (`RECO_PIPELINE_PROFILE`) n'est qu'une étiquette : il ne remplace jamais
     l'empreinte, qui change d'elle-même avec le modèle, le prompt, le
     découpage ou le moteur ;
  4. l'origine du média est celle de la référence ;
  5. aucune migration de source ni expérience réétiquetée n'a touché l'épisode ;
  6. les mesures indispensables sont là (durée audio ; usage de chaque appel).

Les épisodes historiques, traités avant la télémétrie, sont exclus pour
`no_telemetry` : leurs appels, reprises, jetons et temps humain ne sont pas
reconstruits. Seul leur état final (catalogue) est rapporté.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from telemetry.donnees import Donnees

REQUIRED_STAGES = ("transcribe", "extract")
MIN_EPISODES = 3

# Ordre = priorité : un épisode reçoit le PREMIER code qui l'exclut.
EXCLUSIONS = ("season_unknown", "not_season", "no_telemetry", "source_migration",
              "experiment_only", "retry_only", "not_standard", "not_succeeded",
              "mixed_configuration", "media_mismatch", "missing_duration", "missing_usage")


def _saison(valeur: Any) -> int | None:
    return valeur if isinstance(valeur, int) and not isinstance(valeur, bool) else None


def _passe_nominale(tentatives: list[dict[str, Any]], etape: str) -> dict[str, Any] | None:
    return next((t for t in tentatives if t["stage"] == etape
                 and t["intent"] == "standard_first_pass" and t["status"] == "succeeded"), None)


def _exclusion(tentatives: list[dict[str, Any]], appels: dict[str, list[dict[str, Any]]],
               reference: dict[str, Any]) -> str | None:
    if not tentatives:
        return "no_telemetry"
    intents = {t["intent"] for t in tentatives}
    if "source_migration" in intents:
        return "source_migration"
    for etape in REQUIRED_STAGES:
        siennes = [t for t in tentatives if t["stage"] == etape]
        if not siennes:
            return "no_telemetry"
        nominales = [t for t in siennes if t["intent"] == "standard_first_pass"]
        if not nominales:
            autres = {t["intent"] for t in siennes}
            if autres == {"experiment"}:
                return "experiment_only"
            return "retry_only" if "retry" in autres else "not_standard"
        if _passe_nominale(tentatives, etape) is None:
            repris = any(t["intent"] == "retry" and t["status"] == "succeeded" for t in siennes)
            return "retry_only" if repris else "not_succeeded"
    for etape in REQUIRED_STAGES:
        passe = _passe_nominale(tentatives, etape)
        if passe.get("config_fingerprint") != reference["config"].get(etape):
            return "mixed_configuration"
    transcription = _passe_nominale(tentatives, "transcribe")
    if transcription.get("media_origin") != reference["media_origin"]:
        return "media_mismatch"
    if transcription.get("media_duration_ms") is None:
        return "missing_duration"
    extraction = _passe_nominale(tentatives, "extract")
    siens = appels.get(extraction["id"], [])
    if not siens or any(a["usage_source"] != "provider" for a in siens):
        return "missing_usage"
    return None


def reference(par_episode: dict[str, list[dict[str, Any]]],
              candidats: list[str]) -> dict[str, Any]:
    """Configuration de référence : l'empreinte la plus fréquente, par étape."""
    config: dict[str, str | None] = {}
    for etape in REQUIRED_STAGES:
        cles = Counter(p.get("config_fingerprint") for g in candidats
                       if (p := _passe_nominale(par_episode.get(g, []), etape)) is not None)
        config[etape] = cles.most_common(1)[0][0] if cles else None
    origines = Counter(p.get("media_origin") for g in candidats
                       if (p := _passe_nominale(par_episode.get(g, []), "transcribe")) is not None)
    return {"config": config,
            "media_origin": origines.most_common(1)[0][0] if origines else None,
            "chosenBy": "most_frequent_fingerprint"}


def _etiquette(donnees: Donnees, episodes: list[str]) -> str | None:
    """Le profil déclaré des runs retenus, s'il est unique : une étiquette, rien de plus."""
    runs = {t["workflow_run_id"] for t in donnees.attempts if t.get("episode_guid") in episodes}
    profils = {r.get("pipeline_profile") for r in donnees.runs if r["id"] in runs}
    return profils.pop() if len(profils) == 1 else None


def selection(donnees: Donnees, catalogue: dict[str, dict[str, Any]], *, season: int,
              min_episodes: int = MIN_EPISODES) -> dict[str, Any]:
    """Rapport de sélection : retenus, exclus avec leur code, et référence."""
    par_episode = donnees.tentatives_par_episode()
    appels = donnees.appels_de()
    de_la_saison = [g for g, ep in catalogue.items() if _saison(ep.get("season")) == season]
    ref = reference(par_episode, de_la_saison)

    episodes, exclus = [], defaultdict(list)
    for guid in sorted(catalogue):
        ep = catalogue[guid]
        saison = _saison(ep.get("season"))
        if saison is None:
            code = "season_unknown"
        elif saison != season:
            code = "not_season"
        else:
            code = _exclusion(par_episode.get(guid, []), appels, ref)
        if code is None:
            episodes.append(guid)
        else:
            exclus[code].append(guid)
    qualifiee = len(episodes) >= min_episodes
    return {
        "selector": f"s{season}-standard-first-pass",
        "season": season, "intent": "standard_first_pass",
        "workflowProfile": _etiquette(donnees, episodes), "reference": ref,
        "requiredStages": list(REQUIRED_STAGES), "minEpisodes": min_episodes,
        "candidateEpisodeCount": len(de_la_saison),
        "includedEpisodeCount": len(episodes), "includedEpisodes": episodes,
        # Hors saison : un compte suffit, la liste noierait le rapport.
        "excluded": [{"reason": code, "count": len(exclus[code]),
                      "episodes": None if code in {"not_season", "season_unknown"}
                      else exclus[code]}
                     for code in EXCLUSIONS if exclus.get(code)],
        "finalState": {g: {k: catalogue[g][k] for k in ("number", "transcriptSource",
                                                        "transcriptModel", "recos")}
                       for g in de_la_saison},
        "isQualified": qualifiee,
        "status": "qualified" if qualifiee else "insufficient_data",
    }
