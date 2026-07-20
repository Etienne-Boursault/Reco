"""Tests du registry (orchestration : list + get cached)."""

from __future__ import annotations

import json
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


def _write(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _valid(id_: str, **overrides) -> dict:
    # Préfixe : 2-8 chars (_RE_PREFIX). On padd avec 'x' si trop court.
    raw_prefix = (id_.replace("-", "")[:3] or "src")
    if len(raw_prefix) < 2:
        raw_prefix = (raw_prefix + "xx")[:8]
    base = {
        "id": id_,
        "title": id_.title(),
        "reco_prefix": raw_prefix,
        "hosts": ["A", "B"],
    }
    base.update(overrides)
    return base


@pytest.fixture
def reg(tmp_path: Path) -> SourceRegistry:
    d = tmp_path / "sources"
    d.mkdir()
    return SourceRegistry(sources_dir=d)


# ---------------------------------------------------------------------------
# list_sources
# ---------------------------------------------------------------------------


def test_list_sources_empty(reg: SourceRegistry):
    assert reg.list_sources() == []


def test_list_sources_returns_all_valid_configs(reg: SourceRegistry):
    _write(reg.sources_dir / "alpha.json", _valid("alpha"))
    _write(reg.sources_dir / "beta.json", _valid("beta"))
    ids = sorted(c.id for c in reg.list_sources())
    assert ids == ["alpha", "beta"]


def test_list_sources_skips_invalid_with_log_warning(reg: SourceRegistry, caplog):
    import logging
    _write(reg.sources_dir / "ok.json", _valid("ok"))
    # JSON cassé
    (reg.sources_dir / "broken.json").write_text("{nope", encoding="utf-8")
    # Schéma invalide (id contient une majuscule)
    _write(reg.sources_dir / "bad.json", _valid("bad", reco_prefix="UPPER"))

    with caplog.at_level(logging.WARNING, logger="reco.config"):
        results = reg.list_sources()

    ids = [c.id for c in results]
    assert ids == ["ok"]
    # Au moins deux warnings (broken + bad)
    messages = "\n".join(r.message for r in caplog.records)
    assert "broken.json" in messages
    assert "bad.json" in messages


def test_list_sources_ignores_non_json(reg: SourceRegistry):
    _write(reg.sources_dir / "ok.json", _valid("ok"))
    (reg.sources_dir / "README.md").write_text("# Hello", encoding="utf-8")
    assert [c.id for c in reg.list_sources()] == ["ok"]


def test_list_sources_missing_dir_returns_empty(tmp_path: Path):
    reg = SourceRegistry(sources_dir=tmp_path / "does-not-exist")
    assert reg.list_sources() == []


# ---------------------------------------------------------------------------
# get_source + cache
# ---------------------------------------------------------------------------


def test_get_source_returns_config(reg: SourceRegistry):
    _write(reg.sources_dir / "alpha.json", _valid("alpha"))
    cfg = reg.get_source("alpha")
    assert isinstance(cfg, SourceConfig)
    assert cfg.id == "alpha"


def test_get_source_caches_result(reg: SourceRegistry):
    p = _write(reg.sources_dir / "alpha.json", _valid("alpha"))
    cfg1 = reg.get_source("alpha")
    # Mute le fichier sous le pied : le cache doit retourner l'ancienne version.
    _write(p, _valid("alpha", title="Modifié"))
    cfg2 = reg.get_source("alpha")
    # On compare l'égalité (et le titre) — pas l'identité d'instance,
    # afin de ne pas figer le détail d'implémentation du cache (issue #21).
    assert cfg2 == cfg1
    assert cfg2.title == "Alpha"  # ancien titre (cache)


def test_clear_cache_forces_reload(reg: SourceRegistry):
    p = _write(reg.sources_dir / "alpha.json", _valid("alpha"))
    reg.get_source("alpha")
    _write(p, _valid("alpha", title="Modifié"))
    reg.clear_cache()
    cfg2 = reg.get_source("alpha")
    assert cfg2.title == "Modifié"


def test_get_source_unknown_raises(reg: SourceRegistry):
    with pytest.raises(ConfigLoadError, match="introuvable"):
        reg.get_source("ghost")


# ---------------------------------------------------------------------------
# Helpers module-level (registry par défaut sur SSOT projet)
# ---------------------------------------------------------------------------


def test_module_level_get_source_uses_project_ssot():
    """`get_source('un-bon-moment')` doit marcher sans paramètre (SSOT projet)."""
    clear_default_registry_cache()
    cfg = get_source("un-bon-moment")
    assert cfg.id == "un-bon-moment"
    assert cfg.title == "Un Bon Moment"


def test_module_level_list_sources_returns_project_sources():
    clear_default_registry_cache()
    ids = [c.id for c in list_sources()]
    assert "un-bon-moment" in ids


# ---------------------------------------------------------------------------
# Factory injectable (issue #7)
# ---------------------------------------------------------------------------


def test_get_registry_factory_returns_independent_instances(tmp_path: Path):
    """`get_registry(sources_dir=...)` renvoie une instance dédiée
    (n'affecte pas le singleton)."""
    from tools.config.registry import get_registry

    d1 = tmp_path / "a"; d1.mkdir()
    d2 = tmp_path / "b"; d2.mkdir()
    r1 = get_registry(sources_dir=d1)
    r2 = get_registry(sources_dir=d2)
    assert r1 is not r2
    assert r1.sources_dir == d1
    assert r2.sources_dir == d2
    # Le singleton par défaut reste distinct.
    default = get_registry()
    assert default is not r1 and default is not r2


def test_get_source_accepts_injected_registry(reg: SourceRegistry):
    """`get_source(id, registry=...)` court-circuite le singleton."""
    from tools.config.registry import get_source as mod_get_source

    _write(reg.sources_dir / "alpha.json", _valid("alpha"))
    cfg = mod_get_source("alpha", registry=reg)
    assert cfg.id == "alpha"


# ---------------------------------------------------------------------------
# Thread-safety (issue #8)
# ---------------------------------------------------------------------------


def test_concurrent_get_source_no_race(reg: SourceRegistry):
    """Plusieurs threads peuvent appeler `get_source` en parallèle sans
    race ni KeyError sur le cache."""
    import threading

    _write(reg.sources_dir / "alpha.json", _valid("alpha"))
    results: list = []
    errors: list = []

    def worker():
        try:
            results.append(reg.get_source("alpha"))
        except Exception as exc:  # pragma: no cover — pas attendu
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(results) == 50
    # Toutes les references doivent pointer vers la même instance cache.
    first = results[0]
    assert all(r is first for r in results)


# ---------------------------------------------------------------------------
# clear_default_registry_cache réinitialise (issue #9)
# ---------------------------------------------------------------------------


def test_clear_default_registry_cache_recreates_singleton(monkeypatch, tmp_path: Path):
    """Après `clear_default_registry_cache()`, le singleton est re-créé —
    utile si on a monkeypatché `DEFAULT_SOURCES_DIR` entre deux appels."""
    from tools.config import loader as loader_mod
    from tools.config import registry as reg_mod

    d1 = tmp_path / "v1"; d1.mkdir()
    _write(d1 / "alpha.json", _valid("alpha"))

    # 1) Premier registry pointe sur v1.
    monkeypatch.setattr(loader_mod, "DEFAULT_SOURCES_DIR", d1)
    clear_default_registry_cache()
    r1 = reg_mod.get_registry()
    assert r1.sources_dir == d1
    assert r1.get_source("alpha").id == "alpha"

    # 2) On change le chemin par défaut → clear → nouveau singleton.
    d2 = tmp_path / "v2"; d2.mkdir()
    _write(d2 / "beta.json", _valid("beta"))
    monkeypatch.setattr(loader_mod, "DEFAULT_SOURCES_DIR", d2)
    clear_default_registry_cache()
    r2 = reg_mod.get_registry()
    assert r2 is not r1
    assert r2.sources_dir == d2
    assert r2.get_source("beta").id == "beta"


# ---------------------------------------------------------------------------
# `_*.json` ignoré (issue #25), tri (issue #38), enabled (issue #26)
# ---------------------------------------------------------------------------


def test_list_sources_skips_underscore_prefixed_files(reg: SourceRegistry):
    """Les fichiers `_*.json` sont des brouillons — ignorés silencieusement."""
    _write(reg.sources_dir / "alpha.json", _valid("alpha"))
    _write(reg.sources_dir / "_draft.json", _valid("draft"))
    ids = [c.id for c in reg.list_sources()]
    assert ids == ["alpha"]


def test_list_sources_excludes_disabled_by_default(reg: SourceRegistry):
    _write(reg.sources_dir / "alpha.json", _valid("alpha"))
    _write(reg.sources_dir / "beta.json", _valid("beta", enabled=False))
    ids = [c.id for c in reg.list_sources()]
    assert ids == ["alpha"]


def test_list_sources_include_disabled_flag(reg: SourceRegistry):
    _write(reg.sources_dir / "alpha.json", _valid("alpha"))
    _write(reg.sources_dir / "beta.json", _valid("beta", enabled=False))
    ids = sorted(c.id for c in reg.list_sources(include_disabled=True))
    assert ids == ["alpha", "beta"]


def test_list_sources_sorted_by_id(reg: SourceRegistry):
    _write(reg.sources_dir / "z.json", _valid("zz"))  # id z mappe à zz (prefix 2 chars)
    _write(reg.sources_dir / "alpha.json", _valid("alpha"))
    _write(reg.sources_dir / "m.json", _valid("mm"))
    ids = [c.id for c in reg.list_sources()]
    assert ids == sorted(ids)
