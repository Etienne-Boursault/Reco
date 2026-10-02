"""Tests de la passe, de l'écriture et de la ligne de commande.

Le disque est réel (`tmp_path`), le réseau neutralisé : on remplace
`boutique_links.resoudre` par une résolution mappée par identifiant de reco. Les
substitutions visent le module où la fonction est UTILISÉE — `run` vit dans
`boutique_links`, et remplacer la façade n'aurait aucun effet sur lui.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import boutique_links as bl
import boutique_matching as bm
import enrich_boutique_links as e
from enrichment.field_refresher import EnrichedAtCorruptedError

STEAM = bm.Lien("steam", "buy", "neutral", "Steam",
                "https://store.steampowered.com/app/210970/")
LIBRAIRE = bm.Lien("place-des-libraires", "buy", "indie", "Place des Libraires",
                   "https://www.placedeslibraires.fr/livre/9782709677424-x/")


def _ecrire(racine: Path, source: str, reco: dict) -> Path:
    dossier = racine / source
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{reco['id']}.json"
    chemin.write_text(json.dumps(reco, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    return chemin


@pytest.fixture()
def racine(tmp_path: Path) -> Path:
    r = tmp_path / "recos"
    _ecrire(r, "src-a", {"id": "a-1", "title": "The Witness",
                         "creator": "Thekla, Inc.", "types": ["jeu"],
                         "status": "validated", "links": []})
    _ecrire(r, "src-a", {"id": "a-2", "title": "Les Solitudes de Petite Rivière",
                         "creator": "Kalindi Ramphul", "types": ["livre"],
                         "status": "validated", "links": []})
    _ecrire(r, "src-a", {"id": "a-3", "title": "Un album", "types": ["album"],
                         "status": "validated", "links": []})
    _ecrire(r, "src-a", {"id": "a-4", "title": "Brouillon", "types": ["jeu"],
                         "creator": "Studio", "status": "draft", "links": []})
    _ecrire(r, "src-b", {"id": "b-1", "title": "Blue Prince",
                         "creator": "Dogubomb", "types": ["jeu"],
                         "status": "validated", "links": []})
    return r


def _resolutions(mapping):
    """Fausse résolution : la reco décide de ce qu'elle reçoit."""
    def resoudre(reco, *, session, permettre_sans_studio=False):
        return mapping.get(reco["id"], bm.Resolution(raison=bm.RAISON_NO_MATCH))
    return resoudre


def _lire(chemin: Path) -> dict:
    return json.loads(chemin.read_text(encoding="utf-8"))


# ===== sélection ============================================================
def test_seuls_les_jeux_et_livres_valides_sont_vus(racine, monkeypatch):
    monkeypatch.setattr(bl, "resoudre", _resolutions({}))

    rapport = bl.run(root=racine, session=None, sleep=0)

    # a-3 est un album (hors périmètre), a-4 un brouillon (vu mais non résolu).
    vus = {cas.reco_id for cas in rapport.cas}
    assert vus == {"a-1", "a-2", "a-4", "b-1"}
    assert [c.raison for c in rapport.cas if c.reco_id == "a-4"] == [
        bm.RAISON_NOT_VALIDATED]


def test_les_ids_restreignent_la_passe(racine, monkeypatch):
    """Ce dont la chaîne a besoin : un épisode, pas les 3 000 autres recos."""
    monkeypatch.setattr(bl, "resoudre", _resolutions({}))

    rapport = bl.run(root=racine, session=None, ids=["b-1"], sleep=0)

    assert [cas.reco_id for cas in rapport.cas] == ["b-1"]
    assert rapport.vues == 1


def test_le_filtre_de_types_limite_la_passe(racine, monkeypatch):
    monkeypatch.setattr(bl, "resoudre", _resolutions({}))

    rapport = bl.run(root=racine, session=None, types=("livre",), sleep=0)

    assert [cas.reco_id for cas in rapport.cas] == ["a-2"]


def test_la_limite_borne_les_resolutions(racine, monkeypatch):
    appels = []

    def resoudre(reco, *, session, permettre_sans_studio=False):
        appels.append(reco["id"])
        return bm.Resolution(raison=bm.RAISON_NO_MATCH)

    monkeypatch.setattr(bl, "resoudre", resoudre)
    bl.run(root=racine, session=None, limit=1, sleep=0)

    assert len(appels) == 1


def test_une_source_restreint_le_dossier_parcouru(racine, monkeypatch):
    monkeypatch.setattr(bl, "resoudre", _resolutions({}))

    rapport = bl.run(root=racine, session=None, source="src-b", sleep=0)

    assert [cas.reco_id for cas in rapport.cas] == ["b-1"]


def test_un_fichier_illisible_est_signale_sans_arreter_la_passe(racine, monkeypatch):
    (racine / "src-a" / "casse.json").write_text("{pas du json", encoding="utf-8")
    monkeypatch.setattr(bl, "resoudre", _resolutions({}))

    rapport = bl.run(root=racine, session=None, sleep=0)

    assert any(cas.raison == bm.RAISON_UNREADABLE for cas in rapport.cas)


# ===== écriture =============================================================
def test_la_simulation_n_ecrit_rien(racine, monkeypatch):
    chemin = racine / "src-a" / "a-1.json"
    avant = chemin.read_text(encoding="utf-8")
    monkeypatch.setattr(bl, "resoudre", _resolutions(
        {"a-1": bm.Resolution(liens=(STEAM,), raison=bm.RAISON_OK)}))

    rapport = bl.run(root=racine, session=None, sleep=0)

    assert rapport.ecrites == 0
    assert chemin.read_text(encoding="utf-8") == avant
    assert rapport.servies == {"a-1"}


def test_apply_ecrit_le_lien_et_l_audit(racine, monkeypatch):
    chemin = racine / "src-a" / "a-1.json"
    monkeypatch.setattr(bl, "resoudre", _resolutions(
        {"a-1": bm.Resolution(liens=(STEAM,), raison=bm.RAISON_OK)}))

    rapport = bl.run(root=racine, session=None, apply=True, sleep=0)

    reco = _lire(chemin)
    assert reco["links"] == [{"kind": "buy", "ethics": "neutral", "label": "Steam",
                              "url": "https://store.steampowered.com/app/210970/"}]
    assert "links" in reco["enrichedAt"]
    assert rapport.ecrites == 1


def test_l_isbn_d_un_livre_va_dans_les_identifiants(racine, monkeypatch):
    """Un fait corroboré par la fiche, utile même si le libraire change d'URL."""
    chemin = racine / "src-a" / "a-2.json"
    monkeypatch.setattr(bl, "resoudre", _resolutions(
        {"a-2": bm.Resolution(liens=(LIBRAIRE,), raison=bm.RAISON_OK,
                              isbn="9782709677424")}))

    bl.run(root=racine, session=None, apply=True, sleep=0)

    reco = _lire(chemin)
    assert reco["externalIds"]["isbn"] == "9782709677424"
    assert "externalIds.isbn" in reco["enrichedAt"]


def test_un_isbn_deja_present_n_est_pas_ecrase(racine, monkeypatch):
    chemin = racine / "src-a" / "a-2.json"
    reco = _lire(chemin)
    reco["externalIds"] = {"isbn": "9780000000001"}
    chemin.write_text(json.dumps(reco, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(bl, "resoudre", _resolutions(
        {"a-2": bm.Resolution(liens=(LIBRAIRE,), raison=bm.RAISON_OK,
                              isbn="9782709677424")}))

    bl.run(root=racine, session=None, apply=True, sleep=0)

    assert _lire(chemin)["externalIds"]["isbn"] == "9780000000001"


def test_un_lien_du_meme_hote_n_est_jamais_duplique(racine, monkeypatch):
    """Garde-fou de dernier recours : la sélection l'a déjà écarté."""
    chemin = racine / "src-a" / "a-1.json"
    reco = _lire(chemin)
    reco["links"] = [{"kind": "buy", "ethics": "neutral", "label": "Steam",
                      "url": "https://store.steampowered.com/app/999/"}]
    chemin.write_text(json.dumps(reco, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(bl, "resoudre", _resolutions(
        {"a-1": bm.Resolution(liens=(STEAM,), raison=bm.RAISON_OK)}))

    bl.run(root=racine, session=None, apply=True, sleep=0)

    assert len(_lire(chemin)["links"]) == 1


def test_les_liens_existants_sont_conserves_dans_leur_ordre(racine, monkeypatch):
    chemin = racine / "src-a" / "a-1.json"
    reco = _lire(chemin)
    reco["links"] = [{"kind": "info", "ethics": "indie", "label": "Wikipédia",
                      "url": "https://fr.wikipedia.org/wiki/The_Witness"}]
    chemin.write_text(json.dumps(reco, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(bl, "resoudre", _resolutions(
        {"a-1": bm.Resolution(liens=(STEAM,), raison=bm.RAISON_OK)}))

    bl.run(root=racine, session=None, apply=True, sleep=0)

    labels = [lien["label"] for lien in _lire(chemin)["links"]]
    assert labels == ["Wikipédia", "Steam"]


def test_un_audit_corrompu_empeche_l_ecriture_sans_arreter_la_passe(racine,
                                                                   monkeypatch):
    chemin = racine / "src-a" / "a-1.json"
    reco = _lire(chemin)
    reco["enrichedAt"] = "pas un dict"
    chemin.write_text(json.dumps(reco, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(bl, "resoudre", _resolutions(
        {"a-1": bm.Resolution(liens=(STEAM,), raison=bm.RAISON_OK),
         "b-1": bm.Resolution(liens=(STEAM,), raison=bm.RAISON_OK)}))

    rapport = bl.run(root=racine, session=None, apply=True, sleep=0)

    assert _lire(chemin)["links"] == []
    assert rapport.ecrites == 1  # b-1 est passée


def test_appliquer_leve_sur_un_audit_corrompu():
    reco = {"links": [], "enrichedAt": "pas un dict"}

    with pytest.raises(EnrichedAtCorruptedError):
        bl.appliquer(reco, bm.Resolution(liens=(STEAM,), raison=bm.RAISON_OK))


# ===== pannes ===============================================================
def test_une_source_injoignable_est_tracee_et_la_passe_continue(racine,
                                                               monkeypatch):
    def resoudre(reco, *, session, permettre_sans_studio=False):
        if reco["id"] == "a-1":
            raise bl.BoutiqueInjoignable("limite d'appels atteinte (429)")
        return bm.Resolution(liens=(STEAM,), raison=bm.RAISON_OK)

    monkeypatch.setattr(bl, "resoudre", resoudre)
    rapport = bl.run(root=racine, session=None, apply=True, sleep=0)

    panne = next(c for c in rapport.cas if c.reco_id == "a-1")
    assert panne.raison == bm.RAISON_HTTP_ERROR
    assert "429" in panne.detail
    assert "b-1" in rapport.servies


# ===== rapport ==============================================================
def test_le_rapport_distingue_ce_qui_demande_un_arbitrage(racine, monkeypatch):
    monkeypatch.setattr(bl, "resoudre", _resolutions(
        {"a-1": bm.Resolution(raison=bm.RAISON_AMBIGUOUS, detail="1 / 2"),
         "a-2": bm.Resolution(raison=bm.RAISON_NO_ISBN),
         "b-1": bm.Resolution(liens=(STEAM,), raison=bm.RAISON_OK)}))

    rapport = bl.run(root=racine, session=None, sleep=0)

    assert [c.reco_id for c in rapport.a_arbitrer] == ["a-1"]
    assert rapport.servies == {"b-1"}


def test_le_rapport_se_met_en_forme_et_se_serialise(racine, monkeypatch):
    monkeypatch.setattr(bl, "resoudre", _resolutions(
        {"a-1": bm.Resolution(liens=(STEAM,), raison=bm.RAISON_OK,
                              preuve="Thekla, Inc.")}))

    rapport = bl.run(root=racine, session=None, sleep=0)
    texte = e.format_rapport(rapport)
    charge = e.rapport_payload(rapport)

    assert "liens posés" in texte
    assert "jeu" in texte
    assert charge["servies"] == ["a-1"]
    assert any(cas["preuve"] == "Thekla, Inc." for cas in charge["cas"])


# ===== ligne de commande ====================================================
def test_la_simulation_est_le_defaut_de_la_ligne_de_commande(racine, monkeypatch,
                                                            capsys):
    recu = {}

    def run(**kwargs):
        recu.update(kwargs)
        return bl.RapportBoutique()

    monkeypatch.setattr(e, "run", run)
    monkeypatch.setattr(e, "RECOS_DIR", racine)

    assert e.main([]) == 0
    assert recu["apply"] is False
    assert recu["permettre_sans_studio"] is False


def test_les_options_arrivent_jusqu_a_la_passe(racine, monkeypatch, tmp_path):
    recu = {}

    def run(**kwargs):
        recu.update(kwargs)
        return bl.RapportBoutique(vues=1)

    monkeypatch.setattr(e, "run", run)
    monkeypatch.setattr(e, "RECOS_DIR", racine)
    fichier = tmp_path / "ids.txt"
    fichier.write_text("a-1\n# commentaire\nb-1\n", encoding="utf-8")
    rapport_json = tmp_path / "rapport.json"

    assert e.main(["--types", "jeu,livre", "--ids", f"@{fichier}",
                   "--jeux-sans-studio", "--limit", "3",
                   "--json", str(rapport_json)]) == 0

    assert recu["types"] == ("jeu", "livre")
    assert recu["ids"] == {"a-1", "b-1"}
    assert recu["permettre_sans_studio"] is True
    assert recu["limit"] == 3
    assert json.loads(rapport_json.read_text(encoding="utf-8"))["vues"] == 1


def test_apply_prend_le_verrou_du_serveur_de_relecture(racine, monkeypatch):
    pris = []

    class Verrou:
        def __enter__(self):
            pris.append(True)

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(e, "acquire_pipeline_lock", lambda force=False: Verrou())
    monkeypatch.setattr(e, "run", lambda **_k: bl.RapportBoutique())
    monkeypatch.setattr(e, "RECOS_DIR", racine)

    assert e.main(["--apply"]) == 0
    assert pris == [True]


def test_un_verrou_occupe_arrete_la_commande(racine, monkeypatch):
    def occupe(force=False):
        raise e.ServerLockBusy("le serveur de relecture tourne")

    monkeypatch.setattr(e, "acquire_pipeline_lock", occupe)
    monkeypatch.setattr(e, "run", lambda **_k: pytest.fail("ne doit pas écrire"))
    monkeypatch.setattr(e, "RECOS_DIR", racine)

    assert e.main(["--apply"]) == 1


def test_une_pause_separe_deux_recos(racine, monkeypatch):
    """Politesse envers les sources, et seule protection contre leurs limites."""
    pauses = []
    monkeypatch.setattr(bl.time, "sleep", pauses.append)
    monkeypatch.setattr(bl, "resoudre", _resolutions({}))

    bl.run(root=racine, session=None, types=("jeu",), sleep=0.5)

    # a-1 et b-1 sont résolues (a-4 est un brouillon, écarté avant la pause).
    assert pauses == [0.5, 0.5]
