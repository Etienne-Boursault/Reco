"""Décor commun : aucun test ne doit pouvoir appeler Wikidata pour de vrai.

Le réseau de cette passe passe par un seul point, `wikidata_links._get`. On le
remplace par défaut par un double qui ÉCHOUE bruyamment : un test qui oublierait
de simuler sa réponse partirait sinon sur le réseau, et vert ou rouge selon la
connexion de la machine. Le piège est connu du dépôt — la fixture qui neutralise
TMDB ne couvrait qu'une des deux passes, et les tests allaient chercher la vraie
clé en se contentant d'un avertissement.

Un test qui porte sur le client remplace simplement ce double : son `monkeypatch`
s'applique après celui du décor.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def wikidata_muet(monkeypatch):
    """Tout appel non simulé casse le test, au lieu de sortir sur le réseau."""
    import wikidata_links

    def interdit(*_a, **_k):
        raise AssertionError(
            "appel réseau non simulé : remplacez `wikidata_links._get` "
            "(ou la fonction de client) dans ce test")

    monkeypatch.setattr(wikidata_links, "_get", interdit)
