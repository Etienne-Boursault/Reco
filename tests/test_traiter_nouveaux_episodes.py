"""Tests de `tools/traiter_nouveaux_episodes.py` — la chaîne automatique sur venus.

Transcription, extraction, client d'API et verrou sont des doubles : aucun
modèle ne tourne, aucun appel n'est facturé.
"""
from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import traiter_nouveaux_episodes as tne

# Capturée AVANT que la fixture `tmdb_hors_ligne` ne remplace l'attribut du
# module : c'est la vraie passe, celle qui sert de défaut à `finaliser`.
from traiter_nouveaux_episodes import _fiches_tmdb as _vraie_passe_tmdb
from traiter_nouveaux_episodes import _fiches_video as _vraie_passe_video

SOURCE = "demo-source"


@pytest.fixture
def content(tmp_path, monkeypatch):
    import common

    for name, sub in (("SOURCES_DIR", "sources"), ("EPISODES_DIR", "episodes"),
                      ("OUTPUT_DIR", "output"), ("TRANSCRIPTS_DIR", "output/transcripts"),
                      ("AUDIO_DIR", "output/audio")):
        monkeypatch.setattr(common, name, tmp_path / sub)
    (tmp_path / "sources").mkdir()
    (tmp_path / "episodes" / SOURCE).mkdir(parents=True)
    (tmp_path / "sources" / f"{SOURCE}.json").write_text(
        json.dumps({"id": SOURCE, "title": "Démo", "hosts": ["A"]}), encoding="utf-8")
    return tmp_path


def _episode(root: Path, guid: str, status: str = "none", transcript: bool = False,
             **champs) -> Path:
    import common

    path = root / "episodes" / SOURCE / f"{common.slugify(guid)}.json"
    path.write_text(json.dumps({"sourceId": SOURCE, "guid": guid, "title": f"Titre {guid}",
                                "transcriptStatus": status, **champs}), encoding="utf-8")
    if transcript:
        t = common.transcript_path_for(SOURCE, guid)
        t.parent.mkdir(parents=True, exist_ok=True)
        t.write_text("[00:00:01] bonjour\n", encoding="utf-8")
    return path


class Inbox(list):
    def __call__(self, text: str) -> None:
        self.append(text)


@pytest.fixture
def inbox():
    return Inbox()


def _no_lock():
    return contextlib.nullcontext()


def _sans_precision(*_a, **_k):
    """La réécoute des citations ne trouve rien à corriger."""
    return SimpleNamespace(precisees=[])


# ===== detecter ==============================================================
def test_detecter_announces_new_episodes_and_unrecognized_videos(content, inbox):
    _episode(content, "yt-new")
    result = SimpleNamespace(created=["yt-new"],
                             unrecognized=[{"id": "clip", "title": "Un extrait"}])

    assert tne.detecter(SOURCE, inbox, fetch=lambda _s: result) == 0

    assert "Nouvel épisode détecté : Titre yt-new" in inbox[0]
    assert "« Un extrait »" in inbox[1] and "watch?v=clip" in inbox[1]


# ===== transcrire ============================================================
def test_transcrire_only_touches_youtube_episodes_not_yet_transcribed(content, inbox):
    _episode(content, "yt-todo")
    _episode(content, "yt-done", status="auto")
    _episode(content, "6a47e41c08da", status="none")  # épisode Acast : jamais
    calls = []

    tne.transcrire(SOURCE, inbox, tne.load_state(SOURCE),
                   transcriber=lambda s, p, m, lang, force, amorce:
                   calls.append((p.name, m, lang, amorce)))

    assert calls == [("yt-todo.json", "large-v3-turbo", "fr",
                      "Bonjour et bienvenue dans Démo, avec A. Aujourd'hui : Titre yt-todo.")]


def test_audio_is_kept_after_transcription_for_the_quote_pass(content, inbox):
    """La réécoute des citations en a besoin juste après : c'est `extraire` qui le retire."""
    import common

    _episode(content, "yt-todo")
    audio = common.AUDIO_DIR / SOURCE / "yt-todo-yt.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"x")

    tne.transcrire(SOURCE, inbox, tne.load_state(SOURCE), transcriber=lambda *a, **k: None)

    assert audio.exists()


def test_the_audio_is_downloaded_once_per_episode(content, inbox, monkeypatch):
    """Vu sur venus le 2026-09-18 : 62 Mo retéléchargés pour la réécoute des citations.

    Transcription et réécoute passent toutes deux par `transcribe._resolve_audio`,
    comme les vraies ; seul yt-dlp est simulé.
    """
    import common
    import transcribe

    # `transcribe` a importé AUDIO_DIR par son nom : sans ceci, le test écrirait
    # dans le vrai dossier audio.
    monkeypatch.setattr(transcribe, "AUDIO_DIR", common.AUDIO_DIR)
    telechargements = []

    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def download(self, urls):
            telechargements.extend(urls)
            Path(self.opts["outtmpl"].replace(".%(ext)s", ".mp3")).write_bytes(b"audio")

    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=FakeYDL))
    chemin = _episode(content, "yt-todo", youtubeUrl="https://www.youtube.com/watch?v=todo")

    def transcriber(source_id, path, model, lang, force, amorce):
        transcribe._resolve_audio(source_id, json.loads(path.read_text(encoding="utf-8")))
        _episode(content, "yt-todo", status="auto", transcript=True,
                 youtubeUrl="https://www.youtube.com/watch?v=todo")

    def preciseur(source_id, guid, *, apply):
        transcribe._resolve_audio(source_id, json.loads(chemin.read_text(encoding="utf-8")))
        return SimpleNamespace(precisees=[])

    state = tne.load_state(SOURCE)
    tne.transcrire(SOURCE, inbox, state, transcriber=transcriber)
    tne.extraire(SOURCE, inbox, state, review_url="u", client_factory=lambda: "c",
                 extractor=lambda *a, **k: 1, lock=_no_lock, model="m", preciseur=preciseur)

    assert telechargements == ["https://www.youtube.com/watch?v=todo"]
    assert state["extracted"] == ["yt-todo"]
    assert list((common.AUDIO_DIR / SOURCE).iterdir()) == []


def test_a_lasting_transcription_failure_is_reported_once(content, inbox):
    _episode(content, "yt-todo")
    state = tne.load_state(SOURCE)

    def broken(*_args, **_kwargs):
        raise RuntimeError("yt-dlp : Sign in to confirm")

    tne.transcrire(SOURCE, inbox, state, transcriber=broken)
    tne.transcrire(SOURCE, inbox, state, transcriber=broken)
    assert len(inbox) == 1 and "Sign in to confirm" in inbox[0]

    tne.transcrire(SOURCE, inbox, state, transcriber=lambda *a, **k: None)
    assert state["lastErrors"] == {}


def test_the_amorce_uses_the_hosts_and_the_episode_title_without_its_suffix():
    source = {"title": "Un Bon Moment", "hosts": ["Kyan Khojandi", "Navo"],
              "youtubeTitleSuffixPatterns": ["un bon moment"]}
    episode = {"guid": "yt-1", "title": "Orelsan, le boss final (Un Bon Moment, S6-E1)"}

    assert tne.amorce_pour(source, episode) == (
        "Bonjour et bienvenue dans Un Bon Moment, avec Kyan Khojandi, Navo. "
        "Aujourd'hui : Orelsan, le boss final.")


# ===== a-extraire / extraire =================================================
def test_only_transcribed_youtube_episodes_not_yet_extracted_are_pending(content):
    _episode(content, "yt-ready", status="auto", transcript=True)
    _episode(content, "yt-no-file", status="auto")
    _episode(content, "yt-waiting")
    _episode(content, "yt-already", status="auto", transcript=True)
    _episode(content, "acast-old", status="auto", transcript=True)
    state = {"extracted": ["yt-already"], "lastErrors": {}}

    pending = tne.a_extraire(SOURCE, state)

    assert [ep["guid"] for _, ep in pending] == ["yt-ready"]


def test_extraire_marks_the_episode_and_sends_the_validation_link(content, inbox):
    _episode(content, "yt--abc", status="auto", transcript=True)
    state = tne.load_state(SOURCE)
    seen = []

    def extractor(source_id, path, client, dry_run, *, model, source):
        seen.append((path.name, client, dry_run, model, source["title"]))
        return 7

    rc = tne.extraire(SOURCE, inbox, state, review_url="http://10.8.0.1:8000/",
                      client_factory=lambda: "client", extractor=extractor,
                      lock=_no_lock, model="claude-test", preciseur=_sans_precision)

    assert rc == 0
    assert seen == [("yt-abc.json", "client", False, "claude-test", "Démo")]
    assert state["extracted"] == ["yt--abc"]
    assert inbox == [("✅ Titre yt--abc : 7 reco(s) à valider.\n"
                      "http://10.8.0.1:8000/ep?guid=yt--abc")]

    tne.extraire(SOURCE, inbox, state, review_url="u", client_factory=lambda: "client",
                 extractor=extractor, lock=_no_lock, model="m", preciseur=_sans_precision)
    assert len(seen) == 1  # jamais ré-extrait, donc jamais refacturé


def test_precised_quotes_are_announced_and_the_audio_is_dropped(content, inbox):
    import common

    _episode(content, "yt-ready", status="auto", transcript=True)
    audio = common.AUDIO_DIR / SOURCE / "yt-ready-yt.m4a"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"x")
    vues = []

    def preciseur(source_id, guid, *, apply):
        vues.append((guid, apply))
        return SimpleNamespace(precisees=[object(), object()])

    tne.extraire(SOURCE, inbox, tne.load_state(SOURCE), review_url="u",
                 client_factory=lambda: "c", extractor=lambda *a, **k: 4,
                 lock=_no_lock, model="m", preciseur=preciseur)

    assert vues == [("yt-ready", True)]
    assert "2 citation(s) précisée(s)" in inbox[0]
    assert not audio.exists()


def test_a_failing_quote_pass_does_not_lose_the_episode(content, inbox):
    _episode(content, "yt-ready", status="auto", transcript=True)

    def preciseur(*_a, **_k):
        raise RuntimeError("audio introuvable")

    state = tne.load_state(SOURCE)
    tne.extraire(SOURCE, inbox, state, review_url="u", client_factory=lambda: "c",
                 extractor=lambda *a, **k: 4, lock=_no_lock, model="m", preciseur=preciseur)

    assert state["extracted"] == ["yt-ready"]
    assert "4 reco(s) à valider" in inbox[0] and "citation" not in inbox[0]


def test_an_invalid_api_key_is_reported_once_and_nothing_is_marked(content, inbox):
    _episode(content, "yt-ready", status="auto", transcript=True)
    state = tne.load_state(SOURCE)

    def refused():
        raise RuntimeError("401 invalid x-api-key")

    for _ in range(2):
        assert tne.extraire(SOURCE, inbox, state, review_url="u", client_factory=refused,
                            extractor=lambda *a, **k: 0, lock=_no_lock, model="m") == 1

    assert len(inbox) == 1 and "401" in inbox[0]
    assert state["extracted"] == []


def test_a_failing_episode_does_not_block_the_next_one(content, inbox):
    _episode(content, "yt-a", status="auto", transcript=True)
    _episode(content, "yt-b", status="auto", transcript=True)
    state = tne.load_state(SOURCE)

    def extractor(source_id, path, *_a, **_k):
        if path.name == "yt-a.json":
            raise RuntimeError("500 overloaded")
        return 3

    tne.extraire(SOURCE, inbox, state, review_url="u", client_factory=lambda: "c",
                 extractor=extractor, lock=_no_lock, model="m", preciseur=_sans_precision)

    assert state["extracted"] == ["yt-b"]
    assert "overloaded" in inbox[0] and "3 reco(s)" in inbox[1]


def test_extraction_waits_when_the_review_server_holds_the_lock(content, inbox):
    from review_lock import ServerLockBusy

    _episode(content, "yt-ready", status="auto", transcript=True)
    state = tne.load_state(SOURCE)

    @contextlib.contextmanager
    def busy():
        raise ServerLockBusy("review_server actif")
        yield  # pragma: no cover

    rc = tne.extraire(SOURCE, inbox, state, review_url="u", client_factory=lambda: "c",
                      extractor=lambda *a, **k: 1, lock=busy, model="m")

    assert rc == 1 and state["extracted"] == []
    assert "verrou" in inbox[0]


# ===== CLI ===================================================================
def test_a_extraire_exit_code_drives_the_host_script(content):
    assert tne.main(["a-extraire", "--source", SOURCE]) == 1
    _episode(content, "yt-ready", status="auto", transcript=True)
    assert tne.main(["a-extraire", "--source", SOURCE]) == 0


def test_state_survives_between_steps(content, monkeypatch):
    _episode(content, "yt-todo")

    def broken(*_a, **_k):
        raise RuntimeError("panne")

    monkeypatch.setattr(tne, "build_notify", lambda _c: lambda _t: None)
    monkeypatch.setattr("transcribe.transcribe_episode", broken)

    tne.main(["transcrire", "--source", SOURCE, "--notify", "none"])

    saved = json.loads(tne.state_path(SOURCE).read_text(encoding="utf-8"))
    assert "transcription:yt-todo" in saved["lastErrors"]


def test_the_cli_detects_through_the_real_step(content, monkeypatch, caplog):
    _episode(content, "yt-neuf")
    monkeypatch.setattr(tne, "fetch_youtube_episodes", lambda source_id: SimpleNamespace(
        created=["yt-neuf"],
        unrecognized=[{"id": "abc", "title": "Bande-annonce"}]))

    with caplog.at_level("INFO"):
        assert tne.main(["detecter", "--source", SOURCE, "--notify", "none"]) == 0

    messages = [r.getMessage() for r in caplog.records if "Notification" in r.getMessage()]
    assert any("Titre yt-neuf" in m for m in messages)
    assert any("Bande-annonce" in m and "youtube.com/watch?v=abc" in m for m in messages)


def test_the_cli_passes_the_review_url_to_the_extraction(content, monkeypatch):
    recu = {}
    monkeypatch.setattr(tne, "build_notify", lambda canal: recu.setdefault("canal", canal))
    monkeypatch.setattr(tne, "extraire",
                        lambda source, notify, state, **kw: recu.update(kw) or 0)

    assert tne.main(["extraire", "--source", SOURCE, "--notify", "none",
                     "--review-url", "http://10.8.0.1:8000/"]) == 0
    assert recu == {"canal": "none", "review_url": "http://10.8.0.1:8000/"}


# ===== notifications =========================================================
def test_without_a_channel_the_notification_is_only_logged(caplog):
    notify = tne.build_notify("none")
    with caplog.at_level("INFO"):
        notify("coucou")
    assert any("coucou" in r.getMessage() for r in caplog.records)


def test_with_a_channel_the_notification_is_sent_as_text(monkeypatch):
    import poll_rss

    envoyes = []
    monkeypatch.setattr(poll_rss, "_build_sender",
                        lambda canal: SimpleNamespace(send=envoyes.append) if canal == "matrix"
                        else pytest.fail(f"canal inattendu : {canal}"))

    tne.build_notify("matrix")("coucou")

    assert envoyes == [{"msgtype": "m.text", "body": "coucou"}]


def test_the_extraction_asks_the_review_server_for_the_pipeline_lock(monkeypatch):
    """Le verrou réel vient de review_lock, sans forcer : le serveur a priorité."""
    import review_lock

    demandes = []
    monkeypatch.setattr(review_lock, "acquire_pipeline_lock",
                        lambda force: demandes.append(force) or contextlib.nullcontext())

    with tne._pipeline_lock():
        pass

    assert demandes == [False]

# ===== finaliser =============================================================
@pytest.fixture(autouse=True)
def tmdb_hors_ligne(monkeypatch):
    """Aucun test ne doit appeler TMDB, ni pour le « où regarder », ni pour les fiches.

    `finaliser` résout ses passes à l'appel : sans ces doubles, un test qui n'en
    fournit pas irait chercher la vraie clé et le vrai réseau. Les DEUX passes
    vidéo en dépendent — la seconde a été oubliée ici pendant quelques minutes,
    et les tests se contentaient de journaliser « TMDB_API_KEY absent ».
    """
    monkeypatch.setattr(tne, "_fiches_tmdb", lambda *_a, **_k: _rapport_tmdb())
    monkeypatch.setattr(tne, "_fiches_video", lambda *_a, **_k: _rapport_video())


def _rapport_tmdb(servies=(), introuvables=()):
    """Double du rapport TMDB (cf. enrich_tmdb.RapportTmdb)."""
    return SimpleNamespace(servies=set(servies), vues=len(servies) + len(introuvables),
                           ecrites=len(servies), introuvables=list(introuvables))


def _rapport_video(servies=()):
    """Double du rapport des fiches de référence (cf. video_links_report.Report)."""
    return SimpleNamespace(servies=set(servies), seen=len(servies),
                           written=len(servies), filled=[])


@pytest.fixture
def recos(content, monkeypatch):
    import common

    dossier = content / "recos"
    (dossier / SOURCE).mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", dossier)
    return dossier


def _reco(dossier: Path, reco_id: str, guid: str, status: str = "validated",
          **champs) -> Path:
    chemin = dossier / SOURCE / f"{reco_id}.json"
    chemin.write_text(json.dumps({"id": reco_id, "episodeGuid": guid, "sourceId": SOURCE,
                                  "title": f"Titre {reco_id}", "types": ["album"],
                                  "status": status, **champs}, ensure_ascii=False),
                      encoding="utf-8")
    return chemin


def _rapport(liens: int = 0, raisons: dict[str, str] | None = None, servies=()):
    """Double du rapport d'enrichissement musical (`servies` : ids qui ont reçu un lien)."""
    return SimpleNamespace(
        linked=[f"lien-{i}" for i in range(liens)],
        outcomes=[SimpleNamespace(reco_id=rid, reason=raison,
                                  links=1 if rid in servies else 0)
                  for rid, raison in (raisons or {}).items()])


def _plan(items_created=(), items_reused=(), mentions_created=(), errors=(), drafts=()):
    """Double du plan de publication (cf. publier_episode.Plan)."""
    return SimpleNamespace(items_created=list(items_created), items_reused=list(items_reused),
                           mentions_created=list(mentions_created), errors=list(errors),
                           drafts=list(drafts), refused=bool(errors or drafts))


def _liens_vides(*_a, **_k):
    return _rapport()


def _publie_rien(*_a, **_k):
    return _plan()


def test_a_finaliser_waits_while_one_reco_is_still_a_draft(content, recos):
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-1", "yt-1")
    _reco(recos, "r-2", "yt-1", status="draft")

    assert tne.a_finaliser(SOURCE, tne.load_state(SOURCE)) == []


def test_a_finaliser_ignores_an_episode_without_any_reco(content, recos):
    _episode(content, "yt-1", status="auto")
    assert tne.a_finaliser(SOURCE, tne.load_state(SOURCE)) == []


def test_a_finaliser_takes_a_fully_reviewed_episode(content, recos):
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-1", "yt-1")
    _reco(recos, "r-2", "yt-1", status="discarded")

    pending = tne.a_finaliser(SOURCE, tne.load_state(SOURCE))

    assert [ep["guid"] for _p, ep in pending] == ["yt-1"]


def test_a_finaliser_ignores_an_episode_already_finalised(content, recos):
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-1", "yt-1")
    state = tne.load_state(SOURCE)
    state["finalized"].append("yt-1")

    assert tne.a_finaliser(SOURCE, state) == []


def test_finalisation_only_touches_the_recos_of_that_episode(content, recos, inbox):
    """Les recos d'un autre épisode ne doivent jamais partir à l'enrichissement."""
    _episode(content, "yt-1", status="auto")
    _episode(content, "yt-2", status="auto")
    _reco(recos, "r-1", "yt-1")
    _reco(recos, "r-2", "yt-1")
    _reco(recos, "autre", "yt-2", status="draft")  # yt-2 n'est pas relu
    vus = []
    state = tne.load_state(SOURCE)

    def liens(source_id, ids):
        vus.append((source_id, set(ids)))
        return _rapport()

    tne.finaliser(SOURCE, inbox, state, liens=liens, publier=_publie_rien, lock=_no_lock)

    assert vus == [(SOURCE, {"r-1", "r-2"})]
    assert state["finalized"] == ["yt-1"]


def test_finalisation_lists_what_is_left_to_do_by_hand(content, recos, inbox):
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-lie", "yt-1", links=[{"url": "https://www.deezer.com/album/1"}])
    _reco(recos, "r-ambigu", "yt-1", types=["artiste"])
    _reco(recos, "r-livre", "yt-1", types=["livre"])
    _reco(recos, "r-ecartee", "yt-1", status="discarded")

    def liens(_source_id, _ids):
        return _rapport(liens=1, raisons={"r-lie": "linked", "r-ambigu": "ambiguous"},
                        servies={"r-lie"})

    tne.finaliser(SOURCE, inbox, tne.load_state(SOURCE), liens=liens,
                  publier=lambda *_a, **_k: _plan(items_created=["i1", "i2"],
                                                  items_reused=["i3"],
                                                  mentions_created=["m1", "m2", "m3"]),
                  lock=_no_lock)

    message = inbox[0]
    assert "1 lien(s) posé(s)" in message
    assert "2 œuvre(s) créée(s), 1 réutilisée(s), 3 mention(s)" in message
    assert "À compléter à la main (2)" in message
    assert "Titre r-ambigu (artiste) — ambiguous" in message
    assert f"Titre r-livre (livre) — {tne.HORS_PERIMETRE}" in message
    assert "r-lie" not in message and "r-ecartee" not in message


def test_a_reco_just_served_is_not_listed_as_remaining(content, recos, inbox):
    """Le rapport fait foi autant que le disque : les deux doivent concorder."""
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-1", "yt-1")  # sur le disque, elle est encore nue

    tne.finaliser(SOURCE, inbox, tne.load_state(SOURCE),
                  liens=lambda *_a: _rapport(liens=1, raisons={"r-1": "linked"},
                                             servies={"r-1"}),
                  publier=_publie_rien, lock=_no_lock)

    assert "Rien à compléter à la main." in inbox[0]


def test_finalisation_says_when_nothing_is_left(content, recos, inbox):
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-1", "yt-1", links=[{"url": "https://www.deezer.com/album/1"}])

    tne.finaliser(SOURCE, inbox, tne.load_state(SOURCE), liens=_liens_vides,
                  publier=_publie_rien, lock=_no_lock)

    assert "Rien à compléter à la main." in inbox[0]


def test_a_very_long_list_is_cut_short(content, recos, inbox):
    """Un message Matrix illisible ne sert personne : le détail reste sur la page."""
    _episode(content, "yt-1", status="auto")
    for i in range(tne.MAX_RESTES + 3):
        _reco(recos, f"r-{i:02d}", "yt-1")

    tne.finaliser(SOURCE, inbox, tne.load_state(SOURCE), liens=_liens_vides,
                  publier=_publie_rien, lock=_no_lock)

    assert f"À compléter à la main ({tne.MAX_RESTES + 3})" in inbox[0]
    assert inbox[0].count("•") == tne.MAX_RESTES
    assert "… et 3 autre(s)." in inbox[0]


def test_a_refused_publication_leaves_the_episode_to_be_retried(content, recos, inbox):
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-1", "yt-1")
    state = tne.load_state(SOURCE)

    tne.finaliser(SOURCE, inbox, state, liens=_liens_vides,
                  publier=lambda *_a, **_k: _plan(errors=["fiche illisible"]),
                  lock=_no_lock)

    assert state["finalized"] == []
    assert "fiche illisible" in inbox[0] and "⚠️" in inbox[0]


def test_a_failing_episode_does_not_block_the_next_one_at_finalisation(content, recos, inbox):
    _episode(content, "yt-1", status="auto")
    _episode(content, "yt-2", status="auto")
    _reco(recos, "r-1", "yt-1")
    _reco(recos, "r-2", "yt-2")
    state = tne.load_state(SOURCE)

    def liens(_source_id, ids):
        if "r-1" in ids:
            raise RuntimeError("Deezer injoignable")
        return _rapport()

    tne.finaliser(SOURCE, inbox, state, liens=liens, publier=_publie_rien, lock=_no_lock)

    assert state["finalized"] == ["yt-2"]
    assert "Deezer injoignable" in inbox[0]


def test_finalisation_waits_when_the_review_server_holds_the_lock(content, recos, inbox):
    from review_lock import ServerLockBusy

    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-1", "yt-1")
    state = tne.load_state(SOURCE)

    @contextlib.contextmanager
    def busy():
        raise ServerLockBusy("review_server actif")
        yield  # pragma: no cover

    rc = tne.finaliser(SOURCE, inbox, state, liens=_liens_vides, publier=_publie_rien,
                       lock=busy)

    assert rc == 1 and state["finalized"] == []
    assert "verrou" in inbox[0]


def test_finalisation_takes_the_lock_before_writing_anything(content, recos):
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-1", "yt-1")
    ordre = []

    @contextlib.contextmanager
    def lock():
        ordre.append("verrou")
        yield

    tne.finaliser(SOURCE, lambda _t: None, tne.load_state(SOURCE),
                  liens=lambda *_a: ordre.append("liens") or _rapport(),
                  publier=lambda *_a, **_k: ordre.append("publie") or _plan(),
                  lock=lock)

    assert ordre == ["verrou", "liens", "publie"]


def test_finalisation_does_nothing_when_there_is_nothing_to_do(content, recos, inbox):
    assert tne.finaliser(SOURCE, inbox, tne.load_state(SOURCE),
                         liens=lambda *_a: pytest.fail("rien à faire"),
                         publier=_publie_rien, lock=_no_lock) == 0
    assert inbox == []


def test_the_music_pass_is_scoped_and_writes_but_never_guesses(recos, monkeypatch):
    """L'adaptateur réel : périmètre, écriture, artistes ouverts, chemins à l'appel."""
    import common
    import music_links_pipeline

    recu = {}
    monkeypatch.setattr(music_links_pipeline, "run", lambda **kw: recu.update(kw) or "rapport")

    assert tne._liens_musicaux(SOURCE, {"r-1"}) == "rapport"

    assert recu["root"] == common.RECOS_DIR and recu["source"] == SOURCE
    assert recu["ids"] == {"r-1"}
    assert recu["apply"] is True and recu["allow_artists"] is True


def test_the_cli_says_whether_there_is_something_to_finalise(content, recos):
    assert tne.main(["a-finaliser", "--source", SOURCE]) == 1
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-1", "yt-1")
    assert tne.main(["a-finaliser", "--source", SOURCE]) == 0


def test_the_cli_runs_the_finalisation_and_saves_the_state(content, recos, monkeypatch):
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-1", "yt-1")
    pris = []
    monkeypatch.setattr(tne, "build_notify", lambda _c: lambda _t: None)
    monkeypatch.setattr(tne, "_liens_musicaux", lambda *_a: _rapport())
    monkeypatch.setattr("publier_episode.preparer", lambda *_a, **_k: _plan())
    # Si le verrou n'était pas résolu à l'appel, c'est le VRAI qui serait pris.
    monkeypatch.setattr(tne, "_pipeline_lock",
                        lambda: pris.append(True) or contextlib.nullcontext())

    assert tne.main(["finaliser", "--source", SOURCE, "--notify", "none"]) == 0
    assert pris == [True]

    saved = json.loads(tne.state_path(SOURCE).read_text(encoding="utf-8"))
    assert saved["finalized"] == ["yt-1"]


# ===== finalisation : fiches TMDB ============================================
def test_finalisation_asks_tmdb_for_the_same_ids_as_the_music_pass(content, recos, inbox):
    _episode(content, "yt-1", status="auto")
    _episode(content, "yt-2", status="auto")
    _reco(recos, "r-film", "yt-1", types=["film"])
    _reco(recos, "r-album", "yt-1")
    _reco(recos, "autre", "yt-2", status="draft")  # yt-2 n'est pas relu
    vus = []

    def fiches(source_id, ids):
        vus.append((source_id, set(ids)))
        return _rapport_tmdb()

    tne.finaliser(SOURCE, inbox, tne.load_state(SOURCE), liens=_liens_vides,
                  fiches=fiches, publier=_publie_rien, lock=_no_lock)

    assert vus == [(SOURCE, {"r-film", "r-album"})]


def test_a_film_served_by_tmdb_leaves_the_list_and_is_counted(content, recos, inbox):
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-film", "yt-1", types=["film"])
    _reco(recos, "r-livre", "yt-1", types=["livre"])

    tne.finaliser(SOURCE, inbox, tne.load_state(SOURCE), liens=_liens_vides,
                  fiches=lambda *_a: _rapport_tmdb(servies={"r-film"}),
                  publier=_publie_rien, lock=_no_lock)

    message = inbox[0]
    assert "1 fiche(s) TMDB" in message
    assert "À compléter à la main (1)" in message
    assert "Titre r-film" not in message
    assert f"Titre r-livre (livre) — {tne.HORS_PERIMETRE}" in message


def test_a_film_served_by_the_reference_pass_leaves_the_list_and_is_counted(
        content, recos, inbox):
    """Les fiches IMDb/TMDB comptent comme les autres, et sortent de la liste."""
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-film", "yt-1", types=["film"])
    _reco(recos, "r-jeu", "yt-1", types=["jeu"])

    tne.finaliser(SOURCE, inbox, tne.load_state(SOURCE), liens=_liens_vides,
                  fiches=lambda *_a: _rapport_tmdb(),
                  video=lambda *_a: _rapport_video(servies={"r-film"}),
                  publier=_publie_rien, lock=_no_lock)

    message = inbox[0]
    assert "1 fiche(s) de référence" in message
    assert "À compléter à la main (1)" in message
    assert "Titre r-film" not in message
    assert f"Titre r-jeu (jeu) — {tne.HORS_PERIMETRE}" in message


def test_the_two_video_passes_receive_the_episode_ids_only(content, recos, inbox):
    """Le périmètre passé aux deux outils : les recos de CET épisode."""
    _episode(content, "yt-1", status="auto")
    _episode(content, "yt-2", status="auto")
    _reco(recos, "r-ici", "yt-1", types=["film"])
    _reco(recos, "r-ailleurs", "yt-2", types=["film"])
    recus = []

    def note(cle, rapport):
        def passe(_source, ids):
            recus.append((cle, set(ids)))
            return rapport
        return passe

    tne.finaliser(SOURCE, inbox, tne.load_state(SOURCE), liens=_liens_vides,
                  fiches=note("tmdb", _rapport_tmdb()),
                  video=note("video", _rapport_video()),
                  publier=_publie_rien, lock=_no_lock)

    # Les deux épisodes sont finalisés tour à tour : chaque appel ne doit voir
    # que les recos de l'épisode en cours, jamais celles de l'autre.
    assert recus == [("tmdb", {"r-ici"}), ("video", {"r-ici"}),
                     ("tmdb", {"r-ailleurs"}), ("video", {"r-ailleurs"})]


def test_the_reference_pass_runs_after_tmdb(content, recos, inbox):
    """Ordre imposé : TMDB pose l'identifiant dont les fiches se servent ensuite."""
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-film", "yt-1", types=["film"])
    ordre = []

    tne.finaliser(SOURCE, inbox, tne.load_state(SOURCE), liens=_liens_vides,
                  fiches=lambda *_a: ordre.append("tmdb") or _rapport_tmdb(),
                  video=lambda *_a: ordre.append("video") or _rapport_video(),
                  publier=_publie_rien, lock=_no_lock)

    assert ordre == ["tmdb", "video"]


def test_a_reference_pass_failure_costs_nothing_but_a_warning(content, recos, inbox):
    """Une panne ne prive pas l'épisode de ses œuvres, et il reste finalisé."""
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-film", "yt-1", types=["film"])

    def panne(*_a):
        raise RuntimeError("réseau injoignable")

    state = tne.load_state(SOURCE)
    tne.finaliser(SOURCE, inbox, state, liens=_liens_vides,
                  fiches=lambda *_a: _rapport_tmdb(servies={"r-film"}),
                  video=panne, publier=_publie_rien, lock=_no_lock)

    assert "⚠️ Fiches de référence indisponible : RuntimeError: réseau injoignable" in inbox[0]
    assert "1 fiche(s) TMDB" in inbox[0]
    assert state["finalized"] == ["yt-1"]


def test_a_reco_that_already_has_watch_providers_is_not_listed(content, recos, inbox):
    """Les fiches d'un passage précédent ne reviennent pas dans la liste."""
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-film", "yt-1", types=["film"],
          watchProviders=[{"label": "Netflix", "url": "https://x", "ethics": "neutral"}])

    tne.finaliser(SOURCE, inbox, tne.load_state(SOURCE), liens=_liens_vides,
                  fiches=lambda *_a: _rapport_tmdb(), publier=_publie_rien, lock=_no_lock)

    assert "Rien à compléter à la main." in inbox[0]


def test_a_tmdb_failure_costs_nothing_but_a_warning(content, recos, inbox):
    """Clé absente, 401 ou panne réseau : œuvres et mentions restent écrites."""
    _episode(content, "yt-1", status="auto")
    _reco(recos, "r-film", "yt-1", types=["film"])
    ecrit = []

    def panne(*_a, **_k):
        raise RuntimeError("TMDB_API_KEY absent")

    def publier(*_a, **_k):
        ecrit.append(True)
        return _plan(items_created=["i1"], mentions_created=["m1"])

    state = tne.load_state(SOURCE)
    code = tne.finaliser(SOURCE, inbox, state, liens=_liens_vides, fiches=panne,
                         publier=publier, lock=_no_lock)

    assert code == 0 and ecrit == [True]
    # Finalisé quand même : sinon la chaîne repasserait l'épisode à chaque tour.
    assert state["finalized"] == ["yt-1"]
    assert "⚠️ TMDB indisponible : RuntimeError: TMDB_API_KEY absent" in inbox[0]
    assert "1 œuvre(s) créée(s)" in inbox[0]


def test_the_real_tmdb_pass_asks_for_the_episode_scope(monkeypatch):
    """`_fiches_tmdb` doit passer le périmètre et écrire : c'est lui le défaut."""
    appels = []
    monkeypatch.setattr("enrich_tmdb.cle_api", lambda: "fake")
    monkeypatch.setattr("enrich_tmdb.run", lambda **kw: appels.append(kw) or _rapport_tmdb())

    _vraie_passe_tmdb(SOURCE, {"r-1"})

    assert appels == [{"source": SOURCE, "api_key": "fake", "ids": {"r-1"}, "apply": True}]


def test_the_real_reference_pass_is_scoped_and_never_searches_by_title(monkeypatch):
    """`_fiches_video` : périmètre, écriture, et SURTOUT pas de recherche par titre.

    La recherche par titre est le seul endroit où cet outil peut se tromper. La
    chaîne n'en a pas besoin, puisque la passe TMDB vient de poser les
    identifiants — vérifié sur venus le 2026-09-26, les 4 recos de S6-E02 sont
    servies par la population « id-existant ».
    """
    import common

    appels = []
    monkeypatch.setattr("enrich_tmdb.cle_api", lambda: "fake")
    monkeypatch.setattr("enrich_creators.load_episode_years", lambda *_a: {"g1": 2026})
    monkeypatch.setattr("video_links_pipeline.run",
                        lambda **kw: appels.append(kw) or _rapport_video())

    _vraie_passe_video(SOURCE, {"r-1"})

    (recu,) = appels
    assert recu["root"] == common.RECOS_DIR and recu["source"] == SOURCE
    assert recu["ids"] == {"r-1"} and recu["apply"] is True
    assert recu["api_key"] == "fake" and recu["episode_years"] == {"g1": 2026}
    assert "allow_search" not in recu  # le défaut de l'outil est False
