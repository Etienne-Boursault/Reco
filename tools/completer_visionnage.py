"""
completer_visionnage.py — repose les liens de visionnage manquants.

LE MANQUE
---------
124 documents portaient un identifiant TMDB valide sans aucun lien de
visionnage : ni `externalIds.watchPage`, ni `watchProviders`. Leur page
d'oeuvre n'affichait qu'un lien « TMDB » nu — un renvoi vers une fiche, pas un
moyen de voir l'oeuvre.

Une partie de ces manques date du 2026-08-18 : en corrigeant les identifiants
qui designaient un homonyme, on a retire la page et les diffuseurs qui en
DERIVAIENT. C'etait juste — ils decrivaient l'autre oeuvre, « Drive »
annoncait les 19 diffuseurs de « Mulholland Drive » — mais rien ne les avait
reconstruits. Les autres n'avaient jamais ete enrichis.

CE QUI EST POSE
---------------
Ce que l'API TMDB donne pour la France, et rien d'autre :

  `externalIds.watchPage`  le champ `link` de `watch/providers`. C'est la page
                           qui liste les diffuseurs avec leurs VRAIS liens —
                           le seul lien de visionnage reellement direct que ce
                           projet puisse poser sans le fabriquer.
  `watchProviders`         les noms des diffuseurs, avec l'adresse que le
                           pipeline leur associe.

AUCUNE ADRESSE N'EST INVENTEE. Quand l'API ne connait pas de diffuseur
francais, rien n'est ecrit : mieux vaut une page sans lien qu'une page qui
promet un visionnage inexistant.

POURQUOI RE-UTILISER `enrich_tmdb`
-----------------------------------
`tmdb_watch_providers` fait deja exactement ce travail, y compris la
construction des adresses par plateforme. La redupliquer ici ferait diverger
les deux chemins : le jour ou l'une est corrigee, l'autre continuerait a poser
l'ancienne forme.
"""
from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import common  # type: ignore[attr-defined]

log = logging.getLogger("completer_visionnage")


def interroger(tmdb_id: str, kind: str, titre: str) -> tuple[str | None, list[dict]]:
    """Demande a TMDB la page de visionnage et les diffuseurs francais.

    Isolee dans sa propre fonction pour que les tests puissent la remplacer :
    la passe complete fait plus de cent appels reseau, qui n'ont rien a faire
    dans une suite de tests.
    """
    import os

    import requests  # import tardif : inutile quand la fonction est remplacee
    from dotenv import load_dotenv

    from enrich_tmdb import tmdb_watch_providers  # type: ignore[attr-defined]

    load_dotenv(common.TOOLS_DIR / ".env")
    cle = os.getenv("TMDB_API_KEY")
    if not cle:
        raise RuntimeError(
            "TMDB_API_KEY absent de tools/.env : sans clef, l'API repond 401 "
            "et l'oeuvre passerait pour « sans diffuseur ».")
    with requests.Session() as session:
        # `strict=True` est ESSENTIEL : sans lui, une erreur HTTP (401, 500,
        # coupure reseau) renvoie une reponse VIDE, que cette passe lirait
        # comme « aucun diffuseur francais ». Les documents seraient alors
        # marques traites sans l'avoir ete, et le manque deviendrait
        # invisible. Le premier essai s'y est laisse prendre : trois oeuvres
        # comptees « sans diffuseur » alors que la clef n'etait pas chargee.
        return tmdb_watch_providers(session, tmdb_id, kind, titre,
                                    api_key=cle, strict=True)


def _pour_collection(diffuseurs: list[dict], collection: str) -> list[dict]:
    """Renomme le champ porteur du nom selon la collection visee.

    ASYMETRIE DES DEUX SCHEMAS : `content.config.ts` declare
    `watchProviders[].name` cote ITEM et `[].label` cote RECO. Le pipeline
    produit `label` ; l'ecrire tel quel dans un item ARRETE le build, ce qui
    est arrive le 2026-08-18 sur l'item 05d956f0.

    On convertit plutot que d'uniformiser les schemas : la divergence est
    ancienne et touche des centaines de fichiers des deux cotes.
    """
    if collection != "items":
        return diffuseurs
    convertis = []
    for d in diffuseurs:
        copie = dict(d)
        if "label" in copie:
            copie["name"] = copie.pop("label")
        convertis.append(copie)
    return convertis


def _candidats() -> list[tuple[Path, dict[str, Any], str]]:
    """Les documents a completer : un identifiant TMDB, aucun lien de visionnage."""
    out: list[tuple[Path, dict[str, Any], str]] = []
    for racine, collection in ((common.ITEMS_DIR, "items"),
                               (common.RECOS_DIR, "recos")):
        for chemin in sorted(racine.rglob("*.json")):
            try:
                doc = json.loads(chemin.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            # Une reco ecartee ne s'affiche nulle part : l'enrichir depenserait
            # une requete pour rien.
            if collection == "recos" and doc.get("status") == "discarded":
                continue
            ext = doc.get("externalIds")
            if not isinstance(ext, dict):
                continue
            # Le TYPE est aussi necessaire que le numero : sans lui on ne sait
            # pas quelle route interroger, et se tromper renverrait les
            # diffuseurs d'une autre oeuvre.
            if not ext.get("tmdb") or not ext.get("tmdbType"):
                continue
            # Un manque, c'est l'absence de la page OU celle des diffuseurs.
            # Ne tester que la page laissait « Drive » a trois liens : sa page
            # avait ete reconstruite par le correctif des identifiants, mais
            # ses diffuseurs, eux, n'etaient jamais revenus.
            if ext.get("watchPage") and doc.get("watchProviders"):
                continue
            out.append((chemin, doc, collection))
    return out


def executer(*, apply: bool, limite: int | None = None) -> dict[str, Any]:
    """Complete les documents candidats. Renvoie un rapport chiffre."""
    candidats = _candidats()
    if limite is not None:
        candidats = candidats[:limite]
    completes = vides = echecs = 0
    for chemin, doc, collection in candidats:
        ext = doc["externalIds"]
        try:
            page, diffuseurs = interroger(str(ext["tmdb"]), str(ext["tmdbType"]),
                                          doc.get("title") or "")
        except Exception as erreur:  # noqa: BLE001 - une panne ne doit rien casser
            echecs += 1
            log.warning("%s « %s » : %s", doc.get("id"), doc.get("title"), erreur)
            continue
        if not page:
            # Pas de diffuseur francais connu : on n'ecrit rien plutot que de
            # promettre un visionnage inexistant.
            vides += 1
            continue
        completes += 1
        log.info("%s « %s » : %d diffuseur·s", doc.get("id"), doc.get("title"),
                 len(diffuseurs))
        if not apply:
            continue
        ext["watchPage"] = page
        if diffuseurs:
            doc["watchProviders"] = _pour_collection(diffuseurs, collection)
        chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return {"a_completer": len(candidats), "completes": completes,
            "sans_diffuseur": vides, "echecs": echecs}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repose `watchPage` et `watchProviders` sur les documents "
                    "qui ont un identifiant TMDB sans lien de visionnage.")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    parser.add_argument("--limit", type=int, default=None,
                        help="s'arrete apres N documents (pour essayer)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rapport = executer(apply=args.apply, limite=args.limit)
    log.info("%d candidat·s, %d complete·s, %d sans diffuseur francais, %d echec·s",
             rapport["a_completer"], rapport["completes"],
             rapport["sans_diffuseur"], rapport["echecs"])
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
