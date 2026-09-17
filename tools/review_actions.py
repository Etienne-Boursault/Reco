"""
review_actions.py — ce que fait une décision de relecture à une reco.

Source unique pour les deux chemins qui tranchent une reco :
  - le review_server, quand un humain clique (`review_routes._apply_save_action`) ;
  - `apply_verdicts.py`, quand un agent a rendu un fichier de verdicts.

Avant ce module, le second était une copie manuelle du premier, rangée dans le
dossier temporaire d'une session Claude — dossier effacé depuis, copie perdue
avec lui (constaté le 2026-09-17). Une copie diverge ; une fonction partagée,
non.

Ne pose PAS `agentReview.reviewedByHuman` : c'est à l'appelant humain de le
faire. Un verdict d'agent doit rester visible dans la file des doutes.
"""

from __future__ import annotations

from common import log

# Décisions qui tranchent une reco. `unsure` n'en fait pas partie : il laisse la
# reco en `draft` et ne passe jamais par ici.
SAVE_ACTIONS: frozenset[str] = frozenset(
    {"validate", "discard", "citation", "guest-work"})


def _set_recommended_by(reco: dict, recommended: str) -> None:
    if recommended:
        reco["recommendedBy"] = recommended
    elif "recommendedBy" in reco:
        del reco["recommendedBy"]


def apply_review_action(reco: dict, action: str, recommended: str,
                        reco_id: str) -> None:
    """Mute `reco` selon `action` (discard / citation / guest-work / validate).

    Toute autre valeur est traitée comme `validate` : les appelants valident
    l'action en amont (`SAVE_ACTIONS`).
    """
    if action == "discard":
        reco["status"] = "discarded"
        # On préserve `kind` ET `guestWork` à dessein : un humain a
        # peut-être déjà qualifié l'item (citation, œuvre d'invité) puis
        # change d'avis sur la pertinence globale. Réinitialiser ces
        # marqueurs effacerait cette info de re-qualification.
        log.info("Écarté : %s", reco_id)
        return
    if action == "citation":
        _set_recommended_by(reco, recommended)
        reco["status"] = "validated"
        reco["kind"] = "citation"
        # Re-qualifier en citation retire le marqueur « œuvre d'invité ».
        reco.pop("guestWork", None)
        log.info("Citation : %s -> %s", reco_id, recommended or "(personne)")
        return
    if action == "guest-work":
        # Œuvre présentée par un·e invité·e (auto-promo) : c'est une vraie
        # reco (kind=reco) mais marquée pour ne pas polluer les vraies
        # recommandations côté site. recommendedBy géré comme validate.
        _set_recommended_by(reco, recommended)
        reco["status"] = "validated"
        reco["kind"] = "reco"
        reco["guestWork"] = True
        log.info("Œuvre d'invité : %s -> %s", reco_id, recommended or "(personne)")
        return
    # default = validate
    _set_recommended_by(reco, recommended)
    reco["status"] = "validated"
    # Ré-affirme qu'une validation classique = vraie reco, et retire un
    # éventuel marqueur « œuvre d'invité » (re-qualification).
    reco["kind"] = "reco"
    reco.pop("guestWork", None)
    log.info("Validé : %s -> %s", reco_id, recommended or "(personne)")
