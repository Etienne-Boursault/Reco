"""
fix_duplicate_links.py — retire les liens qui font doublon dans une même reco.

DEUX RÈGLES, INDÉPENDANTES, chacune activable seule (`--rule`). Elles ne
partagent que le socle : ce qui les sépare, c'est ce qui rend deux liens
redondants, et ça n'a rien d'universel.

CE QUI N'EST PAS UN DOUBLON
---------------------------
L'audit du 2026-08-15 a passé les 1209 recos actives au crible. La plupart des
paires sur un même hôte sont COMPLÉMENTAIRES, et les supprimer appauvrirait la
carte :

    page artiste + album (Deezer, Qobuz)   morceau + album (Spotify)
    série + tome 1 (Glénat)                deux spectacles distincts (Netflix)
    recherche par auteur + un livre précis (Place des Libraires)

Ce module ne touche donc QUE les deux familles ci-dessous, identifiées une par
une. Aucune heuristique « même hôte donc doublon » : elle se tromperait sur la
majorité des cas.

RÈGLE `allocine` — la fiche et ses onglets
-------------------------------------------
AlloCiné sert la même œuvre sous deux URL portant le MÊME identifiant :

    https://www.allocine.fr/film/fichefilm_gen_cfilm=6608.html   ← la fiche
    https://www.allocine.fr/film/fichefilm-6608/telecharger-vod/ ← un onglet

L'onglet n'est qu'une section de la fiche. On garde la fiche : le visiteur y
accède à tout le reste, l'inverse n'est pas vrai. Le rapprochement se fait sur
l'IDENTIFIANT, jamais sur le titre.

RÈGLE `editions` — deux éditions du même livre
-----------------------------------------------
Un même ouvrage listé deux fois chez Place des Libraires, en grand format et en
poche. La règle est une TABLE CURÉE À LA MAIN (`EDITIONS`), pas une heuristique
de prix : le moins cher est presque toujours le poche, mais « presque » ne
suffit pas quand deux ISBN peuvent désigner deux TRADUCTIONS différentes.

C'est le cas du Tao Te King (`ubm-1145`), volontairement ABSENT de la table :
Folio Sagesses et Quadrige sont deux traductions, et n'en garder qu'une revient
à choisir un traducteur — un acte éditorial, pas un nettoyage de doublon.

Usage :
    python fix_duplicate_links.py                       # dry-run, les 2 règles
    python fix_duplicate_links.py --rule allocine --apply
"""
from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from typing import Any

import dataset_fixes
from dataset_fixes import Change, add_common_args, run

__all__ = ["EDITIONS", "RULES", "allocine_key", "transform_factory"]

#: Fiche canonique : `…_gen_cfilm=<id>.html`. C'est elle qu'on garde.
_RE_FICHE = re.compile(
    r"allocine\.fr/(?:film|series)/fiche(?:film|serie)_gen_c(?:film|serie)=(\d+)",
    re.IGNORECASE)
#: Onglet d'une fiche : `…/fichefilm-<id>/<section>/`. Redondant avec la fiche.
_RE_ONGLET = re.compile(
    r"allocine\.fr/(?:film|series)/fiche(?:film|serie)-(\d+)/[a-z-]+/?$",
    re.IGNORECASE)

#: ISBN à CONSERVER, par reco. Vérifié un par un chez Place des Libraires le
#: 2026-08-15 (collection + prix) : dans chaque cas, l'ISBN retenu est l'édition
#: de poche. Une reco absente de cette table n'est pas touchée.
EDITIONS: dict[str, str] = {
    "ubm-0392": "9791041425723",   # L'homme-dé — Points, 10,80 € (vs 20 €)
    "ubm-0760": "9782070360284",   # Voyage au bout de la nuit — Folio, 11,20 €
    "ubm-1158": "9782253907824",   # La Prochaine fois… — Livre de Poche, 8,40 €
    "ubm-1169": "9782253907824",   # idem, seconde reco du même livre
    "ubm-2741": "9782811218393",   # Blood Song — Bragelonne poche, 7,90 €
    "ubm-2850": "9782253162889",   # Mouchette — Livre de Poche, 9,70 €
    "ubm-2948": "9782290028599",   # Les Particules élémentaires — J'ai lu, 8,70 €
    # ABSENT À DESSEIN — ubm-1145 « Tao Te King » : Folio Sagesses et Quadrige
    # sont deux TRADUCTIONS, pas deux formats. Choisir relève de l'éditorial.
}

_RE_PDL_ISBN = re.compile(r"placedeslibraires\.fr/livre/(\d{13})", re.IGNORECASE)

RULES = ("allocine", "editions")


def allocine_key(url: str) -> tuple[str, str] | None:
    """`("fiche"|"onglet", identifiant)` si l'URL est une page d'œuvre AlloCiné.

    Une URL AlloCiné qui n'est ni l'une ni l'autre (page d'accueil, dossier,
    actualité) renvoie None et n'est jamais touchée.
    """
    if m := _RE_FICHE.search(url):
        return "fiche", m.group(1)
    if m := _RE_ONGLET.search(url):
        return "onglet", m.group(1)
    return None


def _rule_allocine(doc: dict[str, Any], liens: list[dict]) -> tuple[list[dict], list[Change]]:
    """Retire un onglet quand la FICHE du même identifiant est présente."""
    fiches = {k[1] for link in liens
              if (k := allocine_key(link.get("url") or "")) and k[0] == "fiche"}
    garder, changes = [], []
    for link in liens:
        cle = allocine_key(link.get("url") or "")
        if cle and cle[0] == "onglet" and cle[1] in fiches:
            changes.append(Change(field="links[].url", before=link["url"], after=None))
            continue
        garder.append(link)
    return garder, changes


def _rule_editions(doc: dict[str, Any], liens: list[dict]) -> tuple[list[dict], list[Change]]:
    """Ne garde que l'ISBN retenu, pour les recos listées dans `EDITIONS`."""
    isbn_garde = EDITIONS.get(doc.get("id") or "")
    if not isbn_garde:
        return liens, []
    # Ne rien supprimer si l'ISBN attendu n'est PAS là : la donnée a changé
    # depuis la vérification, et la table doit être revue avant d'agir.
    presents = {m.group(1) for link in liens
                if (m := _RE_PDL_ISBN.search(link.get("url") or ""))}
    if isbn_garde not in presents or len(presents) < 2:
        return liens, []
    garder, changes = [], []
    for link in liens:
        m = _RE_PDL_ISBN.search(link.get("url") or "")
        if m and m.group(1) != isbn_garde:
            changes.append(Change(field="links[].url", before=link["url"], after=None))
            continue
        garder.append(link)
    return garder, changes


_IMPLS = {"allocine": _rule_allocine, "editions": _rule_editions}


def transform_factory(rules: Sequence[str]):
    """Construit la transformation pour les règles demandées."""
    impls = [_IMPLS[r] for r in rules]

    def transform(doc: dict[str, Any]) -> list[Change]:
        liens = [link for link in (doc.get("links") or []) if isinstance(link, dict)]
        autres = [link for link in (doc.get("links") or []) if not isinstance(link, dict)]
        changes: list[Change] = []
        for impl in impls:
            liens, ch = impl(doc, liens)
            changes.extend(ch)
        if changes:
            doc["links"] = autres + liens if autres else liens
        return changes

    return transform


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Retire les liens redondants d'une même reco.")
    add_common_args(parser)
    parser.add_argument("--rule", action="append", choices=RULES,
                        help="Règle à appliquer (répétable). Défaut : toutes.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - E/S
    args = build_parser().parse_args(argv)
    rules = args.rule or list(RULES)
    run(transform_factory(rules), args,
        roots=(dataset_fixes.RECOS_DIR,), extra_report={"rules": rules})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
