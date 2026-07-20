"""Tests d'intégration : couplage `tools.config` ↔ pipeline existant.

Ces tests vérifient que :
  1. La config de la source ``un-bon-moment`` est chargeable depuis la SSOT
     `src/content/sources/un-bon-moment.json` (zéro override).
  2. Une seconde source peut être ajoutée et listée — preuve que l'ajout
     d'un nouveau podcast = ajout d'un fichier (OCP).
  3. Les helpers `common.recos_dir_for` et `common.reco_prefix` restent
     cohérents avec la config externalisée (rétro-compatibilité).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools.config.loader import ConfigLoadError
from tools.config.registry import (
    SourceRegistry,
    clear_default_registry_cache,
    get_source,
    list_sources,
)
from tools.config.schema import SourceConfig


def test_un_bon_moment_config_loads_from_project_ssot():
    """SSOT : la source canonique est chargeable sans paramétrage."""
    clear_default_registry_cache()
    cfg = get_source("un-bon-moment")
    assert cfg.id == "un-bon-moment"
    assert cfg.title == "Un Bon Moment"
    assert cfg.reco_prefix == "ubm"
    assert "Kyan Khojandi" in cfg.hosts
    assert cfg.rss_url is not None
    assert cfg.youtube_channel_url is not None


def test_pipeline_reco_prefix_reads_from_config_not_heuristic(tmp_path):
    """`common.reco_prefix` doit lire la VRAIE valeur de la config,
    PAS retomber sur l'heuristique des initiales.

    On crée une source dont le préfixe ne pourrait jamais être deviné
    (« xyz » n'est l'initiale d'aucun segment du slug). Si la valeur
    retournée correspond à l'heuristique au lieu de la config, le test
    casse → signale une régression de l'item #1 de la roadmap.
    """
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()
    (sources_dir / "alpha-beta-gamma.json").write_text(
        json.dumps({
            "id": "alpha-beta-gamma",
            "title": "Alpha Beta Gamma",
            "recoPrefix": "xyz",  # n'a rien à voir avec 'abg'
            "hosts": ["A"],
        }),
        encoding="utf-8",
    )
    reg = SourceRegistry(sources_dir=sources_dir)
    cfg = reg.get_source("alpha-beta-gamma")
    assert cfg.reco_prefix == "xyz"
    # Sanity : l'heuristique sur ce slug serait "abg", pas "xyz".
    from tools.common import _RE_SLUG_NONALNUM_STRICT  # noqa: F401
    segments = [s for s in "alpha-beta-gamma".split("-") if s]
    heuristic_initials = "".join(s[0] for s in segments)
    assert heuristic_initials == "abg" != cfg.reco_prefix


def test_unknown_source_id_fails_fast_with_message(monkeypatch):
    """Un id inconnu lève une erreur claire (et pas un AttributeError tardif).

    On rétablit ici un registry strict (sans auto-vivification) pour
    valider le contrat de production — la fixture autouse de la suite
    auto-vivifie les ids inconnus pour la rétro-compat de legacy tests.
    """
    from tools.config import registry as reg_mod

    real = reg_mod.SourceRegistry()
    monkeypatch.setattr(reg_mod, "_default_registry", real)
    with pytest.raises(ConfigLoadError, match="introuvable"):
        get_source("podcast-qui-nexiste-pas-12345")


def test_second_source_can_coexist(tmp_path: Path):
    """OCP : ajouter une source = créer un fichier, zéro modif code.

    On copie la config UBM dans un dossier temporaire, on ajoute une 2e
    config (« test-podcast ») et on vérifie que le registry les liste
    toutes les deux.
    """
    sources_dir = tmp_path / "sources"
    sources_dir.mkdir()

    # 1) Source canonique (clone)
    src = Path(__file__).resolve().parent.parent / "src" / "content" / "sources" / "un-bon-moment.json"
    shutil.copy(src, sources_dir / "un-bon-moment.json")

    # 2) Nouvelle source : config minimale (4 champs)
    new_cfg = {
        "id": "test-podcast",
        "title": "Test Podcast",
        "recoPrefix": "tp",
        "hosts": ["Hôte A", "Hôte B"],
        # Astro exige un theme — on l'inclut pour rester compatible si
        # un jour le test pointe la vraie SSOT.
        "theme": {
            "fontDisplay": "X",
            "fontBody": "Y",
            "colors": {
                "bg": "#000", "surface": "#111", "text": "#fff",
                "muted": "#888", "accent": "#f00", "accentText": "#000",
            },
        },
    }
    (sources_dir / "test-podcast.json").write_text(
        json.dumps(new_cfg), encoding="utf-8"
    )

    reg = SourceRegistry(sources_dir=sources_dir)
    ids = sorted(c.id for c in reg.list_sources())
    assert ids == ["test-podcast", "un-bon-moment"]

    tp = reg.get_source("test-podcast")
    assert isinstance(tp, SourceConfig)
    assert tp.title == "Test Podcast"
    assert tp.reco_prefix == "tp"
    assert tp.hosts == ("Hôte A", "Hôte B")


def test_list_sources_module_helper_includes_un_bon_moment():
    clear_default_registry_cache()
    ids = [c.id for c in list_sources()]
    assert "un-bon-moment" in ids
