"""Mise à jour ciblée du cache `_load_groups` après l'écriture d'UNE reco.

Avant : chaque /save, /edit, /undo-save… vidait le cache des groupes, et le
rendu suivant relisait les ~3000 recos (0,4 s) — puis `_RECO_PATH_CACHE`, vidé
lui aussi, relisait tout une seconde fois. `refresh_reco_in_cache` relit le seul
fichier écrit ; au moindre doute il retombe sur l'invalidation complète.

On réutilise le harnais de `test_review_server` (`fake_source` monte le contenu
dans `tmp_path` : rien n'est écrit dans le vrai corpus).
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

import review_handler_base as rhb
import review_render as rr
import review_routes as rt
from test_review_server import (  # noqa: F401 — fixtures réutilisées
    _clear_review_server_caches,
    _FakeHandler,
    fake_source,
)


def _recos_dir(source_id: str) -> Path:
    from common import recos_dir_for

    return recos_dir_for(source_id)


def _write(path: Path, data: dict, bump: int = 0) -> None:
    """Écrit une reco ; `bump` décale le mtime (granularité des FS lents)."""
    path.write_text(json.dumps(data), encoding="utf-8")
    if bump:
        future = path.stat().st_mtime + bump
        os.utime(path, (future, future))


def _edit(path: Path, **changes) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(changes)
    _write(path, data)
    return data


def _full_reload(source_id: str):
    """Ce qu'un re-scan complet renverrait (référence d'équivalence)."""
    saved = dict(rr._GROUPS_CACHE)
    rr._clear_groups_cache()
    try:
        return copy.deepcopy(rr._load_groups(source_id))
    finally:
        rr._GROUPS_CACHE.clear()
        rr._GROUPS_CACHE.update(saved)


@pytest.fixture
def no_reread(monkeypatch):
    """Fait échouer toute relecture de reco par `_load_groups`."""
    def _armed():
        monkeypatch.setattr(rr, "read_json", _boom)
    return _armed


def _boom(path):
    raise AssertionError(f"relecture inattendue : {path}")


_READ_JSON = rr.read_json


def _ids(groups, guid):
    return [r["id"] for r in groups.get(guid, [])]


# ===== refresh_reco_in_cache : mise à jour en place ==========================
def test_modification_relit_le_seul_fichier_ecrit(fake_source, monkeypatch):
    rr._load_groups(fake_source)
    p = _recos_dir(fake_source) / "ubm-001.json"
    _edit(p, status="validated", timestamp="02:00:00")
    lus = []
    monkeypatch.setattr(rr, "read_json", lambda q: lus.append(q) or _READ_JSON(q))

    assert rr.refresh_reco_in_cache(fake_source, p) is True
    assert lus == [p]

    monkeypatch.setattr(rr, "read_json", _boom)
    _src, _eps, groups = rr._load_groups(fake_source)  # succès de cache
    assert groups["ep-001"][-2]["id"] == "ubm-001"  # retrié (02:00:00)
    assert groups["ep-001"][-2]["status"] == "validated"
    monkeypatch.setattr(rr, "read_json", _READ_JSON)
    assert rr._load_groups(fake_source)[2] == _full_reload(fake_source)[2]


def test_changement_d_episode_deplace_la_reco(fake_source):
    rr._load_groups(fake_source)
    p = _recos_dir(fake_source) / "ubm-001.json"
    _edit(p, episodeGuid="ep-002")

    assert rr.refresh_reco_in_cache(fake_source, p) is True
    groups = rr._load_groups(fake_source)[2]
    assert "ubm-001" not in _ids(groups, "ep-001")
    assert _ids(groups, "ep-002") == ["ubm-001"]
    assert groups == _full_reload(fake_source)[2]


def test_creation_ajoute_la_reco_et_son_chemin(fake_source, no_reread):
    rr._load_groups(fake_source)
    p = _recos_dir(fake_source) / "ubm-009.json"
    _write(p, {"id": "ubm-009", "episodeGuid": "ep-002", "title": "Neuf",
               "types": ["film"], "status": "draft"})

    assert rr.refresh_reco_in_cache(fake_source, p) is True
    assert rhb._RECO_PATH_CACHE[fake_source]["ubm-009"] == p
    no_reread()
    assert _ids(rr._load_groups(fake_source)[2], "ep-002") == ["ubm-009"]


def test_suppression_retire_la_reco_le_groupe_vide_et_le_chemin(fake_source):
    rr._load_groups(fake_source)
    p = _recos_dir(fake_source) / "ubm-009.json"
    _write(p, {"id": "ubm-009", "episodeGuid": "ep-002", "title": "Seule",
               "types": ["film"], "status": "draft"}, bump=10)
    rr._load_groups(fake_source)
    p.unlink()

    assert rr.refresh_reco_in_cache(fake_source, p) is True
    groups = rr._load_groups(fake_source)[2]
    assert "ep-002" not in groups  # comme un re-scan : pas de groupe vide
    assert "ubm-009" not in rhb._RECO_PATH_CACHE[fake_source]
    assert groups == _full_reload(fake_source)[2]


def test_le_chemin_d_une_autre_reco_n_est_pas_retire(fake_source):
    """Le cache des chemins ne perd une entrée que si elle pointait sur CE
    fichier (un id réattribué ailleurs garde son chemin)."""
    rr._load_groups(fake_source)
    autre = _recos_dir(fake_source) / "ailleurs.json"
    rhb._RECO_PATH_CACHE[fake_source]["ubm-001"] = autre
    p = _recos_dir(fake_source) / "ubm-001.json"
    _edit(p, id="ubm-001b")

    assert rr.refresh_reco_in_cache(fake_source, p) is True
    assert rhb._RECO_PATH_CACHE[fake_source]["ubm-001"] == autre
    assert rhb._RECO_PATH_CACHE[fake_source]["ubm-001b"] == p


def test_sans_cache_des_chemins_rien_a_tenir_a_jour(fake_source):
    rr._load_groups(fake_source)
    rhb._RECO_PATH_CACHE.clear()
    p = _recos_dir(fake_source) / "ubm-001.json"
    _edit(p, status="validated")

    assert rr.refresh_reco_in_cache(fake_source, p) is True
    assert fake_source not in rhb._RECO_PATH_CACHE


def test_un_rescan_reconstruit_le_cache_des_chemins(fake_source, monkeypatch):
    """Le re-scan de `_load_groups` remplit `_RECO_PATH_CACHE` avec ce qu'il
    vient de lire : `_reco_path` n'a plus à relire tous les fichiers."""
    monkeypatch.setattr(rhb, "_rebuild_reco_path_cache", _boom)
    rr._load_groups(fake_source)
    assert rhb._reco_path(fake_source, "ubm-002") == (
        _recos_dir(fake_source) / "ubm-002.json")


# ===== refresh_reco_in_cache : repli sur l'invalidation complète =============
def _assert_invalide(source_id: str) -> None:
    assert source_id not in rr._GROUPS_CACHE
    assert source_id not in rhb._RECO_PATH_CACHE


def test_sans_cache_invalide_tout(fake_source):
    rhb._RECO_PATH_CACHE[fake_source] = {}
    p = _recos_dir(fake_source) / "ubm-001.json"
    assert rr.refresh_reco_in_cache(fake_source, p) is False
    _assert_invalide(fake_source)


def test_chemin_hors_du_dossier_invalide_tout(fake_source, tmp_path):
    rr._load_groups(fake_source)
    assert rr.refresh_reco_in_cache(fake_source, tmp_path / "x.json") is False
    _assert_invalide(fake_source)


def test_une_autre_reco_modifiee_entre_temps_invalide_tout(fake_source):
    """Le pipeline a modifié une AUTRE reco : on ne la connaît pas → re-scan,
    jamais un état faux."""
    rr._load_groups(fake_source)
    _write(_recos_dir(fake_source) / "ubm-002.json",
           {"id": "ubm-002", "episodeGuid": "ep-001", "title": "Pipeline",
            "types": ["livre"], "status": "draft"}, bump=10)
    p = _recos_dir(fake_source) / "ubm-001.json"
    _edit(p, status="validated")

    assert rr.refresh_reco_in_cache(fake_source, p) is False
    _assert_invalide(fake_source)
    groups = rr._load_groups(fake_source)[2]
    titres = {r["id"]: r["title"] for r in groups["ep-001"]}
    assert titres["ubm-002"] == "Pipeline"


def test_une_autre_reco_creee_entre_temps_invalide_tout(fake_source):
    rr._load_groups(fake_source)
    _write(_recos_dir(fake_source) / "ubm-008.json",
           {"id": "ubm-008", "episodeGuid": "ep-001", "title": "Pipeline",
            "types": ["livre"], "status": "draft"})
    p = _recos_dir(fake_source) / "ubm-001.json"
    _edit(p, status="validated")
    assert rr.refresh_reco_in_cache(fake_source, p) is False


def test_un_episode_modifie_invalide_tout(fake_source):
    from common import episodes_dir_for

    rr._load_groups(fake_source)
    ep = episodes_dir_for(fake_source) / "ep-002.json"
    _write(ep, {"guid": "ep-002", "title": "Renommé", "number": 7}, bump=10)
    p = _recos_dir(fake_source) / "ubm-001.json"
    _edit(p, status="validated")

    assert rr.refresh_reco_in_cache(fake_source, p) is False
    assert rr._load_groups(fake_source)[1]["ep-002"]["title"] == "Renommé"


def test_fichier_illisible_invalide_tout(fake_source):
    rr._load_groups(fake_source)
    p = _recos_dir(fake_source) / "ubm-001.json"
    p.write_text("{pas du json", encoding="utf-8")
    assert rr.refresh_reco_in_cache(fake_source, p) is False
    _assert_invalide(fake_source)


# ===== Routes : plus de relecture complète après une décision ================
def _post(source_id, route, body, accept=""):
    h = _FakeHandler(source_id, route, body.encode("utf-8"), accept=accept)
    h.do_POST()
    return h


def _statut(source_id, reco_id):
    for g in rr._load_groups(source_id)[2].values():
        for r in g:
            if r["id"] == reco_id:
                return r.get("status")
    return None


def test_save_met_le_cache_a_jour_sans_tout_relire(fake_source, monkeypatch,
                                                   no_reread):
    """Pendant le POST (écriture + carte fraîche), le cache des groupes ne
    relit QUE la reco décidée — avant, la carte fraîche relisait tout."""
    rr._load_groups(fake_source)
    lus = []
    monkeypatch.setattr(rr, "read_json", lambda q: lus.append(q.name) or _READ_JSON(q))
    h = _post(fake_source, "/save", "id=ubm-001&action=validate&who=Alice",
              accept="application/json")
    assert h._status == 200
    assert json.loads(h.wfile.getvalue())["card_html"]
    assert lus == ["ubm-001.json"]
    no_reread()
    assert _statut(fake_source, "ubm-001") == "validated"
    assert "ubm-001" in rhb._RECO_PATH_CACHE[fake_source]


def test_edit_depuis_les_doutes_une_seule_mise_a_jour(fake_source, no_reread):
    """/edit écrit deux fois (édition puis décision) : le cache suit."""
    rr._load_groups(fake_source)
    h = _FakeHandler(fake_source, "/edit",
                     b"id=ubm-001&title=Mortel%202&types=film&action=discard")
    h.headers["Referer"] = "http://localhost/doutes"
    h.do_POST()
    assert h._status == 303
    no_reread()
    r = rr._load_groups(fake_source)[2]["ep-001"]
    mortel = next(x for x in r if x["id"] == "ubm-001")
    assert (mortel["title"], mortel["status"]) == ("Mortel 2", "discarded")


def test_reenrich_met_le_cache_a_jour(fake_source, monkeypatch, no_reread):
    def _fake_reenrich(path, reco_id):
        _edit(path, creator="Fabrice Gobert")
        return "ep-001", "TMDB : ok", "success"

    monkeypatch.setattr(rt, "apply_reenrich", _fake_reenrich)
    rr._load_groups(fake_source)
    _post(fake_source, "/reenrich", "id=ubm-001")
    no_reread()
    r = rr._load_groups(fake_source)[2]["ep-001"]
    assert next(x for x in r if x["id"] == "ubm-001")["creator"] == "Fabrice Gobert"


def test_undo_save_restaure_dans_le_cache(fake_source, no_reread):
    rr._load_groups(fake_source)
    _post(fake_source, "/save", "id=ubm-001&action=validate")
    h = _post(fake_source, "/undo-save", "", accept="application/json")
    assert json.loads(h.wfile.getvalue())["restored"] is True
    no_reread()
    assert _statut(fake_source, "ubm-001") == "draft"


def test_undo_save_sans_rien_a_annuler_invalide(fake_source):
    rr._load_groups(fake_source)
    _post(fake_source, "/undo-save", "", accept="application/json")
    _assert_invalide(fake_source)


def test_add_puis_delete_reco_suivent_le_cache(fake_source, monkeypatch):
    rr._load_groups(fake_source)
    h = _post(fake_source, "/add-reco", "guid=ep-002")
    assert h._status == 303
    new_id = next(iter(_ids(rr._GROUPS_CACHE[fake_source][1][2], "ep-002")))
    assert new_id in rhb._RECO_PATH_CACHE[fake_source]

    monkeypatch.setattr(rr, "read_json", _boom)
    assert _ids(rr._load_groups(fake_source)[2], "ep-002") == [new_id]
    monkeypatch.setattr(rr, "read_json", _READ_JSON)

    _post(fake_source, "/delete-reco", f"id={new_id}")
    monkeypatch.setattr(rr, "read_json", _boom)
    assert "ep-002" not in rr._load_groups(fake_source)[2]
    assert new_id not in rhb._RECO_PATH_CACHE[fake_source]
