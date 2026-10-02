"""Tests de la passe, de l'écriture et de la ligne de commande.

Le disque est réel (`tmp_path`), le réseau neutralisé : on remplace
`wikidata_links.resoudre` par une résolution mappée par identifiant de reco,
ou les fonctions de client quand c'est leur enchaînement qu'on éprouve. Les
substitutions visent le module où la fonction est UTILISÉE — `run` vit dans
`wikidata_links`, et remplacer la façade n'aurait aucun effet sur lui.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import enrich_wikidata_links as e
import wikidata_links as wl
from enrichment.field_refresher import EnrichedAtCorruptedError

WIKIPEDIA = wl.Lien("wikipedia", "info", "indie", "Wikipédia",
                    "https://fr.wikipedia.org/wiki/Fabe")
INSTAGRAM = wl.Lien("instagram", "social", "neutral", "Instagram",
                    "https://www.instagram.com/fabe/")


def _ecrire(racine: Path, source: str, reco: dict) -> Path:
    dossier = racine / source
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{reco['id']}.json"
    chemin.write_text(json.dumps(reco, ensure_ascii=False, indent=2), encoding="utf-8")
    return chemin


@pytest.fixture()
def racine(tmp_path: Path) -> Path:
    r = tmp_path / "recos"
    _ecrire(r, "src-a", {"id": "a-1", "title": "Fabe", "types": ["artiste"],
                         "status": "validated", "links": []})
    _ecrire(r, "src-a", {"id": "a-2", "title": "Un film", "types": ["film"],
                         "status": "validated", "links": []})
    _ecrire(r, "src-a", {"id": "a-3", "title": "Brouillon", "types": ["artiste"],
                         "status": "draft", "links": []})
    _ecrire(r, "src-b", {"id": "b-1", "title": "Solann", "types": ["artiste"],
                         "status": "validated", "links": []})
    return r


def _resolutions(mapping):
    """Fausse résolution : la reco décide de ce qu'elle reçoit."""
    def resoudre(reco, *, session):
        return mapping.get(reco["id"], wl.Resolution((), e.RAISON_NO_ENTITY))
    return resoudre


def _lire(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


# ===== sélection ============================================================
def test_seuls_les_artistes_valides_sont_vus(racine, monkeypatch):
    """Le film n'est pas même compté ; le brouillon l'est, avec sa raison."""
    monkeypatch.setattr(wl, "resoudre", _resolutions({}))

    rapport = wl.run(root=racine, sleep=0)

    assert rapport.vues == 3  # a-1, a-3 (brouillon), b-1
    raisons = {c.reco_id: c.raison for c in rapport.cas}
    assert raisons["a-3"] == wl.RAISON_NOT_VALIDATED
    assert "a-2" not in raisons


def test_ids_restreint_a_un_episode(racine, monkeypatch):
    """Ce dont la chaîne a besoin : un épisode relu, sans rouvrir le corpus."""
    monkeypatch.setattr(wl, "resoudre", _resolutions({}))

    rapport = wl.run(root=racine, ids={"b-1"}, sleep=0)

    assert rapport.vues == 1
    assert [c.reco_id for c in rapport.cas] == ["b-1"]


def test_une_source_et_un_type_peuvent_filtrer(racine, monkeypatch):
    monkeypatch.setattr(wl, "resoudre", _resolutions({}))

    assert wl.run(root=racine, source="src-b", sleep=0).vues == 1
    assert wl.run(root=racine, types=("artiste",), sleep=0).vues == 3
    assert wl.run(root=racine, types=("livre",), sleep=0).vues == 0


def test_limit_borne_les_appels_sans_fausser_le_compte(racine, monkeypatch):
    appels = []

    def resoudre(reco, *, session):
        appels.append(reco["id"])
        return wl.Resolution((), e.RAISON_NO_ENTITY)

    monkeypatch.setattr(wl, "resoudre", resoudre)

    rapport = wl.run(root=racine, limit=1, sleep=0)

    assert len(appels) == 1 and rapport.vues == 3


def test_un_fichier_illisible_narrete_pas_la_passe(racine, monkeypatch):
    (racine / "src-a" / "casse.json").write_text("{ pas du json", encoding="utf-8")
    monkeypatch.setattr(wl, "resoudre",
                        _resolutions({"a-1": wl.Resolution((WIKIPEDIA,), wl.RAISON_OK)}))

    rapport = wl.run(root=racine, apply=True, sleep=0)

    assert wl.RAISON_UNREADABLE in {c.raison for c in rapport.cas}
    assert rapport.ecrites == 1


# ===== écriture =============================================================
def test_apply_ecrit_les_liens_et_laudit_trail(racine, monkeypatch):
    monkeypatch.setattr(wl, "resoudre", _resolutions(
        {"a-1": wl.Resolution((WIKIPEDIA, INSTAGRAM), wl.RAISON_OK,
                              wl.PREUVE_IDENTIFIANT, "Q1")}))

    rapport = wl.run(root=racine, apply=True, sleep=0)

    ecrit = _lire(racine / "src-a" / "a-1.json")
    assert [lien["url"] for lien in ecrit["links"]] == [WIKIPEDIA.url, INSTAGRAM.url]
    assert "links" in ecrit["enrichedAt"]
    assert rapport.ecrites == 1 and rapport.servies == {"a-1"}


def test_la_simulation_necrit_rien(racine, monkeypatch):
    monkeypatch.setattr(wl, "resoudre",
                        _resolutions({"a-1": wl.Resolution((WIKIPEDIA,), wl.RAISON_OK)}))
    avant = (racine / "src-a" / "a-1.json").read_text(encoding="utf-8")

    rapport = wl.run(root=racine, apply=False, sleep=0)

    assert (racine / "src-a" / "a-1.json").read_text(encoding="utf-8") == avant
    assert rapport.ecrites == 0
    assert rapport.servies == {"a-1"}  # trouvé, mais pas écrit


def test_un_lien_existant_nest_jamais_ecrase(racine):
    deja = {"kind": "info", "ethics": "indie", "label": "Wikipédia",
            "url": "https://fr.wikipedia.org/wiki/Autre_chose"}
    reco = {"id": "x", "links": [deja]}

    wl.appliquer(reco, [WIKIPEDIA, INSTAGRAM])

    assert reco["links"][0] == deja
    assert [lien["url"] for lien in reco["links"]] == [deja["url"], INSTAGRAM.url]


def test_appliquer_sans_rien_de_neuf_ne_touche_pas_laudit_trail():
    reco = {"id": "x", "links": [WIKIPEDIA.as_link()]}

    wl.appliquer(reco, [WIKIPEDIA])

    assert "enrichedAt" not in reco


def test_un_audit_trail_corrompu_fait_sauter_la_reco_pas_la_passe(racine, monkeypatch):
    _ecrire(racine, "src-a", {"id": "a-9", "title": "Fabe", "types": ["artiste"],
                              "status": "validated", "links": [],
                              "enrichedAt": "pas un dict"})
    monkeypatch.setattr(wl, "resoudre",
                        _resolutions({"a-9": wl.Resolution((WIKIPEDIA,), wl.RAISON_OK),
                                      "a-1": wl.Resolution((WIKIPEDIA,), wl.RAISON_OK)}))

    rapport = wl.run(root=racine, apply=True, sleep=0)

    assert rapport.ecrites == 1  # a-1 écrite, a-9 sautée
    assert _lire(racine / "src-a" / "a-9.json")["links"] == []
    with pytest.raises(EnrichedAtCorruptedError):
        wl.appliquer({"id": "z", "enrichedAt": "x"}, [WIKIPEDIA])


# ===== enchaînement des deux chemins ========================================
def test_lidentifiant_est_tente_avant_le_titre(monkeypatch):
    """Et le titre n'est même pas demandé quand l'identifiant a répondu."""
    par_titre = []
    entite = wl.Entite(qid="Q1", label="Solann", natures=("Q5",), frwiki="Solann",
                       claims={"P31": ("Q5",), "P2722": ("78965772",)})
    monkeypatch.setattr(wl, "entites_par_identifiant",
                        lambda *_a, **_k: [entite])
    monkeypatch.setattr(wl, "entites_par_titres",
                        lambda *a, **k: par_titre.append(a) or {})

    resolution = wl.resoudre(
        {"id": "x", "title": "Solann", "types": ["artiste"], "status": "validated",
         "externalIds": {"deezer": "78965772"}, "links": []}, session=None)

    assert resolution.raison == wl.RAISON_OK
    assert resolution.preuve == wl.PREUVE_IDENTIFIANT
    assert par_titre == []


def test_le_titre_sert_de_repli_quand_aucun_identifiant_nest_porte(monkeypatch):
    entite = wl.Entite(qid="Q2", label="Fabe", natures=("Q5",), frwiki="Fabe",
                       claims={"P31": ("Q5",)})
    monkeypatch.setattr(wl, "entites_par_titres", lambda *_a, **_k: {"Fabe": entite})

    resolution = wl.resoudre({"id": "x", "title": "Fabe", "types": ["artiste"],
                              "status": "validated", "links": []}, session=None)

    assert resolution.preuve == wl.PREUVE_TITRE


def test_un_429_devient_une_raison_pas_une_panne(racine, monkeypatch):
    """La reco repart avec `http-error`, et la passe continue."""
    def injoignable(*_a, **_k):
        raise wl.WikidataInjoignable("limite d'appels atteinte (429)")

    monkeypatch.setattr(wl, "entites_par_titres", injoignable)

    rapport = wl.run(root=racine, sleep=0)

    raisons = {c.reco_id: c.raison for c in rapport.cas}
    assert raisons["a-1"] == wl.RAISON_HTTP_ERROR
    assert raisons["b-1"] == wl.RAISON_HTTP_ERROR  # la suivante est tentée
    assert "429" in next(c.detail for c in rapport.cas if c.reco_id == "a-1")


def test_une_coupure_apres_un_candidat_tranche_sur_ce_quon_a(monkeypatch):
    """Deezer a répondu, Spotify non : on ne jette pas ce qui est prouvé."""
    entite = wl.Entite(qid="Q1", label="Solann", natures=("Q5",), frwiki="Solann",
                       claims={"P31": ("Q5",), "P2722": ("78965772",)})
    appels = []

    def par_identifiant(_session, prop, _valeur):
        appels.append(prop)
        if len(appels) == 1:        # Deezer répond
            return [entite]
        raise wl.WikidataInjoignable("429")   # Spotify se dérobe

    monkeypatch.setattr(wl, "entites_par_identifiant", par_identifiant)

    resolution = wl.resoudre(
        {"id": "x", "title": "Solann", "types": ["artiste"], "status": "validated",
         "externalIds": {"deezer": "78965772"},
         "links": [{"url": "https://open.spotify.com/artist/ABC"}]}, session=None)

    assert resolution.raison == wl.RAISON_OK


def test_un_type_non_servi_nappelle_pas_wikidata(monkeypatch):
    """Garde-fou de dernier recours : `resoudre` refuse avant tout appel."""
    assert wl.resoudre({"id": "x", "title": "Linkee", "types": ["autre"]},
                       session=None).raison == wl.RAISON_TYPE_UNSUPPORTED


# ===== rapport ==============================================================
def test_le_rapport_distingue_ce_qui_reste_a_arbitrer(racine, monkeypatch):
    monkeypatch.setattr(wl, "resoudre", _resolutions({
        "a-1": wl.Resolution((), e.RAISON_AMBIGUOUS, detail="Q1 Q2"),
        "b-1": wl.Resolution((WIKIPEDIA,), wl.RAISON_OK),
    }))

    rapport = wl.run(root=racine, sleep=0)
    texte = wl.format_rapport(rapport)

    assert [c.reco_id for c in rapport.a_arbitrer] == ["a-1"]
    assert rapport.liens_poses == 1
    assert "À arbitrer à la main : 1" in texte and "Q1 Q2" in texte


def test_le_rapport_json_est_serialisable(racine, monkeypatch):
    monkeypatch.setattr(wl, "resoudre", _resolutions(
        {"a-1": wl.Resolution((WIKIPEDIA,), wl.RAISON_OK, wl.PREUVE_TITRE, "Q1")}))

    charge = e.rapport_payload(wl.run(root=racine, sleep=0))

    assert json.loads(json.dumps(charge, ensure_ascii=False))["servies"] == ["a-1"]
    assert charge["liens"] == 1


# ===== ligne de commande ====================================================
def test_la_simulation_est_le_defaut_du_cli(racine, monkeypatch, caplog):
    monkeypatch.setattr(e, "RECOS_DIR", racine)
    monkeypatch.setattr(wl, "resoudre",
                        _resolutions({"a-1": wl.Resolution((WIKIPEDIA,), wl.RAISON_OK)}))
    avant = (racine / "src-a" / "a-1.json").read_text(encoding="utf-8")

    with caplog.at_level("INFO"):
        assert e.main(["--source", "src-a"]) == 0

    assert (racine / "src-a" / "a-1.json").read_text(encoding="utf-8") == avant
    assert any("SIMULATION" in r.getMessage() for r in caplog.records)


def test_apply_prend_le_verrou_du_serveur_de_relecture(racine, monkeypatch):
    import contextlib

    pris = []
    monkeypatch.setattr(e, "RECOS_DIR", racine)
    monkeypatch.setattr(e, "acquire_pipeline_lock",
                        lambda force=False: pris.append(force) or contextlib.nullcontext())
    monkeypatch.setattr(wl, "resoudre",
                        _resolutions({"a-1": wl.Resolution((WIKIPEDIA,), wl.RAISON_OK)}))

    assert e.main(["--apply", "--ignore-server-lock"]) == 0

    assert pris == [True]
    assert _lire(racine / "src-a" / "a-1.json")["links"]


def test_un_verrou_occupe_arrete_lecriture(racine, monkeypatch):
    def occupe(force=False):
        raise e.ServerLockBusy("le serveur de relecture tourne")

    monkeypatch.setattr(e, "RECOS_DIR", racine)
    monkeypatch.setattr(e, "acquire_pipeline_lock", occupe)
    monkeypatch.setattr(wl, "resoudre",
                        _resolutions({"a-1": wl.Resolution((WIKIPEDIA,), wl.RAISON_OK)}))

    assert e.main(["--apply"]) == 1
    assert _lire(racine / "src-a" / "a-1.json")["links"] == []


def test_le_cli_accepte_une_liste_dids_en_fichier(racine, tmp_path, monkeypatch):
    fichier = tmp_path / "ids.txt"
    fichier.write_text("# un épisode\nb-1\n", encoding="utf-8")
    monkeypatch.setattr(e, "RECOS_DIR", racine)
    vus = []

    def resoudre(reco, *, session):
        vus.append(reco["id"])
        return wl.Resolution((), e.RAISON_NO_ENTITY)

    monkeypatch.setattr(wl, "resoudre", resoudre)

    assert e.main(["--ids", f"@{fichier}", "--types", "artiste"]) == 0
    assert vus == ["b-1"]


def test_le_cli_ecrit_son_rapport_json(racine, tmp_path, monkeypatch):
    sortie = tmp_path / "rapport.json"
    monkeypatch.setattr(e, "RECOS_DIR", racine)
    monkeypatch.setattr(wl, "resoudre",
                        _resolutions({"a-1": wl.Resolution((WIKIPEDIA,), wl.RAISON_OK)}))

    assert e.main(["--json", str(sortie)]) == 0

    assert json.loads(sortie.read_text(encoding="utf-8"))["servies"] == ["a-1"]
