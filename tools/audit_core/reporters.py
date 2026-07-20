"""audit_core.reporters — Reporter Protocol + escape_md unifié.

SSOT du Reporter Protocol et de l'échappement Markdown pour les
rapports d'audit.

Avant : 3 implémentations divergentes (lint = `\\, *, _, backtick, [, ]`
sans `|`, match_audit = uniquement `|`, enrich_audit = `\\, backtick, |, \n, \r`).
Après : **union complète** = `\\, *, _, backtick, [, ], |, \n, \r`.

Pourquoi tout échapper ? Les messages d'audit transitent par des LLMs et
contiennent souvent des caractères techniques (chemins Windows ``\\``,
fragments markdown ``**bold**``, etc.). Échapper systématiquement coûte
0 et évite les surprises (rendu cassé, injection, diff bruyant).
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

#: Caractères Markdown échappés (union complète — cf. ADR 0019).
#: Ordre : ``\`` en premier (sinon les autres se doublent).
_MD_ESCAPE_CHARS: tuple[str, ...] = (
    "\\",
    "*",
    "_",
    "`",
    "[",
    "]",
    "|",
)

#: Caractères de contrôle remplacés par un espace (cassent les tables MD).
_MD_BLANK_CHARS: tuple[str, ...] = ("\n", "\r")


def escape_md(value: str) -> str:
    """Échappe les méta-caractères Markdown dans une chaîne libre.

    Caractères préfixés par ``\\`` :
        ``\\``, ``*``, ``_``, backtick, ``[``, ``]``, ``|``.

    Caractères remplacés par un espace :
        ``\\n``, ``\\r`` (cassent les tables markdown inline).

    Args:
        value: chaîne à échapper (typiquement un detail de Suspicion
            ou un message d'erreur).

    Returns:
        Une str équivalente safe pour insertion inline Markdown.

    Raises:
        TypeError: si ``value`` n'est pas une str (faute d'usage côté
            caller — ne pas masquer silencieusement).
    """
    if not isinstance(value, str):
        raise TypeError(
            f"escape_md attend une str, reçu {type(value).__name__}"
        )
    out = value
    for c in _MD_ESCAPE_CHARS:
        out = out.replace(c, "\\" + c)
    for c in _MD_BLANK_CHARS:
        out = out.replace(c, " ")
    return out


@runtime_checkable
class Reporter(Protocol):
    """Contrat structurel d'un reporter.

    Un reporter expose :
      - ``format_id`` : identifiant lisible (``"markdown"`` | ``"json"``
        | ``"human"`` | ``"none"``).
      - ``render(report)`` : sérialise le rapport en str.

    Pas d'héritage requis — duck-typing structurel.
    """

    format_id: str

    def render(self, report: Any) -> str: ...  # pragma: no cover


#: Registry de base — vide. Chaque module remplit le sien (lint,
#: match_audit, enrich_audit). Centralisé ici si un jour on veut
#: composer des reporters cross-module.
REPORTERS: dict[str, Reporter] = {}


__all__ = ["REPORTERS", "Reporter", "escape_md"]
