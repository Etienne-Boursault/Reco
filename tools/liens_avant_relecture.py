"""
liens_avant_relecture.py — chercher les liens AVANT la relecture, pas après.

Jusqu'ici, les passes de liens tournaient à la finalisation, une fois tout
relu : l'éditeur relisait sans voir un seul lien, et découvrait après la
publication ce qui manquait (44 % des liens finaux posés à la main sur
S6-E01 à S6-E04). Cette étape lance les MÊMES passes juste après
l'extraction ; la page de relecture montre ensuite, sur chaque carte, les liens
trouvés — un lien faux se retire d'un clic, un manque se voit aussitôt.

Trois contraintes ont dicté la forme :

1. **Les passes ne traitent que les recos validées.** Plutôt que de relâcher ce
   filtre dans sept outils, elles tournent sur une COPIE des brouillons, statut
   forcé à `validated`, dans un dossier temporaire (`common.RECOS_DIR` est
   redirigé le temps des passes ; tous les adaptateurs le lisent à l'appel).
2. **La page de relecture reste ouverte** (pas de verrou pipeline) : l'éditeur
   peut valider une reco pendant que les passes tournent. On ne recopie donc
   jamais la reco entière : seuls les liens NOUVEAUX (et les identifiants
   externes absents) sont fusionnés dans le fichier RELU juste avant
   l'écriture. Statut, attribution, titre : ce qu'a décidé l'humain gagne.
3. **Un lien retiré à la relecture ne revient pas.** La page note son URL dans
   `linksRejected` ; la fusion l'ignore, et `purger_rejetes` le retire en fin
   de finalisation si une passe l'a retrouvé.

La finalisation garde ses passes : elles ne cherchent plus que les plateformes
encore absentes, et servent de filet pour une reco ajoutée ou retitrée pendant
la relecture.
"""
from __future__ import annotations

import contextlib
import copy
import tempfile
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import Any

import common
from align_same_work_links import TITRE_MINI, compatibles, fold_titre
from common import log, read_json, write_json_if_changed

Notify = Callable[[str], None]
Passe = Callable[[str, set[str]], Any]

#: Clé de l'état de la chaîne : épisodes dont les liens ont été cherchés.
ETAT = "liensCherches"
#: Champ de reco : URL retirées à la relecture, à ne jamais reposer.
REJETES = "linksRejected"


def _passes_par_defaut() -> list[tuple[str, Passe]]:
    """Les passes de la finalisation, dans le même ordre (cf. finaliser)."""
    import finalisation_passes as fp
    return [("musique", fp.liens_musicaux), ("TMDB", fp.fiches_tmdb),
            ("fiches", fp.fiches_video), ("Wikidata", fp.liens_wikidata),
            ("boutique", fp.liens_boutique), ("plateformes", fp.liens_plateformes),
            ("jeux", fp.liens_jeux), ("YouTube Music", fp.liens_youtube_music)]


def _urls(doc: dict[str, Any]) -> list[str]:
    return [link["url"] for link in doc.get("links") or []
            if isinstance(link, dict) and link.get("url")]


def _brouillons(source_id: str, guid: str) -> dict[str, tuple[Path, dict[str, Any]]]:
    """`{id: (chemin, reco)}` des brouillons de l'épisode."""
    out = {}
    for path in sorted(common.recos_dir_for(source_id).glob("*.json")):
        doc = read_json(path)
        if (doc.get("episodeGuid") == guid and doc.get("id")
                and doc.get("status", "draft") == "draft"):
            out[doc["id"]] = (path, doc)
    return out


def a_chercher(source_id: str, state: dict[str, Any]) -> list[tuple[Path, dict[str, Any]]]:
    """Épisodes extraits, pas encore finalisés, dont les liens restent à chercher."""
    from traiter_nouveaux_episodes import _youtube_episodes
    faits = set(state.get(ETAT) or []) | set(state.get("finalized") or [])
    return [(path, ep) for path, ep in _youtube_episodes(source_id)
            if ep["guid"] in (state.get("extracted") or []) and ep["guid"] not in faits
            and _brouillons(source_id, ep["guid"])]


# ===== même œuvre ===========================================================
def liens_meme_oeuvre(brouillon: dict[str, Any],
                      corpus: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Liens déjà relus de la même œuvre, à donner au brouillon (vide sinon).

    Mêmes garde-fous qu'`align_same_work_links` (titre assez long, types et
    créateurs compatibles, identifiants non contradictoires), appliqués au
    groupe formé par le corpus validé ET le brouillon.
    """
    titre = fold_titre(brouillon.get("title"))
    if len(titre) < TITRE_MINI:
        return []
    groupe = [d for d in corpus if fold_titre(d.get("title")) == titre]
    if not groupe or compatibles([*groupe, brouillon]) is not None:
        return []
    deja = set(_urls(brouillon))
    union: dict[str, dict[str, Any]] = {}
    for d in groupe:
        for link in d.get("links") or []:
            if isinstance(link, dict) and link.get("url") and link["url"] not in deja:
                union.setdefault(link["url"], dict(link))
    return list(union.values())


def _corpus_valide(source_id: str) -> list[dict[str, Any]]:
    out = []
    for path in common.recos_dir_for(source_id).glob("*.json"):
        try:
            doc = read_json(path)
        except (OSError, ValueError):
            continue
        if doc.get("status") == "validated":
            out.append(doc)
    return out


# ===== copie de travail ======================================================
@contextlib.contextmanager
def _recos_dir(racine: Path) -> Iterator[None]:
    """Redirige `common.RECOS_DIR` le temps des passes (processus mono-tâche)."""
    avant = common.RECOS_DIR
    common.RECOS_DIR = racine
    try:
        yield
    finally:
        common.RECOS_DIR = avant


def _travailler_sur_copie(source_id: str, brouillons: dict[str, dict[str, Any]],
                          corpus: Sequence[dict[str, Any]],
                          passes: Sequence[tuple[str, Passe]]) -> dict[str, dict[str, Any]]:
    """Déroule les passes sur une copie ; renvoie `{id: copie enrichie}`."""
    with tempfile.TemporaryDirectory(prefix="liens-") as tmp:
        racine = Path(tmp)
        dossier = racine / source_id
        dossier.mkdir()
        for rid, doc in brouillons.items():
            travail = copy.deepcopy(doc)
            travail["status"] = "validated"
            rejetes = set(doc.get(REJETES) or [])
            travail["links"] = (list(travail.get("links") or [])
                                + [link for link in liens_meme_oeuvre(doc, corpus)
                                   if link["url"] not in rejetes])
            write_json_if_changed(dossier / f"{rid}.json", travail)
        with _recos_dir(racine):
            for nom, passe in passes:
                try:
                    passe(source_id, set(brouillons))
                except Exception as exc:  # noqa: BLE001 — une panne n'arrête pas les autres.
                    log.warning("liens avant relecture : passe %s en panne : %s", nom, exc)
        return {rid: read_json(dossier / f"{rid}.json") for rid in brouillons}


# ===== fusion =================================================================
def fusionner(copie: dict[str, Any], instantane: dict[str, Any],
              reel: dict[str, Any]) -> dict[str, Any] | None:
    """La reco RÉELLE enrichie de ce que les passes ont trouvé ; None si rien.

    `instantane` est la reco telle qu'au début des passes, `reel` telle qu'à
    l'instant de l'écriture. Seuls les liens nouveaux entrent ; ceux que
    l'humain a retirés entre-temps (absents de `reel`) ou rejetés restent
    dehors ; ceux qu'il a ajoutés restent. L'ordre suit la copie, qui place les
    plateformes en tête, puis viennent les ajouts de l'humain.
    """
    rejetes = set(reel.get(REJETES) or [])
    reels = set(_urls(reel))
    nouveaux = set(_urls(copie)) - set(_urls(instantane)) - rejetes - reels
    ext_copie = copie.get("externalIds") or {}
    ext_reel = reel.get("externalIds") or {}
    ext_nouveaux = {k: v for k, v in ext_copie.items() if k not in ext_reel}
    providers = "watchProviders" in copie and "watchProviders" not in reel
    if not nouveaux and not ext_nouveaux and not providers:
        return None
    sortie = copy.deepcopy(reel)
    gardes = nouveaux | reels
    liens_copie = [link for link in copie.get("links") or []
                   if isinstance(link, dict) and link.get("url") in gardes]
    vus = {link["url"] for link in liens_copie}
    sortie["links"] = liens_copie + [link for link in reel.get("links") or []
                                     if isinstance(link, dict) and link.get("url") not in vus]
    if ext_nouveaux:
        sortie["externalIds"] = {**ext_reel, **ext_nouveaux}
    if providers:
        sortie["watchProviders"] = copie["watchProviders"]
    traces = {k: v for k, v in (copie.get("enrichedAt") or {}).items()
              if k not in (reel.get("enrichedAt") or {})}
    if traces:
        sortie["enrichedAt"] = {**(reel.get("enrichedAt") or {}), **traces}
    return sortie


def chercher_episode(source_id: str, guid: str,
                     passes: Sequence[tuple[str, Passe]] | None = None) -> tuple[int, int]:
    """Cherche les liens des brouillons d'un épisode : `(liens ajoutés, recos sans lien)`."""
    lus = _brouillons(source_id, guid)
    if not lus:
        return 0, 0
    instantanes = {rid: doc for rid, (_p, doc) in lus.items()}
    copies = _travailler_sur_copie(source_id, instantanes, _corpus_valide(source_id),
                                   passes if passes is not None else _passes_par_defaut())
    ajoutes = sans_lien = 0
    for rid, (path, _doc) in lus.items():
        if not path.exists():
            continue  # supprimée pendant les passes
        reel = read_json(path)  # relu À L'INSTANT de l'écriture
        fusion = fusionner(copies[rid], instantanes[rid], reel)
        if fusion is not None:
            ajoutes += len(set(_urls(fusion)) - set(_urls(reel)))
            write_json_if_changed(path, fusion)
        sans_lien += not _urls(fusion or reel)
    return ajoutes, sans_lien


def chercher(source_id: str, notify: Notify, state: dict[str, Any], *,
             passes: Sequence[tuple[str, Passe]] | None = None) -> int:
    """Étape `chercher-liens` de la chaîne : sans verrou, page de relecture ouverte."""
    state.setdefault(ETAT, [])
    for _path, episode in a_chercher(source_id, state):
        guid = episode["guid"]
        try:
            ajoutes, sans_lien = chercher_episode(source_id, guid, passes)
        except Exception as exc:  # noqa: BLE001 — l'épisode suivant doit passer.
            log.error("liens avant relecture impossibles pour %s : %s", guid, exc)
            continue
        state[ETAT].append(guid)
        titre = episode.get("title") or guid
        suite = (f" ; {sans_lien} reco(s) encore sans lien, à compléter pendant la relecture."
                 if sans_lien else ".")
        notify(f"🔗 « {titre} » : {ajoutes} lien(s) trouvé(s) avant la relecture{suite}")
    return 0


def purger_rejetes(source_id: str, ids: set[str]) -> int:
    """Retire les liens rejetés à la relecture qu'une passe aurait reposés."""
    retires = 0
    for path in common.recos_dir_for(source_id).glob("*.json"):
        doc = read_json(path)
        rejetes = set(doc.get(REJETES) or [])
        if doc.get("id") not in ids or not rejetes:
            continue
        gardes = [link for link in doc.get("links") or []
                  if not (isinstance(link, dict) and link.get("url") in rejetes)]
        if len(gardes) != len(doc.get("links") or []):
            retires += len(doc.get("links") or []) - len(gardes)
            doc["links"] = gardes
            write_json_if_changed(path, doc)
    return retires
