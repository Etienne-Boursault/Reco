"""
modeles_llm.py — quel modele d'extraction, et quoi faire quand il disparait.

POURQUOI CE MODULE
------------------
Les fournisseurs retirent leurs modeles tous les quelques mois (OpenAI a
annonce en octobre 2026 le retrait de GPT-4o et GPT-4.1 pour janvier 2027). Le
modele etait ecrit en dur dans `extract_recos.py` : en changer demandait une
PR, et un retrait arretait la chaine de venus en plein episode.

Changer de modele n'est pourtant PAS automatique, et c'est voulu : mesure le
2026-09-17, Haiku proposait 13 recos deja ecartees, Sonnet en ratait un tiers,
Opus trouvait tout pour six fois le prix. Une bascule silencieuse changerait ce
que la chaine trouve. La machine surveille et prepare, l'humain tranche.

CE QU'IL FOURNIT
----------------
- `modele_extraction()` / `modele_secours()` : lus dans `RECO_MODELE_EXTRACTION`
  et `RECO_MODELE_SECOURS` (le `.env` de venus), avec un defaut ecrit ici.
  Changer de modele = changer une ligne du `.env`.
- `modele_introuvable(exc)` : l'erreur qui declenche le secours.
- `accepte_effort(modele)` : lu dans l'API des modeles quand on l'a interrogee
  (`noter_capacites`), sinon deduit du nom.
- `cout(modele, entree, sortie)` : tarifs publics, pour le banc d'essai.
- `veiller(...)` : une fois par semaine, signale un modele configure qui a
  disparu ou dont le retrait est annonce (`retires_at`, `deprecated_at` de
  l'API des modeles), ou un modele plus recent de la meme famille.
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

log = logging.getLogger("reco.modeles")

MODELE_EXTRACTION_DEFAUT = "claude-opus-5"
# Le successeur d'Opus 5 dans la meme gamme : le plus proche de ce qui a ete
# mesure, et moins cher (4 $ / 20 $ contre 5 $ / 25 $ par million de jetons).
MODELE_SECOURS_DEFAUT = "claude-opus-5-5"
ENV_MODELE = "RECO_MODELE_EXTRACTION"
ENV_SECOURS = "RECO_MODELE_SECOURS"
# Valeur de `RECO_MODELE_SECOURS` qui coupe le secours.
SANS_SECOURS = "aucun"

INTERVALLE_VEILLE = timedelta(days=7)

# Tarifs publics en dollars par million de jetons (entree, sortie), releves le
# 2026-10-22. Un modele absent donne un cout inconnu, jamais un cout faux.
PRIX: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.0, 5.0),
}

_NOM = re.compile(r"^claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?$")
# Ce que l'API des modeles a repondu pendant ce processus : prime sur le nom.
_CAPACITES_EFFORT: dict[str, bool] = {}


def modele_extraction(env: Mapping[str, str] = os.environ) -> str:
    return (env.get(ENV_MODELE) or "").strip() or MODELE_EXTRACTION_DEFAUT


def modele_secours(env: Mapping[str, str] = os.environ) -> str | None:
    """Le modele de repli, ou `None` s'il est coupe ou identique au principal."""
    secours = (env.get(ENV_SECOURS) or "").strip() or MODELE_SECOURS_DEFAUT
    if secours.lower() == SANS_SECOURS or secours == modele_extraction(env):
        return None
    return secours


def modele_introuvable(exc: BaseException) -> bool:
    """Le fournisseur ne connait pas (ou plus) le modele demande : HTTP 404."""
    return getattr(exc, "status_code", None) == 404


def famille(modele: str) -> str | None:
    """`claude-opus-5-5` -> `opus`. `None` pour un nom d'une autre forme."""
    trouve = _NOM.match(modele)
    return trouve.group(1) if trouve else None


def _effort_selon_le_nom(modele: str) -> bool:
    """Regle de repli : l'effort existe depuis la generation 4.6 (Haiku : 5)."""
    trouve = _NOM.match(modele)
    if not trouve:
        return False  # Inconnu : ne rien envoyer est sur, un 400 ne l'est pas.
    nom, majeure, mineure = trouve.group(1), int(trouve.group(2)), int(trouve.group(3) or 0)
    if nom in {"fable", "mythos"}:
        return True
    if nom == "haiku":
        return majeure >= 5
    return (majeure, mineure) >= (4, 6)


def accepte_effort(modele: str) -> bool:
    if modele in _CAPACITES_EFFORT:
        return _CAPACITES_EFFORT[modele]
    return _effort_selon_le_nom(modele)


def _champ(objet: Any, nom: str) -> Any:
    """Le SDK rend des objets types (`capabilities.effort`), pas des dicts."""
    return objet[nom] if isinstance(objet, Mapping) else getattr(objet, nom)


def noter_capacites(client: Any, modele: str) -> None:
    """Demande a l'API si le modele accepte `output_config.effort`.

    Jamais bloquant : sans reponse, la regle tiree du nom s'applique.
    """
    try:
        info = client.models.retrieve(modele)
        effort = _champ(_champ(info, "capabilities"), "effort")
        _CAPACITES_EFFORT[modele] = bool(_champ(effort, "supported"))
    except Exception as exc:  # noqa: BLE001 — la regle du nom prend le relais.
        log.info("Capacites de %s non lues (%s) : regle du nom.", modele, type(exc).__name__)


def cout(modele: str, entree: int, sortie: int) -> float | None:
    prix = PRIX.get(modele)
    if prix is None:
        return None
    return (entree * prix[0] + sortie * prix[1]) / 1_000_000


def _present(modele: str, ids: Mapping[str, Any]) -> Any | None:
    """Le modele tel que liste ; un alias couvre ses versions DATEES seulement.

    `claude-opus-5-5` n'est pas une version de `claude-opus-5` : un simple
    prefixe aurait cache la disparition d'Opus 5.
    """
    if modele in ids:
        return ids[modele]
    datee = re.compile(re.escape(modele) + r"-\d{8}")
    return next((m for i, m in ids.items() if datee.fullmatch(i)), None)


def veiller(client: Any, etat: dict[str, Any], notify: Callable[[str], None], *,
            source_id: str, modele: str, secours: str | None,
            maintenant: datetime | None = None) -> int:
    """Une fois par semaine : modele disparu, retrait annonce, ou plus recent.

    Rend le nombre de messages envoyes. Chaque nouveau modele, et chaque date de
    retrait, n'est signale qu'une fois (`etat["veilleModeles"]["signales"]`).
    Une erreur d'API remonte a l'appelant, qui la signale une seule fois.
    """
    maintenant = maintenant or datetime.now(UTC)
    veille = etat.setdefault("veilleModeles", {})
    derniere = veille.get("derniere")
    if derniere and maintenant - datetime.fromisoformat(derniere) < INTERVALLE_VEILLE:
        return 0

    ids = {m.id: m for m in client.models.list()}
    deja = set(veille.get("signales", []))
    messages = []
    for role, nom, variable in (("d'extraction", modele, ENV_MODELE),
                                ("de secours", secours, ENV_SECOURS)):
        if not nom:
            continue
        info = _present(nom, ids)
        remplacer = (f"Choisir un remplaçant au banc d'essai, puis changer {variable} "
                     f"dans le .env de venus.")
        if info is None:
            messages.append(f"⚠️ Le modèle {role} « {nom} » n'est plus proposé par "
                            f"Anthropic. {remplacer}")
            continue
        # Champs hors du schema du SDK (1.11) : lus tels quels, vides jusqu'a
        # l'annonce d'un retrait.
        retrait = getattr(info, "retires_at", None)
        obsolete = getattr(info, "deprecated_at", None)
        cle = f"retrait:{nom}:{retrait or obsolete}"
        if (retrait or obsolete) and cle not in deja:
            quand = (f"sera retiré le {str(retrait)[:10]}" if retrait
                     else f"est obsolète depuis le {str(obsolete)[:10]}")
            messages.append(f"⏳ Le modèle {role} « {nom} » {quand}. {remplacer}")
            deja.add(cle)

    reference = _present(modele, ids)
    if reference is not None and famille(modele):
        recents = sorted(
            (m for m in ids.values()
             if famille(m.id) == famille(modele) and m.created_at > reference.created_at
             and m.id not in deja),
            key=lambda m: m.created_at)
        for m in recents:
            messages.append(
                f"🆕 Nouveau modèle {m.id} ({m.display_name}), plus récent que {modele}. "
                f"À mesurer avant de changer : python banc_modeles.py --source {source_id} "
                f"--modeles {modele} {m.id}")
            deja.add(m.id)

    veille["signales"] = sorted(deja)
    veille["derniere"] = maintenant.isoformat()
    for message in messages:
        notify(message)
    return len(messages)
