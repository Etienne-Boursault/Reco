"""
finalisation_message.py — ce que la finalisation raconte à l'éditeur.

Sorti de `traiter_nouveaux_episodes.py` le 2026-09-25 (règle des 500 lignes par
fichier) : l'intérêt de l'étape `finaliser` n'est pas de poser des liens, c'est
de dire ce qu'il reste à faire à la main. Cette logique mérite son fichier et
ses tests.
"""
from __future__ import annotations

from typing import Any

#: Au-delà, le message Matrix devient illisible ; le détail reste sur la page.
MAX_RESTES = 15
HORS_PERIMETRE = "aucun outil automatique pour ce type"


def restes(rapport: Any, recos: list[dict[str, Any]],
           servies_tmdb: set[str] = frozenset()) -> list[str]:
    """Ce qui reste à la main : une reco affichée sans aucun lien.

    Deux sources concordantes, et non une seule : le fichier relu du disque, et
    le rapport de la passe. Une reco que la passe vient de servir n'a rien à
    faire dans la liste, même si la relecture du disque la donnait encore nue.
    """
    verdicts = {c.reco_id: c for c in rapport.outcomes}
    lignes = []
    for reco in recos:
        reco_id = reco.get("id")
        verdict = verdicts.get(reco_id)
        if reco.get("links") or reco.get("status") == "discarded":
            continue
        if verdict is not None and verdict.links:
            continue
        if reco_id in servies_tmdb or reco.get("watchProviders"):
            continue
        types = "/".join(reco.get("types") or []) or "?"
        raison = verdict.reason if verdict is not None else HORS_PERIMETRE
        lignes.append(f"• {reco.get('title')} ({types}) — {raison}")
    return lignes


def message(titre: str, rapport: Any, plan: Any,
            recos: list[dict[str, Any]], tmdb: Any = None,
            panne_tmdb: str = "") -> str:
    fiches = f" {len(tmdb.servies)} fiche(s) TMDB." if tmdb is not None else ""
    tete = (f"🔗 {titre} : {len(rapport.linked)} lien(s) posé(s), "
            f"{len(plan.items_created)} œuvre(s) créée(s), "
            f"{len(plan.items_reused)} réutilisée(s), "
            f"{len(plan.mentions_created)} mention(s).{fiches}")
    if panne_tmdb:
        tete += f"\n⚠️ TMDB indisponible : {panne_tmdb}"
    servies = tmdb.servies if tmdb is not None else frozenset()
    a_la_main = restes(rapport, recos, servies)
    if not a_la_main:
        return f"{tete}\nRien à compléter à la main."
    reste = len(a_la_main) - MAX_RESTES
    suite = "" if reste <= 0 else f"\n… et {reste} autre(s)."
    return (f"{tete}\nÀ compléter à la main ({len(a_la_main)}) :\n"
            + "\n".join(a_la_main[:MAX_RESTES]) + suite)
