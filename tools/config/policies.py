"""Politiques éditoriales projet (constantes module-level).

Le **schéma** est neutre : `avoid_brands` y vaut `()` par défaut. Les
configs JSON peuplent explicitement ce champ avec la politique souhaitée.
Ce module centralise la liste « par défaut » du projet Reco
(cf. memory ``reco-liens-ethiques``) pour que les configs s'y réfèrent
sans dupliquer la liste.
"""

from __future__ import annotations

__all__ = ["PROJECT_AVOID_BRANDS"]

# Liste à éviter dans les liens marchands — cohérent avec
# ``memory/reco-liens-ethiques.md``. Toute config JSON peut copier cette
# liste ou la spécialiser. Le schéma n'impose RIEN par défaut.
PROJECT_AVOID_BRANDS: tuple[str, ...] = ("Amazon", "Bolloré")
