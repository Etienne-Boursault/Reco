"""Doubles partagés des tests des passes de liens du 2026-10-10.

Aucun réseau : une fausse session répond selon l'URL demandée, avec des pages
réduites à ce que les clients lisent.
"""
from __future__ import annotations

import json
from pathlib import Path


class FausseReponse:
    """Ce que les clients lisent d'une réponse HTTP."""

    def __init__(self, texte="", status_code=200, url="", charge=None):
        self.text = texte
        self.status_code = status_code
        self.url = url
        self._charge = charge

    def json(self):
        if self._charge is None:
            raise ValueError("pas du JSON")
        return self._charge


class FausseSession:
    """Répond selon l'URL demandée (dictionnaire), et garde la trace des appels.

    Une valeur `Exception` est levée ; une URL absente fait échouer le test.
    """

    def __init__(self, pages=None):
        self.pages = dict(pages or {})
        self.appels = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.appels.append({"url": url, "params": params or {}, "headers": headers or {}})
        if url not in self.pages:
            raise AssertionError(f"URL non simulée : {url}")
        reponse = self.pages[url]
        if isinstance(reponse, Exception):
            raise reponse
        if not reponse.url:
            reponse.url = url
        return reponse


def ecrire_reco(racine: Path, source: str, reco: dict) -> Path:
    dossier = racine / source
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{reco['id']}.json"
    chemin.write_text(json.dumps(reco, ensure_ascii=False, indent=2), encoding="utf-8")
    return chemin


def lire(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))
