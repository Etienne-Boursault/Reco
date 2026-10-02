"""Agrégats et rendu du rapport de la passe « boutique ».

Il ne décide de rien : il compte, il classe, il met en forme. Les codes de raison
qu'il agrège viennent de `boutique_matching` et doivent rester STABLES — ce sont
eux qui permettent de comparer deux passes.

Extrait de `boutique_links.py`, qui dépassait les 500 lignes du projet (même
découpage que `music_links_report` et `video_links_report`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from boutique_matching import RAISONS_A_ARBITRER


@dataclass(frozen=True)
class Cas:
    """Le sort d'UNE reco examinée, pour dire à l'humain ce qui lui reste.

    `preuve` porte ce qui a corroboré — studios Steam, ou EAN du livre : sans
    elle, un lien posé serait indiscernable d'un lien deviné à la relecture du
    rapport.
    """

    reco_id: str
    titre: str
    type_: str
    raison: str
    preuve: str | None = None
    liens: int = 0
    detail: str = ""


@dataclass
class RapportBoutique:
    """Agrégats d'une passe (`run`)."""

    vues: int = 0
    ecrites: int = 0
    cas: list[Cas] = field(default_factory=list)

    @property
    def servies(self) -> set[str]:
        """Ids des recos pour lesquelles au moins un lien a été posé.

        Même nom et même sens que `enrich_tmdb.Rapport.servies` et
        `video_links_report.Report.servies` : la chaîne traite toutes ses passes
        de la même façon pour composer son message.
        """
        return {cas.reco_id for cas in self.cas if cas.liens}

    @property
    def a_arbitrer(self) -> list[Cas]:
        """Refus qui demandent un œil humain, pas ceux qui constatent une absence."""
        return [cas for cas in self.cas if cas.raison in RAISONS_A_ARBITRER]


def format_rapport(rapport: RapportBoutique) -> str:
    """Rapport lisible : par type, puis les raisons, puis ce qui reste à faire."""
    par_type: dict[str, dict[str, int]] = {}
    raisons: dict[str, int] = {}
    for cas in rapport.cas:
        compteur = par_type.setdefault(cas.type_ or "?", {"vues": 0, "liens": 0})
        compteur["vues"] += 1
        compteur["liens"] += cas.liens
        raisons[cas.raison] = raisons.get(cas.raison, 0) + 1

    lignes = ["", f"{'type':10} {'vues':>6} {'liens posés':>12}", "-" * 60]
    for type_ in sorted(par_type):
        lignes.append(f"{type_:10} {par_type[type_]['vues']:6} "
                      f"{par_type[type_]['liens']:12}")
    lignes += ["-" * 60, "Refus / raisons :"]
    for raison, n in sorted(raisons.items(), key=lambda kv: (-kv[1], kv[0])):
        lignes.append(f"  {raison:24} {n:5}")
    poses = sum(cas.liens for cas in rapport.cas)
    lignes += ["-" * 60,
               (f"Recos vues : {rapport.vues} · liens posés : {poses} "
                f"· fichiers écrits : {rapport.ecrites}"),
               f"À arbitrer à la main : {len(rapport.a_arbitrer)}"]
    return "\n".join(lignes)


def rapport_payload(rapport: RapportBoutique) -> dict[str, Any]:
    """Version JSON-sérialisable du rapport (relecture humaine)."""
    return {
        "vues": rapport.vues,
        "ecrites": rapport.ecrites,
        "servies": sorted(rapport.servies),
        "cas": [{"id": c.reco_id, "titre": c.titre, "type": c.type_,
                 "raison": c.raison, "preuve": c.preuve, "liens": c.liens,
                 "detail": c.detail}
                for c in rapport.cas],
    }
