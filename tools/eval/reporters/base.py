"""Protocol ``EvalReporter`` (réexporté) + registre extensible.

OCP : ajouter un format = ajouter un module + s'enregistrer ici.
Le CLI consomme ``REPORTERS`` sans connaître les implémentations.
"""
from __future__ import annotations

from typing import Mapping

from tools.eval.types import EvalReporter

__all__ = ["EvalReporter", "REPORTERS", "register_reporter"]


REPORTERS: dict[str, type] = {}


def register_reporter(name: str):
    """Décorateur d'enregistrement : ``@register_reporter("csv")``."""

    def decorator(reporter_cls: type) -> type:
        REPORTERS[name] = reporter_cls
        return reporter_cls

    return decorator


def get_registry() -> Mapping[str, type]:
    """Vue immuable du registre."""
    return dict(REPORTERS)
