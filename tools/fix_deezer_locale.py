"""
fix_deezer_locale.py — retire le segment de locale des URL Deezer.

`https://www.deezer.com/us/album/262200072` → `https://www.deezer.com/album/262200072`

POURQUOI SUPPRIMER PLUTÔT QUE FORCER `/fr/`
    Sans segment de locale, Deezer redirige selon le visiteur. Vérifié :
    `https://www.deezer.com/artist/259` renvoie 200 et atterrit sur
    `/fr/artist/259` avec `Accept-Language: fr-FR`, sur `/us/artist/259`
    avec `en-US` — même œuvre (« Michael Jackson ») dans les deux cas.
    Le projet étant duplicable (un fork peut être anglophone), câbler la
    boutique française en dur imposerait un choix franco-centré aux forks.

L'IDENTIFIANT NUMÉRIQUE N'EST JAMAIS TOUCHÉ : seul le segment de locale
disparaît, tout ce qui suit la section est recopié tel quel.

SECTIONS TRAITÉES
    Uniquement celles vérifiées en HTTP sans locale (200 + contenu attendu) :
    album, track, artist, show. Toute autre section rencontrée dans le
    corpus est SIGNALÉE et laissée intacte — on ne réécrit pas une forme
    d'URL dont on n'a pas constaté le comportement.

Usage :
    python fix_deezer_locale.py                      # dry-run (défaut)
    python fix_deezer_locale.py --json rapport.json  # détail machine
    python fix_deezer_locale.py --apply              # écrit
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from typing import Any

from common import log
from dataset_fixes import Change, add_common_args, run

#: Sections Deezer dont le comportement sans locale a été constaté en HTTP.
VERIFIED_SECTIONS = ("album", "track", "artist", "show")

#: Locale = exactement deux lettres, et SEULEMENT si la section qui suit est
#: connue. Un `deezer.com/xx/…` inattendu passe ainsi à travers sans dégât.
_LOCALE_RE = re.compile(
    r"^(?P<host>https?://(?:www\.)?deezer\.com)/[a-z]{2}"
    r"(?P<rest>/(?:" + "|".join(VERIFIED_SECTIONS) + r")/.*)$",
    re.IGNORECASE,
)

#: Une locale suivie d'une section NON vérifiée : on ne touche pas, on signale.
_UNVERIFIED_RE = re.compile(
    r"^https?://(?:www\.)?deezer\.com/[a-z]{2}/(?P<section>[a-z]+)/", re.IGNORECASE
)


def strip_locale(url: str) -> str | None:
    """Renvoie l'URL sans segment de locale, ou None si rien à changer.

    >>> strip_locale("https://www.deezer.com/us/album/262200072")
    'https://www.deezer.com/album/262200072'
    >>> strip_locale("https://www.deezer.com/album/262200072") is None
    True
    """
    match = _LOCALE_RE.match(url)
    if not match:
        return None
    return match.group("host") + match.group("rest")


def unverified_section(url: str) -> str | None:
    """Section Deezer localisée mais non vérifiée (donc à ne pas réécrire)."""
    if strip_locale(url) is not None:
        return None
    match = _UNVERIFIED_RE.match(url)
    return match.group("section").lower() if match else None


def _iter_url_slots(reco: dict[str, Any]) -> list[tuple[str, Any, str, str]]:
    """Tous les emplacements porteurs d'URL : (libellé, conteneur, clé, valeur).

    Une URL Deezer peut vivre dans cinq endroits distincts du schéma. Les
    oublier reviendrait à ne corriger qu'une partie du corpus : dans l'état
    actuel, les locales sont justement dans `links[]` et `linkOverrides`,
    pas dans `externalIds`.
    """
    slots: list[tuple[str, Any, str, str]] = []
    for key in ("links", "customLinks", "watchProviders"):
        entries = reco.get(key)
        if not isinstance(entries, list):
            continue
        for idx, entry in enumerate(entries):
            if isinstance(entry, dict) and isinstance(entry.get("url"), str):
                slots.append((f"{key}[{idx}].url", entry, "url", entry["url"]))
    overrides = reco.get("linkOverrides")
    if isinstance(overrides, dict):
        for label, url in overrides.items():
            if isinstance(url, str):
                slots.append((f"linkOverrides[{label!r}]", overrides, label, url))
    ext = reco.get("externalIds")
    if isinstance(ext, dict) and isinstance(ext.get("deezer"), str):
        slots.append(("externalIds.deezer", ext, "deezer", ext["deezer"]))
    return slots


def transform(reco: dict[str, Any]) -> list[Change]:
    """Retire la locale de chaque URL Deezer de la reco. Mute `reco` en place."""
    changes: list[Change] = []
    for label, container, key, url in _iter_url_slots(reco):
        section = unverified_section(url)
        if section:
            log.warning("  %s · section Deezer non vérifiée (%s), laissée intacte : %s",
                        reco.get("id", "?"), section, url)
            continue
        fixed = strip_locale(url)
        if fixed is None or fixed == url:
            continue
        container[key] = fixed
        changes.append(Change(field=label, before=url, after=fixed))
    return changes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retire le segment de locale (/us/, /en/, /fr/…) des URL "
                    "Deezer pour que Deezer redirige selon le visiteur.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(transform, args, extra_report={"verified_sections": list(VERIFIED_SECTIONS)})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
