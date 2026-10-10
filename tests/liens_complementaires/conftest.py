"""Décor commun des passes du 2026-10-10 : aucun test ne sort sur le réseau.

Trois portes de sortie, toutes fermées par défaut et bruyamment :
- Wikidata (`wikidata_links._get`, et la copie qu'en importe `jeux_wikidata`) ;
- les pages web, si un test oubliait sa fausse session (`requests.Session.get`) ;
- yt-dlp (`youtube_music_links.chercher` / `detailler`).
Un test qui éprouve l'un de ces clients le remplace lui-même : son
`monkeypatch` s'applique après celui du décor. Les doubles (sessions, réponses)
sont dans `tests/_liens_fakes.py`.
"""
from __future__ import annotations

import pytest


def _interdit(*_a, **_k):
    raise AssertionError("appel réseau non simulé dans un test")


@pytest.fixture(autouse=True)
def reseau_ferme(monkeypatch):
    import requests

    import jeux_wikidata
    import wikidata_links
    import youtube_music_links

    monkeypatch.setattr(wikidata_links, "_get", _interdit)
    monkeypatch.setattr(jeux_wikidata, "_get", _interdit)
    monkeypatch.setattr(requests.Session, "get", _interdit)
    monkeypatch.setattr(youtube_music_links, "chercher", _interdit)
    monkeypatch.setattr(youtube_music_links, "detailler", _interdit)
