"""Tests de tools/banc_modeles.py — mesurer un modele sur des episodes relus.

Le client est un double : il repond la meme liste de recos a chaque morceau,
et compte les jetons. Rien n'est facture, rien n'est ecrit dans le corpus.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

import banc_modeles as bm

SOURCE = "demo-source"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    import common
    for name, sub in (("SOURCES_DIR", "sources"), ("EPISODES_DIR", "episodes"),
                      ("RECOS_DIR", "recos"), ("OUTPUT_DIR", "output"),
                      ("TRANSCRIPTS_DIR", "output/transcripts")):
        monkeypatch.setattr(common, name, tmp_path / sub)
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources" / f"{SOURCE}.json").write_text(
        json.dumps({"id": SOURCE, "title": "Démo", "hosts": ["A"]}), encoding="utf-8")
    return tmp_path


def _episode(racine, guid, date, recos, transcrit=True):
    import common
    dossier = racine / "episodes" / SOURCE
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{guid}.json").write_text(json.dumps(
        {"sourceId": SOURCE, "guid": guid, "title": f"Titre {guid}", "date": date}),
        encoding="utf-8")
    recos_dir = racine / "recos" / SOURCE
    recos_dir.mkdir(parents=True, exist_ok=True)
    for i, (titre, statut) in enumerate(recos):
        (recos_dir / f"{guid}-{i}.json").write_text(json.dumps(
            {"id": f"{guid}-{i}", "episodeGuid": guid, "title": titre, "status": statut}),
            encoding="utf-8")
    if transcrit:
        t = common.transcript_path_for(SOURCE, guid)
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text("[00:00:01] bonjour\n", encoding="utf-8")


class Client:
    def __init__(self, titres):
        self.titres = titres
        self.modeles = []
        self.messages = SimpleNamespace(create=self._creer)
        self.models = SimpleNamespace()  # pas de capacites : regle du nom

    def _creer(self, **params):
        self.modeles.append(params["model"])
        recos = [{"title": t, "type": "film", "quote": "q", "timestamp": "00:00:01"}
                 for t in self.titres]
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps({"recos": recos}))],
            usage=SimpleNamespace(input_tokens=100_000, output_tokens=10_000))


def test_meme_titre_tolere_accents_casse_et_petites_fautes():
    assert bm.meme_titre("Les Piliers de la Terre", "les piliers de la terre")
    assert bm.meme_titre("Kaamelott", "Kaamelot")
    assert bm.meme_titre("Fleabag", "Fleabag (série)")
    assert not bm.meme_titre("Alien", "Aliens vs Predator : Requiem")
    assert not bm.meme_titre("", "Alien")


def test_seuls_les_episodes_entierement_relus_et_transcrits_comptent(corpus):
    _episode(corpus, "yt-ancien", "2026-01-01", [("A", "validated")])
    _episode(corpus, "yt-recent", "2026-03-01", [("B", "validated"), ("C", "discarded")])
    _episode(corpus, "yt-en-cours", "2026-04-01", [("D", "draft"), ("E", "validated")])
    _episode(corpus, "yt-sans-texte", "2026-05-01", [("F", "validated")], transcrit=False)
    _episode(corpus, "yt-tout-ecarte", "2026-06-01", [("G", "discarded")])

    assert [e["guid"] for e in bm.episodes_relus(SOURCE, 5)] == ["yt-recent", "yt-ancien"]
    assert [e["guid"] for e in bm.episodes_relus(SOURCE, 1)] == ["yt-recent"]


def test_le_banc_compare_a_la_relecture_et_chiffre_le_cout(corpus):
    _episode(corpus, "yt-1", "2026-03-01",
             [("Fleabag", "validated"), ("Kaamelott", "validated"), ("Alien", "discarded")])
    client = Client(["Fleabag", "Alien", "Inconnu au corpus"])
    episodes = bm.episodes_relus(SOURCE, 3)
    ticks = iter([0.0, 12.5])

    (r,) = bm.mesurer(client, SOURCE, ["claude-opus-5"], episodes, horloge=lambda: next(ticks))

    assert client.modeles == ["claude-opus-5"]
    assert (r.candidats, r.retrouvees, r.a_retrouver) == (3, 1, 2)
    assert (r.ecartees_reproposees, r.autres) == (1, 1)
    assert r.manquees == ["Kaamelott"]
    assert r.cout == pytest.approx(0.75)  # 0,1 M x 5 $ + 0,01 M x 25 $
    assert r.secondes == 12.5
    assert "| claude-opus-5 | 0.75 | 3 | 1 / 2 | 1 | 1 |" in bm.tableau([r])


def test_un_modele_sans_tarif_affiche_un_cout_inconnu():
    r = bm.Resultat("modele-inconnu", episodes=1)
    assert "| modele-inconnu | inconnu |" in bm.tableau([r])


def test_le_plan_n_appelle_rien(corpus, monkeypatch):
    _episode(corpus, "yt-1", "2026-03-01", [("Fleabag", "validated")])
    monkeypatch.delenv("RECO_MODELE_EXTRACTION", raising=False)
    monkeypatch.delenv("RECO_MODELE_SECOURS", raising=False)

    assert bm.main(["--source", SOURCE, "--plan"]) == 0


def test_sans_episode_relu_le_banc_refuse(corpus):
    assert bm.main(["--source", SOURCE, "--plan"]) == 1


def test_le_rapport_est_ecrit_hors_du_corpus(corpus, monkeypatch, capsys):
    import common
    _episode(corpus, "yt-1", "2026-03-01", [("Fleabag", "validated")])
    monkeypatch.setattr(common, "make_anthropic_client", lambda: Client(["Fleabag"]))

    assert bm.main(["--source", SOURCE, "--modeles", "claude-sonnet-5-5"]) == 0

    (rapport,) = (corpus / "output" / "banc_modeles").glob("*.json")
    donnees = json.loads(rapport.read_text(encoding="utf-8"))
    assert donnees["episodes"] == ["yt-1"]
    assert donnees["resultats"][0]["retrouvees"] == 1
    assert "claude-sonnet-5-5" in capsys.readouterr().out
