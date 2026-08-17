"""Fixtures partagées par les tests de `tools/review_table.py`.

Le fichier de tests d'origine dépassait 500 lignes ; il a été scindé en trois
— collecte, rendu, échappement. Ces deux constructeurs y sont communs, et vivent
donc ici plutôt que d'être recopiés : un jeu de données de test dupliqué diverge
toujours, et les deux moitiés finissent par ne plus tester la même chose.

Ce module n'est PAS un fichier de tests (`python_files = ["test_*.py"]`) : il
est simplement importable, `pythonpath` incluant `tests`.
"""
from __future__ import annotations

import review_table as rtab

__all__ = ["_patch", "_reco"]


def _reco(rid, **kw):
    """Une reco active minimale, complétée par les champs passés."""
    r = {"id": rid, "episodeGuid": "g1", "title": f"Titre {rid}",
         "types": ["film"], "status": "validated", "timestamp": "00:10:00"}
    r.update(kw)
    return r


def _patch(monkeypatch, recos, episodes=None, curation=None, proposals=None):
    """Substitue les trois sources de la page : corpus, sidecar, propositions.

    Les recos sont regroupées par `episodeGuid` comme le fait le chargeur réel,
    afin qu'une reco rattachée à un guid inconnu suive le même chemin qu'en
    production.
    """
    source = {"title": "Démo", "hosts": ["Alice"]}
    episodes = episodes or {"g1": {"guid": "g1", "title": "Ép. 1",
                                   "season": 1, "number": 3, "date": "2021-02-14"}}
    groups: dict[str, list[dict]] = {}
    for r in recos:
        groups.setdefault(r.get("episodeGuid", ""), []).append(r)
    monkeypatch.setattr(rtab, "_load_groups",
                        lambda s: (source, episodes, groups))
    monkeypatch.setattr(rtab, "load_curation", lambda s: curation or {})
    monkeypatch.setattr(rtab, "load_type_proposals", lambda: proposals or {})
