"""
item.py — Entité `Item` (œuvre référencée) et value objects associés.

Un `Item` représente une **œuvre culturelle référencée** (film, livre,
série, album, etc.) — indépendamment de la (ou des) `Mention`(s) qui
y font référence dans un épisode. Mêmes invariants qu'un agrégat DDD :
immuable, validé à la construction, identifié par un `id` stable.

Pure logique de domaine — **aucune dépendance IO** (pas de fichier,
pas de réseau). Toutes les valeurs invalides lèvent `ValueError`.
"""
from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ItemType(StrEnum):
    """Catégorie d'œuvre. Les valeurs sont stables (sérialisation JSON)."""

    BOOK = "livre"
    FILM = "film"
    SERIES = "serie"
    MUSIC = "musique"
    ALBUM = "album"
    ARTIST = "artiste"
    PODCAST = "podcast"
    GAME = "jeu"
    COMIC = "bd"
    ARTICLE = "article"
    SHOW = "spectacle"      # spectacle vivant (stand-up, théâtre…)
    PLACE = "lieu"          # restaurant, ville, lieu géographique
    VIDEO = "video"         # vidéo YouTube spécifique
    OTHER = "autre"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


_TMDB_TYPES: frozenset[str | None] = frozenset({None, "movie", "tv"})


@dataclass(frozen=True)
class ExternalIds:
    """Identifiants externes d'une œuvre (TMDB, Spotify, etc.). Tous facultatifs."""

    tmdb: int | None = None
    tmdb_type: str | None = None  # "movie" | "tv" | None
    spotify: str | None = None
    musicbrainz: str | None = None
    openlibrary: str | None = None
    isbn: str | None = None
    justwatch: str | None = None

    def __post_init__(self) -> None:
        if self.tmdb_type not in _TMDB_TYPES:
            allowed = "None, 'movie' ou 'tv'"
            raise ValueError(
                f"ExternalIds.tmdb_type invalide: {self.tmdb_type!r}; attendu {allowed}"
            )
        # Senior M1 : bool est sous-type d'int en Python → rejet explicite.
        if self.tmdb is not None and (
            not isinstance(self.tmdb, int) or isinstance(self.tmdb, bool)
        ):
            raise ValueError(
                f"ExternalIds.tmdb doit être int (pas bool), "
                f"reçu {type(self.tmdb).__name__}"
            )

    # ------------------------------------------------------------------
    # B11 — factory tolérante pour input legacy / enricher
    # ------------------------------------------------------------------
    @classmethod
    def from_partial(cls, **kwargs: object) -> "ExternalIds":
        """Construit un `ExternalIds` à partir d'un dict potentiellement
        partiel et hétérogène.

        - Filtre les valeurs ``None`` (n'écrase pas un default).
        - Coerce ``tmdb`` (string décimale → int) si possible.
        - N'accepte que les noms de champs déclarés sur la dataclass
          (les inconnus sont ignorés — forward compat soft).

        Réutilisable par tout enricher / parser qui veut éviter de
        ré-implémenter la même normalisation défensive.
        """
        known = {f.name for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
        filtered: dict[str, object] = {}
        for k, v in kwargs.items():
            if k not in known or v is None:
                continue
            if k == "tmdb" and isinstance(v, str):
                try:
                    v = int(v)
                except ValueError:
                    # On laisse passer → __post_init__ lèvera proprement.
                    pass
            filtered[k] = v
        return cls(**filtered)  # type: ignore[arg-type]


_ETHICS_VALUES: frozenset[str | None] = frozenset({None, "indie", "neutral", "avoid"})


@dataclass(frozen=True)
class WatchProvider:
    """Plateforme de visionnage (Netflix, Disney+…) avec deeplink.

    `ethics` aligne le champ sur la politique éditoriale (cf. mémoire
    `reco-liens-ethiques`) : ``indie`` (à privilégier), ``neutral``,
    ``avoid`` (Amazon, Bolloré…). Aligné sur la valeur côté Reco legacy
    et préservé au round-trip.
    """

    name: str
    url: str
    region: str | None = None
    ethics: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("WatchProvider.name ne peut pas être vide")
        if not self.url or not self.url.strip():
            raise ValueError("WatchProvider.url ne peut pas être vide")
        if self.ethics not in _ETHICS_VALUES:
            allowed = "None, 'indie', 'neutral' ou 'avoid'"
            raise ValueError(
                f"WatchProvider.ethics invalide: {self.ethics!r}; attendu {allowed}"
            )


@dataclass(frozen=True)
class CustomLink:
    """Lien personnalisé (label libre + URL) attaché manuellement à un Item."""

    label: str
    url: str

    def __post_init__(self) -> None:
        if not self.label or not self.label.strip():
            raise ValueError("CustomLink.label ne peut pas être vide")
        if not self.url or not self.url.strip():
            raise ValueError("CustomLink.url ne peut pas être vide")


# ---------------------------------------------------------------------------
# Item
# ---------------------------------------------------------------------------


# C4 — Tightened : refuse les ids pathologiques (tirets répétés, leading/
# trailing dash). Reste rétro-compatible avec les ids 8-char hex existants.
_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ID_MAX_LEN = 64
_MIN_YEAR = 1800
_MAX_YEAR = 2100


@dataclass(frozen=True)
class Item:
    """Œuvre référencée — agrégat immuable du domaine.

    Invariants validés à la construction :
      - `id` : non vide, ^[a-z0-9-]{1,64}$
      - `types` : tuple non vide d'`ItemType`
      - `title` : non vide
      - `year` : ∈ [1800, 2100] si défini
      - `tmdb_type` : ∈ {None, 'movie', 'tv'}
      - `schema_version` : >= 1
      - collections passées comme `list` → rejetées (doivent être `tuple`)
    """

    id: str
    """Identifiant stable de l'œuvre. Politique de génération **ouverte** :
    par défaut hash hex 8 chars dérivé de `canonical_key` (cf.
    `tools.domain.services.identity.generate_item_id`), mais le contrat
    public est uniquement le format `^[a-z0-9-]{1,64}$`. Slug-kebab,
    ULID ou autres schémas sont acceptables tant qu'ils matchent."""

    types: tuple[ItemType, ...]
    title: str
    creator: str | None = None
    year: int | None = None
    aliases: tuple[str, ...] = ()
    external_ids: ExternalIds = field(default_factory=ExternalIds)
    custom_links: tuple[CustomLink, ...] = ()
    watch_providers: tuple[WatchProvider, ...] = ()
    link_overrides: Mapping[str, str] = field(default_factory=dict)
    recommended_by: str | None = None
    """C13 — DÉPRÉCIÉ : la sémantique « qui a recommandé » appartient à la
    `Mention` (le même Item peut être recommandé par plusieurs personnes
    dans des épisodes différents). Conservé pour rétro-compat de
    sérialisation legacy ; ne pas utiliser dans le nouveau code.
    """
    schema_version: int = 1

    def __post_init__(self) -> None:
        # --- id ---
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("Item.id ne peut pas être vide")
        if len(self.id) > _ID_MAX_LEN or not _ID_PATTERN.match(self.id):
            raise ValueError(
                f"Item.id invalide: {self.id!r}; attendu ^[a-z0-9]+(-[a-z0-9]+)*$ "
                f"(max {_ID_MAX_LEN} chars)"
            )

        # --- types ---
        if not isinstance(self.types, tuple):
            raise ValueError(
                f"Item.types doit être un tuple, reçu {type(self.types).__name__}"
            )
        if len(self.types) == 0:
            raise ValueError("Item.types ne peut pas être vide (tuple vide)")
        for t in self.types:
            if not isinstance(t, ItemType):
                raise ValueError(
                    f"Item.types contient une valeur non-ItemType: {t!r} "
                    f"(type={type(t).__name__})"
                )

        # --- title --- (Senior M8 : strip à la construction)
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("Item.title ne peut pas être vide")
        stripped_title = self.title.strip()
        if stripped_title != self.title:
            object.__setattr__(self, "title", stripped_title)

        # --- creator (None OK) ---
        if self.creator is not None and (
            not isinstance(self.creator, str) or not self.creator.strip()
        ):
            raise ValueError("Item.creator doit être None ou une chaîne non vide")

        # --- year ---
        if self.year is not None:
            if not isinstance(self.year, int) or isinstance(self.year, bool):
                raise ValueError(
                    f"Item.year doit être int ou None, reçu {type(self.year).__name__}"
                )
            if self.year < _MIN_YEAR or self.year > _MAX_YEAR:
                raise ValueError(
                    f"Item.year hors borne: {self.year} "
                    f"(attendu [{_MIN_YEAR}, {_MAX_YEAR}])"
                )

        # --- aliases ---
        if not isinstance(self.aliases, tuple):
            raise ValueError(
                f"Item.aliases doit être un tuple, reçu {type(self.aliases).__name__}"
            )
        for alias in self.aliases:
            if not isinstance(alias, str) or not alias.strip():
                raise ValueError(
                    f"Item.aliases ne doit contenir que des chaînes non vides "
                    f"(élément invalide: {alias!r})"
                )

        # --- custom_links / watch_providers ---
        if not isinstance(self.custom_links, tuple):
            raise ValueError(
                f"Item.custom_links doit être un tuple, reçu {type(self.custom_links).__name__}"
            )
        for link in self.custom_links:
            if not isinstance(link, CustomLink):
                raise ValueError(
                    f"Item.custom_links ne doit contenir que des CustomLink "
                    f"(élément invalide: {type(link).__name__})"
                )
        if not isinstance(self.watch_providers, tuple):
            raise ValueError(
                f"Item.watch_providers doit être un tuple, reçu {type(self.watch_providers).__name__}"
            )
        for wp in self.watch_providers:
            if not isinstance(wp, WatchProvider):
                raise ValueError(
                    f"Item.watch_providers ne doit contenir que des WatchProvider "
                    f"(élément invalide: {type(wp).__name__})"
                )

        # --- link_overrides : Mapping[str, str], gelé via MappingProxyType ---
        if not isinstance(self.link_overrides, Mapping):
            raise ValueError(
                f"Item.link_overrides doit être un Mapping, reçu {type(self.link_overrides).__name__}"
            )
        for k, v in self.link_overrides.items():
            if not isinstance(k, str) or not k.strip():
                raise ValueError(
                    f"Item.link_overrides : clé invalide {k!r} (str non vide requis)"
                )
            if not isinstance(v, str) or not v.strip():
                raise ValueError(
                    f"Item.link_overrides : valeur invalide {v!r} pour {k!r} (str non vide requis)"
                )
        # Geler : copie dans MappingProxyType pour bloquer la mutation in-place.
        object.__setattr__(
            self,
            "link_overrides",
            MappingProxyType(dict(self.link_overrides)),
        )

        # --- recommended_by : None ou str non-blank ---
        if self.recommended_by is not None:
            if not isinstance(self.recommended_by, str) or not self.recommended_by.strip():
                raise ValueError(
                    "Item.recommended_by doit être None ou une chaîne non vide"
                )

        # --- schema_version ---
        if not isinstance(self.schema_version, int) or isinstance(
            self.schema_version, bool
        ):
            raise ValueError(
                f"Item.schema_version doit être un int (pas bool), "
                f"reçu {type(self.schema_version).__name__}"
            )
        if self.schema_version < 1:
            raise ValueError(
                f"Item.schema_version doit être >= 1, reçu {self.schema_version}"
            )


__all__ = [
    "ItemType",
    "ExternalIds",
    "WatchProvider",
    "CustomLink",
    "Item",
]
