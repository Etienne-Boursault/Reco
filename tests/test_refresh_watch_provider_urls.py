"""Tests de tools/refresh_watch_provider_urls.py : reconstruire les boutons
« où regarder » des recos déjà publiées, sans rappeler TMDB."""
from __future__ import annotations

import json
import sys

import refresh_watch_provider_urls as refresh


def _reco(dossier, nom, contenu):
    (dossier / nom).write_text(json.dumps(contenu, ensure_ascii=False), encoding="utf-8")


def test_la_reconstruction_retire_les_plateformes_mortes_et_les_doublons(tmp_path, monkeypatch):
    _reco(tmp_path, "0001.json", {"id": "ubm-0001", "title": "Mortel", "watchProviders": [
        {"label": "Orange VOD", "url": "https://video.orange.fr/search?q=Mortel", "ethics": "neutral"},
        {"label": "Paramount Plus", "url": "x", "ethics": "neutral"},
        {"label": "Paramount Plus Premium", "url": "x", "ethics": "neutral"},
    ]})
    _reco(tmp_path, "0002.json", {"id": "ubm-0002", "title": "Sans plateforme"})
    monkeypatch.setattr(refresh, "recos_dir_for", lambda source: tmp_path)
    monkeypatch.setattr(sys, "argv", ["refresh", "--source", "un-bon-moment"])

    refresh.main()

    reco = json.loads((tmp_path / "0001.json").read_text(encoding="utf-8"))
    assert [p["label"] for p in reco["watchProviders"]] == ["Paramount Plus"]
    assert "paramountplus.com" in reco["watchProviders"][0]["url"]
    assert "watchProviders" not in json.loads((tmp_path / "0002.json").read_text(encoding="utf-8"))

    # Idempotent : un second passage ne réécrit rien.
    ecritures = []
    reel = refresh.write_json_if_changed
    monkeypatch.setattr(refresh, "write_json_if_changed",
                        lambda p, d: ecritures.append(reel(p, d)) or ecritures[-1])
    refresh.main()
    assert ecritures == [False]


def test_une_reco_qui_perd_tous_ses_boutons_perd_le_champ(tmp_path, monkeypatch):
    """Comme enrich_tmdb, qui retire la clé quand la liste est vide."""
    _reco(tmp_path, "0001.json", {"id": "ubm-0001", "title": "Mortel", "watchProviders": [
        {"label": "Orange VOD", "url": "https://video.orange.fr/search?q=Mortel", "ethics": "neutral"},
    ]})
    monkeypatch.setattr(refresh, "recos_dir_for", lambda source: tmp_path)
    monkeypatch.setattr(sys, "argv", ["refresh", "--source", "un-bon-moment"])

    refresh.main()

    assert "watchProviders" not in json.loads((tmp_path / "0001.json").read_text(encoding="utf-8"))
