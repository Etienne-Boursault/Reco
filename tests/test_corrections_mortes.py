"""Garde : aucune correction curée ne doit être MORTE.

POURQUOI CE FICHIER EXISTE — cinq incidents du 2026-08-17
---------------------------------------------------------
`fix_reco_anomalies.CORRECTIONS` associe à chaque reco un état ATTENDU (la
clé `attendu`) et des modifications à y appliquer. Si l'état attendu ne
correspond plus, l'entrée ne fait rien — et c'est voulu : une fois la
correction appliquée, la garde cesse naturellement de mordre.

Le problème est ailleurs. Une garde peut cesser de correspondre pour une tout
autre raison : parce qu'une AUTRE passe a modifié la reco entre-temps. L'entrée
devient alors muette alors que son travail n'est PAS fait, et son silence
ressemble en tout point à un succès. Cinq cas relevés le même jour :

    ubm-1547  redéfinissait la liste de liens pour écarter une fiche AlloCiné
              fautive ; la fiche partie, elle n'effaçait plus que trois liens
              corrects
    ubm-0279  gardait sur un `creator` déjà corrigé
    ubm-2861  attendait `types: [livre]` quand la reco porte `jeu` — son
              retrait de lien en double n'a JAMAIS tourné, et les deux
              adresses de l'éditeur étaient toujours là
    ubm-2892  garde devenue caduque après un changement de type
    ubm-0487  le titre corrigé, la garde a cessé de mordre — et la page
              générique `/spectacles`, qui doublonnait celle du spectacle,
              n'a jamais été retirée

Aucun test ne les voyait. Les quatre premiers ont été trouvés par hasard, en
butant sur des clés dupliquées. Le cinquième a été trouvé par ce fichier, à sa
toute première exécution.

CE QUE CE FICHIER VÉRIFIE EXACTEMENT
------------------------------------
Pas « la garde correspond-elle ? » — la réponse est non pour toute correction
déjà appliquée, et c'est sain. Mais bien : « la garde ne correspond pas ET
l'effet n'est pas réalisé ». Cette conjonction-là ne peut signifier qu'une
chose : l'entrée est morte sans avoir agi.
"""
from __future__ import annotations

import json

import pytest

import fix_reco_anomalies as fra
from common import CONTENT_DIR


def _recos() -> dict[str, dict]:
    out = {}
    for chemin in (CONTENT_DIR / "recos").rglob("*.json"):
        doc = json.loads(chemin.read_text(encoding="utf-8"))
        if doc.get("id"):
            out[doc["id"]] = doc
    return out


def _garde_correspond(doc: dict, attendu: dict) -> bool:
    """Même comparaison que `fix_reco_anomalies` : les listes hors ordre."""
    for champ, valeur in attendu.items():
        actuel = doc.get(champ)
        if isinstance(valeur, list):
            if sorted(actuel or []) != sorted(valeur):
                return False
        elif actuel != valeur:
            return False
    return True


def _urls(doc: dict) -> list[str]:
    return [lien.get("url") or "" for lien in (doc.get("links") or [])
            if isinstance(lien, dict)]


def _effets_non_realises(doc: dict, fix: dict) -> list[str]:
    """Ce que l'entrée voulait faire et qui n'est toujours pas fait."""
    restants = []
    if "types" in fix and sorted(doc.get("types") or []) != sorted(fix["types"]):
        restants.append(f"types encore {doc.get('types')}")
    if "titre" in fix and doc.get("title") != fix["titre"]:
        restants.append("titre non corrigé")
    if "creator" in fix:
        vise = fix["creator"]
        actuel = doc.get("creator")
        if (vise is None and "creator" in doc) or (vise is not None and actuel != vise):
            restants.append("creator non corrigé")
    if "recommande_par" in fix and doc.get("recommendedBy") != fix["recommande_par"]:
        restants.append("recommendedBy non corrigé")
    if "liens" in fix and _urls(doc) != [lien["url"] for lien in fix["liens"]]:
        restants.append("liste de liens non conforme")
    for fragment in fix.get("retirer_liens", ()):
        if any(fragment in url for url in _urls(doc)):
            restants.append(f"lien à retirer encore présent : {fragment}")
    for lien in fix.get("ajouter_liens", ()):
        if lien["url"] not in _urls(doc):
            restants.append(f"lien à ajouter absent : {lien['url'][:48]}")
    ids = doc.get("externalIds")
    if isinstance(ids, dict):
        for cle in fix.get("retirer_external_ids", ()):
            if cle in ids:
                restants.append(f"externalIds.{cle} encore présent")
    for alias in fix.get("retirer_alias", ()):
        if alias in (doc.get("aliases") or []):
            restants.append(f"alias encore présent : {alias}")
    return restants


def test_le_corpus_et_la_table_ne_sont_pas_vides():
    """Sans cette garde, le test ci-dessous passerait sur zéro entrée et
    annoncerait une table saine qu'il n'a jamais regardée."""
    assert len(_recos()) > 500
    assert len(fra.CORRECTIONS) > 50


@pytest.mark.parametrize("reco_id", sorted(fra.CORRECTIONS))
def test_aucune_correction_nest_muette_avec_du_travail_en_attente(reco_id):
    recos = _recos()
    doc = recos.get(reco_id)
    assert doc is not None, (
        f"« {reco_id} » n'existe dans aucune reco : l'entrée ne s'appliquera "
        f"jamais."
    )
    fix = fra.CORRECTIONS[reco_id]
    if _garde_correspond(doc, fix.get("attendu") or {}):
        return  # l'entrée peut encore agir : rien à signaler
    restants = _effets_non_realises(doc, fix)
    assert not restants, (
        f"« {reco_id} » : la garde `attendu` ne correspond plus À LA FOIS que "
        f"le travail reste à faire — l'entrée est morte sans avoir agi. "
        f"En attente : {restants}. "
        f"Réaccroche `attendu` à l'état courant de la reco."
    )
