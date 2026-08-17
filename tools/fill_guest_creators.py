"""
fill_guest_creators.py — déduit le créateur d'une œuvre présentée par son auteur.

LE PROBLÈME
    27 recommandations portent `guestWork: true` — « c'est l'œuvre de la
    personne qui en parle » — mais leur champ `creator` est vide. La carte
    affichait alors une étoile sans nom à qualifier : un signe qui pose une
    question sans donner de quoi y répondre.

    Masquer l'étoile aurait été traiter le symptôme. L'information EXISTE :
    `guestWork` dit que l'auteur est dans `recommendedBy`.

LA RÈGLE, ET SES LIMITES
    `recommendedBy` mêle les ANIMATEURS de l'émission et les INVITÉS
    (« Kyan Khojandi & Clément Cotentin »). Les animateurs sont déclarés par la
    source (`hosts`) : on les retire, et il reste l'invité.

        un seul invité       → c'est lui l'auteur
        aucun invité         → l'œuvre est celle des animateurs eux-mêmes,
                               qui la présentent (« Bref 2 », « Une Bonne
                               Soirée ») : on garde `recommendedBy` tel quel
        plusieurs invités    → ON NE TRANCHE PAS

    Ce dernier cas est le cœur de l'outil : deux invités, et rien dans la
    donnée ne dit lequel des deux a écrit l'œuvre. Deviner produirait une
    attribution fausse — exactement le défaut qu'on répare. Ces recos sont
    listées pour arbitrage humain.

    Un `creator` DÉJÀ renseigné n'est jamais réécrit : l'outil comble, il ne
    corrige pas.

Usage :
    python fill_guest_creators.py                      # dry-run (défaut)
    python fill_guest_creators.py --json rapport.json  # détail machine
    python fill_guest_creators.py --apply              # écrit
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections.abc import Sequence
from functools import cache
from pathlib import Path
from typing import Any

from common import CONTENT_DIR, log
from dataset_fixes import Change, add_common_args, run

#: Séparateurs employés dans `recommendedBy` — relevés sur le corpus :
#: « A & B », « A, B », « A et B ».
_SEPARATEURS = re.compile(r"\s*(?:&|,|\bet\b)\s*", re.IGNORECASE)

#: Recos écartées faute de pouvoir trancher (remplie par `transform`, lue par
#: le rapport). Variable de module pour rester inspectable en test.
AMBIGUS: list[dict[str, Any]] = []


def sources_dir() -> Path:
    """Résolu à L'APPEL, jamais figé à l'import.

    Une constante de module a déjà résisté au monkeypatch d'une suite de tests,
    qui a modifié 29 fichiers du vrai corpus en croyant travailler dans un
    dossier temporaire.
    """
    return CONTENT_DIR / "sources"


def fold(valeur: Any) -> str:
    """Forme comparable : sans diacritiques, casse repliée, espaces normalisés."""
    if not isinstance(valeur, str):
        return ""
    decompose = unicodedata.normalize("NFD", valeur)
    sans_accents = "".join(c for c in decompose
                           if unicodedata.category(c) != "Mn")
    return " ".join(sans_accents.lower().split())


@cache
def _hosts_bruts(chemin: str) -> tuple[str, ...]:
    try:
        data = json.loads(Path(chemin).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    return tuple(h for h in (data.get("hosts") or []) if isinstance(h, str))


def hosts_de(source_id: str) -> set[str]:
    """Animateurs d'une source, repliés. Vide si la source est introuvable.

    Sans animateurs connus, TOUS les noms de `recommendedBy` passent pour des
    invités : l'outil devient alors plus prudent, pas plus hasardeux — deux
    noms donnent un cas ambigu, donc écarté.
    """
    return {fold(h) for h in _hosts_bruts(str(sources_dir() / f"{source_id}.json"))}


def personnes(recommended_by: Any) -> list[str]:
    """Découpe `recommendedBy` en noms individuels, dans l'ordre."""
    if not isinstance(recommended_by, str):
        return []
    return [p.strip() for p in _SEPARATEURS.split(recommended_by) if p.strip()]


def invites(recommended_by: Any, hosts: set[str]) -> list[str]:
    """Les noms de `recommendedBy` qui ne sont pas des animateurs."""
    return [p for p in personnes(recommended_by) if fold(p) not in hosts]


def source_id_de(reco: dict[str, Any]) -> str:
    """`sourceId` est tantôt une chaîne, tantôt une référence `{id: …}`."""
    brut = reco.get("sourceId")
    if isinstance(brut, dict):
        brut = brut.get("id")
    return brut if isinstance(brut, str) else ""


def createur_deduit(reco: dict[str, Any]) -> str | None:
    """Le créateur déductible, ou None s'il ne l'est pas.

    >>> createur_deduit({"guestWork": True, "recommendedBy": "Natoo",
    ...                  "sourceId": "inconnue"})
    'Natoo'
    """
    if not reco.get("guestWork"):
        return None
    if isinstance(reco.get("creator"), str) and reco["creator"].strip():
        return None                       # on comble, on ne corrige pas
    rb = reco.get("recommendedBy")
    if not isinstance(rb, str) or not rb.strip():
        return None
    gens = invites(rb, hosts_de(source_id_de(reco)))
    if len(gens) == 1:
        return gens[0]
    if not gens:
        # Que des animateurs : l'œuvre est la LEUR, et ils la présentent.
        return rb.strip()
    return None                           # plusieurs invités → arbitrage humain


def transform(reco: dict[str, Any]) -> list[Change]:
    """Renseigne `creator` quand il se déduit. Mute `reco` en place."""
    if not reco.get("guestWork"):
        return []
    if isinstance(reco.get("creator"), str) and reco["creator"].strip():
        return []
    createur = createur_deduit(reco)
    if createur is None:
        rb = reco.get("recommendedBy")
        gens = invites(rb, hosts_de(source_id_de(reco)))
        if len(gens) > 1:
            AMBIGUS.append({"id": reco.get("id"), "title": reco.get("title"),
                            "recommendedBy": rb, "invites": gens})
        return []
    reco["creator"] = createur
    return [Change(field="creator", before=None, after=createur)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Renseigne le `creator` des œuvres présentées par leur "
                    "auteur (`guestWork`) quand il se déduit de `recommendedBy`.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - E/S
    args = build_parser().parse_args(argv)
    AMBIGUS.clear()
    run(transform, args, extra_report=lambda _res: {"ambigus": AMBIGUS})
    if AMBIGUS:
        log.info("%d reco(s) à arbitrer À LA MAIN (plusieurs invités) :",
                 len(AMBIGUS))
        for cas in AMBIGUS:
            log.info("   %s · « %s » — invités : %s",
                     cas["id"], cas["title"], ", ".join(cas["invites"]))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
