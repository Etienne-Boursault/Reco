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
    """Isole chaque test sur ses propres fichiers verrou (verrous ET `.pid`
    siblings — sinon les tests écriraient dans le vrai `tools/output/`)."""
    monkeypatch.setattr(
        review_lock, "_LOCK_DIR", tmp_path,
    )
    monkeypatch.setattr(
        review_lock, "_SERVER_LOCK_PATH", tmp_path / ".review_server.lock",
    )
    monkeypatch.setattr(
        review_lock, "_PIPELINE_LOCK_PATH", tmp_path / ".review_pipeline.lock",
    )
    monkeypatch.setattr(
        review_lock, "_SERVER_PID_PATH", tmp_path / ".review_server.pid",
    )
    monkeypatch.setattr(
        review_lock, "_PIPELINE_PID_PATH", tmp_path / ".review_pipeline.pid",
    )


class _FlakyLock:
    """Verrou factice dont `release()` échoue — simule un filelock déjà
    invalidé (fichier supprimé sous nos pieds, FS réseau…)."""

    def __init__(self):
        self.released = False

    def release(self):
        self.released = True
        raise RuntimeError("filelock déjà relâché")


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
    with pytest.raises(ValueError), review_lock.acquire_pipeline_lock():
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


# ===== _peek_locked =========================================================
def test_peek_reports_free_when_no_lockfile():
    assert review_lock._peek_locked(review_lock._PIPELINE_LOCK_PATH) is False


def test_peek_reports_free_when_lockfile_is_a_leftover():
    """Un lockfile résiduel (process tué sans release propre) ne doit PAS être
    pris pour un verrou actif : sinon plus rien ne redémarrerait sans ménage
    manuel dans `tools/output/`."""
    leftover = review_lock._PIPELINE_LOCK_PATH
    leftover.parent.mkdir(parents=True, exist_ok=True)
    leftover.touch()

    assert review_lock._peek_locked(leftover) is False
    # Et le pipeline redémarre bien malgré le résidu.
    with review_lock.acquire_pipeline_lock():
        pass


def test_peek_reports_taken_while_held():
    with review_lock.acquire_pipeline_lock():
        assert review_lock._peek_locked(review_lock._PIPELINE_LOCK_PATH) is True


# ===== message UX : indice de PID ==========================================
def test_server_busy_message_includes_pid_when_available():
    with review_lock.acquire_server_lock():
        import os
        with pytest.raises(review_lock.ServerLockBusy) as err:
            with review_lock.acquire_pipeline_lock():
                pass
    assert f"(PID {os.getpid()})" in str(err.value)


def test_server_busy_message_omits_pid_when_file_missing():
    """Sans fichier `.pid` lisible, le message reste utilisable (pas de crash,
    juste pas d'indice de PID)."""
    with review_lock.acquire_server_lock():
        review_lock._SERVER_PID_PATH.unlink()
        with pytest.raises(review_lock.ServerLockBusy) as err:
            with review_lock.acquire_pipeline_lock():
                pass
    assert "PID" not in str(err.value)
    assert "--force" in str(err.value)


def test_server_busy_message_omits_pid_when_file_empty():
    with review_lock.acquire_server_lock():
        review_lock._SERVER_PID_PATH.write_text("  \n", encoding="utf-8")
        with pytest.raises(review_lock.ServerLockBusy) as err:
            with review_lock.acquire_pipeline_lock():
                pass
    assert "PID" not in str(err.value)


# ===== robustesse : le diagnostic ne casse jamais le run ====================
def test_server_starts_even_if_pid_file_cannot_be_written(monkeypatch, tmp_path):
    """Le `.pid` est purement diagnostique : un disque en lecture seule ne doit
    pas empêcher le serveur de démarrer."""
    unwritable = tmp_path / "sous-dossier-absent" / ".review_server.pid"
    monkeypatch.setattr(review_lock, "_SERVER_PID_PATH", unwritable)

    with review_lock.acquire_server_lock():
        assert not unwritable.exists()


def test_pipeline_starts_even_if_pid_file_cannot_be_written(monkeypatch, tmp_path):
    unwritable = tmp_path / "sous-dossier-absent" / ".review_pipeline.pid"
    monkeypatch.setattr(review_lock, "_PIPELINE_PID_PATH", unwritable)

    with review_lock.acquire_pipeline_lock():
        assert not unwritable.exists()


@pytest.mark.parametrize("acquire, pid_attr", [
    (review_lock.acquire_server_lock, "_SERVER_PID_PATH"),
    (review_lock.acquire_pipeline_lock, "_PIPELINE_PID_PATH"),
])
def test_release_failure_is_swallowed(monkeypatch, acquire, pid_attr):
    """Un `release()` qui échoue ne doit pas faire remonter d'exception depuis
    le `finally` (best-effort documenté)."""
    flaky = _FlakyLock()
    monkeypatch.setattr(review_lock, "_try_acquire",
                        lambda path, *, role: flaky)
    monkeypatch.setattr(review_lock, "_peek_locked", lambda path: False)

    with acquire():
        pass

    assert flaky.released is True
    assert not getattr(review_lock, pid_attr).exists()


@pytest.mark.parametrize("acquire, pid_attr", [
    (review_lock.acquire_server_lock, "_SERVER_PID_PATH"),
    (review_lock.acquire_pipeline_lock, "_PIPELINE_PID_PATH"),
])
def test_pid_cleanup_failure_is_swallowed(monkeypatch, acquire, pid_attr):
    """Idem pour la suppression du `.pid` en sortie."""
    from pathlib import Path

    real_unlink = Path.unlink

    def _boom(self, missing_ok=False):
        if self.name.endswith(".pid"):
            raise OSError("fichier verrouillé")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _boom)

    with acquire():
        pass

    # Le `.pid` n'a pas pu être nettoyé, mais aucune exception n'a fui.
    assert getattr(review_lock, pid_attr).exists()


def test_forced_pipeline_runs_without_lock_and_releases_nothing():
    """`force=True` alors qu'un autre pipeline tient déjà le verrou : le bloc
    s'exécute SANS verrou (`lock is None`) — ni écriture de `.pid`, ni release
    au finally."""
    with review_lock.acquire_pipeline_lock():
        review_lock._PIPELINE_PID_PATH.unlink()
        with review_lock.acquire_pipeline_lock(force=True):
            assert not review_lock._PIPELINE_PID_PATH.exists()
    # Le verrou du premier contexte est bien libéré à sa propre sortie.
    with review_lock.acquire_pipeline_lock():
        pass
