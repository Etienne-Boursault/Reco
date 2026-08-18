"""Tests de `tools/fix_floodcast_recos.py`.

CE QUE FAIT CET OUTIL, ET POURQUOI
----------------------------------
L'episode « Special FLOODCAST avec Florent Bernard et Adrien Menielle »
(guid c950798f…, 17 fevrier 2020) a vu deux de ses recos ECARTEES le
2026-07-18 pour « transcript inexploitable : inverifiable ». Le motif est
caduc : le transcript existe (196 Ko, 4722 lignes) et les invites figurent
desormais dans les metadonnees de l'episode — l'autre motif invoque.

Reecoute faite, l'editeur a tranche quatre points. Les timecodes sont sur la
timeline YOUTUBE, seule source du transcript de cet episode.

CE QUE LES TESTS PROTEGENT
--------------------------
La CREATION de recos est plus dangereuse que leur modification : un
identifiant deja pris ecraserait une reco existante en silence. Les gardes
sont donc testees pour elles-memes, pas seulement le cas nominal.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import common
import dataset_fixes as df
import fix_floodcast_recos as ffr


@pytest.fixture
def recos_root(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "src" / "content" / "recos"
    (root / "un-bon-moment").mkdir(parents=True)
    monkeypatch.setattr(common, "RECOS_DIR", root)
    monkeypatch.setattr(df, "RECOS_DIR", root)
    items = tmp_path / "src" / "content" / "items"
    items.mkdir(parents=True)
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(df, "ITEMS_DIR", items)
    return root


# ===== Les deux restaurations ==============================================
def test_souchon_est_restaure_et_attribue_a_florent_bernard():
    reco = {"id": "ubm-0599", "title": "Souchon", "status": "discarded"}
    changes = ffr.transform(reco)
    assert reco["status"] == "validated"
    assert reco["recommendedBy"] == "Florent Bernard"
    assert {c.field for c in changes} == {"status", "recommendedBy"}


def test_souchon_n_est_PAS_une_oeuvre_d_invite():
    """Florent Bernard mentionne Alain Souchon en fan, pas en auteur."""
    reco = {"id": "ubm-0599", "title": "Souchon", "status": "discarded"}
    ffr.transform(reco)
    assert "guestWork" not in reco


def test_derby_girl_est_restaure_attribue_ET_marque_oeuvre_d_invite():
    reco = {"id": "ubm-1023", "title": "Derby Girl", "status": "discarded",
            "recommendedBy": "Navo"}
    ffr.transform(reco)
    assert reco["status"] == "validated"
    assert reco["recommendedBy"] == "Adrien Ménielle"
    assert reco["guestWork"] is True


def test_le_titre_sert_de_garde():
    """Si le corpus a bouge depuis la reecoute, on n'ecrit rien."""
    reco = {"id": "ubm-0599", "title": "Autre chose", "status": "discarded"}
    assert ffr.transform(reco) == []
    assert reco["status"] == "discarded"


def test_une_reco_hors_perimetre_n_est_pas_touchee():
    reco = {"id": "ubm-9999", "title": "X", "status": "discarded"}
    assert ffr.transform(reco) == []


def test_la_passe_est_idempotente():
    reco = {"id": "ubm-1023", "title": "Derby Girl", "status": "discarded"}
    ffr.transform(reco)
    assert ffr.transform(reco) == []


# ===== Les deux creations ==================================================
def test_les_deux_recos_sont_creees(recos_root: Path):
    crees = ffr.creer(recos_root, apply=True)
    assert len(crees) == 2
    titres = set()
    for chemin in crees:
        doc = json.loads(Path(chemin).read_text(encoding="utf-8"))
        titres.add(doc["title"])
    assert titres == {"Pitch", "La Flamme"}


def test_les_creations_sont_des_oeuvres_de_florent_bernard(recos_root: Path):
    for chemin in ffr.creer(recos_root, apply=True):
        doc = json.loads(Path(chemin).read_text(encoding="utf-8"))
        assert doc["recommendedBy"] == "Florent Bernard"
        assert doc["guestWork"] is True
        assert doc["episodeGuid"] == ffr.EPISODE_GUID


def test_creer_sans_apply_n_ecrit_rien(recos_root: Path):
    crees = ffr.creer(recos_root, apply=False)
    assert len(crees) == 2  # annonce ce qu'il ferait
    assert not list((recos_root / "un-bon-moment").glob("*.json"))


def test_un_identifiant_DEJA_PRIS_bloque_la_creation(recos_root: Path):
    """La garde essentielle : creer par-dessus une reco existante
    l'effacerait sans laisser de trace."""
    existant = recos_root / "un-bon-moment" / "3207.json"
    existant.write_text(json.dumps({"id": "ubm-3207", "title": "Autre"}),
                        encoding="utf-8")
    with pytest.raises(SystemExit):
        ffr.creer(recos_root, apply=True)
    assert json.loads(existant.read_text(encoding="utf-8"))["title"] == "Autre"


def test_la_creation_est_idempotente(recos_root: Path):
    """Rejouer ne doit pas dupliquer : si la reco est deja la, on la saute."""
    ffr.creer(recos_root, apply=True)
    assert ffr.creer(recos_root, apply=True) == []


# ===== Coherence des donnees ecrites =======================================
def test_les_kind_de_liens_sont_ceux_du_schema():
    """`kind: "ticket"` a deja casse le build sur ce projet."""
    admis = {"buy", "borrow", "streaming", "info", "official", "social"}
    for entree in ffr.CREATIONS:
        for lien in entree["links"]:
            assert lien["kind"] in admis, lien


def test_les_ethics_sont_celles_du_schema():
    for entree in ffr.CREATIONS:
        for lien in entree["links"]:
            assert lien["ethics"] in {"indie", "neutral", "avoid"}, lien


def test_aucune_creation_n_emet_guestWork_null():
    """Le schema declare `guestWork: z.boolean().optional()` SANS
    `nullable()` : un `null` arrete le build."""
    for entree in ffr.CREATIONS:
        assert entree.get("guestWork") is True


def test_chaque_creation_porte_sa_citation_et_son_timecode():
    for entree in ffr.CREATIONS:
        assert entree["quote"].strip(), entree["title"]
        assert entree["timestamp"].count(":") == 2, entree["title"]


# ===== CLI =================================================================
def _ecrire(chemin: Path, doc: dict) -> Path:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    return chemin


def test_main_dry_run_ne_touche_a_rien(recos_root: Path, tmp_path: Path):
    p = _ecrire(recos_root / "un-bon-moment" / "0599.json",
                {"id": "ubm-0599", "title": "Souchon", "status": "discarded"})
    avant = p.read_text(encoding="utf-8")
    rapport = tmp_path / "r.json"
    assert ffr.main(["--json", str(rapport)]) == 0
    assert p.read_text(encoding="utf-8") == avant
    # ... et rien n'a ete cree non plus.
    assert not (recos_root / "un-bon-moment" / "3207.json").exists()


def test_main_apply_restaure_ET_cree(recos_root: Path):
    p = _ecrire(recos_root / "un-bon-moment" / "1023.json",
                {"id": "ubm-1023", "title": "Derby Girl", "status": "discarded",
                 "recommendedBy": "Navo"})
    assert ffr.main(["--apply"]) == 0
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["status"] == "validated"
    assert doc["recommendedBy"] == "Adrien Ménielle"
    assert doc["guestWork"] is True
    cree = json.loads((recos_root / "un-bon-moment" / "3207.json")
                      .read_text(encoding="utf-8"))
    assert cree["title"] == "Pitch"


def test_build_parser_expose_les_options_communes():
    args = ffr.build_parser().parse_args([])
    assert args.apply is False


# ===== Liens de Derby Girl =================================================
def test_derby_girl_recoit_la_paire_TMDB():
    """Restauree, la reco n'affichait qu'un lien de RECHERCHE JustWatch, alors
    qu'elle porte un identifiant TMDB valide (tv/112390 = Derby Girl, 2020,
    Charlotte Vecchiet et Nikola Lange — verifie contre l'API). La paire fiche
    + « Où regarder » est la convention du corpus : 269 recos la portent."""
    reco = {"id": "ubm-1023", "title": "Derby Girl", "status": "discarded"}
    ffr.transform(reco)
    urls = [lien["url"] for lien in reco["links"]]
    assert urls == [
        "https://www.themoviedb.org/tv/112390",
        "https://www.themoviedb.org/tv/112390-derby-girl/watch?locale=FR",
    ]


def test_la_paire_TMDB_respecte_la_convention_du_corpus():
    reco = {"id": "ubm-1023", "title": "Derby Girl", "status": "discarded"}
    ffr.transform(reco)
    fiche, ou_regarder = reco["links"]
    assert (fiche["kind"], fiche["label"]) == ("info", "TMDB")
    assert (ou_regarder["kind"], ou_regarder["label"]) == ("streaming", "Où regarder")
    assert {fiche["ethics"], ou_regarder["ethics"]} == {"neutral"}


def test_les_liens_existants_ne_sont_pas_ecrases():
    reco = {"id": "ubm-1023", "title": "Derby Girl", "status": "discarded",
            "links": [{"url": "https://exemple.fr/x", "label": "L"}]}
    ffr.transform(reco)
    assert reco["links"][0]["url"] == "https://exemple.fr/x"
    assert len(reco["links"]) == 3


def test_les_liens_ne_sont_pas_ajoutes_deux_fois():
    reco = {"id": "ubm-1023", "title": "Derby Girl", "status": "discarded"}
    ffr.transform(reco)
    ffr.transform(reco)
    assert len(reco["links"]) == 2


def test_souchon_ne_recoit_AUCUN_lien_pose_a_la_main():
    """Le resolveur automatique lui donne deja « Foule sentimentale » sur
    Deezer — la chanson citee dans l'episode a 00:07:27. Rien a ajouter."""
    reco = {"id": "ubm-0599", "title": "Souchon", "status": "discarded"}
    ffr.transform(reco)
    assert "links" not in reco
