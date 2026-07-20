"""
reco_parser.py — Conversion **pure** d'un dict reco legacy en
`(Item, Mention)`.

Zéro IO. Aucune dépendance externe (juste le domaine). L'identité de
l'Item (`item.id`) est déléguée à un *resolver* injecté :

    item_id = item_id_resolver(canonical_key, creator, types)

Le resolver encapsule la décision « item existant à réutiliser ou
nouvel id ». Cette indirection permet :
- d'utiliser un `IdentityRegistry` côté service (production) ;
- d'injecter un mock dans les tests (vérifier les arguments passés) ;
- d'ajouter une stratégie alternative (ex. id slug-kebab) sans toucher
  le parser → conforme OCP.

Le parser ne crée **pas** les `extraction_history.extra` à partir des
champs inconnus aveuglément : il copie uniquement les champs qui ont
besoin d'être préservés pour le round-trip (`timestamp_at_extraction`).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from domain.item import (
    CustomLink,
    ExternalIds,
    Item,
    ItemType,
    WatchProvider,
)
from domain.mention import (
    ExtractionHistoryEntry,
    Mention,
    MentionKind,
    MentionStatus,
    SourceRef,
    TranscriptSource,
)
from domain.services.identity import canonical_key


# ---------------------------------------------------------------------------
# Mapping des types legacy
# ---------------------------------------------------------------------------

# Depuis ADR 0006, les types historiques `spectacle/lieu/video` ont leur
# propre valeur dans `ItemType` (SHOW/PLACE/VIDEO). Ce dict ne sert plus
# qu'à conserver une porte de sortie si des alias additionnels apparaissent.
_TYPE_ALIASES: dict[str, ItemType] = {}


def _parse_types(raw: object) -> tuple[ItemType, ...]:
    """Convertit la liste legacy de types en tuple d'`ItemType`.

    - Types connus (y compris `spectacle/lieu/video` depuis ADR 0006) : direct.
    - Types vraiment inconnus : `ValueError` (mieux vaut signaler).
    - Dédoublonne en préservant l'ordre.
    """
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            f"reco.types invalide: attendu liste non vide, reçu {raw!r}"
        )
    out: list[ItemType] = []
    seen: set[ItemType] = set()
    for t in raw:
        if not isinstance(t, str):
            raise ValueError(f"reco.types contient une valeur non-str: {t!r}")
        if t in _TYPE_ALIASES:
            resolved = _TYPE_ALIASES[t]
        else:
            try:
                resolved = ItemType(t)
            except ValueError as e:
                raise ValueError(
                    f"reco.types contient un type inconnu: {t!r}"
                ) from e
        if resolved not in seen:
            out.append(resolved)
            seen.add(resolved)
    return tuple(out)


# ---------------------------------------------------------------------------
# Timestamp legacy normalization (A5)
# ---------------------------------------------------------------------------

import re as _re_ts  # local alias pour ne pas masquer l'import top
_MMSS_PATTERN = _re_ts.compile(r"^\d{1,2}:\d{2}$")
_HHMMSS_PATTERN = _re_ts.compile(r"^\d{2}:\d{2}:\d{2}$")


def _normalize_timestamp(raw: object) -> str | None:
    """Normalise un timestamp legacy MM:SS → HH:MM:SS.

    Politique (compat legacy uniquement, pas dans le contrat ascendant) :
      - None / "" → None
      - HH:MM:SS valide → tel quel
      - M:SS ou MM:SS → "00:MM:SS" (padding minute si M unique)
      - autre → laisse passer (le domain `SourceRef` rejettera).
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw  # type: ignore[return-value]  # laisse domain rejeter
    s = raw.strip()
    if not s:
        return None
    if _HHMMSS_PATTERN.match(s):
        return s
    if _MMSS_PATTERN.match(s):
        # M:SS ou MM:SS → 00:MM:SS (zero-pad la partie minute).
        mm, ss = s.split(":")
        return f"00:{mm.zfill(2)}:{ss}"
    return s


# ---------------------------------------------------------------------------
# External IDs / collections — coercitions defensives
# ---------------------------------------------------------------------------


def _parse_external_ids(raw: object) -> ExternalIds:
    """Convertit le sous-dict legacy `externalIds` en `ExternalIds`.

    Délègue à `ExternalIds.from_partial` (factory tolérante introduite
    en B11) la normalisation des valeurs partielles + la coercion
    string→int de `tmdb`. Le parser conserve uniquement :
      - la validation que `raw` est un Mapping ;
      - les rejets fail-fast spécifiques au legacy (bool, string vide,
        tmdb non numérique, tmdb type inattendu) que la factory tolère
        silencieusement ;
      - le drop silencieux du `tmdbType` invalide (politique legacy).
    """
    if raw is None:
        return ExternalIds()
    if not isinstance(raw, Mapping):
        raise ValueError(f"reco.externalIds doit être un objet, reçu {raw!r}")

    tmdb_raw = raw.get("tmdb")
    # Validation fail-fast côté parser (la factory serait plus permissive).
    if tmdb_raw is None:
        pass
    elif isinstance(tmdb_raw, bool):
        # bool est sous-type d'int — rejet explicite (cf. domaine).
        raise ValueError(f"reco.externalIds.tmdb invalide (bool): {tmdb_raw!r}")
    elif isinstance(tmdb_raw, int):
        pass
    elif isinstance(tmdb_raw, str) and tmdb_raw.strip():
        try:
            int(tmdb_raw)
        except ValueError as e:
            raise ValueError(
                f"reco.externalIds.tmdb non numérique: {tmdb_raw!r}"
            ) from e
    else:
        raise ValueError(f"reco.externalIds.tmdb invalide: {tmdb_raw!r}")

    tmdb_type = raw.get("tmdbType")
    # Drop silencieux si invalide (politique legacy, contraire à la factory).
    safe_tmdb_type = tmdb_type if tmdb_type in (None, "movie", "tv") else None

    return ExternalIds.from_partial(
        tmdb=tmdb_raw,
        tmdb_type=safe_tmdb_type,
        spotify=raw.get("spotify"),
        musicbrainz=raw.get("musicbrainz"),
        openlibrary=raw.get("openlibrary"),
        isbn=raw.get("isbn"),
        justwatch=raw.get("justwatch"),
    )


def _parse_watch_providers(raw: object) -> tuple[WatchProvider, ...]:
    """Convertit la liste legacy `watchProviders` (clé `label`) en `WatchProvider` (`name`).

    Le champ legacy `ethics` (`indie`/`neutral`/`avoid`) est préservé
    via le domaine (cf. mémoire utilisateur « Liens éthiques »).
    """
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ValueError(
            f"reco.watchProviders doit être une liste, reçu {raw!r}"
        )
    out: list[WatchProvider] = []
    for wp in raw:
        if not isinstance(wp, Mapping):
            raise ValueError(f"watchProvider invalide: {wp!r}")
        # Compat : preferred `name`, fallback `label`.
        name = wp.get("name") or wp.get("label")
        url = wp.get("url")
        if not name or not url:
            raise ValueError(f"watchProvider sans name/url: {wp!r}")
        out.append(WatchProvider(
            name=name,
            url=url,
            region=wp.get("region"),
            ethics=wp.get("ethics"),
        ))
    return tuple(out)


def _parse_custom_links(raw: object) -> tuple[CustomLink, ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"reco.customLinks doit être une liste, reçu {raw!r}")
    out: list[CustomLink] = []
    for cl in raw:
        if not isinstance(cl, Mapping):
            raise ValueError(f"customLink invalide: {cl!r}")
        label = cl.get("label")
        url = cl.get("url")
        if not label or not url:
            raise ValueError(f"customLink sans label/url: {cl!r}")
        out.append(CustomLink(label=label, url=url))
    return tuple(out)


def _parse_link_overrides(raw: object) -> dict[str, str]:
    if not raw:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError(
            f"reco.linkOverrides doit être un objet, reçu {raw!r}"
        )
    out: dict[str, str] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise ValueError(
                f"linkOverrides : couple invalide ({k!r}: {v!r})"
            )
        out[k] = v
    return out


def _parse_aliases(raw: object) -> tuple[str, ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"reco.aliases doit être une liste, reçu {raw!r}")
    for a in raw:
        if not isinstance(a, str) or not a.strip():
            raise ValueError(f"alias invalide: {a!r}")
    # Strip cohérent : on ne conserve que les chaînes non-vides après strip.
    return tuple(a.strip() for a in raw if isinstance(a, str) and a.strip())


# ---------------------------------------------------------------------------
# Extraction history
# ---------------------------------------------------------------------------


_PRESERVED_EXTRA_KEYS = ("timestamp_at_extraction",)
"""Whitelist intentionnelle des clés legacy à préserver dans
`ExtractionHistoryEntry.extra` pour le round-trip.

Politique : on **ne** copie **pas** aveuglément les champs inconnus
(éviterait de fausses garanties de fidélité). Étendre cette whitelist
uniquement si un champ legacy n'a pas d'équivalent first-class dans
`ExtractionHistoryEntry`.
"""


def _parse_extraction_history(
    raw: object,
) -> tuple[ExtractionHistoryEntry, ...]:
    """Convertit la liste legacy en `tuple[ExtractionHistoryEntry, ...]`.

    Préserve `timestamp_at_extraction` dans `extra` pour ne pas perdre
    d'info historique (round-trip).
    """
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ValueError(
            f"reco.extractionHistory doit être une liste, reçu {raw!r}"
        )
    out: list[ExtractionHistoryEntry] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            raise ValueError(f"extractionHistory entrée invalide: {entry!r}")
        extra: dict[str, str] = {}
        for k in _PRESERVED_EXTRA_KEYS:
            v = entry.get(k)
            if v is not None:
                extra[k] = str(v)
        provider = entry.get("llmProvider")
        if not provider:
            raise ValueError(
                "reco.extractionHistory[].llmProvider manquant ou vide"
            )
        model = entry.get("llmModel")
        if not model:
            raise ValueError(
                "reco.extractionHistory[].llmModel manquant ou vide"
            )
        at = entry.get("at")
        if not at:
            raise ValueError(
                "reco.extractionHistory[].at manquant ou vide"
            )
        out.append(
            ExtractionHistoryEntry(
                transcript_model=entry.get("transcriptModel"),
                transcript_source=entry.get("transcriptSource"),
                llm_provider=provider,
                llm_model=model,
                worker=entry.get("worker"),
                at=at,
                extra=extra,
            )
        )
    return tuple(out)


def _parse_extractors(raw: object) -> tuple[str, ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"reco.extractors doit être une liste, reçu {raw!r}")
    for e in raw:
        if not isinstance(e, str) or not e.strip():
            raise ValueError(f"extractor invalide: {e!r}")
    return tuple(raw)


# ---------------------------------------------------------------------------
# Mention enums
# ---------------------------------------------------------------------------


def _parse_kind(raw: object) -> MentionKind:
    """Défaut `RECO` si absent (legacy : tout est reco par défaut)."""
    if raw is None:
        return MentionKind.RECO
    if isinstance(raw, MentionKind):
        return raw
    if isinstance(raw, str):
        try:
            return MentionKind(raw)
        except ValueError as e:
            raise ValueError(f"reco.kind invalide: {raw!r}") from e
    raise ValueError(f"reco.kind invalide: {raw!r}")


def _parse_status(raw: object) -> MentionStatus:
    """Défaut `DRAFT` si absent."""
    if raw is None:
        return MentionStatus.DRAFT
    if isinstance(raw, MentionStatus):
        return raw
    if isinstance(raw, str):
        try:
            return MentionStatus(raw)
        except ValueError as e:
            raise ValueError(f"reco.status invalide: {raw!r}") from e
    raise ValueError(f"reco.status invalide: {raw!r}")


def _parse_transcript_source(raw: object) -> TranscriptSource | None:
    if raw is None:
        return None
    if isinstance(raw, TranscriptSource):
        return raw
    if isinstance(raw, str):
        try:
            return TranscriptSource(raw)
        except ValueError as e:
            raise ValueError(f"reco.transcriptSource invalide: {raw!r}") from e
    raise ValueError(f"reco.transcriptSource invalide: {raw!r}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


ItemIdResolver = Callable[
    [str, str | None, tuple[ItemType, ...]],
    str,
]
"""Signature du resolver : (canonical_key, creator, types) → item_id.

Le canonical_key est déjà calculé par le parser (cohérence interne) ;
creator/types sont fournis pour permettre des stratégies plus riches
(ex. shadow-merge basé sur l'identité éditoriale)."""


def reco_dict_to_item_mention(
    reco: Mapping[str, Any],
    *,
    item_id_resolver: ItemIdResolver,
) -> tuple[Item, Mention]:
    """Convertit un dict reco legacy en `(Item, Mention)`.

    Args:
        reco: Dict legacy (camelCase) lu depuis `src/content/recos/<src>/X.json`.
        item_id_resolver: Fonction qui dérive l'`item_id` à partir de
            `(canonical_key, creator, types)`. Permet d'injecter la
            stratégie de dédoublonnage (registry, repository, mock).

    Returns:
        Tuple `(item, mention)` cohérent (`mention.item_id == item.id`).

    Raises:
        ValueError: Si le reco est mal formé (champ requis manquant ou
            valeur invalide). Le message identifie le champ fautif.
    """
    if not isinstance(reco, Mapping):
        raise ValueError(f"reco doit être un objet, reçu {type(reco).__name__}")

    # --- champs requis ---
    try:
        reco_id = reco["id"]
        title = reco["title"]
        source_id = reco["sourceId"]
    except KeyError as e:
        raise ValueError(f"reco : champ requis manquant : {e}") from e

    if not isinstance(reco_id, str) or not reco_id.strip():
        raise ValueError(f"reco.id invalide: {reco_id!r}")
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"reco.title invalide: {title!r}")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError(f"reco.sourceId invalide: {source_id!r}")

    types = _parse_types(reco.get("types"))
    creator_raw = reco.get("creator")
    # Le domaine refuse `creator=""` ou whitespace — normalise vide → None.
    creator: str | None
    if creator_raw is None:
        creator = None
    elif isinstance(creator_raw, str):
        creator = creator_raw.strip() or None
    else:
        raise ValueError(f"reco.creator invalide: {creator_raw!r}")

    # --- canonical + resolution d'id ---
    canonical = canonical_key(title, creator)
    item_id = item_id_resolver(canonical, creator, types)

    # --- year : normalise str → int (legacy "2020"), valeurs hors bornes → None.
    year_raw = reco.get("year")
    year: int | None
    if year_raw is None:
        year = None
    elif isinstance(year_raw, bool):
        year = None  # bool est sous-type int — rejet silencieux côté legacy
    elif isinstance(year_raw, int):
        year = year_raw if 1800 <= year_raw <= 2100 else None
    elif isinstance(year_raw, str) and year_raw.strip():
        try:
            v = int(year_raw.strip())
            year = v if 1800 <= v <= 2100 else None
        except ValueError:
            year = None
    else:
        year = None

    # --- Item ---
    item = Item(
        id=item_id,
        types=types,
        title=title,
        creator=creator,
        year=year,
        aliases=_parse_aliases(reco.get("aliases")),
        external_ids=_parse_external_ids(reco.get("externalIds")),
        custom_links=_parse_custom_links(reco.get("customLinks")),
        watch_providers=_parse_watch_providers(reco.get("watchProviders")),
        link_overrides=_parse_link_overrides(reco.get("linkOverrides")),
        recommended_by=None,  # appartient à la Mention, pas à l'Item.
    )

    # --- SourceRef ---
    source_ref = SourceRef(
        source_id=source_id,
        episode_guid=reco.get("episodeGuid"),
        timestamp=_normalize_timestamp(reco.get("timestamp")),
        transcript_source=_parse_transcript_source(
            reco.get("transcriptSource")
        ),
    )

    # --- Mention ---
    mention = Mention(
        id=reco_id,
        item_id=item_id,
        source_ref=source_ref,
        recommended_by=reco.get("recommendedBy"),
        quote=reco.get("quote"),
        kind=_parse_kind(reco.get("kind")),
        status=_parse_status(reco.get("status")),
        extraction_history=_parse_extraction_history(
            reco.get("extractionHistory")
        ),
        extractors=_parse_extractors(reco.get("extractors")),
    )

    return item, mention


__all__ = ["reco_dict_to_item_mention", "ItemIdResolver"]
