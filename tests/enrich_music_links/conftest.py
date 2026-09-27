"""Décor commun aux tests de l'enrichissement musical.

Deux plateformes doivent être NEUTRALISÉES par défaut, sinon les tests
dépendraient de la machine qui les lance :

  - **Spotify** lit ses identifiants dans l'environnement, et
    `spotify_credentials()` charge `tools/.env` au passage. Supprimer les
    variables ne suffit donc pas : sur un poste qui possède ce fichier (celui de
    l'éditeur), `load_dotenv` les remettrait et la passe partirait sur le
    réseau. On remplace la fonction elle-même.
  - **Qobuz** ouvre de vraies pages web. Les tests qui ne parlent pas de Qobuz
    n'ont pas à l'attendre. Son interrupteur d'exploitation (`RECO_QOBUZ`) est
    remis à l'état actif pour la même raison : sur une machine qui l'a coupé,
    les tests qui attendent un refus de Qobuz verraient un `qobuz-disabled`.

Un test qui porte sur l'une des deux remplace simplement ces doubles : son
`monkeypatch` s'applique après celui du décor.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def spotify_et_qobuz_muets(monkeypatch):
    """Spotify sans identifiants et Qobuz sans réponse, sauf mention contraire."""
    import music_links_clients
    import music_links_pipeline

    monkeypatch.setattr(music_links_clients, "spotify_credentials", lambda: None)
    monkeypatch.setattr(music_links_pipeline, "spotify_credentials", lambda: None)
    monkeypatch.setattr(music_links_pipeline, "qobuz_candidates",
                        lambda *_a, **_k: [])
    monkeypatch.delenv("RECO_QOBUZ", raising=False)
