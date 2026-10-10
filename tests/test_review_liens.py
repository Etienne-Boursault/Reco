"""Bloc « Liens » de la carte et route /retirer-lien (page de relecture)."""
from __future__ import annotations

import json

import review_render as rr
from _html_helpers import parse
from test_review_server import (  # noqa: F401 — fixtures et doublure partagées
    _clear_review_server_caches,
    _FakeHandler,
    fake_source,
)

DEEZER = {"ethics": "neutral", "kind": "streaming", "label": "Deezer",
          "url": "https://www.deezer.com/track/1"}
PRIME = {"ethics": "avoid", "kind": "streaming", "label": "Prime Video",
         "url": "https://www.primevideo.com/x"}


def test_render_liens_shows_each_link_with_a_remove_button():
    out = rr.render_liens({"id": "r-1", "links": [DEEZER, PRIME, {"label": "x"},
                                                  {"label": "<js>", "url": "javascript:alert(1)"}]})
    soup = parse(out)
    liens = soup.select(".liens li")
    assert len(liens) == 3  # le lien sans URL est ignoré
    assert liens[0].a["href"] == DEEZER["url"] and liens[0].a["rel"] == ["noopener", "noreferrer"]
    assert "lien-avoid" in liens[1].a["class"]
    assert liens[2].a is None and "&lt;js&gt;" in out  # URL dangereuse : texte seul
    forms = soup.select("form.lien-retirer")
    assert {f.select_one("[name=url]")["value"] for f in forms} >= {DEEZER["url"]}
    assert all(f["action"] == "/retirer-lien" for f in forms)


def test_render_liens_says_when_there_is_none():
    assert "aucun pour l’instant" in rr.render_liens({"id": "r-1"})


def test_card_contains_the_links_block(fake_source):  # noqa: F811
    soup = parse(rr._reco_card({"id": "x", "title": "T", "links": [DEEZER]},
                               {"guid": "g", "title": "Ep"}, [], fake_source))
    assert soup.select_one("li.row .liens a")["href"] == DEEZER["url"]


def _reco_path(source):
    import common
    return common.recos_dir_for(source) / "ubm-001.json"


def _poster(source, body, accept="application/json"):
    h = _FakeHandler(source, "/retirer-lien", body.encode(), accept=accept)
    h.do_POST()
    return h


def test_retirer_lien_removes_it_and_remembers_it(fake_source):  # noqa: F811
    path = _reco_path(fake_source)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["links"] = [DEEZER, PRIME]
    path.write_text(json.dumps(doc), encoding="utf-8")

    h = _poster(fake_source, "id=ubm-001&url=https%3A%2F%2Fwww.primevideo.com%2Fx")

    assert h._status == 200
    payload = json.loads(h.wfile.getvalue().decode("utf-8"))
    assert payload["kind"] == "success" and "primevideo" not in payload["card_html"]
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["links"] == [DEEZER] and doc["linksRejected"] == [PRIME["url"]]
    # Une seconde fois : plus rien à retirer, aucune écriture.
    h = _poster(fake_source, "id=ubm-001&url=https%3A%2F%2Fwww.primevideo.com%2Fx")
    assert json.loads(h.wfile.getvalue().decode("utf-8"))["kind"] == "warning"


def test_retirer_lien_refuses_bad_requests(fake_source):  # noqa: F811
    for body in ("id=../x&url=https%3A%2F%2Fa", "id=ubm-001&url=", "id=ubm-999&url=https%3A%2F%2Fa"):
        h = _poster(fake_source, body)
        assert json.loads(h.wfile.getvalue().decode("utf-8"))["kind"] == "error"


def test_retirer_lien_already_rejected_is_not_listed_twice(fake_source):  # noqa: F811
    """Une passe a reposé un lien déjà rejeté : on le retire, sans doublon."""
    path = _reco_path(fake_source)
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc.update(links=[PRIME], linksRejected=[PRIME["url"]])
    path.write_text(json.dumps(doc), encoding="utf-8")

    _poster(fake_source, "id=ubm-001&url=https%3A%2F%2Fwww.primevideo.com%2Fx", accept="")

    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["links"] == [] and doc["linksRejected"] == [PRIME["url"]]
