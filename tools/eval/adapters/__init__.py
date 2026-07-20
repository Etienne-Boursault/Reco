"""Adaptateurs : transforment des types externes en ``ExtractedReco``."""
from __future__ import annotations

from tools.eval.adapters.legacy_reco_adapter import (
    LegacyRecoExtractionSource,
    legacy_recos_to_extracted,
)

__all__ = ["LegacyRecoExtractionSource", "legacy_recos_to_extracted"]
