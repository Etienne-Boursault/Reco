"""Tests de `tools/fix_creator_aliases.py` — fusion des variantes de `creator`.

Deux garanties tenues ici :
  - le correctif ne REMPLIT jamais un `creator` vide (d'où son innocuité
    vis-à-vis de `tools/creators_exclusions.txt`) ;
  - la détection de doublons ne CORRIGE rien : elle rapporte.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import fix_creator_aliases as fca


@pytest.fixture
def recos_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "src" / "content" / "recos"
    root.mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", root)
    monkeypatch.setattr(df, "RECOS_DIR", root)
    monkeypatch.setattr(fca, "RECOS_DIR", root)
    # `items` DOIT être redirigé lui aussi : le correctif balaie les deux
    # collections (cf. `fix_creator_aliases.alias_roots`). Sans cette ligne,
    # les tests liraient — et écriraient — dans le VRAI dossier `src/content/
    # items` du dépôt. C'est arrivé le 2026-07-31 : une suite de tests a
    # réécrit 29 fichiers du corpus.
    items = tmp_path / "src" / "content" / "items"
    items.mkdir(parents=True)
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(df, "ITEMS_DIR", items)
    return root


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


# ===== fold ================================================================
def test_fold_strips_diacritics_and_case():
    assert fca.fold("Éléonore Costes") == fca.fold("Eleonore COSTES") == "eleonore costes"


def test_fold_normalises_apostrophes_hyphens_and_spaces():
    assert fca.fold("Section d’Assaut") == fca.fold("section  d'assaut")
    assert fca.fold("Jean-Pierre") == fca.fold("Jean Pierre")


def test_fold_handles_typographic_apostrophe_variant():
    assert fca.fold("Lʼun") == fca.fold("l'un")


# ===== transform ===========================================================
def test_transform_rewrites_a_known_alias():
    reco = {"id": "ubm-1", "creator": "Vincent Delherme"}
    changes = fca.transform(reco)
    assert reco["creator"] == "Vincent Delerm"
    assert changes[0].before == "Vincent Delherme"


def test_transform_ignores_unknown_creator():
    reco = {"id": "ubm-1", "creator": "Quelqu'un d'autre"}
    assert fca.transform(reco) == []
    assert reco["creator"] == "Quelqu'un d'autre"


def test_transform_never_fills_an_absent_or_empty_creator():
    """Garantie centrale : jamais d'écriture sur un `creator` vide.

    C'est ce qui rend le correctif incapable de violer
    `tools/creators_exclusions.txt` (« ce creator doit rester VIDE »).
    """
    for reco in ({"id": "ubm-1"}, {"id": "ubm-2", "creator": ""},
                 {"id": "ubm-3", "creator": None}, {"id": "ubm-4", "creator": 42}):
        before = dict(reco)
        assert fca.transform(reco) == []
        assert reco == before


def test_all_alias_targets_differ_from_their_source():
    """Une ligne identité passerait inaperçue et polluerait les rapports."""
    for wrong, right in fca.ALIASES.items():
        assert wrong != right


# ===== collect_creators ====================================================
def test_collect_creators_groups_ids_and_skips_blanks(recos_root: Path):
    _write(recos_root / "s" / "a.json", {"id": "a", "creator": "X"})
    _write(recos_root / "s" / "b.json", {"id": "b", "creator": "X"})
    _write(recos_root / "s" / "c.json", {"id": "c", "creator": "   "})
    _write(recos_root / "s" / "d.json", {"id": "d"})
    assert fca.collect_creators() == {"X": ["a", "b"]}


def test_collect_creators_falls_back_to_filename(recos_root: Path):
    _write(recos_root / "s" / "sans-id.json", {"creator": "X"})
    assert fca.collect_creators() == {"X": ["sans-id"]}


def test_collect_creators_skips_unreadable_file(recos_root: Path, caplog):
    (recos_root / "s").mkdir(parents=True)
    (recos_root / "s" / "ko.json").write_text("{", encoding="utf-8")
    with caplog.at_level("WARNING"):
        assert fca.collect_creators() == {}
    assert "lecture impossible" in caplog.text


# ===== folding_groups ======================================================
def test_folding_groups_pairs_accent_variants():
    groups = fca.folding_groups({"Éléonore Costes": ["a"], "Eleonore Costes": ["b"]})
    assert len(groups) == 1
    assert [v["valeur"] for v in groups[0]["variantes"]] == ["Eleonore Costes", "Éléonore Costes"]
    assert groups[0]["placeholder"] is False


def test_folding_groups_ignores_singletons():
    assert fca.folding_groups({"Seule": ["a"]}) == []


def test_folding_groups_flags_placeholders():
    groups = fca.folding_groups({"Inconnu": ["a"], "inconnu": ["b"]})
    assert groups[0]["placeholder"] is True


def test_folding_groups_truncates_id_list():
    ids = [f"ubm-{i}" for i in range(20)]
    groups = fca.folding_groups({"Tiesto": ids, "Tiësto": ["x"]})
    variant = next(v for v in groups[0]["variantes"] if v["valeur"] == "Tiesto")
    assert variant["occurrences"] == 20 and len(variant["ids"]) == 8


# ===== similarity_pairs ====================================================
def test_similarity_pairs_catches_a_spelling_error_folding_misses():
    """« Delherme » vs « Delerm » : le `h` n'est pas un diacritique."""
    by_value = {"Vincent Delherme": ["a"], "Vincent Delerm": ["b"]}
    assert fca.folding_groups(by_value) == []
    pairs = fca.similarity_pairs(by_value, 0.90)
    assert len(pairs) == 1 and pairs[0]["similarite"] >= 0.90


def test_similarity_pairs_respects_threshold():
    by_value = {"Vincent Delherme": ["a"], "Vincent Delerm": ["b"]}
    assert fca.similarity_pairs(by_value, 0.999) == []


def test_similarity_pairs_skips_far_apart_lengths():
    by_value = {"Bob": ["a"], "Bob Marley et les Wailers": ["b"]}
    assert fca.similarity_pairs(by_value, 0.10) == []


def test_similarity_pairs_excludes_placeholders():
    assert fca.similarity_pairs({"Inconnu": ["a"], "inconnus": ["b"]}, 0.10) == []


def test_similarity_pairs_sorted_by_descending_similarity():
    by_value = {"Aaaa": ["1"], "Aaab": ["2"], "Bbbb": ["3"]}
    pairs = fca.similarity_pairs(by_value, 0.10)
    assert [p["similarite"] for p in pairs] == sorted(
        (p["similarite"] for p in pairs), reverse=True)


# ===== audit / log_audit ===================================================
def test_audit_reports_without_correcting(recos_root: Path):
    _write(recos_root / "s" / "a.json", {"id": "a", "creator": "Tiesto"})
    _write(recos_root / "s" / "b.json", {"id": "b", "creator": "Tiësto"})
    report = fca.audit(None, 0.90)
    assert report["creators_distincts"] == 2
    assert len(report["groupes_repli_unicode"]) == 1
    assert json.loads(recos_root.joinpath("s/a.json").read_text("utf-8"))["creator"] == "Tiesto"


def test_log_audit_mentions_disputed_and_groups(caplog):
    # Entrée SYNTHÉTIQUE, et non `fca.DISPUTED` : ce test vérifie le RENDU d'un
    # litige, pas qu'il en existe un dans la table. Y brancher la vraie table le
    # rendait dépendant de son contenu — il cassait dès qu'on résolvait le
    # dernier litige, ce qui est pourtant le but recherché.
    report = {
        "canoniques_contestees": [{
            "groupe": "Groupe Témoin",
            "variantes_corpus": ["Groupe Temoin", "Groupe Témoin"],
            "consigne_initiale": "Groupe Temoin → Groupe Témoin",
            "constat": "Aucune source ne tranche.",
            "canonique_probable": "Groupe Témoin",
        }],
        "groupes_repli_unicode": [
            {"cle": "tiesto", "placeholder": False,
             "variantes": [{"valeur": "Tiesto", "occurrences": 1, "ids": ["a"]}]},
            {"cle": "inconnu", "placeholder": True, "variantes": []},
        ],
        "paires_similaires": [],
    }
    with caplog.at_level("INFO"):
        fca.log_audit(report)
    assert "CONTESTÉ" in caplog.text and "Groupe Témoin" in caplog.text
    assert "1 groupe(s)" in caplog.text
    assert "'Tiesto' x1" in caplog.text


def test_disputed_est_vide_et_alias_couvre_chedid():
    """Le litige Chedid est tranché : il ne doit plus vivre dans les deux tables.

    Une entrée qui reste dans `DISPUTED` après avoir été résolue transforme la
    liste en cimetière — et laisse croire qu'un arbitrage reste dû.
    """
    assert fca.DISPUTED == []
    assert fca.ALIASES["Mathieu Chédid"] == "Matthieu Chedid"
    assert fca.ALIASES["Matthieu Chédid"] == "Matthieu Chedid"
    # La forme canonique ne doit jamais être elle-même une clé à réécrire,
    # sous peine de boucle.
    for fautive, canonique in fca.ALIASES.items():
        assert canonique not in fca.ALIASES, (
            f"« {canonique} » est à la fois cible (de « {fautive} ») et source")


def test_disputed_entries_are_not_applied():
    """La table contestée ne doit surtout pas fuiter dans les corrections."""
    for item in fca.DISPUTED:
        for variant in item["variantes_corpus"]:
            assert variant not in fca.ALIASES


# ===== CLI =================================================================
def test_main_dry_run_writes_report_only(recos_root: Path, tmp_path: Path):
    path = _write(recos_root / "s" / "a.json", {"id": "a", "creator": "Swann Perisse"})
    before = path.read_text(encoding="utf-8")
    report = tmp_path / "r.json"
    assert fca.main(["--json", str(report)]) == 0
    assert path.read_text(encoding="utf-8") == before
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["applied"] is False and data["files"] == 1
    assert data["audit"]["alias_appliques"] == fca.ALIASES


def test_main_apply_touches_only_the_creator_line(recos_root: Path):
    original = {"id": "a", "creator": "Swann Perisse", "title": "Un titre",
                "links": [{"url": "https://x"}]}
    path = _write(recos_root / "s" / "a.json", original)
    before_lines = path.read_text(encoding="utf-8").splitlines()
    assert fca.main(["--apply"]) == 0
    after_lines = path.read_text(encoding="utf-8").splitlines()
    differing = [(b, a) for b, a in zip(before_lines, after_lines, strict=True) if b != a]
    assert len(differing) == 1
    assert differing[0][1].strip() == '"creator": "Swann Périssé",'


def test_main_respects_exclude_ids(recos_root: Path):
    path = _write(recos_root / "s" / "a.json", {"id": "a", "creator": "Swann Perisse"})
    assert fca.main(["--apply", "--exclude-ids", "a"]) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["creator"] == "Swann Perisse"


def test_build_parser_similarity_default_and_override():
    assert fca.build_parser().parse_args([]).similarity == pytest.approx(0.90)
    assert fca.build_parser().parse_args(["--similarity", "0.8"]).similarity == pytest.approx(0.8)


# ===== Placeholders : vider plutôt que nommer ==============================
def test_transform_vide_un_createur_placeholder():
    """« N/A » n'est pas un nom, c'est un trou déguisé en valeur.

    Le garder coûte deux fois : il s'affiche tel quel sur la carte, et il fait
    croire à 33 œuvres qu'elles partagent un créateur — ce qui fausse toute
    détection de doublons. Relevé le 2026-08-16 : 33 occurrences, dont une
    seule sur une reco active.
    """
    for brut in ("N/A", "n/a", "  N/A  ", "Inconnu", "?"):
        reco = {"id": "ubm-1", "creator": brut}
        changes = fca.transform(reco)
        assert reco["creator"] is None, brut
        assert len(changes) == 1 and changes[0].after is None, brut


def test_transform_ne_touche_pas_un_vrai_nom():
    reco = {"id": "ubm-1", "creator": "Anna Apter"}
    assert fca.transform(reco) == []
    assert reco["creator"] == "Anna Apter"


def test_transform_laisse_un_createur_deja_vide():
    """Ne JAMAIS remplir un champ vide : c'est ce qui rend ce correctif
    structurellement incapable de violer `creators_exclusions.txt`."""
    for vide in (None, "", "   "):
        reco = {"id": "ubm-1", "creator": vide}
        assert fca.transform(reco) == []


def test_un_alias_prime_sur_le_placeholder():
    """Si une valeur est à la fois dans ALIASES et repliée en placeholder,
    la table curée l'emporte — elle est explicite, l'autre est générique."""
    reco = {"id": "ubm-1", "creator": "Orel San"}
    fca.transform(reco)
    assert reco["creator"] == "Orelsan"
