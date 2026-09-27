"""Raccordement de l'étape `publier` à la chaîne de venus.

La mécanique git est éprouvée dans `test_publication.py`, sur un vrai dépôt. Ici
on ne vérifie que le câblage : qui est en attente, ce que la ligne de commande
rend au script d'hôte, et que l'état retient ce qui a été poussé.

Fichier séparé de `test_traiter_nouveaux_episodes.py`, qui dépasse déjà largement
les 500 lignes du projet.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import publication as pub
import traiter_nouveaux_episodes as tne

SOURCE = "demo-source"


@pytest.fixture
def content(tmp_path, monkeypatch):
    import common

    for name, sub in (("SOURCES_DIR", "sources"), ("EPISODES_DIR", "episodes"),
                      ("OUTPUT_DIR", "output")):
        monkeypatch.setattr(common, name, tmp_path / sub)
    (tmp_path / "sources").mkdir()
    (tmp_path / "episodes" / SOURCE).mkdir(parents=True)
    return tmp_path


def _episode(root: Path, guid: str) -> Path:
    import common

    chemin = root / "episodes" / SOURCE / f"{common.slugify(guid)}.json"
    chemin.write_text(json.dumps({"sourceId": SOURCE, "guid": guid,
                                  "title": f"Titre {guid}", "transcriptStatus": "auto"}),
                      encoding="utf-8")
    return chemin


def _etat(finalized=(), published=()) -> dict:
    return {"extracted": [], "finalized": list(finalized), "published": list(published),
            "lastErrors": {}}


def test_only_finalised_and_unpublished_episodes_are_pending(content):
    _episode(content, "yt-relu")
    _episode(content, "yt-en-cours")
    _episode(content, "yt-deja")

    pending = tne.a_publier(SOURCE, _etat(finalized=["yt-relu", "yt-deja"],
                                          published=["yt-deja"]))

    assert [e["guid"] for _c, e in pending] == ["yt-relu"]


def test_an_old_state_without_the_published_key_does_not_crash(content):
    """Les états écrits avant cette étape n'ont pas la clé : la chaîne doit tenir."""
    _episode(content, "yt-relu")

    pending = tne.a_publier(SOURCE, {"finalized": ["yt-relu"]})

    assert [e["guid"] for _c, e in pending] == ["yt-relu"]


def test_load_state_creates_the_published_list(content):
    assert tne.load_state(SOURCE)["published"] == []


def test_the_cli_says_whether_there_is_something_to_publish(content, monkeypatch):
    assert tne.main(["a-publier", "--source", SOURCE]) == 1

    _episode(content, "yt-relu")
    tne.save_state(SOURCE, _etat(finalized=["yt-relu"]))

    assert tne.main(["a-publier", "--source", SOURCE]) == 0


def test_the_cli_publishes_and_remembers_it(content, monkeypatch):
    _episode(content, "yt-relu")
    tne.save_state(SOURCE, _etat(finalized=["yt-relu"]))
    envoyes = []
    monkeypatch.setattr(tne, "build_notify", lambda _c: envoyes.append)
    monkeypatch.setattr(pub, "publier_episode",
                        lambda *_a, **_k: pub.Publication("yt-relu", fichiers=3,
                                                          lien="https://exemple.test/pr/1",
                                                          pr_ouverte=True))

    assert tne.main(["publier", "--source", SOURCE, "--notify", "none"]) == 0

    saved = json.loads(tne.state_path(SOURCE).read_text(encoding="utf-8"))
    assert saved["published"] == ["yt-relu"]
    assert envoyes and "https://exemple.test/pr/1" in envoyes[0]


def test_a_publication_failure_is_reported_once(content, monkeypatch):
    """Le rapporteur de la chaîne est bien branché : une panne qui dure ne spamme pas."""
    _episode(content, "yt-relu")
    envoyes = []
    monkeypatch.setattr(pub, "publier_episode",
                        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("cle refusee")))
    state = _etat(finalized=["yt-relu"])

    tne.publier(SOURCE, envoyes.append, state)
    tne.publier(SOURCE, envoyes.append, state)

    assert len(envoyes) == 1 and "cle refusee" in envoyes[0]
    assert state["published"] == []
