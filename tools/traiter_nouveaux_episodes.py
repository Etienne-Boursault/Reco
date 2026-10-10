"""
traiter_nouveaux_episodes.py — la chaîne automatique d'un nouvel épisode.

Lancé à intervalles réguliers sur venus, en huit temps que le script d'hôte
enchaîne (cf. deploy/venus/) :

    detecter     nouvelles vidéos de la chaîne -> épisodes `yt-…`
    transcrire   épisodes `yt-…` pas encore transcrits (faster-whisper, CPU)
    a-extraire   code 0 s'il reste un épisode transcrit à extraire, 1 sinon
    extraire     extraction des recos, puis message avec le lien de validation
    a-finaliser  code 0 s'il reste un épisode entièrement relu, 1 sinon
    finaliser    liens d'écoute + œuvres et mentions, puis message du reste à faire
    a-publier    code 0 s'il reste un épisode finalisé à pousser, 1 sinon
    publier      commit + branche sur GitHub, puis message avec le lien de la PR

Pourquoi découper : l'extraction et la finalisation prennent le verrou pipeline,
que le review_server tient tant qu'il tourne (cf. review_lock.py). Le script
d'hôte n'arrête donc la page de validation que le temps de ces étapes — une à
deux minutes — et seulement quand `a-extraire` ou `a-finaliser` a répondu qu'il
y a du travail.

Seuls les épisodes `yt-…` sont concernés. Les épisodes Acast ont été traités à
la main : les ré-extraire serait facturé et écraserait des mois de relecture.

État : `tools/output/pipeline/<source>.json` — épisodes déjà extraits, finalisés,
publiés, et dernière erreur signalée par étape et par épisode, pour qu'une panne
qui dure ne produise pas un message à chaque passage.

Usage :
    python traiter_nouveaux_episodes.py --source un-bon-moment detecter
    python traiter_nouveaux_episodes.py --source un-bon-moment transcrire
    python traiter_nouveaux_episodes.py --source un-bon-moment a-extraire
    python traiter_nouveaux_episodes.py --source un-bon-moment extraire
    python traiter_nouveaux_episodes.py --source un-bon-moment a-finaliser
    python traiter_nouveaux_episodes.py --source un-bon-moment finaliser
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import urllib.parse
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import common
from caler_citations import resume as _resume_calage
from common import (
    format_timestamp,
    list_episode_files,
    load_source,
    log,
    read_json,
    slugify,
    transcript_path_for,
    write_json_if_changed,
)
from fetch_youtube_episodes import GUID_PREFIX, fetch_youtube_episodes

# Ré-exportés : la section « finalisation » vit ici, son message dans son module.
from finalisation_message import HORS_PERIMETRE, MAX_RESTES, Passe  # noqa: F401
from finalisation_message import message as _message_finalisation
from finalisation_message import restes as _restes  # noqa: F401
from finalisation_passes import fiches_tmdb as _fiches_tmdb
from finalisation_passes import fiches_video as _fiches_video
from finalisation_passes import liens_boutique as _liens_boutique
from finalisation_passes import liens_jeux as _liens_jeux
from finalisation_passes import liens_musicaux as _liens_musicaux
from finalisation_passes import liens_plateformes as _liens_plateformes
from finalisation_passes import liens_wikidata as _liens_wikidata
from finalisation_passes import liens_youtube_music as _liens_youtube_music
from finalisation_passes import meme_oeuvre as _meme_oeuvre
from match_youtube import _build_suffix_regex

# Mesuré sur le CPU de venus le 2026-09-17 : 4,8 × le temps réel, un épisode de
# 82 min en ~17 min. `large-v3` y tient 1,4 × : une heure par épisode.
WHISPER_MODEL = "large-v3-turbo"
DEFAULT_REVIEW_URL = "http://10.8.0.1:8000"

Notify = Callable[[str], None]
PasseLiens = Callable[[str, set[str]], Any]


# ===== état ==================================================================
def state_path(source_id: str) -> Path:
    return common.OUTPUT_DIR / "pipeline" / f"{slugify(source_id)}.json"


def load_state(source_id: str) -> dict[str, Any]:
    path = state_path(source_id)
    state = read_json(path) if path.exists() else {}
    state.setdefault("extracted", [])
    state.setdefault("finalized", [])
    state.setdefault("published", [])
    state.setdefault("lastErrors", {})
    return state


def save_state(source_id: str, state: dict[str, Any]) -> None:
    path = state_path(source_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_if_changed(path, state)


def _report_once(state: dict[str, Any], key: str, message: str, notify: Notify) -> None:
    """Signale une erreur, sauf si c'est la même qu'au passage précédent."""
    log.error("%s", message)
    if state["lastErrors"].get(key) != message:
        notify(message)
        state["lastErrors"][key] = message


def _clear_error(state: dict[str, Any], key: str) -> None:
    state["lastErrors"].pop(key, None)


def _youtube_episodes(source_id: str) -> list[tuple[Path, dict[str, Any]]]:
    out = []
    for path in list_episode_files(source_id):
        episode = read_json(path)
        if str(episode.get("guid", "")).startswith(GUID_PREFIX):
            out.append((path, episode))
    return out


def _title(episode: dict[str, Any]) -> str:
    return episode.get("title") or episode["guid"]


def amorce_pour(source: dict[str, Any], episode: dict[str, Any]) -> str:
    """Phrase ponctuée redonnée au modèle à chaque fenêtre de transcription.

    Elle ne contient que ce qu'on sait avant d'écouter : les animateurs et le
    titre de la vidéo, où figure l'invité. Sans elle, la ponctuation s'éteint
    au fil de l'épisode (mesuré le 2026-09-17) ; avec elle, elle tient.
    """
    suffixe = _build_suffix_regex(tuple(source.get("youtubeTitleSuffixPatterns") or ()))
    titre = _title(episode)
    if suffixe is not None:
        titre = suffixe.sub("", titre)
    hotes = ", ".join(source.get("hosts") or []) or "ses animateurs"
    return (f"Bonjour et bienvenue dans {source.get('title', 'ce podcast')}, avec {hotes}. "
            f"Aujourd'hui : {titre.strip()}.")


# ===== étapes ================================================================
def detecter(source_id: str, notify: Notify,
             fetch: Callable[[str], Any] | None = None) -> int:
    # Résolu à l'appel : un défaut figé dans la signature rend la ligne de
    # commande intestable (voir le même choix dans fetch_youtube_episodes).
    result = (fetch or fetch_youtube_episodes)(source_id)
    titles = {ep["guid"]: _title(ep) for _, ep in _youtube_episodes(source_id)}
    for guid in result.created:
        notify(f"🎙️ Nouvel épisode détecté : {titles.get(guid, guid)}. "
               "Transcription en cours.")
    for video in result.unrecognized:
        notify(f"❓ Vidéo non reconnue sur la chaîne : « {video['title']} » "
               f"https://www.youtube.com/watch?v={video['id']}\n"
               "Si c'est un épisode, son titre n'a pas le format attendu "
               "(suffixe du podcast et « S<saison>-E<numéro> ») : rien n'a été traité.")
    return 0


def _remove_audio(source_id: str, guid: str) -> None:
    """Retire l'audio d'un épisode, une fois l'extraction terminée.

    Il sert deux fois dans le même passage de tick.sh : à la transcription, puis
    à la réécoute des citations qui suit l'extraction. Le retirer dès la
    transcription obligeait à retélécharger 62 Mo. Si l'extraction échoue, il
    reste jusqu'au passage qui la réussit. Au-delà, il se retélécharge : inutile
    de garder ~70 Mo par épisode (ni de les sauvegarder).
    """
    folder = common.AUDIO_DIR / source_id
    for path in folder.glob(f"{slugify(guid)}*"):
        with contextlib.suppress(OSError):
            path.unlink()


def _signaler_trous(episode: dict[str, Any], bilan: Any, notify: Notify) -> None:
    """Dit à l'éditeur où la machine a renoncé à retrouver un passage.

    Le comblement rattrape la plupart des trous, mais pas tous, et un trou non
    rattrapé est invisible : le transcript enchaîne deux phrases sans marquer
    qu'il manque quelque chose. C'est ainsi qu'une reco de Kyan a disparu de
    S6-E03 (01:11:58) et qu'elle n'a été retrouvée que parce que l'éditeur
    connaissait l'émission. Ces horodatages lui disent où tendre l'oreille.

    Silencieux quand tout est comblé : un message qui arrive à chaque épisode
    sans rien à dire finit par ne plus être lu.
    """
    if not getattr(bilan, "non_combles", None):
        return
    fenetres = ", ".join(f"{format_timestamp(debut)} (+{silence:.0f} s)"
                         for debut, silence in bilan.non_combles)
    notify(f"🕳️ {_title(episode)} : {len(bilan.non_combles)} passage(s) muet(s) que la "
           f"réécoute n'a pas su retrouver — {fenetres}. "
           f"La plupart sont de vrais silences ; à vérifier si l'un d'eux tombe dans "
           f"les recommandations.")


def transcrire(source_id: str, notify: Notify, state: dict[str, Any],
               transcriber: Callable[..., Any] | None = None,
               model: str = WHISPER_MODEL) -> int:
    if transcriber is None:
        from transcribe import transcribe_episode as transcriber
    source = load_source(source_id)
    for path, episode in _youtube_episodes(source_id):
        if episode.get("transcriptStatus", "none") != "none":
            continue
        key = f"transcription:{episode['guid']}"
        try:
            transcriber(source_id, path, model, "fr", False,
                        amorce=amorce_pour(source, episode),
                        signaler=lambda bilan, ep=episode: _signaler_trous(ep, bilan, notify))
        except Exception as exc:  # noqa: BLE001 — l'épisode suivant doit passer quand même.
            _report_once(state, key,
                         f"⚠️ Transcription impossible pour « {_title(episode)} » : {exc}",
                         notify)
            continue
        _clear_error(state, key)
        # L'audio reste pour la réécoute des citations : `extraire` le retire.
    return 0


def a_extraire(source_id: str, state: dict[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    return [
        (path, episode) for path, episode in _youtube_episodes(source_id)
        if episode.get("transcriptStatus") in {"auto", "validated"}
        and episode["guid"] not in state["extracted"]
        and transcript_path_for(source_id, episode["guid"]).exists()
    ]


def _pipeline_lock() -> contextlib.AbstractContextManager[None]:
    from review_lock import acquire_pipeline_lock
    return acquire_pipeline_lock(force=False)


def extraire(source_id: str, notify: Notify, state: dict[str, Any], *,
             review_url: str,
             client_factory: Callable[[], Any] | None = None,
             extractor: Callable[..., int] | None = None,
             preciseur: Callable[..., Any] | None = None,
             caleur: Callable[..., Any] | None = None,
             lock: Callable[[], contextlib.AbstractContextManager[None]] = _pipeline_lock,
             model: str | None = None) -> int:
    pending = a_extraire(source_id, state)
    if not pending:
        return 0
    if client_factory is None:
        from common import make_anthropic_client as client_factory
    if extractor is None:
        from extract_recos import extract_for_episode as extractor
    if model is None:
        from extract_recos import MODEL as model
    if preciseur is None:
        from preciser_citations import preciser_episode as preciseur
    if caleur is None:
        from caler_citations import caler_episode as caleur

    try:
        client = client_factory()
    except Exception as exc:  # noqa: BLE001
        _report_once(state, "extraction:client", f"⚠️ Extraction impossible : {exc}", notify)
        return 1
    _clear_error(state, "extraction:client")

    from review_lock import LockBusy
    try:
        with lock():
            _clear_error(state, "extraction:verrou")
            source = load_source(source_id)
            for path, episode in pending:
                _extract_one(source_id, path, episode, state, notify, client=client,
                             extractor=extractor, model=model, source=source,
                             review_url=review_url, preciseur=preciseur, caleur=caleur)
    except LockBusy as exc:
        _report_once(state, "extraction:verrou",
                     f"⚠️ Extraction repoussée, la page de validation tient le verrou : {exc}",
                     notify)
        return 1
    return 0


def _extract_one(source_id: str, path: Path, episode: dict[str, Any],
                 state: dict[str, Any], notify: Notify, **kwargs: Any) -> None:
    guid = episode["guid"]
    key = f"extraction:{guid}"
    try:
        count = kwargs["extractor"](source_id, path, kwargs["client"], False,
                                    model=kwargs["model"], source=kwargs["source"])
    except Exception as exc:  # noqa: BLE001
        _report_once(state, key,
                     f"⚠️ Extraction impossible pour « {_title(episode)} » : {exc}", notify)
        return
    _clear_error(state, key)
    state["extracted"].append(guid)

    # Réécoute ciblée : la citation publiée vient telle quelle de la
    # transcription, qui écorche les noms propres ; l'extraction, elle, vient
    # de les rétablir. Si elle échoue, l'épisode reste relisable.
    citations = 0
    try:
        citations = len(kwargs["preciseur"](source_id, guid, apply=True).precisees)
    except Exception as exc:  # noqa: BLE001
        log.warning("Citations non précisées pour %s : %s", guid, exc)
    finally:
        _remove_audio(source_id, guid)

    # Calage sur la transcription : le minutage sur la ligne où la citation est
    # dite, les noms mal transcrits sur la graphie du titre et du créateur.
    # Chaque nom rétabli est cité dans le message : la relecture tranche.
    calage = ""
    try:
        calage = _resume_calage(kwargs["caleur"](source_id, guid, apply=True))
    except Exception as exc:  # noqa: BLE001
        log.warning("Citations non calées pour %s : %s", guid, exc)

    precisees = f" {citations} citation(s) précisée(s)." if citations else ""
    calage = f"\n{calage}" if calage else ""
    link = f"{kwargs['review_url'].rstrip('/')}/ep?guid={urllib.parse.quote(guid, safe='')}"
    notify(f"✅ {_title(episode)} : {count} reco(s) à valider.{precisees}{calage}\n{link}")


# ===== finalisation ==========================================================


def _recos_de(source_id: str, guid: str) -> list[dict[str, Any]]:
    from publier_episode import _episode_recos
    return _episode_recos(source_id, guid)


def a_finaliser(source_id: str, state: dict[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    """Épisodes relus de bout en bout, pas encore finalisés.

    Une seule reco encore en brouillon suffit à attendre : `publier_episode`
    refuserait l'épisode entier, et poser des liens sur une reco qui sera
    peut-être écartée serait du travail perdu.
    """
    pending = []
    for path, episode in _youtube_episodes(source_id):
        if episode["guid"] in state["finalized"]:
            continue
        statuts = [r.get("status", "draft") for r in _recos_de(source_id, episode["guid"])]
        if statuts and "draft" not in statuts:
            pending.append((path, episode))
    return pending


def finaliser(source_id: str, notify: Notify, state: dict[str, Any], *,
              liens: PasseLiens | None = None, fiches: PasseLiens | None = None,
              video: PasseLiens | None = None, wikidata: PasseLiens | None = None,
              boutique: PasseLiens | None = None, plateformes: PasseLiens | None = None,
              jeux: PasseLiens | None = None, youtube_music: PasseLiens | None = None,
              oeuvre: PasseLiens | None = None,
              publier: Callable[..., Any] | None = None,
              lock: Callable[[], contextlib.AbstractContextManager[None]] | None = None) -> int:
    pending = a_finaliser(source_id, state)
    if not pending:
        return 0
    # Résolus à l'appel : un défaut figé dans la signature est lié à la
    # définition, et un test qui le remplace prendrait le VRAI verrou.
    liens = liens or _liens_musicaux
    oeuvre = oeuvre or _meme_oeuvre
    # Ordre imposé : TMDB pose `externalIds.tmdb` et les fournisseurs FR, dont
    # se servent les fiches puis les plateformes ; YouTube Music suit Wikidata
    # pour ne pas doubler l'Instagram que celui-ci aurait donné.
    complements = [
        ("TMDB", "fiche(s) TMDB", fiches or _fiches_tmdb),
        ("Fiches de référence", "fiche(s) de référence", video or _fiches_video),
        ("Wikidata", "lien(s) Wikidata", wikidata or _liens_wikidata),
        ("Steam et libraires", "lien(s) d'achat", boutique or _liens_boutique),
        ("Plateformes vidéo", "lien(s) de plateforme", plateformes or _liens_plateformes),
        ("Jeux par Wikidata", "lien(s) de jeu", jeux or _liens_jeux),
        ("YouTube Music", "lien(s) YouTube Music", youtube_music or _liens_youtube_music),
    ]
    lock = lock or _pipeline_lock
    if publier is None:
        from publier_episode import preparer as publier

    from review_lock import LockBusy
    try:
        with lock():
            _clear_error(state, "finalisation:verrou")
            for _path, episode in pending:
                _finaliser_un(source_id, episode, state, notify, liens=liens,
                              complements=complements, oeuvre=oeuvre, publier=publier)
    except LockBusy as exc:
        _report_once(state, "finalisation:verrou",
                     f"⚠️ Finalisation repoussée, la page de validation tient le verrou : {exc}",
                     notify)
        return 1
    return 0


def _finaliser_un(source_id: str, episode: dict[str, Any], state: dict[str, Any],
                  notify: Notify, *, liens: PasseLiens,
                  complements: list[tuple[str, str, PasseLiens]],
                  oeuvre: PasseLiens,
                  publier: Callable[..., Any]) -> None:
    guid = episode["guid"]
    key = f"finalisation:{guid}"
    ids = {r["id"] for r in _recos_de(source_id, guid) if r.get("id")}
    # D'abord les liens déjà relus d'une même œuvre : les passes suivantes ne
    # chercheront que les plateformes encore absentes.
    aligne = _passe_sans_bloquer("Même œuvre", "lien(s) repris du corpus",
                                 oeuvre, source_id, ids, guid)
    try:
        rapport = liens(source_id, ids)
        plan = publier(source_id, guid, apply=True)
    except Exception as exc:  # noqa: BLE001 — l'épisode suivant doit passer quand même.
        _report_once(state, key,
                     f"⚠️ Finalisation impossible pour « {_title(episode)} » : {exc}", notify)
        return
    if plan.refused:
        motif = ", ".join(plan.errors or plan.drafts)
        _report_once(state, key,
                     f"⚠️ Œuvres et mentions non écrites pour « {_title(episode)} » : {motif}",
                     notify)
        return
    # Les passes complémentaires en dernier, et jamais bloquantes : clé
    # absente, 401 ou panne réseau ne doivent pas priver l'épisode de ses
    # œuvres et de ses mentions, déjà écrites ci-dessus. L'épisode reste
    # finalisé, le message le signale.
    passes = [aligne] + [_passe_sans_bloquer(nom, unite, passe, source_id, ids, guid)
                         for nom, unite, passe in complements]
    _clear_error(state, key)
    state["finalized"].append(guid)
    # Relu après les passes : ce sont elles qui viennent d'écrire.
    notify(_message_finalisation(_title(episode), rapport, plan,
                                 _recos_de(source_id, guid), passes))


def _passe_sans_bloquer(nom: str, unite: str, passe: Callable[[str, set[str]], Any],
                        source_id: str, ids: set[str], guid: str) -> Passe:
    """Déroule une passe complémentaire ; une panne devient un message, pas un arrêt."""
    try:
        rapport = passe(source_id, ids)
    except Exception as exc:  # noqa: BLE001 — l'épisode garde ses œuvres et mentions.
        panne = f"{type(exc).__name__}: {str(exc)[:120]}"
        log.warning("%s non récupéré(s) pour %s : %s", unite, guid, panne)
        return Passe(nom, unite, panne=panne)
    return Passe(nom, unite, frozenset(rapport.servies))


# ===== publication ==========================================================
def a_publier(source_id: str, state: dict[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    """Épisodes finalisés — œuvres et mentions écrites — pas encore poussés."""
    return [(path, episode) for path, episode in _youtube_episodes(source_id)
            if episode["guid"] in state["finalized"]
            and episode["guid"] not in state.get("published", [])]


def publier(source_id: str, notify: Notify, state: dict[str, Any], **kwargs: Any) -> int:
    """Pousse les épisodes en attente. La mécanique git vit dans `publication`."""
    from publication import publier_les_episodes
    return publier_les_episodes(source_id, a_publier(source_id, state), notify, state,
                                rapporter=_report_once, oublier=_clear_error, **kwargs)


# ===== notification ==========================================================
def build_notify(channel: str) -> Notify:
    sender = None
    if channel != "none":
        from poll_rss import _build_sender
        sender = _build_sender(channel)

    def notify(text: str) -> None:
        log.info("Notification : %s", text)
        if sender is not None:
            sender.send({"msgtype": "m.text", "body": text})

    return notify


# ===== CLI ===================================================================
STEPS = ("detecter", "transcrire", "a-extraire", "extraire", "a-finaliser", "finaliser",
         "a-publier", "publier")
#: Étapes qui ne font que répondre « il y a du travail » (code 0) ou non (code 1).
SONDES = {"a-extraire": ("à extraire", a_extraire),
          "a-finaliser": ("à finaliser", a_finaliser),
          "a-publier": ("à publier", a_publier)}


@contextlib.contextmanager
def _state(source_id: str) -> Iterator[dict[str, Any]]:
    state = load_state(source_id)
    try:
        yield state
    finally:
        save_state(source_id, state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chaîne automatique d'un nouvel épisode.")
    parser.add_argument("etape", choices=STEPS)
    parser.add_argument("--source", required=True)
    parser.add_argument("--notify", default=os.environ.get("RECO_NOTIFY", "matrix"),
                        help="matrix | discord | slack | email | none (défaut: %(default)s)")
    parser.add_argument("--review-url",
                        default=os.environ.get("RECO_REVIEW_URL", DEFAULT_REVIEW_URL),
                        help="Adresse de la page de validation, pour les liens.")
    parser.add_argument("--modele-transcription", default=WHISPER_MODEL)
    args = parser.parse_args(argv)

    if args.etape in SONDES:
        libelle, sonde = SONDES[args.etape]
        pending = sonde(args.source, load_state(args.source))
        log.info("%d épisode(s) %s.", len(pending), libelle)
        return 0 if pending else 1

    notify = build_notify(args.notify)
    if args.etape == "detecter":
        return detecter(args.source, notify)
    with _state(args.source) as state:
        if args.etape == "transcrire":
            return transcrire(args.source, notify, state, model=args.modele_transcription)
        if args.etape == "finaliser":
            return finaliser(args.source, notify, state)
        if args.etape == "publier":
            return publier(args.source, notify, state)
        return extraire(args.source, notify, state, review_url=args.review_url)


if __name__ == "__main__":
    sys.exit(main())
