"""
migrate_watch_page.py — renomme `externalIds.justwatch` en `externalIds.watchPage`.

POURQUOI
    Le champ portait un nom qui ment. TMDB a changé son API : la clé
    `watch/providers` → `results.FR.link` ne renvoie plus une URL JustWatch
    mais une URL themoviedb.org. Constat sur le corpus (2026-07-31) :

        237 recos + 214 items portent le champ ;
        451/451 pointent sur `www.themoviedb.org` ;
        0 pointe sur `justwatch.com`.

    Conséquence concrète : dans le serveur de relecture, le bouton
    « JustWatch » envoyait vers TMDB.

    `watchPage` décrit la FONCTION (« la page où regarder ») et non le
    fournisseur — si la source change encore, le nom reste vrai.

CE QUE FAIT LE SCRIPT
    Renomme la clé, à l'identique, dans `src/content/recos/**` ET
    `src/content/items/**`. La VALEUR n'est jamais touchée : ce correctif
    répare un nom, pas des URL. Si `watchPage` existe déjà, il ne l'écrase
    pas (idempotence) et signale la collision.

Usage :
    python migrate_watch_page.py                      # dry-run (défaut)
    python migrate_watch_page.py --json rapport.json  # détail machine
    python migrate_watch_page.py --apply              # écrit
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse

from common import CONTENT_DIR, RECOS_DIR, log
from dataset_fixes import Change, add_common_args, run

OLD_KEY = "justwatch"
NEW_KEY = "watchPage"

#: `linkOverrides` est indexé par le LIBELLÉ exact produit par merchants.ts.
#: Ce libellé passe de « JustWatch » à « Où regarder » (un lien qui part chez
#: TMDB ne peut pas s'appeler JustWatch). Sans cette seconde migration, les
#: overrides existants deviendraient orphelins — silencieusement.
OLD_LABEL = "JustWatch"
NEW_LABEL = "Où regarder"

#: Le champ vit dans les deux collections ; n'en migrer qu'une laisserait le
#: corpus incohérent (cf. `content.config.ts` : recos ET items le déclarent).
ITEMS_DIR = CONTENT_DIR / "items"
MIGRATION_ROOTS = (RECOS_DIR, ITEMS_DIR)


def _rename_key(
    container: dict[str, Any], old: str, new: str, label: str, doc_id: str
) -> list[Change]:
    """Renomme `old` en `new` dans `container`, sans jamais écraser `new`."""
    if old not in container:
        return []
    value = container[old]
    if new in container:
        log.warning("  %s · `%s` ET `%s` présents — clé `%s` laissée intacte.",
                    doc_id, old, new, old)
        return []
    del container[old]
    container[new] = value
    return [Change(field=f"{label}.{old} → {label}.{new}", before=value, after=value)]


def transform(doc: dict[str, Any]) -> list[Change]:
    """Renomme la clé dans `externalIds` ET dans `linkOverrides`. Mute `doc`.

    Les VALEURS sont recopiées telles quelles — ce correctif répare des noms,
    jamais des URL.
    """
    doc_id = doc.get("id", "?")
    changes: list[Change] = []
    ext = doc.get("externalIds")
    if isinstance(ext, dict):
        changes += _rename_key(ext, OLD_KEY, NEW_KEY, "externalIds", doc_id)
    overrides = doc.get("linkOverrides")
    if isinstance(overrides, dict):
        changes += _rename_key(overrides, OLD_LABEL, NEW_LABEL, "linkOverrides", doc_id)
    return changes


def host_census(results: Sequence[Any]) -> dict[str, Any]:
    """Répartition par hôte des valeurs migrées — la preuve que le nom mentait."""
    hosts: Counter[str] = Counter()
    for res in results:
        for chg in res.changes:
            value = chg.after
            host = urlparse(value).netloc if isinstance(value, str) else ""
            hosts[host or "(valeur non-URL)"] += 1
    return {"hotes_des_valeurs": dict(hosts.most_common())}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Renomme `externalIds.justwatch` en `externalIds.watchPage` "
                    "dans les recos et les items (la valeur n'est pas touchée).")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = run(transform, args, roots=MIGRATION_ROOTS, extra_report=host_census)
    for host, count in host_census(results)["hotes_des_valeurs"].items():
        log.info("  hôte des valeurs migrées : %s × %d", host, count)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
