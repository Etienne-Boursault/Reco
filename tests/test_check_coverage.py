"""Tests du garde-fou de couverture par métrique (`scripts/check_coverage.py`).

Ce script existe parce que `--cov-fail-under` de coverage.py porte sur un
TOTAL COMBINÉ lignes+branches : un run à 99 % de lignes et 91 % de branches le
passerait sans broncher. L'exigence du projet étant ≥95 % sur CHAQUE métrique,
il faut les comparer séparément.

Le mode de défaillance le plus important est testé ici : un rapport absent ou
illisible doit ÉCHOUER, jamais passer en silence. C'est très exactement le
piège dont ce dépôt sort — un `fail_under` configuré et jamais évalué.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import check_coverage as cc  # noqa: E402


def _report(stmts: float, branches: float) -> dict:
    return {
        "totals": {
            "percent_statements_covered": stmts,
            "percent_branches_covered": branches,
            "num_statements": 1000,
            "covered_lines": int(10 * stmts),
            "num_branches": 400,
            "covered_branches": int(4 * branches),
        }
    }


def _write(tmp_path: Path, payload) -> Path:
    p = tmp_path / "coverage.json"
    p.write_text(json.dumps(payload) if not isinstance(payload, str) else payload,
                 encoding="utf-8")
    return p


# ===== Cas nominaux ========================================================
def test_les_deux_metriques_au_dessus_passe(tmp_path, capsys):
    path = _write(tmp_path, _report(98.9, 97.8))
    assert cc.main(["--input", str(path), "--min", "95"]) == 0


def test_affiche_les_deux_chiffres_meme_quand_tout_va_bien(tmp_path, capsys):
    """Une CI verte muette laisse la dérive s'installer entre deux mesures."""
    path = _write(tmp_path, _report(98.9, 97.8))
    cc.main(["--input", str(path), "--min", "95"])
    out = capsys.readouterr().out
    assert "98.9" in out
    assert "97.8" in out


def test_exactement_au_seuil_passe(tmp_path):
    path = _write(tmp_path, _report(95.0, 95.0))
    assert cc.main(["--input", str(path), "--min", "95"]) == 0


# ===== Chaque métrique fait échouer indépendamment ==========================
def test_statements_en_dessous_echoue(tmp_path, capsys):
    path = _write(tmp_path, _report(94.9, 99.0))
    assert cc.main(["--input", str(path), "--min", "95"]) == 1
    assert "statements" in capsys.readouterr().out


def test_branches_en_dessous_echoue(tmp_path, capsys):
    """LE cas que `--cov-fail-under` laisserait passer : combiné bon, branches non."""
    path = _write(tmp_path, _report(99.0, 91.0))
    assert cc.main(["--input", str(path), "--min", "95"]) == 1
    assert "branches" in capsys.readouterr().out


def test_les_deux_en_dessous_signale_les_deux(tmp_path, capsys):
    path = _write(tmp_path, _report(90.0, 80.0))
    assert cc.main(["--input", str(path), "--min", "95"]) == 1
    out = capsys.readouterr().out
    assert "statements" in out
    assert "branches" in out


def test_le_message_dit_combien_il_manque(tmp_path, capsys):
    """« coverage failed » sec fait perdre dix minutes à chaque fois."""
    path = _write(tmp_path, _report(90.0, 99.0))
    cc.main(["--input", str(path), "--min", "95"])
    out = capsys.readouterr().out
    assert "95" in out          # le seuil
    assert "90.0" in out        # la valeur
    assert "50" in out          # 1000 statements → il en manque 50


# ===== Défaillances : bruyantes, jamais silencieuses ========================
def test_rapport_absent_echoue(tmp_path, capsys):
    absent = tmp_path / "nulle-part.json"
    assert cc.main(["--input", str(absent), "--min", "95"]) == 1
    assert "introuvable" in capsys.readouterr().out.lower()


def test_rapport_illisible_echoue(tmp_path, capsys):
    path = _write(tmp_path, "{ ceci n'est pas du json")
    assert cc.main(["--input", str(path), "--min", "95"]) == 1
    assert "illisible" in capsys.readouterr().out.lower()


def test_totals_manquant_echoue(tmp_path, capsys):
    path = _write(tmp_path, {"files": {}})
    assert cc.main(["--input", str(path), "--min", "95"]) == 1


@pytest.mark.parametrize("cle", ["percent_statements_covered", "percent_branches_covered"])
def test_metrique_manquante_echoue(tmp_path, capsys, cle):
    payload = _report(99.0, 99.0)
    del payload["totals"][cle]
    path = _write(tmp_path, payload)
    assert cc.main(["--input", str(path), "--min", "95"]) == 1


# ===== Interface ===========================================================
def test_seuil_par_defaut_est_95(tmp_path):
    path = _write(tmp_path, _report(96.0, 96.0))
    assert cc.main(["--input", str(path)]) == 0
    path = _write(tmp_path, _report(94.0, 96.0))
    assert cc.main(["--input", str(path)]) == 1


def test_input_par_defaut_est_coverage_json_a_la_racine():
    assert cc.build_parser().parse_args([]).input == "coverage.json"
