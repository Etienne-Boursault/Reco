"""Configuration partagée des tests. Le pyproject.toml ajoute `tools/` au
pythonpath, donc on peut importer `common`, `match_youtube`, etc. directement."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Sources synthétiques injectées dans le registry pour les tests qui
# utilisent des ids fictifs (ex. "demo-source") via `reco_prefix(...)` ou
# `_allocate_new_reco(...)`.
#
# Depuis l'issue #14 (suppression du fallback heuristique de `reco_prefix`),
# tout id qui n'a pas de config JSON lève FileNotFoundError. On dote
# donc la suite d'un mini-registry de tests pour ne pas avoir à
# matérialiser un fichier JSON dans chaque test.
# ---------------------------------------------------------------------------

_SYNTHETIC_TEST_SOURCES: dict[str, dict[str, Any]] = {
    "demo-source": {
        "id": "demo-source",
        "title": "Demo Source",
        # Conserve l'ancien préfixe heuristique ("demo-source" → "ds")
        # pour respecter les assertions historiques sur les IDs de recos
        # générés par `_allocate_new_reco`.
        "reco_prefix": "ds",
        "hosts": ("Demo Host",),
    },
    "demo-src": {
        "id": "demo-src",
        "title": "Demo Src",
        "reco_prefix": "ds",
        "hosts": ("Demo Host",),
    },
    "x": {
        "id": "x",
        "title": "X",
        "reco_prefix": "xx",
        "hosts": ("X",),
    },
    "src": {
        "id": "src",
        "title": "Src",
        "reco_prefix": "src",
        "hosts": ("Host",),
    },
}


@pytest.fixture(autouse=True)
def _seed_synthetic_sources_in_registry(monkeypatch):
    """Précharge des `SourceConfig` synthétiques dans le registry par défaut,
    avec auto-vivification pour les ids inconnus.

    Garantit que `reco_prefix("demo-source")` (utilisé par de nombreux
    tests historiques) renvoie une valeur sans nécessiter de fichier
    JSON physique. Sans ce shim, l'issue #14 (config-only, plus
    d'heuristique) casserait ~15 tests legacy.

    Implémentation : on remplace ``_default_registry`` par une sous-classe
    qui :
      - 1) renvoie un cache pré-rempli avec les entrées connues
           (`_SYNTHETIC_TEST_SOURCES`) ;
      - 2) tente la lecture disque réelle (utile pour les tests qui
           pointent une vraie SSOT, comme `un-bon-moment`) ;
      - 3) en cas d'absence ou d'erreur, fabrique un `SourceConfig`
           synthétique reproduisant l'ancienne heuristique des initiales.
    """
    from tools.config import registry as reg_mod
    from tools.config.loader import ConfigLoadError
    from tools.config.schema import SourceConfig

    def _heuristic_prefix(source_id: str) -> str:
        """Reproduit l'ancienne heuristique pour fabriquer un préfixe par défaut."""
        import re as _re

        segments = [s for s in source_id.split("-") if s]
        initials = "".join(s[0] for s in segments if s)
        if len(initials) >= 2:
            # Cap à 8 car _RE_PREFIX = {2,8}
            return initials[:8] or "xx"
        return (_re.sub(r"[^a-z0-9]", "", source_id)[:3] or "rec").ljust(2, "x")[:8]

    class _AutoSourceRegistry(reg_mod.SourceRegistry):
        def get_source(self, source_id):  # type: ignore[override]
            cached = self._cache.get(source_id)
            if cached is not None:
                return cached
            # 1) Tentative lecture disque (vraie SSOT pour `un-bon-moment`).
            try:
                cfg = super().get_source(source_id)
                return cfg
            except ConfigLoadError:
                pass
            # 2) Fabrication d'un synthétique (DRY heuristique).
            synth = SourceConfig(
                id=source_id,
                title=source_id.replace("-", " ").title() or "Synth",
                reco_prefix=_heuristic_prefix(source_id),
                hosts=("Synthetic",),
            )
            self._cache[source_id] = synth
            return synth

    fresh = _AutoSourceRegistry()
    for sid, kwargs in _SYNTHETIC_TEST_SOURCES.items():
        fresh._cache[sid] = SourceConfig(**kwargs)
    monkeypatch.setattr(reg_mod, "_default_registry", fresh)
    yield


@pytest.fixture(autouse=True)
def _isolate_review_lock_paths(tmp_path_factory, monkeypatch):
    """Isole les fichiers verrou de tools/review_lock sur un dossier temp
    par test.

    Pourquoi autouse : beaucoup de tests appellent `extract_recos.main` /
    `enrich_*.main` qui prennent maintenant un verrou pipeline. Sans
    isolation, deux tests qui appellent `main()` se gêneraient mutuellement
    (et un review_server qui tourne sur la machine du dev bloquerait
    toute la suite). On redirige donc systématiquement les paths du
    verrou vers un dossier temp dédié.
    """
    import review_lock
    d = tmp_path_factory.mktemp("review_lock")
    monkeypatch.setattr(review_lock, "_LOCK_DIR", d)
    monkeypatch.setattr(
        review_lock, "_SERVER_LOCK_PATH", d / ".review_server.lock",
    )
    monkeypatch.setattr(
        review_lock, "_PIPELINE_LOCK_PATH", d / ".review_pipeline.lock",
    )


@pytest.fixture
def anthropic_client_returning():
    """Factory : fabrique un MagicMock Anthropic dont messages.create renvoie
    un message texte donné. Mutualise un helper qui était dupliqué entre
    test_ocr_thumbnails.py et test_rematch_with_ocr_main.py."""

    def _make(text: str):
        block = SimpleNamespace(type="text", text=text)
        msg = SimpleNamespace(content=[block])
        client = MagicMock()
        client.messages.create.return_value = msg
        return client

    return _make


@pytest.fixture
def tmp_episode_json(tmp_path: Path):
    """Factory qui crée un fichier JSON d'épisode à `tmp_path / file`."""

    def _make(name: str, data: dict[str, Any]) -> Path:
        p = tmp_path / name
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return p

    return _make
