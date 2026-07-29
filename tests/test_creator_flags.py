"""Tests de creator_flags.py — signalements « situation de l'artiste »."""
from __future__ import annotations

import json

import creator_flags as cf


def _write_flags(tmp_path, flags):
    p = tmp_path / "creator-flags.json"
    p.write_text(json.dumps({"flags": flags}, ensure_ascii=False), encoding="utf-8")
    return p


def _use(tmp_path, monkeypatch, flags):
    p = _write_flags(tmp_path, flags)
    monkeypatch.setattr(cf, "_FLAGS_PATH", p)
    monkeypatch.setattr(cf, "_cache", {"mtime": None, "index": {}})
    return p


def test_no_flag_returns_empty(tmp_path, monkeypatch):
    _use(tmp_path, monkeypatch, [])
    assert cf.flag_for("Quelqu'un") is None
    assert cf.flag_badge_html("Quelqu'un") == ""


def test_match_is_accent_and_case_insensitive(tmp_path, monkeypatch):
    _use(tmp_path, monkeypatch, [
        {"names": ["Gérard Exemple"], "situation": "Mis en examen.",
         "source": "https://ex.fr/a", "severity": "accusation"},
    ])
    assert cf.flag_for("Gérard Exemple")
    assert cf.flag_for("gerard  exemple")   # accents + casse + espaces
    assert cf.flag_for("GÉRARD EXEMPLE")
    assert cf.flag_for("Autre Personne") is None


def test_badge_contains_situation_and_source(tmp_path, monkeypatch):
    _use(tmp_path, monkeypatch, [
        {"names": ["X Y"], "situation": "Condamné en 2023.",
         "source": "https://ex.fr/b", "severity": "condamnation"},
    ])
    html = cf.flag_badge_html("X Y")
    assert 'data-severity="condamnation"' in html
    assert "Condamné en 2023." in html
    assert 'href="https://ex.fr/b"' in html
    assert 'target="_blank"' in html


def test_incomplete_entries_ignored(tmp_path, monkeypatch):
    """Une entrée sans situation OU sans source est ignorée (curation garde-fou)."""
    _use(tmp_path, monkeypatch, [
        {"names": ["No Source"], "situation": "Truc."},          # pas de source
        {"names": ["No Sit"], "source": "https://ex.fr/c"},      # pas de situation
        {"situation": "x", "source": "https://ex.fr/d"},          # pas de names
    ])
    assert cf.flag_for("No Source") is None
    assert cf.flag_for("No Sit") is None


def test_non_http_source_omitted_from_badge(tmp_path, monkeypatch):
    """Une source non http(s) (ex. javascript:) ne produit pas de lien."""
    _use(tmp_path, monkeypatch, [
        {"names": ["Z"], "situation": "S.", "source": "javascript:alert(1)"},
    ])
    html = cf.flag_badge_html("Z")
    assert html != ""                 # le badge s'affiche quand même
    assert "javascript:" not in html  # mais pas de lien source
    assert "cflag-src" not in html


def test_missing_file_is_graceful(tmp_path, monkeypatch):
    """Fichier absent → aucun signalement, pas d'exception."""
    monkeypatch.setattr(cf, "_FLAGS_PATH", tmp_path / "does-not-exist.json")
    monkeypatch.setattr(cf, "_cache", {"mtime": None, "index": {}})
    assert cf.flag_for("Whoever") is None
    assert cf.flag_badge_html("Whoever") == ""


def test_reloads_on_file_change(tmp_path, monkeypatch):
    """Éditer le fichier est pris en compte sans redémarrage (cache sur mtime)."""
    p = _use(tmp_path, monkeypatch, [])
    assert cf.flag_for("Nouveau") is None
    # Réécrit avec une mtime distincte (utime explicite : évite la granularité FS).
    import os
    p.write_text(json.dumps({"flags": [
        {"names": ["Nouveau"], "situation": "S.", "source": "https://ex.fr/e"},
    ]}), encoding="utf-8")
    os.utime(p, (1_000_000, 2_000_000))
    assert cf.flag_for("Nouveau")


def test_missing_flags_file_yields_no_signalement(tmp_path, monkeypatch):
    """Le fichier est curé à la main et livré VIDE : son absence doit être un
    cas normal, jamais une erreur au build."""
    monkeypatch.setattr(cf, "_FLAGS_PATH", tmp_path / "jamais-cree.json")
    monkeypatch.setattr(cf, "_cache", {"mtime": None, "index": {}})

    assert cf.flag_for("Quelqu'un") is None
    assert cf.flag_badge_html("Quelqu'un") == ""


def test_unreadable_flags_file_is_ignored(tmp_path, monkeypatch, caplog):
    """JSON corrompu : on log et on ignore les signalements plutôt que de
    casser la génération du site."""
    p = tmp_path / "creator-flags.json"
    p.write_text("{ tronqué", encoding="utf-8")
    monkeypatch.setattr(cf, "_FLAGS_PATH", p)
    monkeypatch.setattr(cf, "_cache", {"mtime": None, "index": {}})

    with caplog.at_level("WARNING", logger="reco"):
        assert cf.flag_for("Quelqu'un") is None

    assert "illisible" in caplog.text


def test_flag_for_empty_creator_returns_none(tmp_path, monkeypatch):
    """Une œuvre sans créateur renseigné ne doit pas déclencher de lookup."""
    _use(tmp_path, monkeypatch, [
        {"names": ["Quelqu'un"], "label": "situation", "source": "https://x"},
    ])

    assert cf.flag_for(None) is None
    assert cf.flag_for("") is None


def test_build_index_survives_a_file_deleted_mid_read(tmp_path, monkeypatch):
    """`_build_index` est protégé contre la disparition du fichier entre le
    `stat()` de `_index()` et sa propre lecture (édition manuelle en cours).
    On l'appelle directement : par le flux normal, `_index()` intercepte déjà
    l'absence en amont."""
    monkeypatch.setattr(cf, "_FLAGS_PATH", tmp_path / "supprime-entre-temps.json")

    assert cf._build_index() == {}


def test_first_declaration_wins_for_duplicate_names(tmp_path, monkeypatch):
    """Deux entrées visant le même créateur : la première déclarée l'emporte
    (le fichier est curé à la main, l'ordre y fait foi)."""
    _use(tmp_path, monkeypatch, [
        {"names": ["Roman Polanski"], "situation": "première",
         "source": "https://exemple.fr/1"},
        {"names": ["roman  polanski", ""], "situation": "seconde",
         "source": "https://exemple.fr/2"},
    ])

    flag = cf.flag_for("Roman Polanski")

    assert flag is not None
    assert flag["situation"] == "première"

