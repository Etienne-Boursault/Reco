"""Tests de `tools/fix_tmdb_ids.py` — pose d'identifiants TMDB curés.

Ce module écrit un identifiant que PERSONNE NE VOIT, et c'est précisément ce
qui le rend dangereux : `enrich_video_links` le promeut en lien visible plus
tard. Une entrée fautive ne se manifeste donc pas à l'écriture mais des
semaines après, sous la forme d'un lien vers un homonyme. La moitié des tests
ci-dessous vérifient les conditions dans lesquelles le module REFUSE d'écrire.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import fix_tmdb_ids as fti


@pytest.fixture
def recos_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "src" / "content" / "recos"
    root.mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", root)
    monkeypatch.setattr(df, "RECOS_DIR", root)
    items = tmp_path / "src" / "content" / "items"
    items.mkdir(parents=True)
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(df, "ITEMS_DIR", items)
    return root


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


# ===== Pose de l'identifiant ===============================================
def test_pose_l_identifiant_prevu():
    reco = {"id": "ubm-1530", "title": "Friends"}
    changes = fti.transform(reco)
    assert reco["externalIds"] == {"tmdb": "1668", "tmdbType": "tv"}
    assert [c.field for c in changes] == ["externalIds.tmdb"]
    assert changes[0].after == "tv/1668"


def test_complete_un_bloc_externalIds_existant_sans_l_ecraser():
    reco = {"id": "ubm-3134", "title": "Drive",
            "externalIds": {"imdb": "tt0780504"}}
    fti.transform(reco)
    assert reco["externalIds"] == {"imdb": "tt0780504", "tmdb": "64690",
                                   "tmdbType": "movie"}


def test_un_externalIds_non_dict_est_remplace_sans_lever():
    """Le corpus contient de la donnée héritée : elle ne doit pas faire tomber
    la passe."""
    reco = {"id": "ubm-1530", "title": "Friends", "externalIds": "hérité"}
    fti.transform(reco)
    assert reco["externalIds"]["tmdb"] == "1668"


# ===== Ce que le module REFUSE d'écrire ====================================
def test_une_reco_absente_de_la_table_n_est_pas_touchee():
    reco = {"id": "ubm-9999", "title": "Friends"}
    assert fti.transform(reco) == []
    assert "externalIds" not in reco


def test_un_titre_QUI_A_CHANGE_annule_la_decision():
    """Le titre attendu est une garde, pas une donnée. Une reco renommée peut
    désigner une autre œuvre, et lui poser l'identifiant décidé pour l'ancienne
    serait exactement l'erreur que ce module cherche à éviter."""
    reco = {"id": "ubm-1530", "title": "Friends from College"}
    assert fti.transform(reco) == []
    assert "externalIds" not in reco


def test_un_identifiant_DEJA_present_n_est_jamais_ecrase():
    """Il peut venir d'une relecture humaine, mieux informée que cette table."""
    reco = {"id": "ubm-1530", "title": "Friends",
            "externalIds": {"tmdb": "42", "tmdbType": "tv"}}
    assert fti.transform(reco) == []
    assert reco["externalIds"]["tmdb"] == "42"


def test_la_passe_est_idempotente():
    reco = {"id": "ubm-1530", "title": "Friends"}
    fti.transform(reco)
    assert fti.transform(reco) == []


# ===== Rectifications ======================================================
def test_rectifie_un_titre_que_TMDB_a_montre_faux():
    reco = {"id": "ubm-1804", "title": "Mister Nobody"}
    changes = fti.transform(reco)
    assert reco["title"] == "Mr. Nobody"
    assert "title" in [c.field for c in changes]


def test_l_identifiant_est_pose_AVANT_la_rectification_du_titre():
    """L'ordre décide du résultat : la garde d'`IDENTIFIANTS` attend l'ancien
    titre. Inverser les deux poserait la rectification et perdrait
    l'identifiant, sans que rien ne le signale."""
    reco = {"id": "ubm-1804", "title": "Mister Nobody"}
    fti.transform(reco)
    assert reco["externalIds"]["tmdb"] == "31011"
    assert reco["title"] == "Mr. Nobody"


def test_rectifie_une_annee_fausse():
    reco = {"id": "ubm-3109", "title": "La Chèvre", "year": 1985}
    fti.transform(reco)
    assert reco["year"] == 1981


def test_une_rectification_DEJA_faite_n_est_pas_rejouee():
    reco = {"id": "ubm-3109", "title": "La Chèvre", "year": 1981}
    changes = fti.transform(reco)
    assert [c.field for c in changes] == ["externalIds.tmdb"]


def test_une_rectification_s_applique_meme_si_l_identifiant_est_deja_la():
    """Les deux sorties anticipées de la pose d'identifiant ne doivent pas
    emporter la rectification avec elles."""
    reco = {"id": "ubm-1804", "title": "Mister Nobody",
            "externalIds": {"tmdb": "31011", "tmdbType": "movie"}}
    changes = fti.transform(reco)
    assert reco["title"] == "Mr. Nobody"
    assert [c.field for c in changes] == ["title"]


# ===== Cohérence des tables ================================================
def test_les_types_TMDB_sont_ceux_que_l_API_connait():
    """`movie` et `tv` sont les deux seules valeurs admises par le schéma
    (`content.config.ts`). Une faute de frappe ici passerait l'écriture et
    casserait le build."""
    for _, (_, genre, _) in fti.IDENTIFIANTS.items():
        assert genre in {"movie", "tv"}


def test_les_identifiants_sont_des_chaines_de_chiffres():
    """Le schéma déclare `tmdb: z.string()`. Un entier y arrêterait le build."""
    for _, (_, _, tmdb_id) in fti.IDENTIFIANTS.items():
        assert isinstance(tmdb_id, str) and tmdb_id.isdigit()


def test_aucune_rectification_ne_contredit_la_garde_de_sa_propre_entree():
    """Une rectification du TITRE d'une reco dont l'identifiant est aussi prévu
    ne peut viser que le titre attendu par la garde — sinon l'une des deux
    tables se tait pour toujours."""
    for rid, (champ, avant, _) in fti.RECTIFICATIONS.items():
        if champ == "title" and rid in fti.IDENTIFIANTS:
            assert fti.IDENTIFIANTS[rid][0] == avant


# ===== CLI =================================================================
def test_main_dry_run_n_ecrit_pas(recos_root: Path, tmp_path: Path):
    path = _write(recos_root / "s" / "a.json", {"id": "ubm-1530", "title": "Friends"})
    avant = path.read_text(encoding="utf-8")
    report = tmp_path / "r.json"
    assert fti.main(["--json", str(report)]) == 0
    assert path.read_text(encoding="utf-8") == avant
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["applied"] is False
    assert data["entrees"] == len(fti.IDENTIFIANTS)


def test_main_apply_ecrit_l_identifiant(recos_root: Path):
    path = _write(recos_root / "s" / "a.json", {"id": "ubm-1530", "title": "Friends"})
    assert fti.main(["--apply"]) == 0
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["externalIds"] == {"tmdb": "1668", "tmdbType": "tv"}
