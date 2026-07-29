"""Chemins d'erreur de `tools/review_routes_reco.py` (routes /add-reco et
/delete-reco).

Le nominal et les refus courants sont couverts par `tests/test_review_server.py`
via son `_FakeHandler` HTTP complet. Ici on cible les gardes de dernier recours
— celles qui ne se déclenchent que si `Path.resolve()` échoue ou si un fichier
résiste à la suppression — en pilotant le mixin directement, sans socket.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import review_routes_reco as rrr


class _Probe(rrr.RecoCrudRoutesMixin):
    """Instance minimale du mixin : `source_id` + les deux helpers de réponse
    attendus de `BaseHandler`."""

    def __init__(self, source_id: str = "demo-source"):
        self.source_id = source_id
        self.redirects: list[str] = []
        self.sent: list[tuple[int, str]] = []

    def _send_redirect(self, location: str) -> None:
        self.redirects.append(location)

    def _send(self, status: int, body: str) -> None:
        self.sent.append((status, body))


class _UnresolvablePath:
    """Chemin dont la résolution échoue — simule un FS qui rend `resolve()`
    impossible (boucle de liens symboliques, montage disparu…).

    Duck-typé volontairement : sous-classer `pathlib.Path` dépendrait de son
    API interne (`_flavour`, renommé selon les versions de Python), alors que
    le code testé n'appelle que `exists()` et `resolve()`.
    """

    def __init__(self, display: Path):
        self._display = display

    def __str__(self) -> str:
        return str(self._display)

    def exists(self) -> bool:
        return True

    def resolve(self, strict: bool = False):
        raise OSError("montage disparu")


# ===== _assert_under_recos =================================================
def test_assert_under_recos_accepts_a_path_inside_the_source_dir(monkeypatch,
                                                                 tmp_path):
    monkeypatch.setattr(rrr, "recos_dir_for", lambda src: tmp_path)

    assert rrr._assert_under_recos(tmp_path / "0001.json", "demo-source") is True


def test_assert_under_recos_rejects_a_path_outside(monkeypatch, tmp_path):
    monkeypatch.setattr(rrr, "recos_dir_for", lambda src: tmp_path / "recos")

    assert rrr._assert_under_recos(tmp_path / "ailleurs.json", "demo-source") is False


def test_assert_under_recos_rejects_when_resolution_fails(monkeypatch, tmp_path):
    """`resolve()` qui lève ne doit pas propager : on refuse, point."""
    monkeypatch.setattr(rrr, "recos_dir_for", lambda src: tmp_path)

    assert rrr._assert_under_recos(_UnresolvablePath(tmp_path / "x.json"),
                                   "demo-source") is False


def test_assert_under_recos_rejects_path_with_null_byte(monkeypatch, tmp_path):
    """Un octet nul dans le chemin fait lever `ValueError` à l'OS — la garde
    doit l'absorber (elle est là pour d'éventuels chemins d'origine externe)."""
    monkeypatch.setattr(rrr, "recos_dir_for", lambda src: tmp_path)

    assert rrr._assert_under_recos(Path("x\0y.json"), "demo-source") is False


# ===== /add-reco : stub créé hors du dossier de la source ==================
@pytest.fixture
def add_reco_env(monkeypatch, tmp_path):
    """Neutralise la lecture disque de `_load_groups` (l'épisode existe)."""
    monkeypatch.setattr(rrr, "_load_groups",
                        lambda src: (None, {"ep-001": object()}, None))
    monkeypatch.setattr(rrr, "recos_dir_for", lambda src: tmp_path / "recos")
    return tmp_path


def test_add_reco_deletes_the_stub_created_outside_the_recos_dir(add_reco_env,
                                                                 monkeypatch):
    """Defense in depth : si l'allocation produit un fichier hors du dossier de
    la source, il est supprimé et la requête abandonnée."""
    intruder = add_reco_env / "intrus.json"
    intruder.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(rrr, "_allocate_new_reco",
                        lambda src, guid: ("ds-0001", intruder))

    probe = _Probe()
    probe._handle_add_reco({"guid": ["ep-001"]})

    assert probe.redirects == ["/"]
    assert not intruder.exists()


def test_add_reco_aborts_even_if_the_stray_stub_cannot_be_deleted(add_reco_env,
                                                                  monkeypatch):
    """Le fichier hors zone résiste à la suppression : on abandonne quand même
    proprement (pas de 500), sans le référencer nulle part."""
    intruder = add_reco_env / "intrus.json"
    intruder.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(rrr, "_allocate_new_reco",
                        lambda src, guid: ("ds-0001", intruder))

    real_unlink = Path.unlink

    def _boom(self, missing_ok=False):
        if self.name == "intrus.json":
            raise OSError("verrouillé par un autre process")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _boom)

    probe = _Probe()
    probe._handle_add_reco({"guid": ["ep-001"]})

    assert probe.redirects == ["/"]
    assert intruder.exists()


# ===== /delete-reco : résolution de chemin impossible ======================
def test_delete_reco_redirects_when_path_resolution_fails(monkeypatch, tmp_path):
    """Si on ne peut pas prouver que le fichier est dans la zone autorisée, on
    ne supprime RIEN et on redirige (au lieu de remonter une OSError)."""
    monkeypatch.setattr(rrr, "recos_dir_for", lambda src: tmp_path)
    monkeypatch.setattr(rrr, "_reco_path",
                        lambda src, rid: _UnresolvablePath(tmp_path / "ds-0001.json"))

    probe = _Probe()
    probe._handle_delete_reco({"id": ["ds-0001"]})

    assert probe.redirects == ["/"]
    assert probe.sent == []  # ni 403 ni 500


# ===== _reco_id_in_recent_backup ===========================================
def _manifest(backup_dir: Path, name: str, payload: dict) -> Path:
    d = backup_dir / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    return d


def test_recent_backup_keeps_scanning_after_a_non_matching_manifest(
    monkeypatch, tmp_path,
):
    """Le scan doit parcourir TOUS les backups récents : un manifest de la
    bonne source mais sans l'id cherché ne doit pas arrêter la recherche
    (sinon on raterait la reco ressuscitable et l'avertissement #13)."""
    backup = tmp_path / "dedup-backup"
    _manifest(backup, "2026-07-28T10-00-00",
              {"source_id": "demo-source", "keep_id": "ds-0009",
               "loser_ids": ["ds-0010"]})
    _manifest(backup, "2026-07-27T10-00-00",
              {"source_id": "demo-source", "keep_id": "ds-0001",
               "loser_ids": []})
    monkeypatch.setattr(rrr, "BACKUP_DIR", backup)

    probe = _Probe()

    # Le plus récent (trié décroissant) ne contient pas l'id : on continue.
    assert probe._reco_id_in_recent_backup("ds-0001") is True
    assert probe._reco_id_in_recent_backup("ds-0010") is True
    assert probe._reco_id_in_recent_backup("ds-9999") is False
