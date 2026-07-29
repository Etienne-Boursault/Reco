"""tools.meta — Méta-agrégateur de registries Reco.

Package autonome (pas de dépendance circulaire avec `common`) qui :

  - valide un document `reco-registry.json` (schemaVersion=1) ;
  - fetche les registries déclarés dans un fichier (YAML/JSON) ;
  - agrège les résultats en un `meta_index.json` consommable par les pages
    Astro sous `/_meta/`.

Cf. ADR 0045.
"""
from __future__ import annotations

from .aggregator import aggregate_entries, dedupe_by_slug, slug_from_site_url
from .fetcher import RegistryFetcher, RegistryFetchError, load_registries_file
from .validator import RegistryValidationError, validate_registry

__all__ = [
    "RegistryFetchError",
    "RegistryFetcher",
    "RegistryValidationError",
    "aggregate_entries",
    "dedupe_by_slug",
    "load_registries_file",
    "slug_from_site_url",
    "validate_registry",
]
