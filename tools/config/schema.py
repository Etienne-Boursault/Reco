"""Schéma `SourceConfig` — couche domaine pure (sans I/O ni effet de bord).

SRP : ce module ne fait QUE définir et valider la structure d'une source.
La lecture disque vit dans ``loader.py``, l'orchestration dans ``registry.py``,
la traduction camelCase/Astro vit dans ``astro_adapter.py``.

Immutable (``frozen=True``) pour que les modules consommateurs puissent
injecter une `SourceConfig` sans craindre une mutation latérale (DIP).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, fields
from typing import Any, Mapping

from tools.config.astro_adapter import normalize_payload

__all__ = ["SourceConfig"]

_log = logging.getLogger("reco.config")

# Slug : minuscules, chiffres, tirets internes. Doit commencer par alnum.
_RE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Préfixe reco : alnum minuscule, 2 à 8 caractères (évite « x » trop court
# et préfixes obscurs trop longs).
_RE_PREFIX = re.compile(r"^[a-z0-9]{2,8}$")
# Couleur hex 6 chars (# obligatoire).
_RE_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

_REQUIRED_FIELDS = ("id", "title", "reco_prefix", "hosts")
_VALID_TRANSCRIPT_SOURCES = ("youtube", "acast")

# Version courante du schéma. Toute valeur supérieure → warning (futur
# fichier produit par une version plus récente). Une valeur inférieure
# pourrait déclencher une migration le jour venu.
CURRENT_SCHEMA_VERSION: int = 1

# Champs typés "tuple" : on convertit les listes JSON en tuple
# automatiquement avant instanciation.
_TUPLE_FIELDS = frozenset(
    {
        "hosts",
        "avoid_brands",
        "extraction_anchor_patterns",
        "youtube_title_suffix_patterns",
    }
)


@dataclass(frozen=True, slots=True)
class SourceConfig:
    """Configuration immuable d'une source (podcast) du pipeline.

    Champs requis : ``id``, ``title``, ``reco_prefix``, ``hosts``.
    Tout le reste a un défaut raisonnable pour qu'une config minimale
    (4 lignes) suffise à brancher une nouvelle source.
    """

    # --- Identité ---------------------------------------------------------
    id: str
    """Slug stable utilisé pour les dossiers et URLs (ex. ``un-bon-moment``)."""

    title: str
    """Titre humain affiché (ex. ``Un Bon Moment``)."""

    reco_prefix: str
    """Préfixe court des IDs de recos (ex. ``ubm`` → ``ubm-0001``)."""

    hosts: tuple[str, ...]
    """Hôtes réguliers du podcast (au moins un — utilisé dans le prompt LLM)."""

    # --- Optionnels : flux de données ------------------------------------
    description: str = ""
    rss_url: str | None = None
    youtube_channel_url: str | None = None
    spotify_show_id: str | None = None

    # --- Optionnels : pipeline -------------------------------------------
    transcript_default_source: str = "youtube"
    """Source par défaut des transcripts (``youtube`` ou ``acast``)."""

    extraction_anchor_patterns: tuple[str, ...] = ()
    """Indices textuels (substring, insensible casse) du moment-clé
    "ta reco ?". Vide = pas d'ancrage. Ce ne sont PAS des regex —
    `extract_recos.py` les utilise via ``in`` après normalisation."""

    youtube_title_suffix_patterns: tuple[str, ...] = ()
    """Fragments de suffixe entre parenthèses à retirer avant matching YT
    (ex. ``("un bon moment", "a good time")`` retire
    ``(Un Bon Moment, S5-E31)``). Vide = aucun retrait."""

    # --- Optionnels : site public ----------------------------------------
    site_color_accent: str = "#ffd23f"
    site_url: str | None = None

    # --- Optionnels : politique éditoriale -------------------------------
    avoid_brands: tuple[str, ...] = ()
    """Marques à éviter dans les liens marchands. Par défaut vide — voir
    ``tools.config.policies.PROJECT_AVOID_BRANDS`` pour la politique du
    projet Reco. Chaque config JSON décide explicitement."""

    # --- Métadonnées -----------------------------------------------------
    enabled: bool = True
    """Si False, la source est ignorée par ``list_sources()`` (et donc
    par le pipeline). Permet de désactiver temporairement une source
    sans supprimer son fichier."""

    schema_version: int = 1
    """Version du schéma. Un payload avec ``schemaVersion`` supérieur
    déclenche un warning (forward-compat soft)."""

    extra: Mapping[str, Any] = field(default_factory=dict)
    """Champs non-schéma stockés tel quel pour les forks/usages spéci-
    fiques. Le pipeline officiel n'y touche pas. Stocké en
    ``MappingProxyType`` (lecture seule)."""

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        # --- Types stricts (refuse les listes, ints à la place de strings, etc.)
        if not isinstance(self.id, str):
            raise TypeError(f"`id` doit être une chaîne, pas {type(self.id).__name__}.")
        if not isinstance(self.title, str):
            raise TypeError(
                f"`title` doit être une chaîne, pas {type(self.title).__name__}."
            )
        if not isinstance(self.reco_prefix, str):
            raise TypeError(
                f"`reco_prefix` doit être une chaîne, "
                f"pas {type(self.reco_prefix).__name__}."
            )
        if not isinstance(self.description, str):
            raise TypeError(
                f"`description` doit être une chaîne, "
                f"pas {type(self.description).__name__}."
            )

        for opt_name in ("rss_url", "youtube_channel_url", "spotify_show_id", "site_url"):
            v = getattr(self, opt_name)
            if v is not None and not isinstance(v, str):
                raise TypeError(
                    f"`{opt_name}` doit être une chaîne ou None, "
                    f"pas {type(v).__name__}."
                )

        if not isinstance(self.hosts, tuple):
            raise TypeError(
                "`hosts` doit être un tuple (immutabilité DIP), pas une liste."
            )
        if not all(isinstance(h, str) for h in self.hosts):
            raise TypeError("`hosts` ne doit contenir que des chaînes.")

        if not isinstance(self.avoid_brands, tuple):
            raise TypeError("`avoid_brands` doit être un tuple, pas une liste.")
        if not all(isinstance(b, str) for b in self.avoid_brands):
            raise TypeError("`avoid_brands` ne doit contenir que des chaînes.")

        if not isinstance(self.extraction_anchor_patterns, tuple):
            raise TypeError(
                "`extraction_anchor_patterns` doit être un tuple, pas une liste."
            )
        if not all(isinstance(p, str) for p in self.extraction_anchor_patterns):
            raise TypeError(
                "`extraction_anchor_patterns` ne doit contenir que des chaînes."
            )

        if not isinstance(self.youtube_title_suffix_patterns, tuple):
            raise TypeError(
                "`youtube_title_suffix_patterns` doit être un tuple, pas une liste."
            )
        if not all(isinstance(p, str) for p in self.youtube_title_suffix_patterns):
            raise TypeError(
                "`youtube_title_suffix_patterns` ne doit contenir que des chaînes."
            )

        if not isinstance(self.enabled, bool):
            raise TypeError(
                f"`enabled` doit être un bool, pas {type(self.enabled).__name__}."
            )
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool):
            raise TypeError("`schema_version` doit être un entier.")

        # --- Valeurs
        if not self.id or not _RE_ID.match(self.id):
            raise ValueError(
                f"`id` invalide : {self.id!r} — attendu slug [a-z0-9]+(-[a-z0-9]+)*."
            )
        if not self.title.strip():
            raise ValueError("`title` ne peut pas être vide.")
        if not self.reco_prefix or not _RE_PREFIX.match(self.reco_prefix):
            raise ValueError(
                f"`reco_prefix` invalide : {self.reco_prefix!r} — "
                "attendu alphanumérique minuscule, 2 à 8 caractères."
            )
        if not self.hosts:
            raise ValueError("`hosts` doit contenir au moins un nom.")
        if self.transcript_default_source not in _VALID_TRANSCRIPT_SOURCES:
            raise ValueError(
                "`transcript_default_source` invalide : "
                f"{self.transcript_default_source!r} — attendu un de "
                f"{_VALID_TRANSCRIPT_SOURCES}."
            )
        if not _RE_HEX_COLOR.match(self.site_color_accent):
            raise ValueError(
                f"`site_color_accent` invalide : {self.site_color_accent!r} — "
                "attendu un code hex 6 chiffres préfixé # (ex. #ffd23f)."
            )

        # --- `extra` doit être un mapping
        # On stocke une copie défensive sous forme de dict standard pour
        # rester compatible avec `dataclasses.asdict` (qui essaie de
        # deepcopier les valeurs et trébuche sur MappingProxyType en 3.12).
        # `frozen=True` protège la *réassignation* (`cfg.extra = ...`).
        # La mutation in-place reste possible — c'est un compromis assumé
        # pour la sérialisation. Voir issue #13.
        if not isinstance(self.extra, Mapping):
            raise TypeError("`extra` doit être un mapping (dict-like).")
        # Toujours faire une copie défensive (le tests `test_extra_is_defensive_copy`
        # garantit que muter la source ne pollue pas `cfg.extra`).
        object.__setattr__(self, "extra", dict(self.extra))

    # ------------------------------------------------------------------
    # Construction depuis un dict (JSON-like)
    # ------------------------------------------------------------------
    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
        *,
        expected_id: str | None = None,
    ) -> "SourceConfig":
        """Construit une `SourceConfig` à partir d'un payload JSON.

        Args:
            payload: dict-like (camelCase Astro ou snake_case Python).
            expected_id: si fourni, doit matcher ``payload["id"]`` (et
                est injecté si absent). Centralise ici la règle "id mismatch"
                qui vivait dans le loader.

        - Normalise via ``astro_adapter`` (camelCase → snake_case, drop
          des champs Astro-only).
        - Convertit les listes JSON en tuples (immutabilité).
        - Sépare les champs connus des "extras" (préservés dans
          ``SourceConfig.extra``).
        - Log un warning pour les champs vraiment inconnus dont la
          forme n'est pas un extra légitime.
        - Lève ``ValueError`` si un champ requis manque ou est null.
        """
        # 1) Normalisation Astro → Python (camel → snake, drop UI fields).
        normalized = normalize_payload(payload)

        # 2) Injection / validation de l'id attendu (vient du nom de fichier).
        if expected_id is not None:
            payload_id = normalized.get("id")
            if payload_id is None:
                normalized["id"] = expected_id
            elif payload_id != expected_id:
                raise ValueError(
                    f"id mismatch : attendu {expected_id!r}, "
                    f"trouvé {payload_id!r} dans le payload."
                )

        # 3) Champs requis : distinguer absent vs null (les deux sont
        #    fatals, mais on remonte un message clair en français).
        missing = [
            k for k in _REQUIRED_FIELDS
            if k not in normalized or normalized.get(k) is None
        ]
        if missing:
            raise ValueError(
                f"Champs requis manquants dans la config : {missing}"
            )

        # 4) Schema version : warn si version inconnue (forward-compat).
        sv = normalized.get("schema_version")
        if sv is not None and isinstance(sv, int) and sv > CURRENT_SCHEMA_VERSION:
            _log.warning(
                "schemaVersion=%s supérieur à la version connue (%s). "
                "Champs récents potentiellement ignorés.",
                sv,
                CURRENT_SCHEMA_VERSION,
            )

        # 5) Tri schema vs extras vs warnings.
        known = {f.name for f in fields(cls)}
        kwargs: dict[str, Any] = {}
        extras: dict[str, Any] = {}
        for k, v in normalized.items():
            if k == "extra":
                # `extra` explicite (cas roundtrip from asdict) — on le
                # fusionnera plus bas.
                if isinstance(v, Mapping):
                    extras.update(v)
                continue
            if k in known:
                # Description: None → "" (Astro permet d'omettre,
                # le schéma exige str)
                if k == "description" and v is None:
                    v = ""
                # Tuple-ify les listes pour les champs tuple
                if k in _TUPLE_FIELDS and isinstance(v, list):
                    v = tuple(v)
                kwargs[k] = v
            else:
                # Champ vraiment inconnu : warning + stash dans extras
                # (le fork peut le récupérer via cfg.extra[k]).
                _log.warning(
                    "Champ inconnu dans la config source : %s (préservé dans `extra`).",
                    k,
                )
                extras[k] = v

        if extras:
            kwargs.setdefault("extra", extras)

        return cls(**kwargs)
