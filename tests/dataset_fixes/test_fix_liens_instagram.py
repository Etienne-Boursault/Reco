"""Tests de `tools/fix_liens_instagram.py`.

Le lien Instagram arrive EN DERNIER dans l'ordre éditorial : il ne doit jamais
prendre la place d'un lien qui mène à l'œuvre. La carte n'en affichant que six,
la quasi-totalité de ces tests porte sur ce que l'outil REFUSE d'écrire — un
ajout de trop est invisible dans le diff mais évince un lien à l'écran.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import fix_liens_instagram as fli


@pytest.fixture
def recos_root(tmp_path: Path, monkeypatch) -> Path:
    """Redirige le corpus vers un `tmp_path`.

    Sans cette redirection, une suite de tests écrit dans le VRAI corpus
    (arrivé le 2026-07-31 : 29 fichiers réécrits).
    """
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
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _liens(n: int) -> list[dict]:
    """`n` liens distincts, tels que la carte les compte (labels différents)."""
    return [{"label": f"P{i}", "url": f"https://exemple.fr/{i}",
             "kind": "info", "ethics": "neutral"} for i in range(n)]


def _reco(handle: str = "laurentbaffie", nb_liens: int = 2, **extra) -> dict:
    reco = {"id": "ubm-0038", "title": "Un titre",
            "externalIds": {"instagram": handle}, "links": _liens(nb_liens)}
    reco.update(extra)
    return reco


# ===== Ce que l'outil écrit ================================================
def test_ajoute_le_lien_instagram():
    reco = _reco()
    changes = fli.transform(reco)
    assert reco["links"][-1] == {
        "label": "Instagram",
        "url": "https://www.instagram.com/laurentbaffie/",
        "kind": "social",
        "ethics": "neutral",
    }
    assert [c.field for c in changes] == ["links"]


def test_le_lien_est_ajoute_EN_DERNIER():
    """L'ordre de la liste EST l'ordre d'affichage : Instagram doit fermer la
    marche, jamais évincer un lien qui mène à l'œuvre."""
    reco = _reco(nb_liens=5)
    fli.transform(reco)
    assert [lien["label"] for lien in reco["links"]] == [
        "P0", "P1", "P2", "P3", "P4", "Instagram"]


def test_les_liens_existants_sont_conserves_a_l_identique():
    reco = _reco(nb_liens=3)
    avant = [dict(lien) for lien in reco["links"]]
    fli.transform(reco)
    assert reco["links"][:3] == avant


def test_le_changement_decrit_l_avant_et_l_apres():
    reco = _reco(nb_liens=1)
    (change,) = fli.transform(reco)
    assert change.before == ["https://exemple.fr/0"]
    assert change.after == ["https://exemple.fr/0",
                            "https://www.instagram.com/laurentbaffie/"]


def test_un_arobase_de_tete_est_retire():
    """Le schéma demande le handle nu, mais rien ne l'impose à l'écriture."""
    reco = _reco(handle="@laurentbaffie")
    fli.transform(reco)
    assert reco["links"][-1]["url"] == "https://www.instagram.com/laurentbaffie/"


def test_les_espaces_de_bordure_sont_retires():
    reco = _reco(handle="  laurentbaffie  ")
    fli.transform(reco)
    assert reco["links"][-1]["url"] == "https://www.instagram.com/laurentbaffie/"


def test_un_lien_herite_mal_forme_ne_fait_pas_lever():
    """Le corpus porte de la donnée héritée : elle ne doit pas faire tomber la
    passe sur les 3000 autres fichiers."""
    reco = _reco()
    reco["links"] = ["hérité", None, {"label": "P0", "url": "https://exemple.fr/0"}]
    fli.transform(reco)
    assert reco["links"][-1]["label"] == "Instagram"


def test_un_lien_sans_label_ne_fait_pas_lever():
    reco = _reco()
    reco["links"] = [{"url": "https://exemple.fr/0"}]
    fli.transform(reco)
    assert reco["links"][-1]["label"] == "Instagram"


# ===== Le plafond des six liens ============================================
def test_refuse_quand_la_carte_affiche_deja_six_liens():
    """CONDITION D'ACCEPTATION N°1 : une carte pleine ne bouge pas d'un pixel."""
    reco = _reco(nb_liens=6)
    assert fli.transform(reco) == []
    assert len(reco["links"]) == 6


def test_refuse_au_dela_de_six_liens():
    reco = _reco(nb_liens=7)
    assert fli.transform(reco) == []
    assert len(reco["links"]) == 7


def test_accepte_a_cinq_liens():
    """La borne est bien « moins de six », pas « moins de cinq »."""
    reco = _reco(nb_liens=5)
    assert fli.transform(reco) != []
    assert len(reco["links"]) == 6


def test_les_labels_en_double_ne_comptent_qu_une_fois():
    """La carte déduplique par label avant de couper à six : six liens dont
    deux homonymes n'en affichent que cinq, il reste donc une place."""
    reco = _reco(nb_liens=6)
    reco["links"][5]["label"] = reco["links"][0]["label"]
    assert fli.transform(reco) != []


def test_la_deduplication_ignore_la_casse():
    reco = _reco(nb_liens=6)
    reco["links"][5]["label"] = reco["links"][0]["label"].lower()
    assert fli.transform(reco) != []


def test_les_custom_links_comptent_dans_le_plafond():
    """`RecoCard` concatène `customLinks` AVANT `links` puis coupe à six : les
    ignorer ferait sauter un lien saisi à la main."""
    reco = _reco(nb_liens=4, customLinks=[
        {"label": "C1", "url": "https://exemple.fr/c1"},
        {"label": "C2", "url": "https://exemple.fr/c2"}])
    assert fli.transform(reco) == []


def test_un_custom_link_mal_forme_ne_fait_pas_lever():
    reco = _reco(nb_liens=2, customLinks=["hérité"])
    assert fli.transform(reco) != []


# ===== Les refus =============================================================
def test_refuse_sans_handle():
    reco = _reco()
    reco["externalIds"] = {}
    assert fli.transform(reco) == []
    assert len(reco["links"]) == 2


def test_refuse_sans_externalids():
    reco = _reco()
    del reco["externalIds"]
    assert fli.transform(reco) == []


def test_refuse_un_handle_qui_n_est_pas_une_chaine():
    """Donnée héritée : un handle numérique arriverait en `int`."""
    reco = _reco()
    reco["externalIds"]["instagram"] = 12345
    assert fli.transform(reco) == []


@pytest.mark.parametrize("handle", [
    "",                 # vide après nettoyage
    "avec espace",
    "avec/slash",       # injection de chemin dans l'URL
    "avec?query",
    "a" * 31,           # au-delà de la limite Instagram
])
def test_refuse_un_handle_invalide(handle: str):
    """Le handle est interpolé dans un chemin d'URL : on le valide avant, avec
    la MÊME règle que `merchants.ts` (`IG_HANDLE_RE`)."""
    reco = _reco(handle=handle)
    assert fli.transform(reco) == []


def test_refuse_quand_la_reco_n_a_AUCUN_lien():
    """Piège majeur : `RecoCard` n'appelle le résolveur automatique que si
    `links` est VIDE. Y écrire un unique lien Instagram supprimerait donc tous
    les liens auto-générés de la carte — Deezer, JustWatch, libraires — au
    profit du seul Instagram. Une carte y perdrait au change."""
    reco = _reco(nb_liens=0)
    assert fli.transform(reco) == []
    assert reco["links"] == []


def test_refuse_quand_links_est_absent():
    reco = _reco()
    del reco["links"]
    assert fli.transform(reco) == []
    assert "links" not in reco


def test_refuse_quand_links_n_est_pas_une_liste():
    reco = _reco()
    reco["links"] = {"label": "P0", "url": "https://exemple.fr/0"}
    assert fli.transform(reco) == []


def test_refuse_un_second_lien_instagram():
    reco = _reco(nb_liens=2)
    reco["links"][0]["label"] = "Instagram"
    assert fli.transform(reco) == []


def test_refuse_un_second_lien_instagram_quelle_que_soit_la_casse():
    """La carte déduplique par label en minuscules : « INSTAGRAM » et
    « Instagram » sont le même lien pour elle."""
    reco = _reco(nb_liens=2)
    reco["links"][0]["label"] = "INSTAGRAM"
    assert fli.transform(reco) == []


def test_refuse_une_url_deja_presente_sous_un_autre_label():
    """Un lien peut porter le label « Insta » : le label ne suffit pas à
    détecter le doublon, l'URL non plus toute seule."""
    reco = _reco(nb_liens=2)
    reco["links"][0] = {"label": "Insta",
                        "url": "https://www.instagram.com/laurentbaffie/"}
    assert fli.transform(reco) == []


def test_la_passe_est_idempotente():
    reco = _reco()
    assert fli.transform(reco) != []
    assert fli.transform(reco) == []
    assert len(reco["links"]) == 3


# ===== Conformité au schéma ================================================
def test_le_kind_est_celui_du_schema():
    """`content.config.ts` déclare une énumération fermée ; une valeur hors
    liste passe l'écriture et casse le build — c'est déjà arrivé avec
    `kind: "ticket"`."""
    assert fli.KIND in {"buy", "borrow", "streaming", "info", "official", "social"}


def test_l_ethics_est_celle_du_schema():
    assert fli.ETHICS in {"indie", "neutral", "avoid"}


def test_le_plafond_est_celui_de_la_carte():
    """`RecoCard.astro` fait un `slice(0, 6)`."""
    assert fli.AFFICHES == 6


def test_l_url_est_en_https():
    reco = _reco()
    fli.transform(reco)
    assert reco["links"][-1]["url"].startswith("https://www.instagram.com/")


# ===== CLI ==================================================================
def test_main_dry_run_n_ecrit_pas(recos_root: Path, tmp_path: Path):
    path = _write(recos_root / "s" / "a.json", _reco())
    avant = path.read_text(encoding="utf-8")
    report = tmp_path / "r.json"
    assert fli.main(["--json", str(report)]) == 0
    assert path.read_text(encoding="utf-8") == avant
    rapport = json.loads(report.read_text(encoding="utf-8"))
    assert rapport["applied"] is False
    assert rapport["plafond_affichage"] == 6


def test_main_apply_ecrit_le_lien(recos_root: Path):
    path = _write(recos_root / "s" / "a.json", _reco())
    assert fli.main(["--apply"]) == 0
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["links"][-1]["url"] == "https://www.instagram.com/laurentbaffie/"


def test_main_apply_ne_touche_pas_une_carte_pleine(recos_root: Path):
    path = _write(recos_root / "s" / "b.json", _reco(nb_liens=6))
    avant = path.read_text(encoding="utf-8")
    assert fli.main(["--apply"]) == 0
    assert path.read_text(encoding="utf-8") == avant


def test_build_parser_expose_les_options_communes():
    args = fli.build_parser().parse_args([])
    assert args.apply is False
    assert args.source is None
    assert args.json_path is None
