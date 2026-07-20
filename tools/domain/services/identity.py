"""
identity.py — Stratégie d'identification d'`Item` (canonicalisation + ID).

Service pur (zéro IO). Donne :
  - `canonical_key(title, creator, types)` → clé déterministe normalisée
    pour comparer deux Items « représentent-ils la même œuvre ? »
  - `ItemIdentityService.generate_id(canonical, existing_ids)` → id stable
    dérivé d'un hash + résolution de collision (`-1`, `-2`…).
  - `ItemIdentityService.find_match(...)` → recherche d'un Item existant
    par canonical + types compatibles.

Aucune logique IO, aucune dépendance externe (juste `hashlib` et
`unicodedata` de la stdlib).
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Mapping

from ..item import ItemType

# Tout ce qui n'est pas alphanumérique devient un espace (puis condensé).
_PUNCT_RE = re.compile(r"[^a-z0-9]+")
_WS_RE = re.compile(r"\s+")


def _normalize_text(value: str) -> str:
    """Normalise une chaîne : lowercase + sans diacritiques + sans ponctuation.

    - NFKD pour décomposer les diacritiques, puis filtre `combining`
    - lowercase
    - remplace tout non-alphanumérique par espace
    - condense espaces, strip
    """
    decomposed = unicodedata.normalize("NFKD", value)
    no_diacritics = "".join(
        ch for ch in decomposed if not unicodedata.combining(ch)
    )
    lowered = no_diacritics.lower()
    spaced = _PUNCT_RE.sub(" ", lowered)
    return _WS_RE.sub(" ", spaced).strip()


_SEPARATOR = "\x00"  # NUL byte — invariant absolu : impossible dans une chaîne normalisée.


def canonical_key(
    title: str,
    creator: str | None = None,
    types: tuple[ItemType, ...] | None = None,  # deprecated — ignoré
) -> str:
    """Construit une clé canonique stable pour identifier une œuvre.

    Forme : ``"{title_norm}\\x00{creator_norm or ''}"`` (séparateur NUL
    impossible à produire par `_normalize_text` → invariant absolu).

    Note ADR 0002 : les `types` ne participent **plus** à la clé. Deux
    items représentant la même œuvre (titre + créateur) mais avec des
    `types` différents partagent la même clé canonique. L'intersection
    des types est vérifiée séparément (`find_match`, `can_merge_items`).

    Args:
        title: Titre de l'œuvre (non vide).
        creator: Auteur/réalisateur/artiste (peut être None).
        types: **Déprécié** — ignoré. Conservé pour compat ascendante des
            anciens callsites. Si fourni, doit rester un tuple d'`ItemType`
            (validation conservée pour ne pas masquer un bug).

    Raises:
        ValueError: si `title` est vide ou vide après normalisation.
    """
    if not isinstance(title, str) or not title.strip():
        raise ValueError("canonical_key: title ne peut pas être vide")

    # types est déprécié → on ne lève pas si absent, mais on conserve la
    # validation type si fourni (évite que du code legacy passe n'importe quoi).
    if types is not None:
        if not isinstance(types, tuple):
            raise ValueError(
                "canonical_key: types (déprécié) doit être un tuple si fourni"
            )
        for t in types:
            if not isinstance(t, ItemType):
                raise ValueError(
                    f"canonical_key: types contient une valeur non-ItemType: {t!r}"
                )

    title_norm = _normalize_text(title)
    if not title_norm:
        raise ValueError(
            "canonical_key: title vide après normalisation (que des séparateurs ?)"
        )
    creator_norm = _normalize_text(creator) if creator else ""
    # Invariant : `_normalize_text` ne peut pas produire le NUL byte
    # (substitué par espace via _PUNCT_RE). On vérifie en defensive.
    assert _SEPARATOR not in title_norm and _SEPARATOR not in creator_norm, (
        "canonical_key: séparateur NUL apparu dans une chaîne normalisée — invariant cassé"
    )
    return f"{title_norm}{_SEPARATOR}{creator_norm}"


def generate_item_id(canonical: str, existing_ids: frozenset[str]) -> str:
    """Génère un id stable depuis `canonical` et résout les collisions.

    - Forme : 8 premiers hex chars de sha256(canonical).
    - Si collision dans `existing_ids` → suffixe `-1`, `-2`, …

    ⚠️ **Stabilité après suppression**

    Cette fonction est **déterministe** pour un (canonical, existing_ids)
    donné, mais le résultat **dépend** de `existing_ids`. Si un item
    historique est supprimé, un nouvel item ayant la même canonical_key
    pourra réutiliser un id précédemment occupé (ex. `abc12345-1` peut
    redevenir `abc12345` si `abc12345` est libéré). C'est inacceptable
    pour une persistance long-terme.

    **Contrat d'usage** : `generate_item_id` n'est valable qu'**à la
    création** d'un item. Une fois attribué, un `Item.id` doit être
    persisté et **jamais recalculé**. Le mapping `canonical → id` doit
    être conservé côté repository (cf. `ItemRepository.existing_index`),
    pas re-dérivé du contenu.

    Pour éviter ce piège, utiliser `IdentityRegistry.reserve_id` qui
    mémorise explicitement les attributions.

    Args:
        canonical: Clé canonique (cf. `canonical_key`). Non vide.
        existing_ids: Ids déjà utilisés (pour suffixage).

    Returns:
        Id valide pour `Item.id` (matche `^[a-z0-9-]{1,64}$`).
    """
    if not isinstance(canonical, str) or not canonical:
        raise ValueError("generate_id: canonical ne peut pas être vide")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]
    if digest not in existing_ids:
        return digest
    # Collision : suffixer jusqu'à libre.
    suffix = 1
    while f"{digest}-{suffix}" in existing_ids:
        suffix += 1
    return f"{digest}-{suffix}"


def find_matching_item(
    candidate_canonical: str,
    candidate_types: tuple[ItemType, ...],
    existing: Mapping[str, tuple[str, tuple[ItemType, ...]]],
) -> str | None:
    """Cherche un Item existant qui matche `candidate_canonical` + types.

    Match si :
      - même `canonical` exact ; ET
      - intersection non vide entre `candidate_types` et types existants.

    Args:
        candidate_canonical: Clé canonique du candidat.
        candidate_types: Tuple non vide d'`ItemType` du candidat.
        existing: Dict `{item_id: (canonical, types)}`.

    Returns:
        L'`item_id` du premier match dans l'ordre d'itération de
        `existing`, ou None.

    Note (C14) :
        L'ordre déterministe du résultat repose entièrement sur l'ordre
        d'itération du `Mapping` fourni. Les implémentations de
        `ItemRepository.existing_index` (cf. `ports.py`) DOIVENT
        retourner un mapping stable (`dict` Python ≥3.7 trié par
        `item_id` côté backend JSON, `OrderedDict` ou `MappingProxyType`
        autorisés). En cas de collision (deux items avec même canonical
        + types qui intersectent), le premier dans l'ordre `existing`
        gagne — reproductible mais arbitraire ; à éviter par un audit
        de dédup côté repository.
    """
    if not isinstance(candidate_types, tuple) or len(candidate_types) == 0:
        raise ValueError("find_match: candidate_types ne peut pas être vide")
    candidate_set = set(candidate_types)
    for item_id, (canonical, types) in existing.items():
        if canonical != candidate_canonical:
            continue
        if candidate_set & set(types):
            return item_id
    return None


class IdentityRegistry:
    """Registre en mémoire qui mémoïse les attributions `canonical → id`.

    Évite le piège de `generate_item_id` (instabilité après suppression).
    Utilisable côté repository pour matérialiser le contrat "un id, une fois".

    Exemple :
        >>> reg = IdentityRegistry()
        >>> id1 = reg.reserve_id("title\\x00creator")
        >>> id2 = reg.reserve_id("title\\x00creator")  # même clé → même id
        >>> assert id1 == id2
    """

    def __init__(self) -> None:
        self._by_canonical: dict[str, str] = {}
        self._used_ids: set[str] = set()

    def reserve_id(self, canonical: str) -> str:
        """Réserve (ou récupère) un id pour `canonical`.

        Garantit qu'une même `canonical` renvoie toujours le même id
        au sein du registre, même après suppression d'autres ids
        (qui restent dans `_used_ids` pour la stabilité).
        """
        if canonical in self._by_canonical:
            return self._by_canonical[canonical]
        new_id = generate_item_id(canonical, frozenset(self._used_ids))
        self._by_canonical[canonical] = new_id
        self._used_ids.add(new_id)
        return new_id

    def seed(self, canonical: str, item_id: str) -> None:
        """Pré-déclare une attribution canonique → id existante.

        Usage typique : hydrater le registry depuis un repository avant
        un run de migration. Permet d'éviter de re-générer un id pour un
        canonical déjà persisté.

        Args:
            canonical: clé canonique de l'item déjà connu.
            item_id: id déjà attribué (cf. `Item.id`).

        Raises:
            ValueError: si `canonical` est déjà associé à un *autre* id
                (conflit d'attribution). Idempotent si la même paire est
                seedée plusieurs fois (no-op).
        """
        if not isinstance(canonical, str) or not canonical:
            raise ValueError("seed: canonical ne peut pas être vide")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("seed: item_id ne peut pas être vide")
        existing = self._by_canonical.get(canonical)
        if existing is not None and existing != item_id:
            raise ValueError(
                f"seed: conflit d'attribution pour canonical={canonical!r}; "
                f"déjà associé à {existing!r}, refus de remplacer par {item_id!r}"
            )
        # Idempotent : même paire → no-op.
        self._by_canonical[canonical] = item_id
        self._used_ids.add(item_id)

    def has(self, canonical: str) -> bool:
        return canonical in self._by_canonical


class ItemIdentityService:
    """Alias historique (déprécié) — utiliser les fonctions module-level.

    Conservé pour compat ascendante. Les nouveaux callsites doivent
    utiliser `generate_item_id` et `find_matching_item` directement.
    """

    @staticmethod
    def generate_id(canonical: str, existing_ids: frozenset[str]) -> str:
        return generate_item_id(canonical, existing_ids)

    @staticmethod
    def find_match(
        candidate_canonical: str,
        candidate_types: tuple[ItemType, ...],
        existing: Mapping[str, tuple[str, tuple[ItemType, ...]]],
    ) -> str | None:
        return find_matching_item(candidate_canonical, candidate_types, existing)


__all__ = [
    "canonical_key",
    "generate_item_id",
    "find_matching_item",
    "IdentityRegistry",
    "ItemIdentityService",
]
