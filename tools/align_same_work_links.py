"""
align_same_work_links.py — même œuvre, mêmes liens.

LE PROBLÈME
-----------
Une même œuvre recommandée dans plusieurs épisodes n'a pas les mêmes liens
d'un épisode à l'autre : « The Office » renvoie à Netflix ici, à Prime Video
là ; « Orelsan » à Spotify dans une reco, à Deezer dans une autre. Aucun de
ces liens n'est faux — mais le visiteur reçoit une expérience différente selon
la page où il tombe, et la reco la plus pauvre le prive de ce que la plus riche
lui offrait. Constaté le 2026-08-16 sur 79 groupes de titres.

CE QU'ON FAIT
-------------
Pour chaque groupe d'œuvres identiques, chaque reco reçoit l'UNION des liens du
groupe. Union et non « la plus riche écrase les autres » : personne ne perd un
lien qu'il était seul à porter.

DEUX ŒUVRES PEUVENT PARTAGER UN TITRE
--------------------------------------
C'est le risque de ce module, et il est réel : « Happy End » désigne un ALBUM
d'Albin de la Simone et un PODCAST de Blandine Lehout. Fusionner leurs liens
enverrait l'auditeur d'un podcast vers un album qui n'a rien à voir.

Quatre garde-fous, cumulatifs :
  - **titre trop court** → ignoré, un titre de trois lettres se répète par
    hasard ;
  - **types incompatibles** → groupe ignoré (c'est ce qui sauve « Happy End ») ;
  - **créateurs incompatibles** → groupe ignoré. Deux noms différents et non
    vides sur un même titre désignent probablement deux œuvres. La comparaison
    est faite sur la forme repliée, sans quoi une simple différence d'accent
    ferait renoncer à un groupe légitime ;
  - **identifiants contradictoires** → groupe ignoré. Le seul qui repose sur un
    FAIT et non sur une ressemblance : deux fiches AlloCiné, IMDb, TMDB, Deezer
    ou Spotify d'identifiants différents ne peuvent pas être la même œuvre.

Ce quatrième garde-fou a été ajouté APRÈS une régression : « Bref » (2011,
Canal+) et « Bref.2 » (2025, Disney+) partagent le titre ET le créateur. Les
trois premiers garde-fous les ont laissés passer, et la reco de Bref.2 a reçu
les fiches de la série de 2011. Le titre ne suffit pas à identifier une œuvre ;
un identifiant, si.

Le rapport liste les groupes ÉCARTÉS avec leur motif : c'est là qu'on relit le
travail, pas dans ceux qui sont passés.
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from typing import Any

import dataset_fixes
from common import read_json
from dataset_fixes import Change, add_common_args, iter_reco_files, run

__all__ = ["compatibles", "fold_titre", "grouper", "identifiants",
           "transform_factory"]

#: En deçà, un titre se répète par coïncidence (« Vu », « Art », « 60 »…).
TITRE_MINI = 4

#: Hôtes dont l'URL porte un IDENTIFIANT D'ŒUVRE stable. Deux identifiants
#: différents sur le même hôte désignent forcément deux œuvres — c'est un fait,
#: pas une heuristique, et c'est ce qui permet de distinguer « Bref » de
#: « Bref.2 » là où le titre et le créateur sont identiques.
#:
#: Netflix, Disney+ ou Prime Video en sont ABSENTS à dessein : deux de leurs
#: URL peuvent désigner deux saisons, ou deux pages, d'une même œuvre. On n'en
#: conclut donc rien.
_IDENTIFIANTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("allocine", re.compile(r"allocine\.fr/\w+/fiche\w+?[_-](?:gen_c\w+=)?(\d+)")),
    ("imdb", re.compile(r"imdb\.com/title/(tt\d+)")),
    ("tmdb", re.compile(r"themoviedb\.org/(movie|tv)/(\d+)")),
    ("deezer", re.compile(r"deezer\.com/(?:\w\w/)?(album|track|artist)/(\d+)")),
    ("spotify", re.compile(r"open\.spotify\.com/(?:intl-\w+/)?(album|track|artist)/(\w+)")),
)


def identifiants(doc: dict[str, Any]) -> dict[str, set[str]]:
    """`{hôte: {identifiants trouvés}}` pour une reco."""
    out: dict[str, set[str]] = defaultdict(set)
    for link in (doc.get("links") or []):
        if not isinstance(link, dict):
            continue
        url = link.get("url") or ""
        for nom, rx in _IDENTIFIANTS:
            m = rx.search(url)
            if m:
                out[nom].add("/".join(m.groups()))
    return out


def fold_titre(s: str | None) -> str:
    """Titre replié : sans diacritiques, sans ponctuation, casse repliée."""
    s = unicodedata.normalize("NFD", (s or "").strip().lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def compatibles(docs: Sequence[dict[str, Any]]) -> str | None:
    """`None` si le groupe désigne bien UNE œuvre, sinon le motif du refus."""
    types = [set(d.get("types") or ()) for d in docs]
    if any(not t for t in types):
        return "une reco sans type"
    if not set.intersection(*types):
        return "types disjoints — probablement deux œuvres homonymes"
    createurs = sorted({fold_titre(d.get("creator")) for d in docs} - {""})
    # Un nom CONTENU dans un autre n'est pas un autre nom : c'est la même
    # œuvre créditée plus ou moins complètement. « patrick » ⊂ « patrick
    # baud » est une fiche incomplète ; « greg daniels » ⊂ « greg daniels
    # michael schur » est un co-créateur ajouté. Refuser ces groupes privait
    # d'alignement des œuvres évidentes (Bref, Better Call Saul, The Office).
    # C'est le TITRE identique qui rend cette tolérance sûre : sans lui, une
    # inclusion de noms ne prouverait rien.
    for a in createurs:
        if not all(a in b or b in a for b in createurs):
            return f"créateurs différents : {createurs}"
    # Dernier garde-fou, et le seul qui repose sur un FAIT plutôt qu'une
    # ressemblance : deux fiches d'identifiants différents chez le même
    # fournisseur ne peuvent pas désigner la même œuvre.
    par_hote: dict[str, set[str]] = defaultdict(set)
    for d in docs:
        for hote, ids in identifiants(d).items():
            par_hote[hote] |= ids
    for hote, ids in sorted(par_hote.items()):
        if len(ids) > 1:
            return f"identifiants {hote} contradictoires : {sorted(ids)}"
    return None


def grouper(docs: Sequence[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Regroupe par titre replié, en ne gardant que les groupes de 2 et plus."""
    par: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in docs:
        t = fold_titre(d.get("title"))
        if len(t) >= TITRE_MINI:
            par[t].append(d)
    return {t: ds for t, ds in par.items() if len(ds) > 1}


def _liens_valides(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return [link for link in (doc.get("links") or [])
            if isinstance(link, dict) and link.get("url")]


def transform_factory(cibles: dict[str, list[dict[str, Any]]],
                      rapport: dict[str, Any]):
    """`cibles` : {id de reco: liens à poser}. Calculé en amont, sur tout le
    corpus — une transformation ne voit qu'un document à la fois."""
    def transform(doc: dict[str, Any]) -> list[Change]:
        voulus = cibles.get(doc.get("id") or "")
        if not voulus:
            return []
        actuels = [link["url"] for link in _liens_valides(doc)]
        if actuels == [link["url"] for link in voulus]:
            return []
        doc["links"] = [dict(link) for link in voulus]
        return [Change(field="links", before=actuels,
                       after=[link["url"] for link in voulus])]
    return transform


def planifier(source: str | None = None) -> tuple[dict, dict]:
    """Calcule ce que chaque reco devrait porter, et pourquoi.

    Renvoie `(cibles, rapport)`. Ne lit que les recos ACTIVES : aligner une
    reco écartée n'apporte rien, elle ne s'affiche nulle part.
    """
    docs = []
    for path in iter_reco_files(source, (dataset_fixes.RECOS_DIR,)):
        try:
            d = read_json(path)
        except (OSError, ValueError):
            continue
        if d.get("status") == "validated" and d.get("id"):
            docs.append(d)

    cibles: dict[str, list[dict[str, Any]]] = {}
    ecartes: list[dict[str, Any]] = []
    alignes: list[dict[str, Any]] = []
    for _titre, groupe in sorted(grouper(docs).items()):
        motif = compatibles(groupe)
        if motif:
            ecartes.append({"titre": groupe[0].get("title"), "motif": motif,
                            "ids": [d["id"] for d in groupe]})
            continue
        # Union, dans l'ordre de première apparition : l'ordre des liens porte
        # une intention éditoriale (l'indépendant avant le grand distributeur),
        # et un tri alphabétique la détruirait.
        union: dict[str, dict[str, Any]] = {}
        for d in groupe:
            for link in _liens_valides(d):
                union.setdefault(link["url"], link)
        if len(union) < 2:
            continue
        voulus = list(union.values())
        touches = [d["id"] for d in groupe
                   if [link["url"] for link in _liens_valides(d)] != list(union)]
        if not touches:
            continue
        for rid in touches:
            cibles[rid] = voulus
        alignes.append({"titre": groupe[0].get("title"), "liens": len(union),
                        "recos": touches})
    return cibles, {"alignes": alignes, "ecartes": ecartes}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Donne les mêmes liens à toutes les recos d'une même œuvre.")
    add_common_args(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - E/S
    args = build_parser().parse_args(argv)
    cibles, rapport = planifier(args.source)
    run(transform_factory(cibles, rapport), args,
        roots=(dataset_fixes.RECOS_DIR,), extra_report=rapport)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
