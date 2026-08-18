"""Tests de `tools/completer_visionnage.py`.

POURQUOI CET OUTIL EXISTE
-------------------------
124 documents portaient un identifiant TMDB valide sans aucun lien de
visionnage : ni `externalIds.watchPage`, ni `watchProviders`. Leur page
d'oeuvre n'affichait donc qu'un lien « TMDB » nu — un renvoi vers une fiche,
pas un moyen de voir l'oeuvre.

Une partie vient des correctifs du 2026-08-18 : en retirant l'identifiant d'un
homonyme, on a retire avec lui la page et les diffuseurs qui en derivaient —
a juste titre, ils decrivaient l'autre oeuvre — mais rien ne les avait
reconstruits. Les autres n'avaient jamais ete enrichis.

CE QUE L'OUTIL POSE
-------------------
Ce que l'API TMDB donne pour la France, et rien d'autre :
  - `externalIds.watchPage`, le champ `link` de `watch/providers`. C'est la
    page qui liste les diffuseurs avec leurs VRAIS liens.
  - `watchProviders`, les noms des diffuseurs.

Il n'INVENTE aucune adresse. Quand l'API ne connait pas de diffuseur francais,
il n'ecrit rien : mieux vaut une page sans lien qu'une page qui promet un
visionnage inexistant.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import completer_visionnage as cv


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch):
    import common
    items = tmp_path / "items"
    recos = tmp_path / "recos"
    items.mkdir()
    recos.mkdir()
    monkeypatch.setattr(common, "ITEMS_DIR", items)
    monkeypatch.setattr(common, "RECOS_DIR", recos)
    return items, recos


def _doc(chemin: Path, **champs):
    base = {"id": "x", "title": "Drive",
            "externalIds": {"tmdb": 64690, "tmdbType": "movie"}}
    base.update(champs)
    chemin.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    return chemin


#: Ce que l'API rend pour « Drive » en France, reduit a l'essentiel.
REPONSE = ("https://www.themoviedb.org/movie/64690-drive/watch?locale=FR",
           [{"name": "Sooner", "url": "https://www.sooner.fr/recherche?q=Drive"},
            {"name": "Apple TV Store",
             "url": "https://tv.apple.com/search?term=Drive"}])


# ===== Ce qu'il pose =======================================================
def test_la_page_de_visionnage_est_posee(corpus, monkeypatch):
    items, _ = corpus
    p = _doc(items / "a.json")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    cv.executer(apply=True)
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["externalIds"]["watchPage"] == REPONSE[0]


def test_les_diffuseurs_sont_poses(corpus, monkeypatch):
    items, _ = corpus
    p = _doc(items / "a.json")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    cv.executer(apply=True)
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert [d["name"] for d in doc["watchProviders"]] == ["Sooner", "Apple TV Store"]


def test_rien_n_est_ecrit_sans_apply(corpus, monkeypatch):
    items, _ = corpus
    p = _doc(items / "a.json")
    avant = p.read_text(encoding="utf-8")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    rapport = cv.executer(apply=False)
    assert p.read_text(encoding="utf-8") == avant
    assert rapport["a_completer"] == 1


# ===== Ce qu'il refuse de faire ============================================
def test_une_oeuvre_SANS_diffuseur_francais_ne_recoit_RIEN(corpus, monkeypatch):
    """Mieux vaut une page sans lien qu'une page qui promet un visionnage
    inexistant."""
    items, _ = corpus
    p = _doc(items / "a.json")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: (None, []))
    cv.executer(apply=True)
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert "watchPage" not in doc["externalIds"]
    assert "watchProviders" not in doc


def test_un_document_SANS_identifiant_est_ignore(corpus, monkeypatch):
    items, _ = corpus
    p = _doc(items / "a.json", externalIds={})
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    cv.executer(apply=True)
    assert "watchPage" not in (json.loads(p.read_text(encoding="utf-8"))
                               .get("externalIds") or {})


def test_un_identifiant_SANS_type_est_ignore(corpus, monkeypatch):
    """Sans le type, on ne sait pas quelle route interroger — et se tromper
    renverrait les diffuseurs d'une autre oeuvre."""
    items, _ = corpus
    p = _doc(items / "a.json", externalIds={"tmdb": 64690})
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    cv.executer(apply=True)
    assert "watchPage" not in json.loads(p.read_text(encoding="utf-8"))["externalIds"]


def test_une_reco_ECARTEE_n_est_pas_enrichie(corpus, monkeypatch):
    """Elle ne s'affiche nulle part : l'enrichir depenserait une requete pour
    rien."""
    _, recos = corpus
    p = _doc(recos / "a.json", status="discarded")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    cv.executer(apply=True)
    assert "watchPage" not in json.loads(p.read_text(encoding="utf-8"))["externalIds"]


def test_une_panne_d_API_n_efface_rien(corpus, monkeypatch):
    """Une exception ne doit pas laisser le document a moitie modifie."""
    items, _ = corpus
    p = _doc(items / "a.json")
    avant = p.read_text(encoding="utf-8")

    def tombe(*a, **k):
        raise RuntimeError("API indisponible")

    monkeypatch.setattr(cv, "interroger", tombe)
    rapport = cv.executer(apply=True)
    assert p.read_text(encoding="utf-8") == avant
    assert rapport["echecs"] == 1


def test_un_json_illisible_ne_fait_pas_tomber_la_passe(corpus, monkeypatch):
    items, _ = corpus
    (items / "casse.json").write_text("{ pas du json", encoding="utf-8")
    _doc(items / "a.json")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    assert cv.executer(apply=True)["completes"] == 1


# ===== Les deux collections ================================================
def test_recos_ET_items_sont_traites(corpus, monkeypatch):
    items, recos = corpus
    a = _doc(items / "a.json")
    b = _doc(recos / "b.json", status="validated")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    cv.executer(apply=True)
    for p in (a, b):
        assert json.loads(p.read_text(encoding="utf-8"))["externalIds"]["watchPage"]


# ===== CLI =================================================================
def test_main_dry_run_par_defaut(corpus, monkeypatch):
    items, _ = corpus
    p = _doc(items / "a.json")
    avant = p.read_text(encoding="utf-8")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    assert cv.main([]) == 0
    assert p.read_text(encoding="utf-8") == avant


def test_main_apply(corpus, monkeypatch):
    items, _ = corpus
    p = _doc(items / "a.json")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    assert cv.main(["--apply"]) == 0
    assert json.loads(p.read_text(encoding="utf-8"))["externalIds"]["watchPage"]


def test_main_limite_le_nombre_d_appels(corpus, monkeypatch):
    """`--limit` sert a essayer sur quelques cas avant de lancer les 124."""
    items, _ = corpus
    for i in range(3):
        _doc(items / f"{i}.json", id=f"x{i}")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    assert cv.main(["--apply", "--limit", "2"]) == 0
    faits = sum(1 for f in items.glob("*.json")
                if "watchPage" in json.loads(f.read_text(encoding="utf-8"))["externalIds"])
    assert faits == 2


# ===== La fonction d'appel, sans reseau ====================================
def test_interroger_delegue_au_pipeline(monkeypatch):
    """`interroger` ne fait que brancher la session sur la fonction du
    pipeline. La rediriger ailleurs ferait diverger les deux chemins : le jour
    ou l'un est corrige, l'autre poserait encore l'ancienne forme."""
    import sys
    import types

    vus = {}

    class SessionFactice:
        def __enter__(self): return "session"
        def __exit__(self, *a): return False

    faux_requests = types.SimpleNamespace(Session=SessionFactice)
    faux_enrich = types.SimpleNamespace(
        tmdb_watch_providers=lambda s, i, k, t, **kw: vus.update(
            session=s, tmdb=i, kind=k, titre=t, **kw) or ("PAGE", ["P"]))
    monkeypatch.setitem(sys.modules, "requests", faux_requests)
    monkeypatch.setitem(sys.modules, "enrich_tmdb", faux_enrich)
    monkeypatch.setenv("TMDB_API_KEY", "clef-de-test")

    assert cv.interroger("64690", "movie", "Drive") == ("PAGE", ["P"])
    assert vus["tmdb"] == "64690" and vus["kind"] == "movie"
    # `strict=True` doit etre transmis : sans lui, une panne d'API renverrait
    # une reponse vide que la passe lirait comme « aucun diffuseur ».
    assert vus["strict"] is True
    assert vus["api_key"] == "clef-de-test"


def test_interroger_REFUSE_de_travailler_sans_clef(monkeypatch):
    """Sans clef, l'API repond 401 et l'oeuvre passerait pour « sans
    diffuseur » : le manque deviendrait invisible. Le premier essai reel s'y
    est laisse prendre — trois oeuvres comptees vides alors que la clef
    n'etait pas chargee."""
    import sys
    import types

    monkeypatch.setitem(sys.modules, "requests",
                        types.SimpleNamespace(Session=object))
    monkeypatch.setitem(sys.modules, "enrich_tmdb",
                        types.SimpleNamespace(tmdb_watch_providers=None))
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("TMDB_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TMDB_API_KEY"):
        cv.interroger("1", "movie", "X")


def test_un_externalIds_mal_forme_est_ignore(corpus, monkeypatch):
    """Donnee heritee : le champ peut ne pas etre un objet."""
    items, _ = corpus
    for i, mauvais in enumerate(("texte", [], 42)):
        _doc(items / f"m{i}.json", id=f"m{i}", externalIds=mauvais)
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    assert cv.executer(apply=True)["a_completer"] == 0


def test_une_oeuvre_avec_page_MAIS_sans_diffuseur_recoit_la_page(corpus, monkeypatch):
    """L'API peut connaitre la page sans lister de plateforme : la page reste
    utile, elle mene au recapitulatif TMDB."""
    items, _ = corpus
    p = _doc(items / "a.json")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: ("https://x.fr/w", []))
    cv.executer(apply=True)
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert doc["externalIds"]["watchPage"] == "https://x.fr/w"
    assert "watchProviders" not in doc


# ===== Asymetrie des deux schemas ==========================================
def test_un_ITEM_recoit_des_diffuseurs_nommes_name(corpus, monkeypatch):
    """`content.config.ts` declare `watchProviders[].name` cote ITEM et
    `[].label` cote RECO. Le pipeline produit `label` ; ecrire tel quel dans un
    item ARRETE le build — c'est arrive le 2026-08-18 sur 05d956f0."""
    items, _ = corpus
    p = _doc(items / "a.json")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: (
        "https://x.fr/w", [{"label": "Sooner", "url": "https://s.fr",
                            "ethics": "neutral"}]))
    cv.executer(apply=True)
    fournisseur = json.loads(p.read_text(encoding="utf-8"))["watchProviders"][0]
    assert fournisseur["name"] == "Sooner"
    assert "label" not in fournisseur


def test_une_RECO_recoit_des_diffuseurs_nommes_label(corpus, monkeypatch):
    _, recos = corpus
    p = _doc(recos / "a.json", status="validated")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: (
        "https://x.fr/w", [{"label": "Sooner", "url": "https://s.fr",
                            "ethics": "neutral"}]))
    cv.executer(apply=True)
    fournisseur = json.loads(p.read_text(encoding="utf-8"))["watchProviders"][0]
    assert fournisseur["label"] == "Sooner"
    assert "name" not in fournisseur


def test_les_autres_champs_du_diffuseur_survivent(corpus, monkeypatch):
    items, _ = corpus
    p = _doc(items / "a.json")
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: (
        "https://x.fr/w", [{"label": "Canal VOD", "url": "https://c.fr",
                            "ethics": "avoid"}]))
    cv.executer(apply=True)
    fournisseur = json.loads(p.read_text(encoding="utf-8"))["watchProviders"][0]
    assert fournisseur["url"] == "https://c.fr"
    assert fournisseur["ethics"] == "avoid"


def test_une_page_SANS_diffuseurs_est_aussi_un_manque(corpus, monkeypatch):
    """Le premier critere ne retenait que l'absence de `watchPage`. « Drive »
    en avait une — reconstruite par le correctif des identifiants — mais aucun
    diffuseur, et sa page d'oeuvre restait a trois liens quand les autres en
    retrouvaient vingt."""
    items, _ = corpus
    p = _doc(items / "a.json",
             externalIds={"tmdb": 64690, "tmdbType": "movie",
                          "watchPage": "https://www.themoviedb.org/movie/"
                                       "64690/watch?locale=FR"})
    monkeypatch.setattr(cv, "interroger", lambda *a, **k: REPONSE)
    cv.executer(apply=True)
    doc = json.loads(p.read_text(encoding="utf-8"))
    assert len(doc["watchProviders"]) == 2


def test_un_document_COMPLET_n_est_toujours_pas_reinterroge(corpus, monkeypatch):
    """La garde d'origine reste : page ET diffuseurs presents, on passe."""
    items, _ = corpus
    _doc(items / "a.json",
         externalIds={"tmdb": 64690, "tmdbType": "movie",
                      "watchPage": "https://exemple.fr/x"},
         watchProviders=[{"name": "Sooner", "url": "https://s.fr"}])
    appels = []
    monkeypatch.setattr(cv, "interroger",
                        lambda *a, **k: appels.append(a) or REPONSE)
    cv.executer(apply=True)
    assert appels == []
