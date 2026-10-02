"""Décor commun : aucun test ne doit pouvoir appeler Steam ou un libraire pour de vrai.

Tout le réseau de cette passe passe par `boutique_links._demander`. On le remplace
par défaut par un double qui ÉCHOUE bruyamment : un test qui oublierait de simuler
sa réponse partirait sinon sur le réseau, et serait vert ou rouge selon la
connexion de la machine — et selon l'humeur de Google Books, qui répond 429 sans
prévenir. Le piège est connu du dépôt : la fixture qui neutralisait TMDB ne
couvrait qu'une des deux passes, et les tests allaient chercher la vraie clé en se
contentant d'un avertissement.

Un test qui porte sur un client remplace simplement ce double : son `monkeypatch`
s'applique après celui du décor.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def boutique_muette(monkeypatch):
    """Tout appel non simulé casse le test, au lieu de sortir sur le réseau."""
    import boutique_links

    def interdit(*_a, **_k):
        raise AssertionError(
            "appel réseau non simulé : remplacez `boutique_links._demander` "
            "(ou la fonction de client) dans ce test")

    monkeypatch.setattr(boutique_links, "_demander", interdit)
