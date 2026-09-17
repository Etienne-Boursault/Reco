"""
publier_episode.py — convertit les recos d'UN épisode relu en œuvres et mentions,
sans jamais toucher à l'existant.

Les galeries, les pages d'œuvre, la recherche et les statistiques ne lisent pas
les recos : elles lisent des œuvres (`items`) et des mentions. Le seul outil qui
les produisait, `migrate_reco_to_item_mention.py`, relit TOUTES les recos de la
source et réécrit TOUTES les œuvres et mentions. Vérifié le 2026-09-17 : un
`--apply` effacerait l'enrichissement fait depuis juillet — l'œuvre de ubm-3146
y perdait ses `externalIds` et ses `watchProviders`.

Ce script reprend la MÊME conversion (`reco_dict_to_item_mention`, qui reproduit
à l'identique les mentions publiées) et le même rapprochement avec les œuvres
existantes (titre et créateur normalisés, un type en commun), mais :
  - il ne lit que les recos de l'épisode demandé ;
  - il refuse tant qu'une reco de l'épisode est en brouillon ;
  - une œuvre déjà présente est RÉUTILISÉE, jamais réécrite ;
  - une mention déjà présente est laissée telle quelle ;
  - un identifiant neuf qui tombe sur une fiche existante arrête tout ;
  - une fiche d'œuvre illisible arrête tout : le dépôt l'ignorerait sans bruit,
    et une reco de la même œuvre en créerait un doublon ;
  - `guestWork`, que la conversion ignore, est recopié depuis la reco.

Les recos écartées reçoivent aussi œuvre et mention, comme dans le reste du
corpus : le site masque les mentions `discarded`.

Sans `--apply`, rien n'est écrit : le script dit ce qu'il ferait.

Usage :
    cd tools
    python publier_episode.py --source un-bon-moment --guid yt-XXXX [--apply] [--json]

Codes de sortie : 0 fait (ou simulé) · 2 refusé (brouillons, erreurs, verrou).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

import common
from common import log, read_json, recos_dir_for
from domain.services.identity import generate_item_id
from repository._base import write_json_idempotent
from repository.item_repo import ItemRepoJson
from repository.mention_repo import MentionRepoJson
from repository.migration.reco_parser import reco_dict_to_item_mention
from repository.serialization import mention_to_dict


@dataclass
class Plan:
    guid: str
    drafts: list[str] = field(default_factory=list)
    items_created: list[str] = field(default_factory=list)
    items_reused: list[str] = field(default_factory=list)
    mentions_created: list[str] = field(default_factory=list)
    mentions_existing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def refused(self) -> bool:
        return bool(self.drafts or self.errors)


def _resolveur(item_repo: ItemRepoJson) -> tuple[Callable[..., str], set[str]]:
    """Rattache une reco à une œuvre existante, ou réserve un identifiant neuf.

    Même politique que l'index de la migration : même clé canonique ET au moins
    un type en commun. On ne passe pas par `IdentityRegistry.seed` : il refuse
    deux fiches de même clé, or le corpus en contient (« game of thrones » sans
    créateur, 10e6e524 et 4effb9f7) et la migration plante dessus. Les
    identifiants neufs évitent tous ceux déjà sur disque.
    """
    by_canonical: dict[str, list[tuple[str, tuple[Any, ...]]]] = {}
    existing = item_repo.existing_index()
    for item_id, (canonical, types) in existing.items():
        by_canonical.setdefault(canonical, []).append((item_id, types))
    used = set(existing)
    reused: set[str] = set()
    fresh: dict[str, str] = {}

    def resolve(canonical: str, _creator: str | None, types: tuple[Any, ...]) -> str:
        for item_id, existing_types in by_canonical.get(canonical, ()):
            if set(types) & set(existing_types):
                reused.add(item_id)
                return item_id
        if canonical not in fresh:
            fresh[canonical] = generate_item_id(canonical, frozenset(used))
            used.add(fresh[canonical])
        return fresh[canonical]

    return resolve, reused


def _episode_recos(source_id: str, guid: str) -> list[dict[str, Any]]:
    folder = recos_dir_for(source_id)
    if not folder.is_dir():
        return []
    recos = (read_json(path) for path in sorted(folder.glob("*.json")))
    return [reco for reco in recos if reco.get("episodeGuid") == guid]


def preparer(source_id: str, guid: str, *, apply: bool = False) -> Plan:
    plan = Plan(guid)
    recos = _episode_recos(source_id, guid)
    if not recos:
        plan.errors.append(f"aucune reco pour l'épisode {guid}")
        return plan
    plan.drafts = sorted(r["id"] for r in recos if r.get("status", "draft") == "draft")
    if plan.drafts:
        return plan

    # Résolus à l'appel : les tests redirigent `common.CONTENT_DIR`.
    items_dir = common.CONTENT_DIR / "items"
    mentions_dir = common.CONTENT_DIR / "mentions"
    item_repo = ItemRepoJson(items_dir, source_id)
    mention_repo = MentionRepoJson(mentions_dir, source_id)
    resolver, reused = _resolveur(item_repo)
    unreadable = len(list((items_dir / source_id).glob("*.json"))) - len(item_repo.existing_index())
    if unreadable:
        plan.errors.append(f"{unreadable} fiche(s) d'œuvre illisible(s) : rapprochement incomplet, "
                           "un doublon pourrait être créé")
        return plan

    new_items: dict[str, Any] = {}
    new_mentions: list[tuple[str, dict[str, Any]]] = []
    for reco in recos:
        try:
            item, mention = reco_dict_to_item_mention(reco, item_id_resolver=resolver)
        except (ValueError, KeyError, TypeError) as exc:
            plan.errors.append(f"{reco.get('id')} : {exc}")
            continue
        if mention_repo.exists(mention.id):
            plan.mentions_existing.append(mention.id)
            continue
        if item.id in reused:
            if item.id not in plan.items_reused:
                plan.items_reused.append(item.id)
        elif item_repo.exists(item.id):
            plan.errors.append(
                f"{reco['id']} : l'identifiant neuf {item.id} désigne une fiche existante "
                "qui n'est pas la même œuvre — rien n'est écrit")
            continue
        else:
            new_items.setdefault(item.id, item)
        payload = mention_to_dict(mention)
        if reco.get("guestWork") is True:
            payload["guestWork"] = True
        new_mentions.append((mention.id, payload))

    plan.items_created = sorted(new_items)
    plan.mentions_created = sorted(mention_id for mention_id, _ in new_mentions)
    if plan.errors or not apply:
        return plan

    # Les œuvres d'abord : une mention ne doit jamais pointer vers une fiche absente.
    for item in new_items.values():
        item_repo.upsert(item)
    for mention_id, payload in new_mentions:
        write_json_idempotent(mentions_dir / source_id / f"{mention_id}.json", payload)
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", required=True)
    parser.add_argument("--guid", required=True)
    parser.add_argument("--apply", action="store_true", help="Écrit ; sinon simulation.")
    parser.add_argument("--json", action="store_true", help="Plan en JSON sur stdout.")
    parser.add_argument("--force", action="store_true",
                        help="Ignore le verrou du review_server (écritures concurrentes).")
    args = parser.parse_args(argv)

    if args.apply:
        from review_lock import LockBusy, acquire_pipeline_lock
        try:
            with acquire_pipeline_lock(force=args.force):
                plan = preparer(args.source, args.guid, apply=True)
        except LockBusy as exc:
            log.error("%s", exc)
            return 2
    else:
        plan = preparer(args.source, args.guid)

    if args.json:
        print(json.dumps({**asdict(plan), "refused": plan.refused}, ensure_ascii=False))
    if plan.drafts:
        log.error("Refusé : %d reco(s) encore en brouillon : %s",
                  len(plan.drafts), ", ".join(plan.drafts))
    for error in plan.errors:
        log.error("Refusé : %s", error)
    log.info("%s — œuvres créées %d, réutilisées %d ; mentions créées %d, déjà là %d",
             "Écrit" if args.apply and not plan.refused else "Simulation",
             len(plan.items_created), len(plan.items_reused),
             len(plan.mentions_created), len(plan.mentions_existing))
    return 2 if plan.refused else 0


if __name__ == "__main__":
    sys.exit(main())
