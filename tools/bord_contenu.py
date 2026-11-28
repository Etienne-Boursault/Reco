"""bord_contenu.py — sorties à venir, graphies et liens morts du tableau de bord.

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 2, tranche 3c).

Une seule fonction, `lire`, pour le rendu. Elle ne lève jamais, ne touche pas le réseau et
lit des fichiers locaux seulement. Chaque partie illisible vaut `None` (« inconnu »), jamais
« aucun » (F22) ; chaque liste coupée donne son total (F23).

- `sorties` : les recos validées, de type servi, dont la `releaseDate` tombe entre J-30 et J+30
  (la fenêtre de relance de `date_sortie`, plus les 30 jours à venir). Tour 1, F4 : celles à venir
  (`jours > 0`) d'abord, la plus proche en tête, puis les passées, la plus récente en tête, pour que
  la coupe à `LISTE_MAX` ne noie pas les sorties à venir sous les passées. Les fichiers de recos qui ne se lisent pas sont comptés (`illisibles`), pas
  cachés. Un fichier sans le mot `releaseDate` n'est pas ouvert comme JSON : le dépôt compte
  plus de 3 000 recos et `/bord` se lit à chaque affichage.
- `graphies` : les 5 plus vues du registre et le nombre d'entrées. Un registre absent vaut
  « aucune » ; un registre qui existe sans se lire vaut « inconnu ».
- `liens` : le résumé que `verifier_liens.py` écrit sous `bord/liens.json`, avec l'âge du
  rapport. Au-delà de 8 jours il est « ancien » : le contrôle tourne chaque lundi.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

import bord_reseaux
import date_sortie
import graphies
import sorties_annoncees
import sorties_plan
from common import log, recos_dir_for

LISTE_MAX = 10
TITRE_MAX = 200
GRAPHIES_MAX = 5
AGE_ANCIEN = 8  # jours : le contrôle des liens tourne chaque lundi


def _sorties(source_id: str, maintenant: datetime) -> dict[str, Any] | None:
    dossier = recos_dir_for(source_id)
    if not dossier.is_dir():
        return None
    jour = date_sortie.jour_a_paris(maintenant)
    try:
        relancees: set[str] | None = set(
            sorties_plan.lire_etat(sorties_annoncees.etat_path())["relancees"])
    except sorties_plan.EtatIllisible:
        relancees = None
    trouvees: list[tuple[date, str, dict[str, Any]]] = []
    illisibles = 0
    for fichier in sorted(dossier.rglob("*.json")):
        try:
            texte = fichier.read_text(encoding="utf-8")
            if "releaseDate" not in texte:
                continue
            doc = json.loads(texte)
            sortie = _sortie_retenue(doc)
        except (OSError, ValueError):
            illisibles += 1
            continue
        if sortie is None or abs((sortie - jour).days) > date_sortie.FENETRE_JOURS:
            continue
        cle = sorties_plan.cle_de(doc)
        titre = doc.get("title")
        identifiant = str(doc.get("id") or fichier.stem)
        trouvees.append((sortie, identifiant, {
            "id": identifiant,
            "titre": (titre if isinstance(titre, str) and titre else identifiant)[:TITRE_MAX],
            "date": sortie.isoformat(), "jours": (sortie - jour).days,
            "relancee": None if relancees is None else cle in relancees}))
    trouvees.sort(key=lambda t: (0, t[2]["jours"], t[1]) if t[2]["jours"] > 0
                  else (1, -t[2]["jours"], t[1]))
    return {"liste": [t[2] for t in trouvees[:LISTE_MAX]], "total": len(trouvees),
            "illisibles": illisibles}


def _sortie_retenue(doc: Any) -> date | None:
    """La date de sortie d'une reco validée de type servi, sinon None ; ValueError si pas un objet."""
    if not isinstance(doc, dict):
        raise ValueError("reco qui n'est pas un objet")
    if doc.get("status") != "validated" or not date_sortie.type_servi(doc.get("types") or []):
        return None
    try:
        return date_sortie.analyser_date_sortie(doc.get("releaseDate"))
    except date_sortie.DateSortieInvalide:
        return None


def _graphies() -> dict[str, Any] | None:
    try:
        entrees, ecartees = graphies._lire()  # `charger` cache la panne en liste vide (F22)
    except graphies.RegistreIllisible:
        return None
    entrees = sorted(entrees, key=lambda e: (-e["vu"], e["fausse"]))
    return {"total": len(entrees), "ecartees": len(ecartees),
            "plus_vues": [{"fausse": e["fausse"], "juste": e["juste"], "vu": e["vu"]}
                          for e in entrees[:GRAPHIES_MAX]]}


def _entier(valeur: Any) -> bool:
    return isinstance(valeur, int) and not isinstance(valeur, bool)


def _liens(maintenant: datetime) -> dict[str, Any] | None:
    try:
        brut = json.loads((bord_reseaux.dossier() / "liens.json").read_text(encoding="utf-8"))
        jour_rapport = date.fromisoformat(brut["date"])
        comptes = {c: brut[c] for c in ("morts", "nouveaux", "inconnus", "vivants")}
        liste = [{"url": m["url"], "reponse": m["reponse"], "recos": m["recos"]}
                 for m in brut["liste"]]
    except (OSError, ValueError, KeyError, TypeError):  # absent, abîmé ou de forme fausse
        return None
    if not (all(_entier(v) for v in comptes.values())
            and all(isinstance(m["url"], str) and isinstance(m["reponse"], str)
                    and isinstance(m["recos"], list) for m in liste)):
        return None
    age = (maintenant.astimezone(UTC).date() - jour_rapport).days
    return {"date": jour_rapport.isoformat(), "age": age, "ancien": age > AGE_ANCIEN,
            **comptes, "liste": liste}


def lire(source_id: str, *, maintenant: datetime | None = None) -> dict[str, Any]:
    """`{"sorties": …, "graphies": …, "liens": …}` ; une partie illisible vaut `None`."""
    instant = maintenant or datetime.now(UTC)
    parties = {"sorties": lambda: _sorties(source_id, instant), "graphies": _graphies,
               "liens": lambda: _liens(instant)}
    resultat: dict[str, Any] = {}
    for nom, lecture in parties.items():
        try:
            resultat[nom] = lecture()
        except Exception as exc:  # noqa: BLE001 — une partie ne fait jamais tomber `/bord`
            log.warning("tableau de bord : %s illisible (%s : %s)", nom, type(exc).__name__, exc)
            resultat[nom] = None
    return resultat
