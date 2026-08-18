"""Garde : une PLATEFORME n'est jamais le créateur d'une œuvre.

POURQUOI CE FICHIER EXISTE — relevé du 2026-08-18
-------------------------------------------------
Quinze recos créditaient leur diffuseur : « Netflix » pour « La Chute de la
maison Usher », qui est de Mike Flanagan ; « HBO » pour « Silicon Valley »,
qui est de Mike Judge. C'est faux, et c'est VISIBLE — le champ s'affiche sur
la carte, sous le titre.

Le dégât ne s'arrête pas à l'affichage. `align_same_work_links` refuse de
rapprocher deux recos d'une même œuvre quand leurs créateurs diffèrent : c'est
exactement ce qui empêchait « Voulez-vous rire avec moi ce soir » de recevoir
le lien Netflix que sa jumelle portait déjà. Un champ faux en bloquait un
autre.

CE QUE CETTE GARDE NE FAIT PAS
------------------------------
Elle ne vérifie pas qu'un créateur est LE bon — aucun test local ne peut le
savoir. Elle vérifie une propriété plus étroite et décidable : le champ ne
contient pas le nom d'un diffuseur. C'est la faute qui s'est produite, et la
seule qu'un test puisse attraper sans réseau.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common import CONTENT_DIR

#: Diffuseurs et plateformes relevés dans le corpus. Comparés en minuscules,
#: sur le champ ENTIER : « Netflix » est fautif, « Netflix France » aussi,
#: mais « Marie Netflix » — s'il existait un tel nom — ne le serait pas.
PLATEFORMES = frozenset({
    "netflix", "prime video", "amazon prime", "amazon", "disney+", "disney plus",
    "canal+", "canal plus", "apple tv", "apple tv+", "youtube", "spotify",
    "deezer", "arte", "france tv", "france.tv", "hbo", "hbo max", "ocs",
    "molotov", "twitch", "tiktok", "instagram", "paramount+", "crunchyroll",
    "6play", "m6", "tf1", "salto",
})


def _recos() -> list[Path]:
    return sorted((CONTENT_DIR / "recos").rglob("*.json"))


def test_le_corpus_nest_pas_vide():
    """Sans cette garde, le test ci-dessous passerait sur zéro fichier et
    annoncerait une santé qu'il n'a jamais constatée."""
    assert len(_recos()) > 500


def test_aucune_plateforme_nest_creditee_comme_createur():
    fautifs = []
    for chemin in _recos():
        doc = json.loads(chemin.read_text(encoding="utf-8"))
        if doc.get("status") != "validated":
            continue
        createur = (doc.get("creator") or "").strip()
        if createur.lower() in PLATEFORMES:
            fautifs.append(f"{doc.get('id')} « {doc.get('title')} » → {createur}")
    assert not fautifs, (
        f"{len(fautifs)} reco(s) créditent leur diffuseur comme créateur. "
        f"Le champ s'affiche sur la carte, et il bloque le rapprochement des "
        f"œuvres identiques. Exemples : {fautifs[:5]}"
    )


@pytest.mark.parametrize("nom", sorted(PLATEFORMES))
def test_la_liste_des_plateformes_est_en_minuscules(nom):
    """La comparaison se fait en minuscules : une entrée capitalisée ici ne
    correspondrait jamais, et la garde se croirait verte."""
    assert nom == nom.lower()
