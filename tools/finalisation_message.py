"""
finalisation_message.py — ce que la finalisation raconte à l'éditeur.

Sorti de `traiter_nouveaux_episodes.py` le 2026-09-25 (règle des 500 lignes par
fichier) : l'intérêt de l'étape `finaliser` n'est pas de poser des liens, c'est
de dire ce qu'il reste à faire à la main. Cette logique mérite son fichier et
ses tests.

Les passes complémentaires (TMDB, fiches vidéo) passent par `Passe` plutôt que
par des paires d'arguments `xxx` / `panne_xxx` : il y en a eu une, puis deux, et
`enrich_creators` attend son tour. Chacune dit ce qu'elle a servi, ou pourquoi
elle n'a rien pu faire.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

#: Au-delà, le message Matrix devient illisible ; le détail reste sur la page.
MAX_RESTES = 15
HORS_PERIMETRE = "aucun outil automatique pour ce type"


@dataclass(frozen=True)
class Passe:
    """Résultat d'une passe complémentaire, pour le message.

    Deux libellés, parce que les deux phrases ne se lisent pas pareil :
    `unite` se compte (« 2 fiche(s) TMDB. »), `nom` s'annonce en panne
    (« ⚠️ TMDB indisponible : … »). `panne` non vide signifie que la passe n'a
    pas pu tourner : l'épisode a tout de même ses œuvres et ses mentions.
    """

    nom: str
    unite: str
    servies: frozenset[str] = field(default_factory=frozenset)
    panne: str = ""


def restes(rapport: Any, recos: list[dict[str, Any]],
           servies: frozenset[str] | set[str] = frozenset()) -> list[str]:
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
        if reco_id in servies or reco.get("watchProviders"):
            continue
        types = "/".join(reco.get("types") or []) or "?"
        raison = verdict.reason if verdict is not None else HORS_PERIMETRE
        lignes.append(f"• {reco.get('title')} ({types}) — {raison}")
    return lignes


def message(titre: str, rapport: Any, plan: Any,
            recos: list[dict[str, Any]],
            passes: Sequence[Passe] = ()) -> str:
    tete = (f"🔗 {titre} : {len(rapport.linked)} lien(s) posé(s), "
            f"{len(plan.items_created)} œuvre(s) créée(s), "
            f"{len(plan.items_reused)} réutilisée(s), "
            f"{len(plan.mentions_created)} mention(s).")
    servies: set[str] = set()
    pannes = []
    for passe in passes:
        if passe.panne:
            pannes.append(f"⚠️ {passe.nom} indisponible : {passe.panne}")
            continue
        servies |= set(passe.servies)
        tete += f" {len(passe.servies)} {passe.unite}."
    if pannes:
        tete += "\n" + "\n".join(pannes)
    a_la_main = restes(rapport, recos, frozenset(servies))
    if not a_la_main:
        return f"{tete}\nRien à compléter à la main."
    reste = len(a_la_main) - MAX_RESTES
    suite = "" if reste <= 0 else f"\n… et {reste} autre(s)."
    return (f"{tete}\nÀ compléter à la main ({len(a_la_main)}) :\n"
            + "\n".join(a_la_main[:MAX_RESTES]) + suite)
