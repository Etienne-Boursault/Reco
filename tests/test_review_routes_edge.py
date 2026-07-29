"""Routes et chemins d'erreur de `tools/review_routes.py` non couverts par
`tests/test_review_server.py`.

Ce dernier couvre le gros du dispatch ; restaient dans l'ombre deux routes GET
entières (`/doublons`, `/doubt-frag`), le repli **sans JavaScript** de
`/undo-save` (redirection 303 au lieu de la réponse JSON), et une série de
gardes défensives (Referer illisible, épisode disparu, reco illisible).

On réutilise le harnais de `test_review_server` — `_FakeHandler` court-circuite
`BaseHTTPRequestHandler.__init__` pour ne pas ouvrir de socket, et `fake_source`
monte une arborescence de contenu dans `tmp_path`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import review_routes as rt
import review_server as rs
from test_review_server import (  # noqa: F401 — fixtures réutilisées
    _clear_review_server_caches,
    _FakeHandler,
    fake_source,
)


def _recos_dir(source_id: str) -> Path:
    from common import recos_dir_for

    return recos_dir_for(source_id)


# ===== GET /doublons =======================================================
def test_get_doublons_renders_the_dedup_page(fake_source):
    h = _FakeHandler(fake_source, "/doublons")
    h.do_GET()

    assert h._status == 200
    assert h.wfile.getvalue().decode("utf-8").strip() != ""


def test_get_doublons_propagates_flash_and_kind(fake_source):
    """La bannière flash est le seul retour visible sans JS après un POST
    /consolidate : elle doit survivre à la redirection."""
    h = _FakeHandler(
        fake_source,
        "/doublons?flash=3%20recos%20consolid%C3%A9es&kind=success",
    )
    h.do_GET()

    body = h.wfile.getvalue().decode("utf-8")
    assert h._status == 200
    assert "consolidées" in body


def test_get_doublons_rejects_unknown_flash_kind(fake_source, monkeypatch):
    """Un `kind` arbitraire (injection de classe CSS) retombe sur `info`."""
    seen = {}

    def _spy(source_id, flash=None, flash_kind="info"):
        seen["flash"] = flash
        seen["kind"] = flash_kind
        return "<html></html>"

    import review_dedup_page

    monkeypatch.setattr(review_dedup_page, "render_dedup_page", _spy)
    h = _FakeHandler(fake_source, "/doublons?flash=x&kind=evil-class")
    h.do_GET()

    assert seen["kind"] == "info"
    assert seen["flash"] == "x"


def test_get_doublons_without_flash_passes_none(fake_source, monkeypatch):
    seen = {}

    def _spy(source_id, flash=None, flash_kind="info"):
        seen["flash"] = flash
        seen["kind"] = flash_kind
        return "<html></html>"

    import review_dedup_page

    monkeypatch.setattr(review_dedup_page, "render_dedup_page", _spy)
    h = _FakeHandler(fake_source, "/doublons")
    h.do_GET()

    assert seen["flash"] is None
    assert seen["kind"] == "info"


# ===== GET /doubt-frag =====================================================
def test_get_doubt_fragment_is_empty_once_the_reco_left_the_queue(fake_source):
    """Une reco qui n'est plus un doute renvoie un fragment VIDE en 200 : c'est
    ce qui fait disparaître son `<li>` du DOM après le swap AJAX."""
    h = _FakeHandler(fake_source, "/doubt-frag?id=ubm-001")
    h.do_GET()

    assert h._status == 200
    assert h.wfile.getvalue().decode("utf-8") == ""


def test_get_doubt_fragment_edit_mode_returns_the_real_form(fake_source):
    """Sans doublure : `?edit=1` produit bien un formulaire exploitable."""
    h = _FakeHandler(fake_source, "/doubt-frag?id=ubm-001&edit=1")
    h.do_GET()

    body = h.wfile.getvalue().decode("utf-8")
    assert h._status == 200
    assert "<form" in body
    assert "Mortel" in body


def test_get_doubt_fragment_edit_mode(fake_source, monkeypatch):
    """`?edit=1` bascule le fragment en formulaire d'édition — c'est ce qui
    permet « Corriger » sans recharger la page (le lecteur garde sa pause)."""
    seen = {}

    def _spy(source_id, reco_id, edit):
        seen["reco_id"] = reco_id
        seen["edit"] = edit
        return "<form></form>"

    import review_doubts

    monkeypatch.setattr(review_doubts, "render_doubt_fragment", _spy)
    h = _FakeHandler(fake_source, "/doubt-frag?id=ubm-001&edit=1")
    h.do_GET()

    assert seen == {"reco_id": "ubm-001", "edit": True}


def test_get_doubt_fragment_defaults_to_read_mode(fake_source, monkeypatch):
    seen = {}

    def _spy(source_id, reco_id, edit):
        seen["edit"] = edit
        return "<div></div>"

    import review_doubts

    monkeypatch.setattr(review_doubts, "render_doubt_fragment", _spy)
    h = _FakeHandler(fake_source, "/doubt-frag?id=ubm-001&edit=0")
    h.do_GET()

    assert seen["edit"] is False


@pytest.mark.parametrize("bad_id", ["", "../etc/passwd", "pas un id", "ubm 001"])
def test_get_doubt_fragment_rejects_malformed_id(fake_source, bad_id):
    """L'id est validé AVANT toute lecture disque (l'URL est user-supplied)."""
    import urllib.parse

    h = _FakeHandler(
        fake_source, f"/doubt-frag?id={urllib.parse.quote(bad_id)}")
    h.do_GET()

    assert h._status == 404


# ===== POST /undo-save sans JavaScript =====================================
def _push_undo(source_id: str, reco_id: str = "ubm-001",
               guid: str = "ep-001") -> None:
    """Empile un instantané réel via l'API d'undo (pas de fabrication à la
    main du fichier : on veut le même format que la production)."""
    import review_undo

    path = _recos_dir(source_id) / f"{reco_id}.json"
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    snapshot["episodeGuid"] = guid
    review_undo.push_snapshot(source_id, reco_id, str(path), snapshot)


def test_undo_save_without_js_redirects_to_the_episode_queue(fake_source):
    """Sans `Accept: application/json`, on répond en 303 PRG vers la file de
    doutes de l'épisode concerné, flash inclus."""
    _push_undo(fake_source)
    h = _FakeHandler(fake_source, "/undo-save", b"")
    h.do_POST()

    assert h._status == 303
    loc = h._sent_headers["Location"]
    assert loc.startswith("/doutes?ep=ep-001")
    assert "flash=" in loc and "kind=success" in loc


def test_undo_save_without_js_and_without_guid_falls_back_to_queue_root(
    fake_source,
):
    """Instantané sans `episodeGuid` : on retombe sur /doutes sans `?ep=`, et
    le séparateur du flash devient `?` et non `&`."""
    _push_undo(fake_source, guid="")
    h = _FakeHandler(fake_source, "/undo-save", b"")
    h.do_POST()

    loc = h._sent_headers["Location"]
    assert loc.startswith("/doutes?flash=")
    assert "ep=" not in loc


def test_undo_save_without_js_on_empty_stack_warns(fake_source):
    """Rien à annuler : redirection quand même, avec un flash `warning`."""
    h = _FakeHandler(fake_source, "/undo-save", b"")
    h.do_POST()

    assert h._status == 303
    loc = h._sent_headers["Location"]
    assert "kind=warning" in loc
    assert "/doutes" in loc


def test_undo_save_with_json_accept_returns_json(fake_source):
    """Contre-épreuve : avec `Accept: application/json`, pas de redirection."""
    _push_undo(fake_source)
    h = _FakeHandler(fake_source, "/undo-save", b"",
                     accept="application/json")
    h.do_POST()

    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["restored"] is True
    assert payload["reco_id"] == "ubm-001"
    assert "Location" not in h._sent_headers


# ===== _referer_path =======================================================
def test_referer_path_empty_when_header_absent(fake_source):
    h = _FakeHandler(fake_source, "/")
    h.headers.pop("Referer", None)

    assert h._referer_path() == ""


def test_referer_path_extracts_the_path(fake_source):
    h = _FakeHandler(fake_source, "/")
    h.headers["Referer"] = "http://127.0.0.1:8000/doutes?ep=ep-001"

    assert h._referer_path() == "/doutes"


def test_referer_path_empty_when_url_is_unparseable(fake_source):
    """Un Referer forgé illisible ne doit pas faire remonter de `ValueError`
    jusqu'au dispatch POST. Crochet IPv6 non fermé = le cas où `urlparse` lève
    dès l'accès à `.path` (un port non numérique, lui, ne lève qu'à `.port`)."""
    h = _FakeHandler(fake_source, "/")
    h.headers["Referer"] = "http://[::1/doutes"

    assert h._referer_path() == ""


# ===== _cleanup_orphan_tmp_files ===========================================
def test_cleanup_skips_absent_recos_dir(monkeypatch, tmp_path):
    """Source jamais initialisée : rien à nettoyer, aucune exception."""
    import common

    monkeypatch.setattr(common, "RECOS_DIR", tmp_path / "vide")
    monkeypatch.setattr(rt, "BACKUP_DIR", tmp_path / "sans-backup")

    assert rt._cleanup_orphan_tmp_files("source-inconnue") == 0


def test_cleanup_removes_orphans_from_both_dirs(fake_source, monkeypatch,
                                                tmp_path):
    backup = tmp_path / "backup"
    (backup / "2026-07-29").mkdir(parents=True)
    (backup / "2026-07-29" / "x.json.tmp").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(rt, "BACKUP_DIR", backup)
    (_recos_dir(fake_source) / "0001.json.tmp").write_text("{}", encoding="utf-8")

    assert rt._cleanup_orphan_tmp_files(fake_source) == 2
    assert list(_recos_dir(fake_source).glob("*.tmp")) == []


def test_cleanup_survives_undeletable_file(fake_source, monkeypatch, tmp_path):
    monkeypatch.setattr(rt, "BACKUP_DIR", tmp_path / "sans-backup")
    (_recos_dir(fake_source) / "0001.json.tmp").write_text("{}", encoding="utf-8")

    real_unlink = Path.unlink

    def _boom(self, missing_ok=False):
        if self.suffix == ".tmp":
            raise OSError("verrouillé")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _boom)

    assert rt._cleanup_orphan_tmp_files(fake_source) == 0


# ===== POST /consolidate (page /doublons) ==================================
def _consolidate_body(pairs: list[tuple[str, str]]) -> bytes:
    import urllib.parse

    return urllib.parse.urlencode(pairs).encode("utf-8")


def test_consolidate_ignores_malformed_member_ids(fake_source):
    """Les ids viennent d'un formulaire : un id non conforme est ignoré, sans
    faire échouer la consolidation des autres."""
    body = _consolidate_body([
        ("member", "../etc/passwd"), ("member", "ubm-001"), ("keep", "ubm-001"),
    ])
    h = _FakeHandler(fake_source, "/consolidate", body)
    h.do_POST()

    assert h._status == 303
    reco = json.loads(
        (_recos_dir(fake_source) / "ubm-001.json").read_text(encoding="utf-8"))
    assert reco["status"] == "validated"


def test_consolidate_ignores_unknown_reco_id(fake_source):
    """Un id bien formé mais introuvable sur disque est sauté (`_reco_path`
    renvoie None) au lieu de lever."""
    body = _consolidate_body([("member", "ubm-999"), ("keep", "ubm-999")])
    h = _FakeHandler(fake_source, "/consolidate", body)
    h.do_POST()

    assert h._status == 303


def test_consolidate_falls_back_to_validate_on_bad_action(fake_source):
    """`type_<id>` vient du formulaire : une valeur inconnue — ou `discard`,
    qui contredirait la case cochée — retombe sur `validate`."""
    body = _consolidate_body([
        ("member", "ubm-001"), ("keep", "ubm-001"), ("type_ubm-001", "discard"),
    ])
    h = _FakeHandler(fake_source, "/consolidate", body)
    h.do_POST()

    reco = json.loads(
        (_recos_dir(fake_source) / "ubm-001.json").read_text(encoding="utf-8"))
    assert reco["status"] == "validated"


def test_consolidate_keeps_existing_title_when_field_blank(fake_source):
    """Champ titre laissé vide : on garde le titre existant (on n'écrase pas
    une donnée saisie par une chaîne vide)."""
    body = _consolidate_body([
        ("member", "ubm-001"), ("keep", "ubm-001"), ("title_ubm-001", "   "),
    ])
    h = _FakeHandler(fake_source, "/consolidate", body)
    h.do_POST()

    reco = json.loads(
        (_recos_dir(fake_source) / "ubm-001.json").read_text(encoding="utf-8"))
    assert reco["title"] == "Mortel"


def test_consolidate_applies_corrected_title(fake_source):
    body = _consolidate_body([
        ("member", "ubm-001"), ("keep", "ubm-001"),
        ("title_ubm-001", "Mortel (2019)"),
    ])
    h = _FakeHandler(fake_source, "/consolidate", body)
    h.do_POST()

    reco = json.loads(
        (_recos_dir(fake_source) / "ubm-001.json").read_text(encoding="utf-8"))
    assert reco["title"] == "Mortel (2019)"


# ===== POST /edit depuis /doutes : gardes autour de l'instantané d'undo ====
def _edit_body(reco_id: str, title: str = "Mortel corrigé") -> bytes:
    import urllib.parse

    return urllib.parse.urlencode([
        ("id", reco_id), ("title", title), ("types", "film"),
    ]).encode("utf-8")


def test_edit_from_doutes_pushes_a_pre_edit_snapshot(fake_source):
    """Cas nominal de référence : « Corriger » depuis /doutes empile un
    instantané, c'est lui que « ↩ Annuler » restaure."""
    import review_undo

    h = _FakeHandler(fake_source, "/edit", _edit_body("ubm-001"))
    h.headers["Referer"] = "http://127.0.0.1:8000/doutes"
    h.do_POST()

    assert review_undo.has_undo(fake_source) is True
    reco = json.loads(
        (_recos_dir(fake_source) / "ubm-001.json").read_text(encoding="utf-8"))
    assert reco["title"] == "Mortel corrigé"


def test_edit_from_doutes_survives_unreadable_snapshot(fake_source, monkeypatch):
    """L'instantané pré-édition est un confort (l'undo) : s'il est illisible au
    moment de le prendre, la correction s'applique quand même — on ne perd pas
    la saisie de l'utilisateur pour un undo indisponible."""
    import review_undo

    real_read = rt.read_json
    calls = {"n": 0}

    def _first_read_fails(path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("JSON tronqué")
        return real_read(path)

    monkeypatch.setattr(rt, "read_json", _first_read_fails)
    h = _FakeHandler(fake_source, "/edit", _edit_body("ubm-001"))
    h.headers["Referer"] = "http://127.0.0.1:8000/doutes"
    h.do_POST()

    reco = json.loads(
        (_recos_dir(fake_source) / "ubm-001.json").read_text(encoding="utf-8"))
    assert reco["title"] == "Mortel corrigé"
    # Pas d'instantané empilé : il n'a pas pu être pris.
    assert review_undo.has_undo(fake_source) is False


def test_edit_from_doutes_survives_failing_post_edit_marking(fake_source,
                                                             monkeypatch):
    """La pose du marqueur `reviewedByHuman` (qui sort la reco de la file) est
    best-effort : si la relecture échoue, la correction reste appliquée et la
    réponse reste un succès."""
    real_read = rt.read_json
    calls = {"n": 0}

    def _later_read_fails(path):
        calls["n"] += 1
        if calls["n"] >= 2:  # 1er appel = instantané pré-édition, OK
            raise OSError("fichier verrouillé")
        return real_read(path)

    monkeypatch.setattr(rt, "read_json", _later_read_fails)
    h = _FakeHandler(fake_source, "/edit", _edit_body("ubm-001"),
                     accept="application/json")
    h.headers["Referer"] = "http://127.0.0.1:8000/doutes"
    h.do_POST()

    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "success"
    reco = json.loads(
        (_recos_dir(fake_source) / "ubm-001.json").read_text(encoding="utf-8"))
    assert reco["title"] == "Mortel corrigé"
    assert reco.get("agentReview", {}).get("reviewedByHuman") is not True


# ===== _reply_post / _send_json_post =======================================
def test_reply_post_without_flash_omits_the_banner_params(fake_source):
    h = _FakeHandler(fake_source, "/")
    h._reply_post("ep-001", "", "success", "ok", "ubm-001")

    assert h._sent_headers["Location"] == "/ep?guid=ep-001"


def test_send_json_post_omits_card_when_episode_is_gone(fake_source):
    """L'épisode référencé par la reco n'existe plus : on renvoie quand même
    kind/message, avec `card_html` vide, plutôt qu'un 500."""
    path = _recos_dir(fake_source) / "ubm-001.json"
    reco = json.loads(path.read_text(encoding="utf-8"))
    reco["episodeGuid"] = "ep-disparu"
    path.write_text(json.dumps(reco), encoding="utf-8")
    rs._invalidate_reco_path_cache(fake_source)

    h = _FakeHandler(fake_source, "/", accept="application/json")
    h._send_json_post("ep-disparu", "success", "ok", "ubm-001")

    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["card_html"] == ""
    assert payload["kind"] == "success"


def test_send_json_post_skips_rebuild_for_unknown_reco(fake_source):
    """Reco introuvable : on ne tente même pas de reconstruire la carte."""
    h = _FakeHandler(fake_source, "/", accept="application/json")
    h._send_json_post("ep-001", "warning", "rien à faire", "ubm-999")

    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload == {"kind": "warning", "message": "rien à faire",
                       "card_html": ""}


def test_send_json_post_rebuilds_the_card_on_success(fake_source):
    """Contre-épreuve du cas nominal : la carte fraîche est bien renvoyée,
    sinon l'update partiel côté client n'aurait rien à afficher."""
    h = _FakeHandler(fake_source, "/", accept="application/json")
    h._send_json_post("ep-001", "success", "ok", "ubm-001")

    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert "Mortel" in payload["card_html"]


def test_send_json_post_survives_unreadable_reco(fake_source, monkeypatch):
    """Reco illisible pendant le rebuild de la carte : réponse dégradée sans
    HTML, pas d'exception."""
    def _boom(path):
        raise ValueError("JSON tronqué")

    monkeypatch.setattr(rt, "read_json", _boom)
    h = _FakeHandler(fake_source, "/", accept="application/json")
    h._send_json_post("ep-001", "success", "ok", "ubm-001")

    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["card_html"] == ""
