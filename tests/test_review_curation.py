"""Tests pour tools/review_curation.py — sidecar d'annotations de curation.

Le module est neuf : exigence 100 % statements ET branches. Chaque garde
défensive (fichier absent, JSON corrompu, racine non-dict, entrée non-dict,
champ du mauvais type) a donc son test.
"""
from __future__ import annotations

import json

import pytest

import review_curation as rc


@pytest.fixture
def cur_dir(tmp_path, monkeypatch):
    """Redirige le dossier sidecar vers tmp_path."""
    d = tmp_path / "curation"
    monkeypatch.setattr(rc, "CURATION_DIR", d)
    return d


# ===== curation_path =======================================================
def test_curation_path_uses_slugified_source(cur_dir):
    assert rc.curation_path("un-bon-moment") == cur_dir / "un-bon-moment.json"


def test_curation_path_neutralises_path_traversal(cur_dir):
    """Un source_id hostile ne doit pas pouvoir sortir du dossier sidecar."""
    path = rc.curation_path("../../etc/passwd")
    assert path.parent == cur_dir
    assert ".." not in path.name


# ===== load_curation =======================================================
def test_load_curation_missing_file_is_empty(cur_dir):
    assert rc.load_curation("src") == {}


def test_load_curation_corrupt_json_is_empty(cur_dir):
    cur_dir.mkdir(parents=True)
    (cur_dir / "src.json").write_text("{not json", encoding="utf-8")
    assert rc.load_curation("src") == {}


def test_load_curation_non_dict_root_is_empty(cur_dir):
    cur_dir.mkdir(parents=True)
    (cur_dir / "src.json").write_text("[1, 2]", encoding="utf-8")
    assert rc.load_curation("src") == {}


def test_load_curation_unreadable_file_is_empty(cur_dir, monkeypatch):
    """Une OSError autre que FileNotFoundError (permissions…) → {} + warning."""
    cur_dir.mkdir(parents=True)
    p = cur_dir / "src.json"
    p.write_text("{}", encoding="utf-8")

    def _boom(*_a, **_kw):
        raise PermissionError("nope")

    monkeypatch.setattr(rc.Path, "read_text", _boom)
    assert rc.load_curation("src") == {}


def test_load_curation_normalises_entries(cur_dir):
    cur_dir.mkdir(parents=True)
    (cur_dir / "src.json").write_text(json.dumps({
        "ubm-1": {"comment": "  bien vu  ", "checked": True,
                  "updatedAt": "2026-07-31T10:00:00+00:00"},
        "ubm-2": {"comment": "x"},
    }), encoding="utf-8")
    data = rc.load_curation("src")
    assert data["ubm-1"] == {"comment": "bien vu", "checked": True,
                             "updatedAt": "2026-07-31T10:00:00+00:00"}
    # champs absents → valeurs par défaut, jamais de KeyError côté rendu
    assert data["ubm-2"] == {"comment": "x", "checked": False, "updatedAt": ""}


def test_load_curation_skips_non_dict_entries(cur_dir):
    cur_dir.mkdir(parents=True)
    (cur_dir / "src.json").write_text(
        json.dumps({"ubm-1": "juste une string", "ubm-2": {"checked": True}}),
        encoding="utf-8")
    data = rc.load_curation("src")
    assert "ubm-1" not in data
    assert data["ubm-2"]["checked"] is True


def test_load_curation_coerces_wrong_field_types(cur_dir):
    """`comment` numérique et `updatedAt` non-string → repli sur des chaînes."""
    cur_dir.mkdir(parents=True)
    (cur_dir / "src.json").write_text(
        json.dumps({"ubm-1": {"comment": 42, "updatedAt": 7, "checked": "oui"}}),
        encoding="utf-8")
    assert rc.load_curation("src")["ubm-1"] == {
        "comment": "", "checked": True, "updatedAt": ""}


# ===== set_annotation ======================================================
def test_set_annotation_creates_file_and_returns_entry(cur_dir):
    entry = rc.set_annotation("src", "ubm-1", comment="à revoir")
    assert entry["comment"] == "à revoir"
    assert entry["checked"] is False
    assert entry["updatedAt"].endswith("+00:00")
    assert rc.load_curation("src")["ubm-1"]["comment"] == "à revoir"


def test_set_annotation_only_touches_supplied_fields(cur_dir):
    """Deux onglets : poser la coche ne doit PAS effacer le commentaire."""
    rc.set_annotation("src", "ubm-1", comment="mon commentaire")
    rc.set_annotation("src", "ubm-1", checked=True)
    entry = rc.load_curation("src")["ubm-1"]
    assert entry == {"comment": "mon commentaire", "checked": True,
                     "updatedAt": entry["updatedAt"]}


def test_set_annotation_preserves_other_recos(cur_dir):
    """Écrire sur ubm-2 ne perd pas l'annotation de ubm-1 (autre onglet)."""
    rc.set_annotation("src", "ubm-1", comment="un")
    rc.set_annotation("src", "ubm-2", comment="deux")
    data = rc.load_curation("src")
    assert data["ubm-1"]["comment"] == "un"
    assert data["ubm-2"]["comment"] == "deux"


def test_set_annotation_truncates_long_comment(cur_dir):
    entry = rc.set_annotation("src", "ubm-1", comment="a" * (rc.MAX_COMMENT_LEN + 50))
    assert len(entry["comment"]) == rc.MAX_COMMENT_LEN


def test_set_annotation_drops_empty_entry(cur_dir):
    """Commentaire vidé + coche retirée → l'entrée disparaît du sidecar."""
    rc.set_annotation("src", "ubm-1", comment="x", checked=True)
    rc.set_annotation("src", "ubm-1", comment="", checked=False)
    assert rc.load_curation("src") == {}


def test_set_annotation_drop_is_idempotent_on_unknown_id(cur_dir):
    entry = rc.set_annotation("src", "ubm-jamais-vu", comment="   ")
    assert entry == {"comment": "", "checked": False,
                     "updatedAt": entry["updatedAt"]}
    assert rc.load_curation("src") == {}


def test_set_annotation_checked_only_keeps_entry(cur_dir):
    rc.set_annotation("src", "ubm-1", checked=True)
    assert rc.load_curation("src")["ubm-1"]["checked"] is True


# ===== load_type_proposals =================================================
def _write_proposals(tmp_path, monkeypatch, payload) -> None:
    p = tmp_path / "types_proposes.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(rc, "TYPE_PROPOSALS_PATH", p)


def test_load_type_proposals_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(rc, "TYPE_PROPOSALS_PATH", tmp_path / "absent.json")
    assert rc.load_type_proposals() == {}


def test_load_type_proposals_mapping_to_string(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch, {"ubm-1": "film"})
    assert rc.load_type_proposals()["ubm-1"] == {
        "types": ["film"], "reason": "", "confidence": "", "arbitrage": ""}


def test_load_type_proposals_mapping_to_list(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch, {"ubm-1": ["film", "serie", 7]})
    assert rc.load_type_proposals()["ubm-1"]["types"] == ["film", "serie"]


def test_load_type_proposals_mapping_to_object(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch,
                     {"ubm-1": {"types": ["livre"], "reason": "c'est un roman"}})
    assert rc.load_type_proposals()["ubm-1"] == {
        "types": ["livre"], "reason": "c'est un roman",
        "confidence": "", "arbitrage": ""}


def test_load_type_proposals_object_with_types_as_bare_string(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch, {"ubm-1": {"types": "podcast"}})
    assert rc.load_type_proposals()["ubm-1"]["types"] == ["podcast"]


def test_load_type_proposals_object_without_any_type_is_skipped(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch, {"ubm-1": {"reason": "je sais pas"}})
    assert rc.load_type_proposals() == {}


def test_load_type_proposals_object_with_singular_type_and_why(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch,
                     {"ubm-1": {"type": "bd", "why": "album illustré"}})
    assert rc.load_type_proposals()["ubm-1"] == {
        "types": ["bd"], "reason": "album illustré",
        "confidence": "", "arbitrage": ""}


def test_load_type_proposals_object_with_note(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch,
                     {"ubm-1": {"types": ["jeu"], "note": "jeu vidéo"}})
    assert rc.load_type_proposals()["ubm-1"]["reason"] == "jeu vidéo"


def test_load_type_proposals_object_with_non_string_reason(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch, {"ubm-1": {"types": ["jeu"], "reason": 3}})
    assert rc.load_type_proposals()["ubm-1"]["reason"] == ""


def test_load_type_proposals_list_of_objects(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch,
                     [{"id": "ubm-1", "types": ["film"]}, {"id": "ubm-2", "type": "bd"}])
    props = rc.load_type_proposals()
    assert props["ubm-1"]["types"] == ["film"]
    assert props["ubm-2"]["types"] == ["bd"]


def test_load_type_proposals_wrapped_in_proposals_key(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch,
                     {"generatedAt": "x",
                      "proposals": [{"id": "ubm-1", "types": ["film"]}]})
    assert rc.load_type_proposals()["ubm-1"]["types"] == ["film"]


def test_load_type_proposals_french_report_shape(tmp_path, monkeypatch):
    """Forme réellement produite par la passe de reclassement (tout en français)."""
    _write_proposals(tmp_path, monkeypatch, {
        "genereLe": "2026-07-31",
        "statistiques": {"recosAnalysees": 178},
        "propositions": [
            {"id": "ubm-1", "typesActuels": ["autre"], "typesProposes": ["lieu"],
             "justification": "Comedy club à Barbès."},
        ],
    })
    assert rc.load_type_proposals() == {"ubm-1": {
        "types": ["lieu"], "reason": "Comedy club à Barbès.",
        "confidence": "", "arbitrage": ""}}


def test_load_type_proposals_singular_french_type(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch,
                     {"propositions": [{"id": "ubm-1", "typesProposes": "livre"}]})
    assert rc.load_type_proposals()["ubm-1"] == {
        "types": ["livre"], "reason": "", "confidence": "", "arbitrage": ""}


def test_load_type_proposals_skips_malformed_items(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch, [
        "pas un objet",
        {"types": ["film"]},           # sans id
        {"id": "ubm-1", "types": []},  # sans type exploitable
        {"id": "ubm-2", "types": ["film"]},
    ])
    assert list(rc.load_type_proposals()) == ["ubm-2"]


def test_load_type_proposals_non_dict_value_is_skipped(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch, {"ubm-1": 42, "ubm-2": "film"})
    assert list(rc.load_type_proposals()) == ["ubm-2"]


def test_load_type_proposals_non_dict_root_is_empty(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch, "juste une string")
    assert rc.load_type_proposals() == {}


def test_load_type_proposals_carries_confidence_and_arbitrage(tmp_path, monkeypatch):
    """Les 35 cas « à trancher » et le niveau de confiance doivent remonter :
    ce sont eux qu'il ne faut PAS accepter d'un clic mécanique."""
    _write_proposals(tmp_path, monkeypatch, {"proposals": [
        {"id": "ubm-1", "types": ["artiste"], "reason": "chaîne perso",
         "confidence": "inference",
         "arbitrage": "Artiste ou chaîne YouTube ?"},
    ]})
    assert rc.load_type_proposals()["ubm-1"] == {
        "types": ["artiste"], "reason": "chaîne perso",
        "confidence": "inference", "arbitrage": "Artiste ou chaîne YouTube ?"}


def test_load_type_proposals_french_confidence_key(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch, {"propositions": [
        {"id": "ubm-1", "typesProposes": ["film"], "confiance": "certain"}]})
    assert rc.load_type_proposals()["ubm-1"]["confidence"] == "certain"


def test_load_type_proposals_null_arbitrage_is_empty(tmp_path, monkeypatch):
    """`arbitrage: null` (le cas des 143 entrées sans question) → chaîne vide."""
    _write_proposals(tmp_path, monkeypatch, {"proposals": [
        {"id": "ubm-1", "types": ["film"], "arbitrage": None}]})
    assert rc.load_type_proposals()["ubm-1"]["arbitrage"] == ""


def test_load_type_proposals_scalar_value_has_no_extras(tmp_path, monkeypatch):
    _write_proposals(tmp_path, monkeypatch, {"ubm-1": "film"})
    entry = rc.load_type_proposals()["ubm-1"]
    assert entry["confidence"] == "" and entry["arbitrage"] == ""


def test_load_type_proposals_explicit_path(tmp_path):
    p = tmp_path / "ailleurs.json"
    p.write_text(json.dumps({"ubm-9": "album"}), encoding="utf-8")
    assert rc.load_type_proposals(p)["ubm-9"]["types"] == ["album"]
