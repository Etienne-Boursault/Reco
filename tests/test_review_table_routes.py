"""Tests pour tools/review_routes_table.py — routes du tableau de pilotage.

Couvre GET /tableau, POST /curation (commentaire + coche) et POST /accept-type
(acceptation d'une proposition de reclassement), y compris les gardes : id
invalide, reco inconnue, proposition absente, repli sans JavaScript.

On réutilise le harnais de `test_review_server` (`_FakeHandler` court-circuite
`BaseHTTPRequestHandler.__init__`, `fake_source` monte l'arborescence).
"""
from __future__ import annotations

import json
from urllib.parse import urlencode

import pytest

import review_curation as rc
import review_routes_table as rrt
import test_review_server as _trs
from common import read_json
from review_handler_base import _reco_path

# Fixtures du harnais partagé, ré-exposées par AFFECTATION (et non par
# `from … import`) : un paramètre de test nommé `fake_source` serait vu par
# pyflakes comme une redéfinition de l'import (F811), règle qu'on ne veut
# désactiver nulle part — c'est elle qui attrape un test qui en masque un autre.
_FakeHandler = _trs._FakeHandler
fake_source = _trs.fake_source
_clear_review_server_caches = _trs._clear_review_server_caches


@pytest.fixture
def sidecar(tmp_path, monkeypatch):
    """Isole le sidecar de curation et le fichier de propositions dans tmp."""
    monkeypatch.setattr(rc, "CURATION_DIR", tmp_path / "curation")
    monkeypatch.setattr(rc, "TYPE_PROPOSALS_PATH", tmp_path / "types_proposes.json")
    return tmp_path


def _post(source_id: str, route: str, fields: dict, accept: str = "") -> _FakeHandler:
    body = urlencode(fields).encode("utf-8")
    h = _FakeHandler(source_id, route, body=body, accept=accept)
    h.do_POST()
    return h


def _json_body(h: _FakeHandler) -> dict:
    return json.loads(h.wfile.getvalue().decode("utf-8"))


# ===== GET /tableau ========================================================
def test_get_tableau_renders(fake_source, sidecar):
    h = _FakeHandler(fake_source, "/tableau")
    h.do_GET()
    body = h.wfile.getvalue().decode("utf-8")
    assert h._status == 200
    assert "reco-table" in body
    # ubm-003 est discarded → absente ; les deux actives sont là.
    assert 'data-id="ubm-001"' in body and 'data-id="ubm-002"' in body
    assert 'data-id="ubm-003"' not in body


def test_get_tableau_propagates_flash(fake_source, sidecar):
    h = _FakeHandler(fake_source, "/tableau?flash=Enregistr%C3%A9&kind=success")
    h.do_GET()
    body = h.wfile.getvalue().decode("utf-8")
    assert "Enregistré" in body and "flash-success" in body


def test_get_tableau_rejects_unknown_flash_kind(fake_source, sidecar, monkeypatch):
    seen = {}

    def _spy(source_id, flash=None, flash_kind="info"):
        seen.update(flash=flash, kind=flash_kind)
        return "<html></html>"

    monkeypatch.setattr(rrt, "render_table_page", _spy)
    h = _FakeHandler(fake_source, "/tableau?flash=x&kind=evil-class")
    h.do_GET()
    assert seen == {"flash": "x", "kind": "info"}


def test_get_tableau_without_flash(fake_source, sidecar, monkeypatch):
    seen = {}

    def _spy(source_id, flash=None, flash_kind="info"):
        seen.update(flash=flash, kind=flash_kind)
        return "<html></html>"

    monkeypatch.setattr(rrt, "render_table_page", _spy)
    _FakeHandler(fake_source, "/tableau").do_GET()
    assert seen == {"flash": None, "kind": "info"}


def test_get_tableau_shows_stored_annotations(fake_source, sidecar):
    rc.set_annotation(fake_source, "ubm-001", comment="à vérifier", checked=True)
    h = _FakeHandler(fake_source, "/tableau")
    h.do_GET()
    body = h.wfile.getvalue().decode("utf-8")
    assert "à vérifier" in body


# ===== POST /curation ======================================================
def test_post_curation_saves_comment(fake_source, sidecar):
    h = _post(fake_source, "/curation",
              {"id": "ubm-001", "comment": "un commentaire"},
              accept="application/json")
    assert h._status == 200
    payload = _json_body(h)
    assert payload["kind"] == "success"
    assert payload["comment"] == "un commentaire"
    assert rc.load_curation(fake_source)["ubm-001"]["comment"] == "un commentaire"


def test_post_curation_saves_checkbox(fake_source, sidecar):
    _post(fake_source, "/curation", {"id": "ubm-001", "checked": "1"},
          accept="application/json")
    assert rc.load_curation(fake_source)["ubm-001"]["checked"] is True


def test_post_curation_unchecking_clears_the_box(fake_source, sidecar):
    rc.set_annotation(fake_source, "ubm-001", comment="garde-moi", checked=True)
    _post(fake_source, "/curation", {"id": "ubm-001", "checked": "0"},
          accept="application/json")
    entry = rc.load_curation(fake_source)["ubm-001"]
    assert entry["checked"] is False
    # Le commentaire de l'autre onglet survit à une écriture de coche seule.
    assert entry["comment"] == "garde-moi"


def test_post_curation_comment_only_keeps_check(fake_source, sidecar):
    rc.set_annotation(fake_source, "ubm-001", checked=True)
    _post(fake_source, "/curation", {"id": "ubm-001", "comment": "note"},
          accept="application/json")
    entry = rc.load_curation(fake_source)["ubm-001"]
    assert entry["checked"] is True and entry["comment"] == "note"


def test_post_curation_rejects_invalid_id(fake_source, sidecar):
    h = _post(fake_source, "/curation", {"id": "../evil", "comment": "x"},
              accept="application/json")
    assert h._status == 400
    assert rc.load_curation(fake_source) == {}


def test_post_curation_rejects_unknown_reco(fake_source, sidecar):
    h = _post(fake_source, "/curation", {"id": "ubm-999", "comment": "x"},
              accept="application/json")
    assert h._status == 404
    assert rc.load_curation(fake_source) == {}


def test_post_curation_without_any_field_is_a_no_op(fake_source, sidecar):
    h = _post(fake_source, "/curation", {"id": "ubm-001"},
              accept="application/json")
    assert h._status == 400
    assert rc.load_curation(fake_source) == {}


def test_post_curation_without_js_redirects(fake_source, sidecar):
    """Repli sans JavaScript : 303 vers /tableau avec le flash."""
    h = _post(fake_source, "/curation", {"id": "ubm-001", "comment": "x"})
    assert h._status == 303
    assert h._sent_headers["Location"].startswith("/tableau?flash=")


def test_post_curation_error_without_js_redirects(fake_source, sidecar):
    h = _post(fake_source, "/curation", {"id": "ubm-999", "comment": "x"})
    assert h._status == 303
    assert "kind=error" in h._sent_headers["Location"]


# ===== POST /accept-type ===================================================
def _write_proposals(sidecar_dir, payload) -> None:
    (sidecar_dir / "types_proposes.json").write_text(
        json.dumps(payload), encoding="utf-8")


def test_post_accept_type_applies_the_proposal(fake_source, sidecar):
    _write_proposals(sidecar, {"ubm-001": {"types": ["serie"], "reason": "c'est une série"}})
    h = _post(fake_source, "/accept-type", {"id": "ubm-001"},
              accept="application/json")
    assert h._status == 200
    payload = _json_body(h)
    assert payload["types"] == ["serie"]
    assert payload["labels"] == "Série"
    assert read_json(_reco_path(fake_source, "ubm-001"))["types"] == ["serie"]


def test_post_accept_type_ignores_client_supplied_types(fake_source, sidecar):
    """Le serveur applique SA proposition, jamais celle postée par le client."""
    _write_proposals(sidecar, {"ubm-001": {"types": ["serie"]}})
    _post(fake_source, "/accept-type", {"id": "ubm-001", "types": "lieu"},
          accept="application/json")
    assert read_json(_reco_path(fake_source, "ubm-001"))["types"] == ["serie"]


def test_post_accept_type_without_proposal_file(fake_source, sidecar):
    h = _post(fake_source, "/accept-type", {"id": "ubm-001"},
              accept="application/json")
    assert h._status == 404
    assert _json_body(h)["kind"] == "error"


def test_post_accept_type_rejects_unknown_type(fake_source, sidecar):
    _write_proposals(sidecar, {"ubm-001": {"types": ["nawak"]}})
    h = _post(fake_source, "/accept-type", {"id": "ubm-001"},
              accept="application/json")
    assert h._status == 404


def test_post_accept_type_rejects_invalid_id(fake_source, sidecar):
    h = _post(fake_source, "/accept-type", {"id": "../evil"},
              accept="application/json")
    assert h._status == 400


def test_post_accept_type_rejects_unknown_reco(fake_source, sidecar):
    _write_proposals(sidecar, {"ubm-999": {"types": ["serie"]}})
    h = _post(fake_source, "/accept-type", {"id": "ubm-999"},
              accept="application/json")
    assert h._status == 404


def test_post_accept_type_unreadable_reco(fake_source, sidecar, monkeypatch):
    _write_proposals(sidecar, {"ubm-001": {"types": ["serie"]}})
    monkeypatch.setattr(rrt, "read_json",
                        lambda _p: (_ for _ in ()).throw(ValueError("corrompu")))
    h = _post(fake_source, "/accept-type", {"id": "ubm-001"},
              accept="application/json")
    assert h._status == 500
    assert _json_body(h)["kind"] == "error"


def test_post_accept_type_without_js_redirects(fake_source, sidecar):
    _write_proposals(sidecar, {"ubm-001": {"types": ["serie"]}})
    h = _post(fake_source, "/accept-type", {"id": "ubm-001"})
    assert h._status == 303
    assert h._sent_headers["Location"].startswith("/tableau?flash=")


# ===== Sécurité du transport (héritée du dispatch POST) ====================
def test_post_curation_refuses_cross_origin(fake_source, sidecar):
    body = urlencode({"id": "ubm-001", "comment": "x"}).encode("utf-8")
    h = _FakeHandler(fake_source, "/curation", body=body)
    h.headers = {"Content-Length": str(len(body)),
                 "Origin": "https://evil.example"}
    h.do_POST()
    assert h._status == 403
    assert rc.load_curation(fake_source) == {}


def test_post_curation_refuses_oversized_body(fake_source, sidecar):
    h = _FakeHandler(fake_source, "/curation", body=b"id=ubm-001")
    h.headers["Content-Length"] = str((1 << 20) + 1)
    h.do_POST()
    assert h._status == 413
    assert rc.load_curation(fake_source) == {}
