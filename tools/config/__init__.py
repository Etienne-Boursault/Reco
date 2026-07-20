"""Configuration multi-source du pipeline Reco.

Couches Clean Architecture :
  - ``schema``   : dataclass `SourceConfig` (DOMAINE pur, sans I/O).
  - ``loader``   : `load_source_config` (couche IO — lit le JSON disque).
  - ``registry`` : `list_sources` / `get_source` (orchestration / cache).

Convention SSOT : la source de vérité d'une source est
``src/content/sources/<id>.json`` — déjà consommé par Astro côté site.
On enrichit ce même fichier des champs propres au pipeline Python, sans
dupliquer la donnée.
"""

from tools.config.schema import SourceConfig

__all__ = ["SourceConfig"]
