"""Garde : aucun `null` là où le schéma Zod attend une chaîne optionnelle.

POURQUOI CE FICHIER EXISTE — incident du 2026-08-17
---------------------------------------------------
La collection `recos` déclare ses champs texte en `z.string().optional()`,
SANS `nullable`. Un correctif de données a vidé 113 `creator` en y écrivant
`null`, croyant exprimer une absence. Zod rapporte `null` comme un objet, et le
build Astro entier s'est arrêté sur :

    creator: Expected type `"string"`, received `"object"`

Aucun test ne l'a vu. La suite était verte, la couverture au-dessus des seuils,
et le défaut n'est apparu qu'au `astro build` — c'est-à-dire au moment du
déploiement. C'est le pire endroit pour l'apprendre.

La seule représentation valable d'une absence est donc l'ABSENCE DE CLÉ, comme
pour les 902 recos sans créateur connu.

CE QUE CE FICHIER NE FAIT PAS
-----------------------------
Il ne rejoue pas le schéma Zod — le faire en Python demanderait de le
retranscrire, donc de le laisser diverger. Il vérifie UNE propriété, celle qui
a cassé : pas de `null` sur les champs texte optionnels. La liste est explicite
plutôt que déduite de `content.config.ts` par expression régulière : analyser
du TypeScript à coups de regex donne une garde qui se croit à jour.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common import CONTENT_DIR

#: Champs de `recos` déclarés `z.string().optional()` — donc jamais `null`.
#: Tenir à jour avec `src/content.config.ts`.
CHAMPS_TEXTE_OPTIONNELS = (
    "creator",
    "recommendedBy",
    "quote",
    "timestamp",
    "note",
)

#: Sous-champs d'`externalIds`, mêmes règles.
CHAMPS_EXTERNAL_IDS = (
    "tmdb", "tmdbType", "imdb", "isbn", "musicbrainz", "youtube",
    "youtubeChannelId", "instagram", "tiktok", "website", "watchPage",
    "deezer", "spotify",
)


def _recos() -> list[Path]:
    return sorted((CONTENT_DIR / "recos").rglob("*.json"))


def test_le_corpus_nest_pas_vide():
    """Sans cette garde, tous les tests ci-dessous passeraient sur zéro fichier
    — et annonceraient un corpus sain qu'ils n'ont jamais regardé."""
    assert len(_recos()) > 1000


@pytest.mark.parametrize("champ", CHAMPS_TEXTE_OPTIONNELS)
def test_aucun_champ_texte_optionnel_ne_vaut_null(champ):
    fautifs = []
    for chemin in _recos():
        data = json.loads(chemin.read_text(encoding="utf-8"))
        if champ in data and data[champ] is None:
            fautifs.append(chemin.name)
    assert not fautifs, (
        f"`{champ}: null` sur {len(fautifs)} reco(s) — le schéma attend une "
        f"chaîne optionnelle, et le build Astro échouera. Retire la CLÉ plutôt "
        f"que d'y écrire null. Exemples : {fautifs[:5]}"
    )


@pytest.mark.parametrize("champ", CHAMPS_EXTERNAL_IDS)
def test_aucun_external_id_ne_vaut_null(champ):
    fautifs = []
    for chemin in _recos():
        ids = json.loads(chemin.read_text(encoding="utf-8")).get("externalIds")
        if isinstance(ids, dict) and champ in ids and ids[champ] is None:
            fautifs.append(chemin.name)
    assert not fautifs, (
        f"`externalIds.{champ}: null` sur {len(fautifs)} reco(s). "
        f"Exemples : {fautifs[:5]}"
    )


def test_aucune_chaine_vide_non_plus_sur_creator():
    """`""` passe le schéma mais affiche une ligne créateur SANS nom : le
    lecteur voit un libellé vide, ce qui est pire qu'une ligne absente."""
    fautifs = [c.name for c in _recos()
               if isinstance(json.loads(c.read_text(encoding="utf-8")).get("creator"), str)
               and not json.loads(c.read_text(encoding="utf-8"))["creator"].strip()]
    assert not fautifs, f"`creator` vide sur : {fautifs[:5]}"
