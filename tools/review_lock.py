"""review_lock.py — Coordination serveur de relecture ↔ scripts pipeline.

Problème historique : `review_server.py` et les scripts du pipeline
(`extract_recos`, `enrich_tmdb`, `enrich_music`, `migrate_*`) écrivent dans
les MÊMES fichiers JSON (`src/content/recos/<src>/`, `src/content/episodes/<src>/`)
sans coordination. Conséquences :

- une validation manuelle écrasée par un re-extract en arrière-plan,
- `read_json` qui lève `ValueError` au milieu d'une écriture non-atomique,
- caches `_RECO_PATH_CACHE` stale après un run pipeline parallèle.

Stratégie : un verrou exclusif (cross-process, cross-platform) via
`filelock`. Deux *rôles* coordonnés :

- **serveur** : tient le verrou « server » de bout en bout. Au démarrage,
  il refuse de démarrer si le verrou « pipeline » est tenu (rare en
  pratique — un humain démarre le serveur après son script).
- **scripts pipeline** : tentent d'acquérir le verrou « pipeline » au
  démarrage et REFUSENT de démarrer si le verrou « server » est déjà tenu
  (sauf `--force`). Message clair côté UX : « le review_server tourne ».

Cette approche évite la complexité d'un vrai lock shared/exclusive
(non-portable sur Windows) tout en garantissant la mutex utile : *le
serveur ne tourne JAMAIS en même temps qu'un script pipeline qui mute
les mêmes fichiers*.

API publique :

    with acquire_server_lock():
        ...  # serveur tourne, scripts pipeline refusés

    with acquire_pipeline_lock(force=args.force):
        ...  # script pipeline tourne, serveur refusé au démarrage

`PipelineLockBusy` / `ServerLockBusy` sont levées en cas de conflit, avec
un message d'erreur explicite à afficher tel quel.

Single-process re-entrancy : nos scripts ne s'imbriquent pas (chacun a
son `main()`), donc on ne gère pas la ré-entrée. Si un test importe deux
scripts qui prennent tous deux le lock, ils doivent libérer avant de
chaîner — c'est le comportement attendu (assertion explicite).
"""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import Iterator

from common import OUTPUT_DIR, log

# Fichiers verrous — dans tools/output/ pour ne PAS polluer src/content/.
# Le dossier output est déjà ignoré par git (cf. .gitignore).
_LOCK_DIR: Path = OUTPUT_DIR
_SERVER_LOCK_PATH: Path = _LOCK_DIR / ".review_server.lock"
_PIPELINE_LOCK_PATH: Path = _LOCK_DIR / ".review_pipeline.lock"
# PID écrit dans un fichier SIBLING (pas dans le lockfile lui-même) car sur
# Windows `filelock` détient le fichier en exclusif → impossible de le re-lire
# pour diagnostiquer. Le `.pid` est librement lisible.
_SERVER_PID_PATH: Path = _LOCK_DIR / ".review_server.pid"
_PIPELINE_PID_PATH: Path = _LOCK_DIR / ".review_pipeline.pid"

# Timeout court : on ne veut PAS attendre. Si le verrou est pris, c'est
# l'autre rôle qui tourne → on échoue vite avec un message clair.
_ACQUIRE_TIMEOUT_S: float = 0.5


class LockBusy(RuntimeError):
    """Le verrou est tenu par un autre processus."""


class ServerLockBusy(LockBusy):
    """Le verrou serveur est tenu — refuse de démarrer un script pipeline."""


class PipelineLockBusy(LockBusy):
    """Le verrou pipeline est tenu — refuse de démarrer le serveur."""


def _ensure_lock_dir() -> None:
    _LOCK_DIR.mkdir(parents=True, exist_ok=True)


def _import_filelock():
    """Import paresseux — `filelock` est dans requirements.txt mais on garde
    l'import retardé pour ne pas pénaliser les scripts qui ne touchent pas
    au verrou (tests unitaires de modules purs).
    """
    try:
        import filelock  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "Le module `filelock` est requis pour la coordination "
            "serveur/pipeline. Installe-le via `pip install -r "
            "tools/requirements.txt`."
        ) from exc
    return filelock


def _try_acquire(path: Path, *, role: str):
    """Tente d'acquérir un FileLock non-bloquant. Renvoie le lock acquis, ou
    None si occupé. `role` sert seulement aux logs.
    """
    filelock = _import_filelock()
    _ensure_lock_dir()
    lock = filelock.FileLock(str(path), timeout=_ACQUIRE_TIMEOUT_S)
    try:
        lock.acquire(timeout=_ACQUIRE_TIMEOUT_S)
    except filelock.Timeout:
        log.debug("Verrou %s (%s) déjà tenu", path.name, role)
        return None
    return lock


def _peek_locked(path: Path) -> bool:
    """True si `path` est actuellement verrouillé par un autre processus.

    On l'évalue en tentant un acquire non-bloquant puis en relâchant
    immédiatement. C'est OK : seul l'état « libre » vs « pris » nous
    intéresse, pas une garantie atomique entre check & acquire (qu'on
    obtient de toute façon ensuite via le vrai acquire du rôle local).
    """
    if not path.exists():
        return False
    filelock = _import_filelock()
    lock = filelock.FileLock(str(path), timeout=0)
    try:
        lock.acquire(timeout=0)
    except filelock.Timeout:
        return True
    else:
        lock.release()
        return False


@contextlib.contextmanager
def acquire_server_lock() -> Iterator[None]:
    """Contexte serveur : refuse si un script pipeline tourne, sinon tient
    le verrou pour toute la vie du serveur.

    Lève `PipelineLockBusy` si un script pipeline est déjà en cours.
    """
    if _peek_locked(_PIPELINE_LOCK_PATH):
        raise PipelineLockBusy(
            "Impossible de démarrer review_server : un script pipeline "
            "tourne actuellement (verrou tools/output/.review_pipeline.lock). "
            "Attends qu'il finisse puis relance."
        )
    lock = _try_acquire(_SERVER_LOCK_PATH, role="server")
    if lock is None:
        # Cas rare : 2 serveurs lancés en parallèle (même rôle).
        raise ServerLockBusy(
            "Un autre review_server tourne déjà "
            "(verrou tools/output/.review_server.lock)."
        )
    try:
        # Écrit le PID dans un fichier SIBLING pour diagnostic.
        try:
            _SERVER_PID_PATH.write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass  # info diagnostique uniquement — ne pas casser le démarrage.
        yield
    finally:
        try:
            lock.release()
        except Exception:  # noqa: BLE001 — on libère best-effort
            pass
        try:
            _SERVER_PID_PATH.unlink(missing_ok=True)
        except OSError:
            pass


@contextlib.contextmanager
def acquire_pipeline_lock(*, force: bool = False) -> Iterator[None]:
    """Contexte pipeline : refuse si le serveur tourne (sauf `force=True`).

    Lève `ServerLockBusy` avec un message UX-friendly si conflit et
    `force` est faux.
    """
    if not force and _peek_locked(_SERVER_LOCK_PATH):
        pid_hint = ""
        try:
            content = _SERVER_PID_PATH.read_text(encoding="utf-8").strip()
            if content:
                pid_hint = f" (PID {content})"
        except OSError:
            pass
        raise ServerLockBusy(
            f"Le review_server tourne actuellement{pid_hint} — "
            "arrête-le d'abord (Ctrl+C dans son terminal) OU relance "
            "avec --force pour ignorer le verrou (à tes risques : "
            "écritures concurrentes possibles)."
        )
    lock = _try_acquire(_PIPELINE_LOCK_PATH, role="pipeline")
    if lock is None and not force:
        raise PipelineLockBusy(
            "Un autre script pipeline tourne déjà "
            "(verrou tools/output/.review_pipeline.lock). Attends-le ou "
            "vérifie qu'aucun processus n'a planté en tenant le verrou."
        )
    try:
        if lock is not None:
            try:
                _PIPELINE_PID_PATH.write_text(
                    str(os.getpid()), encoding="utf-8",
                )
            except OSError:
                pass
        yield
    finally:
        if lock is not None:
            try:
                lock.release()
            except Exception:  # noqa: BLE001
                pass
            try:
                _PIPELINE_PID_PATH.unlink(missing_ok=True)
            except OSError:
                pass


__all__ = [
    "LockBusy",
    "PipelineLockBusy",
    "ServerLockBusy",
    "acquire_pipeline_lock",
    "acquire_server_lock",
]
