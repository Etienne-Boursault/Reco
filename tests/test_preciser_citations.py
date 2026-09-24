"""Tests de `tools/preciser_citations.py` — réécoute ciblée des citations.

Le transcripteur est un double : aucun modèle ne tourne. Le contrat tient en une
phrase — ne remplacer une citation que si la réécoute parle du même passage ET
rétablit un nom que l'ancienne n'avait pas.
"""
from __future__ import annotations

import json
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

import preciser_citations as pc

SOURCE = "demo-source"
GUID = "yt-abc"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    import common

    content = tmp_path / "content"
    monkeypatch.setattr(common, "CONTENT_DIR", content)
    monkeypatch.setattr(common, "RECOS_DIR", content / "recos")
    monkeypatch.setattr(common, "SOURCES_DIR", content / "sources")
    (content / "recos" / SOURCE).mkdir(parents=True)
    (content / "sources").mkdir(parents=True)
    (content / "sources" / f"{SOURCE}.json").write_text(
        json.dumps({"id": SOURCE, "title": "Démo", "hosts": ["Kyan Khojandi", "Navo"]}),
        encoding="utf-8")
    return content


def _reco(content: Path, reco_id: str, **champs) -> Path:
    reco = {"id": reco_id, "episodeGuid": GUID, "sourceId": SOURCE, "status": "draft",
            "title": "Stromae", "types": ["artiste"], "timestamp": "00:58:59",
            "quote": "Que Straumai lui à mon avis c'est un geek", **champs}
    chemin = content / "recos" / SOURCE / f"{reco_id}.json"
    chemin.write_text(json.dumps(reco, ensure_ascii=False), encoding="utf-8")
    return chemin


@contextmanager
def _rien():
    yield


def _lire(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


def _transcripteur(segments, journal=None):
    def transcrire(audio, debut, fin, indices):
        if journal is not None:
            journal.append((debut, fin, indices))
        return list(segments)
    return transcrire


# ===== remplacement ==========================================================
def test_a_repaired_name_replaces_the_quote(corpus):
    chemin = _reco(corpus, "ubm-1")
    journal = []
    segments = ["Ouais.", "Que Stromae lui à mon avis c'est un geek.", "De la prod."]

    bilan = pc.preciser_episode(SOURCE, GUID, apply=True,
                                transcripteur=_transcripteur(segments, journal), audio=Path("a.mp3"))

    assert [p.reco_id for p in bilan.precisees] == ["ubm-1"]
    assert bilan.precisees[0].noms_repares == ["Stromae"]
    assert _lire(chemin)["quote"] == "Que Stromae lui à mon avis c'est un geek."
    # Fenêtre demandée : 15 s avant l'horodatage, 25 s après.
    debut, fin, indices = journal[0]
    assert (debut, fin) == (58 * 60 + 59 - 15, 58 * 60 + 59 + 25)
    assert indices.startswith("Stromae, ") and "Kyan Khojandi" in indices


def test_the_quote_may_span_several_segments(corpus):
    chemin = _reco(corpus, "ubm-1", quote="Que Straumai lui à mon avis c'est un geek de la prod")
    segments = ["Bref.", "Que Stromae lui à mon avis", "c'est un geek de la prod.", "Ouais."]

    pc.preciser_episode(SOURCE, GUID, apply=True,
                        transcripteur=_transcripteur(segments), audio=Path("a.mp3"))

    assert _lire(chemin)["quote"] == "Que Stromae lui à mon avis c'est un geek de la prod."


def test_creator_and_recommender_are_also_given_as_hints(corpus):
    _reco(corpus, "ubm-1", title="Comment c'est loin", creator="Orelsan",
          recommendedBy="Kyan Khojandi")
    journal = []

    pc.preciser_episode(SOURCE, GUID, transcripteur=_transcripteur(["x"], journal),
                        audio=Path("a.mp3"))

    assert journal[0][2] == "Comment c'est loin, Orelsan, Kyan Khojandi, Navo."


# ===== garde-fous ============================================================
def test_nothing_changes_when_no_name_is_repaired(corpus):
    chemin = _reco(corpus, "ubm-1")
    avant = chemin.read_text(encoding="utf-8")
    segments = ["Que Straumai lui à mon avis c'est un geek, quand même."]

    bilan = pc.preciser_episode(SOURCE, GUID, apply=True,
                                transcripteur=_transcripteur(segments), audio=Path("a.mp3"))

    assert bilan.precisees == [] and bilan.inchangees == 1
    assert chemin.read_text(encoding="utf-8") == avant


def test_a_different_passage_is_refused_even_with_the_name(corpus):
    """Sécurité : un texte qui ne ressemble pas à la citation ne la remplace pas."""
    chemin = _reco(corpus, "ubm-1")
    avant = chemin.read_text(encoding="utf-8")
    segments = ["Stromae a fait un concert au Stade de France l'an dernier."]

    bilan = pc.preciser_episode(SOURCE, GUID, apply=True,
                                transcripteur=_transcripteur(segments), audio=Path("a.mp3"))

    assert bilan.precisees == [] and bilan.inchangees == 1
    assert chemin.read_text(encoding="utf-8") == avant


def test_without_apply_nothing_is_written(corpus):
    chemin = _reco(corpus, "ubm-1")
    avant = chemin.read_text(encoding="utf-8")
    segments = ["Que Stromae lui à mon avis c'est un geek."]

    bilan = pc.preciser_episode(SOURCE, GUID, transcripteur=_transcripteur(segments),
                                audio=Path("a.mp3"))

    assert len(bilan.precisees) == 1
    assert chemin.read_text(encoding="utf-8") == avant


def test_discarded_recos_are_ignored(corpus):
    _reco(corpus, "ubm-1", status="discarded")
    bilan = pc.preciser_episode(SOURCE, GUID, transcripteur=_transcripteur(["x"]),
                                audio=Path("a.mp3"))
    assert bilan.examinees == 0 and bilan.erreurs


@pytest.mark.parametrize("champs", [
    {"timestamp": None},
    {"timestamp": "pas une heure"},
    {"quote": ""},
])
def test_a_reco_without_timestamp_or_quote_is_listed_not_touched(corpus, champs):
    _reco(corpus, "ubm-1", **champs)
    bilan = pc.preciser_episode(SOURCE, GUID, transcripteur=_transcripteur(["x"]),
                                audio=Path("a.mp3"))
    assert bilan.sans_horodatage == ["ubm-1"] and bilan.examinees == 0


def test_a_failing_window_does_not_stop_the_others(corpus):
    _reco(corpus, "ubm-1")
    chemin2 = _reco(corpus, "ubm-2", timestamp="01:00:00")

    def transcrire(audio, debut, fin, indices):
        if debut < 3540:
            raise RuntimeError("audio illisible")
        return ["Que Stromae lui à mon avis c'est un geek."]

    bilan = pc.preciser_episode(SOURCE, GUID, apply=True, transcripteur=transcrire,
                                audio=Path("a.mp3"))

    assert len(bilan.erreurs) == 1 and "ubm-1" in bilan.erreurs[0]
    assert [p.reco_id for p in bilan.precisees] == ["ubm-2"]
    assert "Stromae" in _lire(chemin2)["quote"]


def test_timestamps_in_minutes_and_seconds_are_accepted():
    assert pc._secondes("58:59") == 58 * 60 + 59
    assert pc._secondes("01:02:03") == 3723
    assert pc._secondes("hier") is None
    assert pc._secondes(None) is None


def test_an_empty_window_leaves_the_quote_alone(corpus):
    """Whisper peut ne rien rendre (silence, filtre VAD) : on ne touche à rien."""
    chemin = _reco(corpus, "ubm-1")
    avant = _lire(chemin)["quote"]

    bilan = pc.preciser_episode(SOURCE, GUID, apply=True, transcripteur=_transcripteur([]),
                                audio=Path("a.mp3"))

    assert bilan.examinees == 1 and bilan.inchangees == 1 and not bilan.precisees
    assert _lire(chemin)["quote"] == avant


# ===== adaptateur Whisper ====================================================
def test_the_whisper_adapter_hints_the_names_and_clips_the_window(monkeypatch):
    """Le seul intérêt de l'adaptateur : les indices et la fenêtre découpée."""
    appels = []

    class FauxSegment:
        def __init__(self, text):
            self.text = text

    class FauxModele:
        def __init__(self, nom, device, compute_type):
            appels.append({"charge": (nom, device, compute_type)})

        def transcribe(self, audio, **options):
            appels.append({"transcrit": audio, **options})
            return iter([FauxSegment("  Stromae, oui.  ")]), None

    monkeypatch.setitem(sys.modules, "faster_whisper",
                        types.SimpleNamespace(WhisperModel=FauxModele))

    transcrire = pc._transcripteur_whisper()
    assert transcrire(Path("a.mp3"), 10.0, 50.0, "Stromae.") == ["Stromae, oui."]
    transcrire(Path("a.mp3"), 60.0, 100.0, "Stromae.")

    assert appels[0]["charge"] == (pc.MODELE, "cpu", "int8")
    assert appels[1]["hotwords"] == "Stromae." and appels[1]["clip_timestamps"] == [10.0, 50.0]
    assert appels[1]["language"] == "fr" and appels[1]["vad_filter"] is True
    # Le modèle coûte cher à charger : une seule fois pour tout l'épisode.
    assert [a for a in appels if "charge" in a] == appels[:1]


def test_the_audio_and_the_transcriber_are_found_alone_when_not_given(corpus, monkeypatch):
    import common
    import transcribe

    episodes = corpus / "episodes" / SOURCE
    episodes.mkdir(parents=True)
    monkeypatch.setattr(common, "EPISODES_DIR", corpus / "episodes")
    (episodes / "ep.json").write_text(json.dumps({"guid": GUID, "title": "Épisode"}),
                                      encoding="utf-8")
    _reco(corpus, "ubm-1")
    monkeypatch.setattr(transcribe, "_resolve_audio",
                        lambda source_id, episode: (Path("trouve.mp3"), "youtube"))
    monkeypatch.setattr(pc, "_transcripteur_whisper",
                        lambda: _transcripteur(["Que Stromae lui à mon avis c'est un geek."]))

    bilan = pc.preciser_episode(SOURCE, GUID)

    assert [p.noms_repares for p in bilan.precisees] == [["Stromae"]]


# ===== ligne de commande =====================================================
def test_the_cli_simulates_by_default(corpus, monkeypatch, capsys):
    """Sans --apply : pas de verrou, pas d'écriture, et le bilan sur stdout."""
    chemin = _reco(corpus, "ubm-1")
    avant = chemin.read_text(encoding="utf-8")
    monkeypatch.setattr(pc, "preciser_episode",
                        lambda source, guid, **kw: pc.Bilan(
                            guid, examinees=1,
                            precisees=[pc.Precision("ubm-1", "Straumai", "Stromae", ["Stromae"])],
                            sans_horodatage=["ubm-2"]))

    assert pc.main(["--source", SOURCE, "--guid", GUID, "--json"]) == 0

    sortie = json.loads(capsys.readouterr().out)
    assert sortie["precisees"][0]["noms_repares"] == ["Stromae"]
    assert sortie["sans_horodatage"] == ["ubm-2"]
    assert chemin.read_text(encoding="utf-8") == avant


def test_the_cli_takes_the_pipeline_lock_before_writing(corpus, monkeypatch):
    import review_lock

    pris = []
    monkeypatch.setattr(review_lock, "acquire_pipeline_lock",
                        lambda force=False: pris.append(force) or _rien())
    monkeypatch.setattr(pc, "preciser_episode",
                        lambda source, guid, **kw: pris.append(kw) or pc.Bilan(guid))

    assert pc.main(["--source", SOURCE, "--guid", GUID, "--apply", "--force"]) == 0
    assert pris[0] is True and pris[1] == {"apply": True}


def test_the_cli_gives_up_when_the_review_server_holds_the_lock(corpus, monkeypatch):
    import review_lock

    def occupe(force=False):
        raise review_lock.LockBusy("le serveur de relecture tourne")

    monkeypatch.setattr(review_lock, "acquire_pipeline_lock", occupe)
    monkeypatch.setattr(pc, "preciser_episode", lambda *a, **k: pytest.fail("ne doit pas écrire"))

    assert pc.main(["--source", SOURCE, "--guid", GUID, "--apply"]) == 2


def test_the_cli_reports_an_episode_it_could_not_touch(corpus, monkeypatch):
    monkeypatch.setattr(pc, "preciser_episode",
                        lambda source, guid, **kw: pc.Bilan(guid, erreurs=["aucune reco"]))
    assert pc.main(["--source", SOURCE, "--guid", GUID]) == 2
