"""
fix_reco_anomalies.py — corrections ponctuelles, vérifiées une par une.

Chaque ligne de `CORRECTIONS` a été lue AVEC SA CITATION avant d'être écrite :
c'est la parole de l'épisode qui dit ce que la reco désigne, pas le type qu'un
script a deviné ni l'hôte du lien. Aucune heuristique ici — une table curée, et
un motif `attendu` qui refuse d'écrire si la donnée a changé depuis la
vérification.

ORIGINE (audit du 2026-08-16)
-----------------------------
Un croisement type ↔ hôte du lien sur les 1209 recos actives a relevé 78
contradictions. La plupart sont LÉGITIMES — un spectacle filmé sur YouTube, une
bande originale sur Bandcamp — et ne sont pas touchées. Restent les cas où le
type contredit ce que la reco dit d'elle-même.

Le cas fondateur est `ubm-1531` : la reco pointait le site d'un chef étoilé
belge et son restaurant, alors qu'elle parle du vulgarisateur YouTube du même
nom. Deux personnes distinctes, confondues par un homonyme.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse

import dataset_fixes
from dataset_fixes import Change, add_common_args, run

__all__ = ["CLES_EFFET", "CORRECTIONS", "transform"]

# La table vit dans son propre module : elle pesait 1311 des 1533 lignes
# de ce fichier. Reexportee ci-dessous pour que les appelants et les tests
# qui lisent `fix_reco_anomalies.CORRECTIONS` continuent de fonctionner.
from corrections_reco_anomalies import CLES_EFFET, CORRECTIONS


def _hote(url: Any) -> str:
    """Hôte d'une URL, sans `www.` ni casse. Vide si l'URL est illisible.

    Sert à ne pas ajouter deux fois la même plateforme : c'est l'hôte, et non
    l'URL entière, qui dit « Deezer est déjà là ».
    """
    try:
        return (urlparse(str(url)).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _replier(valeur: Any) -> str:
    """Forme comparable d'un alias : les alias sont saisis à la main, et
    « Bref 2 », « bref 2 » et « bref 2  » désignent la même chose."""
    return " ".join(str(valeur).split()).casefold()


def transform(doc: dict[str, Any]) -> list[Change]:
    """Applique la correction curée de cette reco, si l'état d'avant correspond."""
    fix = CORRECTIONS.get(doc.get("id") or "")
    if not fix:
        return []
    # Garde : la donnée a-t-elle bougé depuis la vérification manuelle ?
    #
    # Les listes sont comparées SANS ordre (`types` n'a pas d'ordre porteur de
    # sens), les autres valeurs telles quelles. Trier une chaîne comparerait
    # ses caractères : « Anis Rallye » et « Riens Allaye » passeraient pour
    # identiques, et la garde laisserait écrire sur une donnée qui a changé.
    attendu = fix.get("attendu") or {}
    for champ, valeur in attendu.items():
        actuel = doc.get(champ)
        if isinstance(valeur, list):
            if sorted(actuel or []) != sorted(valeur):
                return []
        elif actuel != valeur:
            return []
    changes: list[Change] = []
    if "types" in fix and sorted(doc.get("types") or []) != sorted(fix["types"]):
        changes.append(Change(field="types", before=doc.get("types"),
                              after=fix["types"]))
        doc["types"] = list(fix["types"])
    # Le TITRE est parfois une description (« Documentaire sur Orelsan ») là
    # où l'œuvre porte un nom. Le corriger change ce que le visiteur cherche.
    if "titre" in fix and doc.get("title") != fix["titre"]:
        changes.append(Change(field="title", before=doc.get("title"),
                              after=fix["titre"]))
        doc["title"] = fix["titre"]
    # La CITATION est ce qui justifie la reco aux yeux du lecteur. Quand
    # l'extraction capture la mauvaise phrase, la carte devient
    # incompréhensible : ubm-0219 affichait une phrase sur « Euphoria » au-
    # dessus d'une fiche « Empathie ». On ne la corrige QUE d'après le
    # transcript, jamais de mémoire.
    if "citation" in fix and doc.get("quote") != fix["citation"]:
        changes.append(Change(field="quote", before=doc.get("quote"),
                              after=fix["citation"]))
        doc["quote"] = fix["citation"]
    if "creator" in fix and doc.get("creator") != fix["creator"]:
        changes.append(Change(field="creator", before=doc.get("creator"),
                              after=fix["creator"]))
        if fix["creator"] is None:
            # RETIRER la clé, ne pas écrire `null` : la collection `recos`
            # déclare `creator: z.string().optional()` SANS `nullable`, et un
            # `null` y arrête le build. Cf. `fill_guest_creators`.
            doc.pop("creator", None)
        else:
            doc["creator"] = fix["creator"]
    # `recommendedBy` porte les mêmes fautes que `creator` — il vient parfois
    # de la même transcription. Le corriger ici plutôt que dans un outil à part
    # évite qu'une reco reste incohérente entre ses deux champs de personnes.
    if "recommande_par" in fix and doc.get("recommendedBy") != fix["recommande_par"]:
        changes.append(Change(field="recommendedBy",
                              before=doc.get("recommendedBy"),
                              after=fix["recommande_par"]))
        doc["recommendedBy"] = fix["recommande_par"]
    if "liens" in fix:
        avant = [link.get("url") for link in (doc.get("links") or [])
                 if isinstance(link, dict)]
        apres = [link["url"] for link in fix["liens"]]
        if avant != apres:
            changes.append(Change(field="links", before=avant, after=apres))
            doc["links"] = [dict(link) for link in fix["liens"]]
    # AJOUT de liens, sans toucher aux existants. Distinct de `liens`, qui
    # REDÉFINIT toute la liste : ici on complète une reco à qui il manque une
    # plateforme, sans risquer d'effacer un lien posé à la main.
    # Un lien dont l'hôte est DÉJÀ présent n'est jamais ajouté — sinon une
    # seconde exécution empilerait les doublons.
    if "ajouter_liens" in fix:
        existants = list(doc.get("links") or [])
        hotes = {_hote(link.get("url") or "") for link in existants
                 if isinstance(link, dict)}
        ajouts = [dict(link) for link in fix["ajouter_liens"]
                  if _hote(link["url"]) not in hotes]
        if ajouts:
            avant_urls = [link.get("url") for link in existants
                          if isinstance(link, dict)]
            doc["links"] = existants + ajouts
            changes.append(Change(
                field="links", before=avant_urls,
                after=[link.get("url") for link in doc["links"]
                       if isinstance(link, dict)]))
    # RETRAIT d'identifiants externes FAUX. Ils ne s'affichent nulle part —
    # et c'est précisément le danger : une passe d'enrichissement peut les
    # promouvoir en lien visible des mois plus tard. Un `externalIds.deezer`
    # posé sur un photographe finirait en lien d'écoute vers un homonyme.
    if "retirer_external_ids" in fix:
        ids = doc.get("externalIds")
        if isinstance(ids, dict):
            retires = {c: ids[c] for c in fix["retirer_external_ids"] if c in ids}
            if retires:
                for cle in retires:
                    del ids[cle]
                changes.append(Change(field="externalIds",
                                      before=retires, after=None))
                if not ids:
                    doc.pop("externalIds", None)
    # RETRAIT ciblé, par fragment d'URL. Distinct de `liens`, qui redéfinit
    # toute la liste : quand un seul lien est fautif parmi sept, redéfinir les
    # sept obligerait à tous les recopier dans la table — verbeux, et surtout
    # fragile, puisque la moindre évolution des six autres invaliderait
    # l'entrée sans qu'on s'en aperçoive.
    if "retirer_liens" in fix:
        garder = [link for link in (doc.get("links") or [])
                  if not (isinstance(link, dict)
                          and any(frag in (link.get("url") or "")
                                  for frag in fix["retirer_liens"]))]
        if len(garder) != len(doc.get("links") or []):
            avant = [link.get("url") for link in (doc.get("links") or [])
                     if isinstance(link, dict)]
            doc["links"] = garder
            changes.append(Change(
                field="links", before=avant,
                after=[link.get("url") for link in garder
                       if isinstance(link, dict)]))
    # RETRAIT d'alias. Un alias FAUX est plus nuisible qu'un alias manquant :
    # c'est lui que lisent les outils d'appariement, et il fait revenir l'erreur
    # à chaque passe. Sur ubm-1547, « bref 2 » a suffi pour attribuer la fiche
    # de « Bref.2 » (2025) à une reco parlant de « Bref » (2011).
    if "retirer_alias" in fix:
        indesirables = {_replier(a) for a in fix["retirer_alias"]}
        avant = list(doc.get("aliases") or [])
        garder = [a for a in avant if _replier(a) not in indesirables]
        if len(garder) != len(avant):
            changes.append(Change(field="aliases", before=avant, after=garder))
            # Pas de liste vide : l'absence d'alias et « aucun alias retenu »
            # doivent se lire de la même façon dans le fichier.
            if garder:
                doc["aliases"] = garder
            else:
                doc.pop("aliases", None)
    return changes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Corrige les recos dont le type contredit leur contenu.")
    add_common_args(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - E/S
    args = build_parser().parse_args(argv)
    run(transform, args, roots=(dataset_fixes.RECOS_DIR,),
        extra_report={"corrections": {k: v["pourquoi"]
                                      for k, v in CORRECTIONS.items()}})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
