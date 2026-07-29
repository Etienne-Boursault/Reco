"""Tests du point d'entrée `tools/review_server.py` — cas non couverts par
`tests/test_review_server.py` (qui teste le nominal 127.0.0.1) :

- mode LAN explicite (`--host 0.0.0.0`) qui bascule `ALLOW_LAN` ;
- refus de démarrer quand un script pipeline (ou un autre serveur) tient le
  verrou → `exit 1` ;
- relâchement best-effort du verrou en sortie ;
- repli de `load_dotenv` quand `python-dotenv` n'est pas installé.

Aucun socket n'est ouvert : `HTTPServer` est remplacé par une doublure.
"""
from __future__ import annotations

import builtins
import contextlib
import importlib
import sys
from typing import ClassVar

import pytest

import review_handler_base
import review_server as rs
from review_lock import PipelineLockBusy, ServerLockBusy


class _FakeServer:
    """Serveur factice : mémorise l'adresse, puis simule un Ctrl+C."""

    instances: ClassVar[list[_FakeServer]] = []

    def __init__(self, addr, handler):
        self.addr = addr
        self.handler = handler
        _FakeServer.instances.append(self)

    def serve_forever(self):
        raise KeyboardInterrupt


@pytest.fixture
def stub_server(monkeypatch):
    _FakeServer.instances = []
    monkeypatch.setattr(rs, "HTTPServer", _FakeServer)
    monkeypatch.setattr(rs, "_cleanup_orphan_tmp_files", lambda src: None)
    monkeypatch.setattr(rs, "load_dotenv", lambda *a, **k: False)
    return _FakeServer


@pytest.fixture(autouse=True)
def _restore_allow_lan(monkeypatch):
    """`main()` mute la globale `review_handler_base.ALLOW_LAN` ; on la restaure
    pour ne pas contaminer les autres tests de la suite."""
    monkeypatch.setattr(review_handler_base, "ALLOW_LAN",
                        review_handler_base.ALLOW_LAN)


def test_localhost_does_not_enable_lan_mode(stub_server, monkeypatch):
    monkeypatch.setattr(review_handler_base, "ALLOW_LAN", False)
    monkeypatch.setattr(rs, "acquire_server_lock", lambda: contextlib.nullcontext())
    monkeypatch.setattr(sys, "argv", ["review_server.py", "--source", "demo"])

    rs.main()

    assert review_handler_base.ALLOW_LAN is False
    assert stub_server.instances[0].addr == ("127.0.0.1", 8000)


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10"])  # noqa: S104 — cas de test du mode LAN
def test_non_local_host_enables_lan_mode(stub_server, monkeypatch, host):
    """Binder ailleurs que sur localhost active explicitement le mode LAN."""
    monkeypatch.setattr(review_handler_base, "ALLOW_LAN", False)
    monkeypatch.setattr(rs, "acquire_server_lock", lambda: contextlib.nullcontext())
    monkeypatch.setattr(sys, "argv",
                        ["review_server.py", "--source", "demo", "--host", host])

    rs.main()

    assert review_handler_base.ALLOW_LAN is True
    assert stub_server.instances[0].addr == (host, 8000)


def test_localhost_alias_stays_local(stub_server, monkeypatch):
    monkeypatch.setattr(review_handler_base, "ALLOW_LAN", False)
    monkeypatch.setattr(rs, "acquire_server_lock", lambda: contextlib.nullcontext())
    monkeypatch.setattr(sys, "argv",
                        ["review_server.py", "--host", "localhost"])

    rs.main()

    assert review_handler_base.ALLOW_LAN is False


@pytest.mark.parametrize("exc", [
    PipelineLockBusy("un script pipeline tourne"),
    ServerLockBusy("un autre review_server tourne"),
])
def test_refuses_to_start_when_lock_is_busy(stub_server, monkeypatch, exc):
    """Verrou occupé → sortie en erreur AVANT d'ouvrir le moindre socket
    (sinon un script pipeline écraserait les validations manuelles)."""
    def _busy():
        raise exc

    monkeypatch.setattr(rs, "acquire_server_lock", _busy)
    monkeypatch.setattr(sys, "argv", ["review_server.py", "--source", "demo"])

    with pytest.raises(SystemExit) as err:
        rs.main()

    assert err.value.code == 1
    assert stub_server.instances == []


def test_lock_is_released_after_shutdown(stub_server, monkeypatch):
    events: list[str] = []

    class _Ctx:
        def __enter__(self):
            events.append("enter")
            return self

        def __exit__(self, *exc):
            events.append("exit")
            return False

    monkeypatch.setattr(rs, "acquire_server_lock", _Ctx)
    monkeypatch.setattr(sys, "argv", ["review_server.py", "--source", "demo"])

    rs.main()

    assert events == ["enter", "exit"]


def test_release_failure_is_swallowed(stub_server, monkeypatch):
    """Le relâchement du verrou est best-effort : une erreur au `__exit__` ne
    doit pas transformer un arrêt propre en traceback."""
    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            raise RuntimeError("filelock déjà libéré")

    monkeypatch.setattr(rs, "acquire_server_lock", _Ctx)
    monkeypatch.setattr(sys, "argv", ["review_server.py", "--source", "demo"])

    rs.main()  # ne doit pas lever


def test_load_dotenv_fallback_when_package_missing(monkeypatch):
    """Sans `python-dotenv` (ex. portable LLM sans pip), le module doit
    s'importer quand même et exposer un `load_dotenv` neutre."""
    real_import = builtins.__import__

    def _no_dotenv(name, *args, **kwargs):
        if name == "dotenv":
            raise ImportError("python-dotenv non installé")
        return real_import(name, *args, **kwargs)

    try:
        monkeypatch.setattr(builtins, "__import__", _no_dotenv)
        monkeypatch.delitem(sys.modules, "dotenv", raising=False)
        degraded = importlib.reload(rs)
        assert degraded.load_dotenv("/chemin/inexistant/.env") is False
    finally:
        monkeypatch.undo()
        importlib.reload(rs)
