"""Inventaire figé des imports legacy `Reco` / `Episode` / `RecoRepository`.

Cf. ADR 0008. Toute nouvelle utilisation au sein de `tools/` doit être
explicitée en mettant à jour `FROZEN_USAGES`. La frontière legacy est
**monotonement décroissante** : on n'autorise pas de nouvelle entrée
sans contre-justification écrite.
"""
from __future__ import annotations

import re
from pathlib import Path

_LEGACY_TYPES = ("Reco", "Episode", "TranscriptSegment", "TranscriptStore",
                 "RecoRepository", "EpisodeRepository", "RecoExtractor")

# Snapshot daté du 2026-06-10 (post P1.2.B / P1.2.C / Phase A fixes).
# Chaque entrée = chemin relatif depuis la racine du repo. Une entrée doit
# être justifiée en commentaire de fin de ligne.
FROZEN_USAGES: frozenset[str] = frozenset({
    # (Aucun call-site production restant — la migration P1.2 a éliminé
    # toutes les utilisations directes des entités legacy hors du package
    # `tools/domain/` qui les expose pour rétro-compat.)
})


def _scan_legacy_imports(root: Path) -> set[str]:
    """Retourne l'ensemble des fichiers `tools/*.py` important une entité legacy.

    Critère : ligne du type ``from domain import …<LegacyType>…`` ou
    ``from domain._legacy import …``. Ignore le package `tools/domain/`
    lui-même (qui DOIT héberger les types legacy pour pouvoir les exporter).
    """
    pattern = re.compile(
        r"^\s*from\s+(?:domain\._legacy|domain)\s+import\s+([^\n]+)",
        re.MULTILINE,
    )
    legacy_names = set(_LEGACY_TYPES)
    out: set[str] = set()
    for path in root.rglob("*.py"):
        rel = path.relative_to(root.parent).as_posix()
        # Ne pas auto-flag le package domaine.
        if rel.startswith("tools/domain/"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for match in pattern.finditer(text):
            imported = match.group(1)
            # Match brut "from domain._legacy import X" → toujours legacy.
            if "_legacy" in match.group(0):
                out.add(rel)
                break
            # Match "from domain import …" → vérifier que la liste contient
            # un type legacy parmi les noms importés.
            tokens = re.findall(r"[A-Za-z_]+", imported)
            if any(tok in legacy_names for tok in tokens):
                out.add(rel)
                break
    return out


def test_no_new_callsite_for_legacy_imports():
    """Inventaire figé. Toute nouvelle utilisation de `Reco`/`Episode`/…
    doit être justifiée et ajoutée explicitement à `FROZEN_USAGES`."""
    root = Path(__file__).resolve().parent.parent / "tools"
    assert root.exists(), f"Racine tools/ introuvable: {root}"
    actual = _scan_legacy_imports(root)
    new = actual - FROZEN_USAGES
    assert not new, (
        f"Nouvelle utilisation legacy détectée : {sorted(new)}.\n"
        "Si l'ajout est volontaire, mets à jour FROZEN_USAGES dans "
        "tests/test_legacy_imports_inventory.py et documente le rationale "
        "(cf. ADR 0008)."
    )
    # Détection des entrées obsolètes : si une entrée listée n'existe plus
    # dans actual, la liste devrait être réduite — mais on ne casse PAS
    # le build pour ça (juste warning informationnel).
    stale = FROZEN_USAGES - actual
    if stale:
        # Pas un assert : on encourage juste à nettoyer.
        import warnings
        warnings.warn(
            f"FROZEN_USAGES contient des entrées obsolètes (à retirer): "
            f"{sorted(stale)}",
            stacklevel=2,
        )


def test_scan_helper_handles_unreadable_files(tmp_path, monkeypatch):
    """Couverture de la branche OSError du scanner."""
    # Crée un fichier puis simule read_text qui raise.
    fake = tmp_path / "tools" / "fake.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("from domain import Reco\n", encoding="utf-8")

    original = Path.read_text

    def boom(self, *a, **k):
        if self == fake:
            raise OSError("simulated")
        return original(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", boom)
    result = _scan_legacy_imports(tmp_path / "tools")
    # fake.py est illisible → doit être skipped (pas d'erreur, pas dans le set).
    assert "tools/fake.py" not in result
