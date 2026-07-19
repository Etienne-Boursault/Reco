"""Tests de tools/review_lock.py — coordination serveur ↔ pipeline.

On vérifie :
  - acquérir le verrou serveur empêche un script pipeline de démarrer,
  - acquérir le verrou pipeline empêche le serveur de démarrer,
  - `force=True` côté pipeline ignore le verrou serveur (escape hatch),
  - les verrous sont libérés correctement à la sortie du context manager.

Note : on patche `_SERVER_LOCK_PATH` et `_PIPELINE_LOCK_PATH` sur `tmp_path`
pour isoler les tests et permettre l'exécution en parallèle d'une instance
réelle du serveur sur la machine du dev.
"""
from __future__ import annotations

import pytest

import review_lock


@pytest.fixture(autouse=True)
def _redirect_lock_paths(tmp_path, monkeypatch):
    """Isole chaque test sur ses propres fichiers verrou."""
    monkeypatch.setattr(
        review_lock, "_LOCK_DIR", tmp_path,
    )
    monkeypatch.setattr(
        review_lock, "_SERVER_LOCK_PATH", tmp_path / ".review_server.lock",
    )
    monkeypatch.setattr(
        review_lock, "_PIPELINE_LOCK_PATH", tmp_path / ".review_pipeline.lock",
    )


def test_pipeline_lock_acquires_when_server_down():
    """Cas nominal : serveur arrêté → pipeline peut démarrer."""
    with review_lock.acquire_pipeline_lock():
        pass  # acquis + libéré sans erreur


def test_server_lock_acquires_when_pipeline_down():
    """Cas nominal : pipeline arrêté → serveur peut démarrer."""
    with review_lock.acquire_server_lock():
        pass


def test_pipeline_refuses_when_server_holds_lock():
    """Si le serveur tient le verrou, pipeline doit échouer (ServerLockBusy)."""
    with review_lock.acquire_server_lock():
        with pytest.raises(review_lock.ServerLockBusy) as excinfo:
            with review_lock.acquire_pipeline_lock():
                pass
        # Message UX : doit mentionner review_server explicitement.
        assert "review_server" in str(excinfo.value).lower()


def test_pipeline_force_bypasses_server_lock():
    """`--force` (force=True) doit permettre au pipeline de tourner même
    quand le serveur a son verrou — escape hatch documenté."""
    with review_lock.acquire_server_lock():
        # Ne doit PAS lever malgré le verrou serveur.
        with review_lock.acquire_pipeline_lock(force=True):
            pass


def test_server_refuses_when_pipeline_holds_lock():
    """Si un script pipeline tient son verrou, serveur refuse de démarrer."""
    with review_lock.acquire_pipeline_lock():
        with pytest.raises(review_lock.PipelineLockBusy):
            with review_lock.acquire_server_lock():
                pass


def test_release_after_use_allows_new_acquire():
    """Après libération, le verrou doit être réacquérable (pas de fuite)."""
    with review_lock.acquire_pipeline_lock():
        pass
    # Doit pouvoir re-prendre immédiatement.
    with review_lock.acquire_pipeline_lock():
        pass


def test_release_even_on_exception():
    """Le contexte libère le verrou même si le bloc lève."""
    with pytest.raises(ValueError):
        with review_lock.acquire_pipeline_lock():
            raise ValueError("boom")
    # Vérifie : on peut re-prendre.
    with review_lock.acquire_pipeline_lock():
        pass


def test_pid_written_to_sibling_file():
    """Le PID est écrit dans un fichier SIBLING (.pid) — pas dans le lockfile
    lui-même, sinon Windows refuse la lecture concurrente (filelock exclusif)."""
    import os
    with review_lock.acquire_server_lock():
        content = review_lock._SERVER_PID_PATH.read_text(encoding="utf-8")
        assert content.strip() == str(os.getpid())
    # Cleanup au release : le .pid est supprimé
    assert not review_lock._SERVER_PID_PATH.exists()


# ===== Conflits même-rôle (revue 2026-07-19) ================================
def test_second_server_raises_server_lock_busy():
    """Deux serveurs en parallèle : le second doit échouer (ServerLockBusy)."""
    with review_lock.acquire_server_lock():
        with pytest.raises(review_lock.ServerLockBusy):
            with review_lock.acquire_server_lock():
                pass


def test_second_pipeline_raises_pipeline_lock_busy():
    """Deux scripts pipeline en parallèle : le second doit échouer
    (PipelineLockBusy) — le verrou serveur n'étant pas tenu, c'est bien le
    conflit pipeline↔pipeline qui est levé."""
    with review_lock.acquire_pipeline_lock():
        with pytest.raises(review_lock.PipelineLockBusy):
            with review_lock.acquire_pipeline_lock():
                pass


def test_lock_busy_hierarchy():
    """`ServerLockBusy` et `PipelineLockBusy` dérivent de `LockBusy` (capture
    générique possible côté appelant)."""
    assert issubclass(review_lock.ServerLockBusy, review_lock.LockBusy)
    assert issubclass(review_lock.PipelineLockBusy, review_lock.LockBusy)
    assert issubclass(review_lock.LockBusy, RuntimeError)
