"""audit_core.settings — helper ``from_source_extra`` factorisé.

Avant : 2 implémentations quasi-identiques (``lint/settings.py``,
``match_audit/settings.py``) + 1 absente (``enrich_audit``).
Après : un seul helper générique paramétré, consommé par les 3.

Le pattern est invariant :

1. Si ``extra`` est un Mapping et contient la clé ``key``, on lit les
   champs connus de ``cls`` (introspection ``dataclasses.fields``).
2. Les ``overrides`` (typiquement des flags CLI) gagnent sur la config.
3. Les valeurs ``None`` côté payload OU côté overrides sont ignorées —
   on conserve les défauts du dataclass cible.

Forward-compat : les payloads peuvent contenir des clés inconnues du
dataclass — elles sont simplement ignorées (un fork peut ainsi commencer
à shipper un nouveau seuil avant que le code l'utilise).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Any, TypeVar

T = TypeVar("T")

#: Champs « tuple-coerçables » : si le payload livre une list/tuple pour
#: ce champ, on convertit en ``tuple(...)`` avant instanciation. Une
#: instance ``cls`` peut surcharger via attribut de classe ``_TUPLE_FIELDS``.
_DEFAULT_TUPLE_NAMES: frozenset[str] = frozenset()


def _coerce_value(name: str, value: Any, tuple_names: frozenset[str]) -> Any:
    """Coerce une valeur de payload vers la forme attendue par le dataclass.

    - list/tuple → tuple(str(x) for x in value) si name ∈ tuple_names.
    - sinon : passe tel quel (le dataclass `__post_init__` validera).
    """
    if name in tuple_names and isinstance(value, (list, tuple)):
        return tuple(value)
    return value


def from_source_extra(
    extra: Mapping[str, Any] | None,
    key: str,
    cls: type[T],
    *,
    overrides: Mapping[str, Any] | None = None,
    tuple_fields: frozenset[str] | None = None,
) -> T:
    """Construit ``cls`` depuis ``extra[key]`` + ``overrides``.

    Args:
        extra: ``SourceConfig.extra`` ou équivalent. ``None`` → défauts.
        key: nom de la sous-section (ex. ``"lint"``, ``"match_audit"``,
            ``"enrich_audit"``).
        cls: dataclass cible. Doit être un ``@dataclass`` (frozen ou non).
        overrides: dict de flags qui gagne sur la config.
            Les valeurs ``None`` sont ignorées (pas d'override).
        tuple_fields: noms de champs à coercer en tuple si le payload
            livre une list. Par défaut : aucun (le dataclass valide).

    Returns:
        Une instance de ``cls``.

    Raises:
        TypeError: si ``cls`` n'est pas un dataclass.
        ValueError: relevé par le ``__post_init__`` de ``cls`` si une
            valeur fournie est invalide.
    """
    if not is_dataclass(cls):
        raise TypeError(
            f"from_source_extra attend un dataclass, reçu {cls!r}"
        )
    known = {f.name for f in fields(cls)}
    tnames = tuple_fields if tuple_fields is not None else _DEFAULT_TUPLE_NAMES

    kwargs: dict[str, Any] = {}

    # 1) Payload depuis extra[key]
    if isinstance(extra, Mapping):
        payload = extra.get(key)
        if isinstance(payload, Mapping):
            for k, v in payload.items():
                if k in known and v is not None:
                    kwargs[k] = _coerce_value(k, v, tnames)

    # 2) Overrides (CLI typiquement) gagnent
    if overrides:
        for k, v in overrides.items():
            if v is not None and k in known:
                kwargs[k] = _coerce_value(k, v, tnames)

    return cls(**kwargs)  # type: ignore[call-arg]


__all__ = ["from_source_extra"]
