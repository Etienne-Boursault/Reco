"""Tests cross-stack Python ↔ Zod (Astro) sur les configs sources.

Stratégie pragmatique (issue #2) : on ne génère pas un JSON Schema unique
(overkill pour 1-2 sources). On vérifie à la place que **chaque** fichier
de `src/content/sources/*.json` est chargeable côté Python sans warning ni
erreur — preuve qu'il n'y a pas de drift Astro→Python.

La vérification Zod côté Node est laissée à `npm run build` (CI), qui
échoue déjà si une config sort du schéma.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from tools.config.loader import DEFAULT_SOURCES_DIR
from tools.config.schema import SourceConfig

# Chemin vers la collection Astro (SSOT projet).
_SOURCES_DIR = DEFAULT_SOURCES_DIR


def _list_real_source_files() -> list[Path]:
    return sorted(p for p in _SOURCES_DIR.glob("*.json") if not p.name.startswith("_"))


@pytest.mark.parametrize(
    "path",
    _list_real_source_files(),
    ids=lambda p: p.stem,
)
def test_each_source_json_loads_without_unknown_field_warning(path: Path, caplog):
    """Charge chaque fichier de la SSOT projet via `SourceConfig.from_dict`.

    Échoue si :
      - le JSON est cassé / le schéma Python refuse la valeur ;
      - un champ du JSON est inconnu de Python (= drift Astro→Python).
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    with caplog.at_level(logging.WARNING, logger="reco.config"):
        cfg = SourceConfig.from_dict(payload, expected_id=path.stem)
    assert isinstance(cfg, SourceConfig)
    # Aucun warning "Champ inconnu" — sinon c'est un signal de drift.
    unknown = [
        r for r in caplog.records
        if "inconnu" in r.message.lower()
    ]
    assert not unknown, (
        f"Drift détecté dans {path.name} : "
        f"{[r.message for r in unknown]}"
    )


def test_real_ssot_has_at_least_one_source():
    """Sanity : la SSOT projet n'est pas vide (sinon les tests ci-dessus
    sont triviaux)."""
    assert len(_list_real_source_files()) >= 1
