"""review_curation.py — Sidecar des annotations de curation (/tableau).

Le tableau de pilotage laisse poser, sur chaque reco, un **commentaire libre**
et une **coche de validation**. Ce sont des marques de *passe de curation*, pas
de la donnée de site : les écrire dans les ~3000 JSON de recos polluerait le
contenu, imposerait une migration du schéma Zod et partirait dans le build
Astro. On les range donc à côté, comme le dépôt le fait déjà ailleurs
(ADR 0015) :

    tools/output/curation/<source>.json   →   {recoId: {comment, checked, updatedAt}}

**Concurrence.** Le serveur est mono-thread et tient le verrou serveur pour
toute sa vie (cf. `review_lock`) : aucun script pipeline n'écrit en parallèle.
Restent les *deux onglets* du navigateur. Chaque écriture est donc un
read-modify-write qui relit le fichier, ne touche QUE les champs fournis de la
reco visée, puis réécrit ATOMIQUEMENT (tmp + fsync + replace, via
`write_json_if_changed`). Conséquence : une annotation posée dans l'onglet A
n'est jamais effacée par une écriture de l'onglet B — ni sur une autre reco, ni
sur l'autre champ de la même reco.

Ce module ne fait QUE de l'I/O sidecar : aucune reco n'est mutée ici.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from common import OUTPUT_DIR, log, slugify, write_json_if_changed

__all__ = [
    "CURATION_DIR",
    "MAX_COMMENT_LEN",
    "TYPE_PROPOSALS_PATH",
    "curation_path",
    "load_curation",
    "load_type_proposals",
    "set_annotation",
]

#: Dossier des sidecars — sous `tools/output/`, donc hors `src/content/` et
#: hors du build. Variable module (et non constante inlinée) pour rester
#: monkeypatchable en test.
CURATION_DIR: Path = OUTPUT_DIR / "curation"

#: Propositions de reclassement produites par la passe « types » (facultatif :
#: le fichier peut ne pas exister — cf. `load_type_proposals`).
TYPE_PROPOSALS_PATH: Path = OUTPUT_DIR / "types_proposes.json"

#: Garde-fou : un commentaire de curation est une note, pas un article. Borne
#: la taille du sidecar même si quelqu'un colle un transcript entier.
MAX_COMMENT_LEN: int = 2000

#: Entrée neutre — sert de base au read-modify-write et de valeur de repli.
_EMPTY: dict = {"comment": "", "checked": False, "updatedAt": ""}


def curation_path(source_id: str) -> Path:
    """Chemin du sidecar d'une source.

    `slugify` neutralise tout `source_id` hostile (`../`, séparateurs) : le
    fichier reste forcément DANS `CURATION_DIR`.
    """
    return CURATION_DIR / f"{slugify(source_id)}.json"


def _now_iso() -> str:
    """Horodatage UTC explicite, à la seconde (« 2026-07-31T10:00:00+00:00 »).

    Le fuseau est épinglé à UTC à dessein : un `datetime.now()` naïf produit
    des horodatages incomparables d'une machine à l'autre.
    """
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _read_json(path: Path):
    """Charge un JSON, ou None si absent / illisible / corrompu."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("Fichier JSON illisible (%s) : %s — ignoré", path, exc)
        return None


def _normalize_entry(value) -> dict | None:
    """Normalise une entrée du sidecar, ou None si elle est inexploitable.

    Tolérant par construction : le fichier peut avoir été édité à la main.
    """
    if not isinstance(value, dict):
        return None
    comment = value.get("comment")
    updated = value.get("updatedAt")
    return {
        "comment": (comment.strip()[:MAX_COMMENT_LEN]
                    if isinstance(comment, str) else ""),
        "checked": bool(value.get("checked")),
        "updatedAt": updated if isinstance(updated, str) else "",
    }


def load_curation(source_id: str) -> dict[str, dict]:
    """Annotations d'une source : `{recoId: {comment, checked, updatedAt}}`.

    Renvoie `{}` si le sidecar n'existe pas encore (cas normal au premier
    passage) ou s'il est illisible — jamais d'exception : la page de
    relecture doit s'afficher même avec un sidecar cassé.
    """
    raw = _read_json(curation_path(source_id))
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for rid, value in raw.items():
        entry = _normalize_entry(value)
        if entry is not None:
            out[str(rid)] = entry
    return out


def set_annotation(source_id: str, reco_id: str, *,
                   comment: str | None = None,
                   checked: bool | None = None) -> dict:
    """Pose commentaire et/ou coche sur une reco. Renvoie l'entrée résultante.

    Les paramètres à `None` ne sont PAS touchés : c'est ce qui rend deux
    onglets inoffensifs l'un pour l'autre (la coche d'un onglet n'écrase pas
    le commentaire de l'autre). Une entrée redevenue vide (pas de commentaire,
    pas de coche) est retirée du fichier plutôt que stockée à blanc.
    """
    data = load_curation(source_id)  # relecture disque à CHAQUE écriture
    entry = dict(data.get(reco_id) or _EMPTY)
    if comment is not None:
        entry["comment"] = comment.strip()[:MAX_COMMENT_LEN]
    if checked is not None:
        entry["checked"] = bool(checked)
    entry["updatedAt"] = _now_iso()
    if entry["comment"] or entry["checked"]:
        data[reco_id] = entry
    else:
        data.pop(reco_id, None)
    write_json_if_changed(curation_path(source_id), data)
    return entry


# ---- Propositions de reclassement de types (facultatif) ---------------------
#: Clés où chercher les types proposés, par ordre de préférence. Les variantes
#: françaises sont là parce que la passe de reclassement écrit son rapport en
#: français : dépendre d'un alias anglais qu'elle ajoute par courtoisie ferait
#: silencieusement disparaître la colonne le jour où il saute.
_TYPES_KEYS: tuple[str, ...] = ("types", "typesProposes", "type")
_REASON_KEYS: tuple[str, ...] = ("reason", "why", "note", "justification")
#: Clés sous lesquelles une liste de propositions peut être encapsulée.
_LIST_KEYS: tuple[str, ...] = ("proposals", "propositions")
#: Niveau de confiance annoncé (« certain » / « inference ») et question
#: d'arbitrage éditorial quand le cas ne se tranche pas tout seul.
_CONFIDENCE_KEYS: tuple[str, ...] = ("confidence", "confiance")
_ARBITRAGE_KEYS: tuple[str, ...] = ("arbitrage",)


def _proposal_parts(value) -> tuple[list[str], str]:
    """(types, raison) depuis une valeur de proposition, quelle que soit sa forme.

    Formats acceptés : `"film"`, `["film"]`, `{"types": [...], "reason": ...}`,
    `{"type": "…"}`, `{"typesProposes": [...], "justification": "…"}`.
    """
    if isinstance(value, str):
        return [value], ""
    if isinstance(value, list):
        return [t for t in value if isinstance(t, str)], ""
    if not isinstance(value, dict):
        return [], ""
    types: list[str] = []
    for key in _TYPES_KEYS:
        raw = value.get(key)
        if isinstance(raw, str):
            types = [raw]
            break
        if isinstance(raw, list):
            types = [t for t in raw if isinstance(t, str)]
            break
    reason = next((value[k] for k in _REASON_KEYS
                   if isinstance(value.get(k), str)), "")
    return types, reason


def _proposals_as_mapping(raw):
    """Ramène les formes « liste » et « {proposals: [...]} » à un mapping id→valeur."""
    if isinstance(raw, dict):
        for key in _LIST_KEYS:
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break
    if isinstance(raw, list):
        return {item["id"]: item for item in raw
                if isinstance(item, dict) and item.get("id")}
    return raw if isinstance(raw, dict) else {}


def _str_field(value, keys: tuple[str, ...]) -> str:
    """Premier champ texte trouvé parmi `keys` (chaîne vide si aucun)."""
    if not isinstance(value, dict):
        return ""
    return next((value[k] for k in keys if isinstance(value.get(k), str)), "")


def load_type_proposals(path: Path | None = None) -> dict[str, dict]:
    """Propositions de reclassement, par reco.

    Chaque entrée : `{"types": [...], "reason": str, "confidence": str,
    "arbitrage": str}`.

    **`types` est un REMPLACEMENT complet du champ `types` de la reco**, pas un
    ajout : `["autre", "serie"] → ["serie"]` veut dire « retirer autre ». Le
    rendu comme l'écriture doivent s'y tenir, sinon on comprend l'inverse de ce
    qui est proposé.

    Renvoie `{}` si le fichier n'existe pas — c'est le cas nominal tant que la
    passe « types » n'a pas tourné, et le tableau doit s'afficher sans lui.
    """
    raw = _proposals_as_mapping(_read_json(path or TYPE_PROPOSALS_PATH))
    out: dict[str, dict] = {}
    for rid, value in raw.items():
        types, reason = _proposal_parts(value)
        if types:
            out[str(rid)] = {
                "types": types,
                "reason": reason,
                "confidence": _str_field(value, _CONFIDENCE_KEYS),
                "arbitrage": _str_field(value, _ARBITRAGE_KEYS),
            }
    return out
