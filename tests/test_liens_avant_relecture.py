"""Liens cherchés AVANT la relecture (`tools/liens_avant_relecture.py`).

Le point délicat est la fusion : la page de relecture reste ouverte pendant
les passes, et ce que l'humain a décidé entre-temps (statut, lien retiré, lien
ajouté) doit toujours gagner. Aucun test ne sort sur le réseau : les passes
sont des doublures qui écrivent dans la copie de travail.
"""
from __future__ import annotations

import json

import pytest

import common
import liens_avant_relecture as lar
import traiter_nouveaux_episodes as tne

SOURCE = "demo"
GUID = "yt-1"


def L(label, url, kind="streaming", ethics="neutral"):
    return {"ethics": ethics, "kind": kind, "label": label, "url": url}


DEEZER = L("Deezer", "https://www.deezer.com/track/1")
APPLE = L("Apple Music", "https://music.apple.com/x")
QOBUZ = L("Qobuz", "https://www.qobuz.com/y")


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    for name, sub in (("SOURCES_DIR", "sources"), ("EPISODES_DIR", "episodes"),
                      ("RECOS_DIR", "recos"), ("OUTPUT_DIR", "output"),
                      ("TRANSCRIPTS_DIR", "output/transcripts")):
        monkeypatch.setattr(common, name, tmp_path / sub)
    (tmp_path / "recos" / SOURCE).mkdir(parents=True)
    (tmp_path / "episodes" / SOURCE).mkdir(parents=True)
    return tmp_path / "recos" / SOURCE


def _reco(dossier, rid, guid=GUID, status="draft", links=(), **champs):
    doc = {"id": rid, "episodeGuid": guid, "sourceId": SOURCE, "title": f"Titre {rid}",
           "creator": "Artiste", "types": ["musique"], "status": status,
           "links": list(links), **champs}
    path = dossier / f"{rid}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def _lire(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _episode(root, guid=GUID):
    (root / "episodes" / SOURCE / f"{common.slugify(guid)}.json").write_text(
        json.dumps({"sourceId": SOURCE, "guid": guid, "title": f"Épisode {guid}"}),
        encoding="utf-8")


def passe_ajoute(*liens):
    """Doublure : ajoute `liens` à chaque reco visée, dans le dossier COURANT."""
    def passe(source_id, ids):
        for path in common.recos_dir_for(source_id).glob("*.json"):
            doc = _lire(path)
            if doc["id"] in ids:
                assert doc["status"] == "validated"  # la copie est « validée »
                doc["links"] = [*doc.get("links", []), *liens]
                path.write_text(json.dumps(doc), encoding="utf-8")
    return passe


# ===== fusion =================================================================
def test_fusion_adds_only_new_links_and_keeps_human_decisions():
    instantane = {"status": "draft", "links": [DEEZER]}
    copie = {"status": "validated", "links": [APPLE, DEEZER, QOBUZ],
             "externalIds": {"tmdb": "1"}, "watchProviders": ["Netflix"],
             "enrichedAt": {"links": "t"}}
    # Pendant les passes : l'humain a validé, retiré Deezer, ajouté un lien.
    perso = L("Site", "https://perso.fr", kind="official")
    reel = {"status": "validated", "recommendedBy": "Carla", "links": [perso],
            "linksRejected": [QOBUZ["url"]]}

    sortie = lar.fusionner(copie, instantane, reel)

    assert sortie["status"] == "validated" and sortie["recommendedBy"] == "Carla"
    assert [link["url"] for link in sortie["links"]] == [APPLE["url"], perso["url"]]
    assert sortie["externalIds"] == {"tmdb": "1"}
    assert sortie["watchProviders"] == ["Netflix"]
    assert sortie["enrichedAt"] == {"links": "t"}
    assert reel["links"] == [perso]  # la reco réelle n'est pas mutée


def test_fusion_returns_none_when_nothing_new():
    reco = {"links": [DEEZER], "externalIds": {"tmdb": "1"}, "watchProviders": []}
    assert lar.fusionner(reco, reco, reco) is None


def test_fusion_keeps_existing_ids_and_providers():
    copie = {"links": [], "externalIds": {"tmdb": "9", "imdb": "tt1"}, "watchProviders": ["X"]}
    reel = {"links": [], "externalIds": {"tmdb": "1"}, "watchProviders": ["Y"]}
    sortie = lar.fusionner(copie, {"links": []}, reel)
    assert sortie["externalIds"] == {"tmdb": "1", "imdb": "tt1"}
    assert sortie["watchProviders"] == ["Y"]


# ===== même œuvre ============================================================
def test_same_work_links_come_from_the_validated_corpus():
    brouillon = {"title": "Fleabag", "types": ["serie"], "creator": "Phoebe Waller-Bridge",
                 "links": [L("IMDb", "https://www.imdb.com/title/tt5687612/", "info")]}
    relue = {"title": "Fleabag", "types": ["serie"], "creator": "Phoebe Waller-Bridge",
             "links": [L("Prime Video", "https://www.primevideo.com/x", ethics="avoid"),
                       L("IMDb", "https://www.imdb.com/title/tt5687612/", "info")]}
    assert [link["label"] for link in lar.liens_meme_oeuvre(brouillon, [relue])] == ["Prime Video"]


def test_same_work_refuses_homonyms_and_short_titles():
    brouillon = {"title": "Happy End", "types": ["album"], "links": []}
    podcast = {"title": "Happy End", "types": ["podcast"], "links": [DEEZER]}
    assert lar.liens_meme_oeuvre(brouillon, [podcast]) == []
    assert lar.liens_meme_oeuvre({"title": "Vu", "types": ["film"]}, [podcast]) == []
    assert lar.liens_meme_oeuvre(brouillon, []) == []


# ===== un épisode de bout en bout ============================================
def test_chercher_episode_writes_found_links_on_the_real_drafts(corpus):
    reel = _reco(corpus, "r-1", links=[DEEZER])
    autre = _reco(corpus, "r-2", guid="yt-2")
    valide = _reco(corpus, "r-3", status="validated")

    ajoutes, sans_lien = lar.chercher_episode(SOURCE, GUID, [("musique", passe_ajoute(APPLE))])

    assert (ajoutes, sans_lien) == (1, 0)
    doc = _lire(reel)
    assert doc["status"] == "draft"  # jamais le statut forcé de la copie
    assert [link["url"] for link in doc["links"]] == [DEEZER["url"], APPLE["url"]]
    assert _lire(autre)["links"] == [] and _lire(valide)["links"] == []
    assert common.RECOS_DIR == corpus.parent  # redirection rendue


def test_a_decision_taken_during_the_passes_is_kept(corpus):
    reel = _reco(corpus, "r-1")

    def humain_pendant_les_passes(source_id, ids):
        doc = _lire(reel)  # la page écrit dans le VRAI fichier
        doc.update(status="validated", recommendedBy="Carla")
        reel.write_text(json.dumps(doc), encoding="utf-8")

    lar.chercher_episode(SOURCE, GUID, [("humain", humain_pendant_les_passes),
                                        ("musique", passe_ajoute(APPLE))])

    doc = _lire(reel)
    assert doc["status"] == "validated" and doc["recommendedBy"] == "Carla"
    assert [link["url"] for link in doc["links"]] == [APPLE["url"]]


def test_a_failing_pass_does_not_stop_the_others(corpus):
    reel = _reco(corpus, "r-1")

    def en_panne(*_a):
        raise RuntimeError("TMDB_API_KEY absent")

    assert lar.chercher_episode(SOURCE, GUID, [("TMDB", en_panne),
                                               ("musique", passe_ajoute(APPLE))]) == (1, 0)
    assert _lire(reel)["links"] == [APPLE]


def test_rejected_and_vanished_recos_are_respected(corpus):
    rejete = _reco(corpus, "r-1", linksRejected=[APPLE["url"]])
    disparue = _reco(corpus, "r-2")

    def supprime(*_a):
        disparue.unlink()

    assert lar.chercher_episode(SOURCE, GUID, [("musique", passe_ajoute(APPLE)),
                                               ("suppression", supprime)]) == (0, 1)
    assert _lire(rejete)["links"] == []


def test_same_work_is_applied_before_the_passes(corpus):
    _reco(corpus, "r-0", guid="yt-0", status="validated", title="Fleabag",
          types=["serie"], links=[QOBUZ])
    reel = _reco(corpus, "r-1", title="Fleabag", types=["serie"])
    vus = []

    def regarde(source_id, ids):
        doc = _lire(common.recos_dir_for(source_id) / "r-1.json")
        vus.append([link["url"] for link in doc["links"]])

    lar.chercher_episode(SOURCE, GUID, [("regarde", regarde)])

    assert vus == [[QOBUZ["url"]]]  # la passe voit déjà le lien du corpus
    assert _lire(reel)["links"] == [QOBUZ]


def test_no_draft_means_nothing_to_do(corpus):
    _reco(corpus, "r-1", status="validated")
    assert lar.chercher_episode(SOURCE, GUID, []) == (0, 0)


# ===== étape de la chaîne =====================================================
def test_a_chercher_and_chercher(corpus, tmp_path):
    _episode(tmp_path, GUID)
    _episode(tmp_path, "yt-2")
    _episode(tmp_path, "yt-3")
    _reco(corpus, "r-1")
    _reco(corpus, "r-2", guid="yt-2")
    _reco(corpus, "r-3", guid="yt-3", status="validated")  # plus rien à relire
    state = {"extracted": [GUID, "yt-2", "yt-3"], "finalized": ["yt-2"]}

    assert [ep["guid"] for _p, ep in lar.a_chercher(SOURCE, state)] == [GUID]

    inbox: list[str] = []
    lar.chercher(SOURCE, inbox.append, state, passes=[("musique", passe_ajoute(APPLE))])

    assert state[lar.ETAT] == [GUID]
    assert inbox == ["🔗 « Épisode yt-1 » : 1 lien(s) trouvé(s) avant la relecture."]
    assert lar.a_chercher(SOURCE, state) == []  # une seule fois par épisode


def test_chercher_reports_recos_left_without_links_and_survives_errors(corpus, tmp_path,
                                                                        monkeypatch):
    _episode(tmp_path, GUID)
    _episode(tmp_path, "yt-2")
    _reco(corpus, "r-1")
    _reco(corpus, "r-2", guid="yt-2")
    state = {"extracted": [GUID, "yt-2"]}
    vraie = lar.chercher_episode

    def parfois(source_id, guid, passes):
        if guid == "yt-2":
            raise OSError("disque plein")
        return vraie(source_id, guid, passes)

    monkeypatch.setattr(lar, "chercher_episode", parfois)
    inbox: list[str] = []
    lar.chercher(SOURCE, inbox.append, state, passes=[])

    assert state[lar.ETAT] == [GUID]  # yt-2 sera retenté au prochain passage
    assert inbox == [("🔗 « Épisode yt-1 » : 0 lien(s) trouvé(s) avant la relecture ; "
                      "1 reco(s) encore sans lien, à compléter pendant la relecture.")]


def test_default_passes_follow_the_finalisation_order():
    noms = [nom for nom, _p in lar._passes_par_defaut()]
    assert noms == ["musique", "TMDB", "fiches", "Wikidata", "boutique", "plateformes",
                    "jeux", "YouTube Music"]


def test_pipeline_cli_knows_the_new_steps(corpus, monkeypatch):
    assert "chercher-liens" in tne.STEPS and "a-chercher-liens" in tne.SONDES
    appels = []
    monkeypatch.setattr(lar, "chercher", lambda *a, **_k: appels.append(a[0]) or 0)
    assert tne.main(["chercher-liens", "--source", SOURCE, "--notify", "none"]) == 0
    assert tne.main(["a-chercher-liens", "--source", SOURCE, "--notify", "none"]) == 1
    assert appels == [SOURCE]


# ===== purge des rejetés ======================================================
def test_purger_rejetes_removes_links_a_pass_put_back(corpus):
    reco = _reco(corpus, "r-1", status="validated", links=[DEEZER, APPLE],
                 linksRejected=[APPLE["url"]])
    sans = _reco(corpus, "r-2", status="validated", links=[APPLE])
    hors = _reco(corpus, "r-3", status="validated", links=[APPLE],
                 linksRejected=[APPLE["url"]])

    assert lar.purger_rejetes(SOURCE, {"r-1", "r-2"}) == 1
    assert _lire(reco)["links"] == [DEEZER]
    assert _lire(sans)["links"] == [APPLE] and _lire(hors)["links"] == [APPLE]
    assert lar.purger_rejetes(SOURCE, {"r-1"}) == 0  # idempotent


def test_an_unreadable_corpus_file_is_skipped(corpus):
    (corpus / "casse.json").write_text("{pas du json", encoding="utf-8")
    _reco(corpus, "r-0", guid="yt-0", status="validated")
    assert [d["id"] for d in lar._corpus_valide(SOURCE)] == ["r-0"]
