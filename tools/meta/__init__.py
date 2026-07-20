"""tools.meta — Méta-agrégateur de registries Reco.

Package autonome (pas de dépendance circulaire avec `common`) qui :

  - valide un document `reco-registry.json` (schemaVersion=1) ;
  - fetche les registries déclarés dans un fichier (YAML/JSON) ;
  - agrège les résultats en un `meta_index.json` consommable par les pages
    Astro sous `/_meta/`.

Cf. ADR 0045.
"""
from __future__ import annotations

from .validator import RegistryValidationError, validate_registry
from .aggregator import aggregate_entries, dedupe_by_slug, slug_from_site_url
from .fetcher import RegistryFetchError, RegistryFetcher, load_registries_file

__all__ = [
    "RegistryValidationError",
    "validate_registry",
    "aggregate_entries",
    "dedupe_by_slug",
    "slug_from_site_url",
    "RegistryFetchError",
    "RegistryFetcher",
    "load_registries_file",
]
