"""Tests de `tools/bord_github.py` — les données GitHub du tableau de bord (tranche 3a).

Aucun appel réseau : l'ouvreur de `bord_distant` est remplacé par un ouvreur construit
avec le faux gestionnaire HTTPS de `test_bord_distant` (il garde chaque requête reçue).
Le cache vit sous `RECO_BORD_DIR` (un dossier temporaire), à côté de celui de l'audience.
Le jeton d'essai est visiblement faux, et chaque test de panne vérifie qu'il ne sort nulle part.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime, timedelta

import filelock
import pytest

import bord_distant as bd
import bord_github as bg
import publication
from test_bord_distant import FauxHttps

JETON = "FAUX-JETON-DESSAI-0000"
MAINTENANT = datetime(2026, 11, 28, 9, 30, tzinfo=UTC)
DEPOT = "Etienne-Boursault/Reco"


@pytest.fixture(autouse=True)
def bord(tmp_path, monkeypatch):
    d = tmp_path / "bord"
    monkeypatch.setenv("RECO_BORD_DIR", str(d))
    monkeypatch.setenv("RECO_GITHUB_TOKEN", JETON)
    monkeypatch.setattr(bg, "_depot", lambda: DEPOT)
    monkeypatch.setattr(bd, "_ATTENTE_VERROU", 0)       # les tests n'attendent pas 60 s
    return d


def _serveur(monkeypatch, *reponses) -> FauxHttps:
    faux = FauxHttps(*reponses)
    ouvreur = urllib.request.build_opener(bd._SansRedirection, faux)
    monkeypatch.setattr(bd, "_ouvreur", lambda: ouvreur)
    return faux


def _json(corps, code=200, entetes=None):
    return (code, {"Content-Type": "application/json", **(entetes or {})},
            json.dumps(corps).encode())


def _pr(numero, branche, *, repo=DEPOT, cree="2026-11-28T08:00:00Z", fusion=None, titre=None):
    return {"number": numero, "title": titre or f"PR {numero}", "created_at": cree,
            "merged_at": fusion,
            "head": {"ref": branche, "repo": {"full_name": repo} if repo else None}}


def _course(conclusion="success", ident=7, date="2026-11-28T09:00:00Z"):
    return {"workflow_runs": [{"id": ident, "conclusion": conclusion, "updated_at": date}]}


def _tout(ouvertes=(), fermees=(), ci=None, deploiement=None):
    return [_json(list(ouvertes)), _json(list(fermees)), _json(_course() if ci is None else ci),
            _json(_course(ident=8) if deploiement is None else deploiement)]


def _cache(bord) -> dict:
    return json.loads((bord / "distant.json").read_text(encoding="utf-8"))


def _ecrire_cache(bord, entree, **autres) -> None:
    bord.mkdir(parents=True, exist_ok=True)
    (bord / "distant.json").write_text(json.dumps({**autres, "github": entree}), encoding="utf-8")


def _donnees():
    return {"depot": DEPOT, "ouvertes": {"episodes": [], "sorties": [], "coupee": False},
            "fusionnees": [], "ci": None, "deploiement": None}


# ---- Les PR ouvertes ----------------------------------------------------------
def test_les_pr_ouvertes_du_depot_seules_sont_gardees_et_separees(monkeypatch, bord):
    _serveur(monkeypatch, *_tout(ouvertes=[
        _pr(1, "contenu/guid-1", cree="2026-11-27T08:00:00Z", titre="Épisode un"),
        _pr(2, "contenu/sorties-2026-12", cree="2026-11-28T08:00:00Z"),
        _pr(3, "contenu/guid-3", cree="2026-11-28T07:00:00Z"),
        _pr(4, "contenu/x", repo="inconnu/Reco"),          # PR d'un fork nommée comme un épisode
        _pr(5, "contenu/y", repo=None),                    # fork supprimé
        _pr(6, "feat/autre"),                              # PR de développement
        _pr(7, "contenu/guid-7", repo="etienne-boursault/reco", cree="2026-11-26T08:00:00Z"),
    ]))
    assert bg.rafraichir(maintenant=MAINTENANT) == "ok"
    ouvertes = _cache(bord)["github"]["donnees"]["ouvertes"]
    assert [p["numero"] for p in ouvertes["episodes"]] == [3, 1, 7]     # les plus récentes d'abord
    assert [p["numero"] for p in ouvertes["sorties"]] == [2]            # jamais prise pour un épisode
    assert ouvertes["coupee"] is False
    assert ouvertes["episodes"][1] == {
        "numero": 1, "titre": "Épisode un", "branche": "contenu/guid-1", "groupe": "episodes",
        "date": "2026-11-27T08:00:00Z", "adresse": f"https://github.com/{DEPOT}/pull/1"}


def test_une_page_pleine_de_pr_ouvertes_dit_qu_elle_est_coupee(monkeypatch, bord):
    _serveur(monkeypatch, *_tout(ouvertes=[_pr(n, f"contenu/g{n}") for n in range(100)]))
    bg.rafraichir(maintenant=MAINTENANT)
    ouvertes = _cache(bord)["github"]["donnees"]["ouvertes"]
    assert ouvertes["coupee"] is True and len(ouvertes["episodes"]) == 100


def test_un_titre_trop_long_est_coupe(monkeypatch, bord):
    _serveur(monkeypatch, *_tout(ouvertes=[_pr(1, "contenu/g", titre="é" * 500)]))
    bg.rafraichir(maintenant=MAINTENANT)
    assert len(_cache(bord)["github"]["donnees"]["ouvertes"]["episodes"][0]["titre"]) == 200


# ---- Les PR fusionnées ---------------------------------------------------------
def test_les_pr_fusionnees_viennent_de_merged_at(monkeypatch, bord):
    _serveur(monkeypatch, *_tout(fermees=[
        _pr(1, "contenu/g1", fusion="2026-11-26T10:00:00Z"),
        _pr(2, "contenu/g2", fusion=None),                        # fermée sans fusion
        _pr(3, "contenu/sorties-a", fusion="2026-11-28T10:00:00Z"),
        _pr(4, "contenu/g4", fusion="2026-11-27T10:00:00Z", repo="fork/Reco"),
        _pr(5, "feat/x", fusion="2026-11-28T11:00:00Z"),
        _pr(6, "contenu/g6", fusion="2026-11-27T12:00:00Z"),
    ]))
    bg.rafraichir(maintenant=MAINTENANT)
    fusionnees = _cache(bord)["github"]["donnees"]["fusionnees"]
    assert [(p["numero"], p["groupe"], p["date"]) for p in fusionnees] == [
        (3, "sorties", "2026-11-28T10:00:00Z"), (6, "episodes", "2026-11-27T12:00:00Z"),
        (1, "episodes", "2026-11-26T10:00:00Z")]


@pytest.mark.parametrize("pr", [
    "pas un objet",
    {"number": 1, "title": "t", "created_at": "2026-11-28T08:00:00Z"},                # pas de head
    {"number": 1, "title": "t", "created_at": "2026-11-28T08:00:00Z", "head": {"repo": 3}},
    {"number": True, "title": "t", "created_at": "2026-11-28T08:00:00Z",
     "head": {"ref": "contenu/a", "repo": {"full_name": DEPOT}}},
    {"number": 1, "title": 5, "created_at": "2026-11-28T08:00:00Z",
     "head": {"ref": "contenu/a", "repo": {"full_name": DEPOT}}},
    {"number": 1, "title": "t", "created_at": "2026-11-28T08:00:00Z",
     "head": {"ref": 4, "repo": {"full_name": DEPOT}}},
    {"number": 1, "title": "t", "created_at": "hier",
     "head": {"ref": "contenu/a", "repo": {"full_name": DEPOT}}},
    {"number": 1, "title": "t", "created_at": "2026-11-28T08:00:00",
     "head": {"ref": "contenu/a", "repo": {"full_name": DEPOT}}},
    {"number": 1, "title": "t", "created_at": None,
     "head": {"ref": "contenu/a", "repo": {"full_name": DEPOT}}},
])
def test_une_forme_inattendue_donne_inconnu_sans_faire_tomber_le_reste(monkeypatch, bord, pr):
    _serveur(monkeypatch, *_tout(ouvertes=[_pr(2, "contenu/bon"), pr]))
    assert bg.rafraichir(maintenant=MAINTENANT) == "ok"
    donnees = _cache(bord)["github"]["donnees"]
    assert donnees["ouvertes"] is None                    # inconnu, jamais « aucune »
    assert donnees["ci"]["conclusion"] == "success"       # les autres blocs restent


def test_une_reponse_qui_n_est_pas_une_liste_donne_inconnu(monkeypatch, bord):
    _serveur(monkeypatch, _json({"message": "x"}), _json({"a": 1}), _json(_course()),
             _json(_course()))
    assert bg.rafraichir(maintenant=MAINTENANT) == "ok"
    donnees = _cache(bord)["github"]["donnees"]
    assert donnees["ouvertes"] is None and donnees["fusionnees"] is None


# ---- La CI et le déploiement ---------------------------------------------------
def test_ci_et_deploiement_rendent_conclusion_date_et_adresse(monkeypatch, bord):
    faux = _serveur(monkeypatch, *_tout(ci=_course("failure", 11, "2026-11-28T07:00:00Z"),
                                        deploiement=_course("success", 12, "2026-11-28T07:05:00Z")))
    bg.rafraichir(maintenant=MAINTENANT)
    donnees = _cache(bord)["github"]["donnees"]
    assert donnees["ci"] == {"conclusion": "failure", "date": "2026-11-28T07:00:00Z",
                             "adresse": f"https://github.com/{DEPOT}/actions/runs/11"}
    assert donnees["deploiement"]["adresse"].endswith("/actions/runs/12")
    adresses = [url for url, _ in faux.requetes]
    base = f"https://api.github.com/repos/{DEPOT}"
    assert adresses == [
        f"{base}/pulls?state=open&per_page=100",
        f"{base}/pulls?state=closed&sort=updated&direction=desc&per_page=30",
        f"{base}/actions/workflows/ci.yml/runs?branch=main&event=push&status=completed&per_page=10",
        f"{base}/actions/workflows/deploy.yml/runs?branch=main&status=completed&per_page=10"]


def test_aucune_execution_donne_inconnu(monkeypatch, bord):
    _serveur(monkeypatch, *_tout(ci={"workflow_runs": []}))
    bg.rafraichir(maintenant=MAINTENANT)
    donnees = _cache(bord)["github"]["donnees"]
    assert donnees["ci"] is None and donnees["deploiement"]["conclusion"] == "success"


@pytest.mark.parametrize("corps", [
    [], {"workflow_runs": "x"}, {"workflow_runs": ["x"]},
    {"workflow_runs": [{"id": "7", "conclusion": "success", "updated_at": "2026-11-28T09:00:00Z"}]},
    {"workflow_runs": [{"id": 7, "conclusion": None, "updated_at": "2026-11-28T09:00:00Z"}]},
    {"workflow_runs": [{"id": 7, "conclusion": "success", "updated_at": "hier"}]},
])
def test_une_execution_de_forme_inattendue_donne_inconnu(monkeypatch, bord, corps):
    _serveur(monkeypatch, *_tout(deploiement=corps))
    assert bg.rafraichir(maintenant=MAINTENANT) == "ok"
    donnees = _cache(bord)["github"]["donnees"]
    assert donnees["deploiement"] is None and donnees["ci"]["conclusion"] == "success"


# ---- Les pannes et la limite de débit --------------------------------------------
@pytest.mark.parametrize("code, entetes, etat, detail", [
    (403, {"X-RateLimit-Remaining": "0"}, "limite", "HTTP 403"),
    (429, {}, "limite", "HTTP 429"),
    (403, {"Retry-After": "60"}, "limite", "HTTP 403"),
    (403, {"X-RateLimit-Remaining": "12"}, "panne", "HTTP 403"),
    (404, {}, "panne", "HTTP 404"),
    (500, {}, "panne", "HTTP 500"),
    (302, {"Location": "https://autre.test/"}, "panne", "HTTP 302"),
])
def test_un_refus_de_l_api_est_une_panne_ou_la_limite(monkeypatch, bord, code, entetes, etat,
                                                       detail):
    faux = _serveur(monkeypatch, *[(code, entetes, b"{}")] * 4)
    assert bg.rafraichir(maintenant=MAINTENANT) == etat
    entree = _cache(bord)["github"]
    assert (entree["etat"], entree["detail"], entree["donnees"]) == (etat, detail, None)
    assert len(faux.requetes) == 4                    # un appel par bloc ; aucune redirection suivie


def test_une_reponse_d_un_autre_hote_est_une_panne(monkeypatch, bord):
    _serveur(monkeypatch, *[(200, {}, b"[]", "https://autre.test/x")] * 4)
    assert bg.rafraichir(maintenant=MAINTENANT) == "panne"
    assert _cache(bord)["github"]["detail"] == "autre hôte"


def test_une_erreur_reseau_est_une_panne_sans_message(monkeypatch, bord):
    _serveur(monkeypatch, *[OSError(f"échec avec {JETON}")] * 4)
    assert bg.rafraichir(maintenant=MAINTENANT) == "panne"
    assert _cache(bord)["github"]["detail"] == "OSError"


def test_json_invalide_et_reponse_trop_longue(monkeypatch, bord):
    _serveur(monkeypatch, *[(200, {}, b"<html>")] * 4)
    assert bg.rafraichir(maintenant=MAINTENANT) == "reponse-illisible"
    assert _cache(bord)["github"]["detail"] == "JSON invalide"
    monkeypatch.setattr(bd, "_TAILLE_MAX", 10)
    _serveur(monkeypatch, *[(200, {}, b"[" + b" " * 50 + b"]")] * 4)
    assert bg.rafraichir(maintenant=MAINTENANT + timedelta(hours=1)) == "reponse-illisible"
    assert _cache(bord)["github"]["detail"] == "trop longue"


def test_un_depot_inconnu_est_une_panne_sans_appel(monkeypatch, bord):
    monkeypatch.setattr(bg, "_depot", lambda: "")
    faux = _serveur(monkeypatch)
    assert bg.rafraichir(maintenant=MAINTENANT) == "panne"
    assert faux.requetes == []
    assert _cache(bord)["github"]["detail"] == "dépôt inconnu"


def test_depot_vient_de_l_adresse_d_origine(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(bg, "Git", lambda racine: type(
        "G", (), {"url_distante": lambda self: "git@github.com:Etienne-Boursault/Reco.git"})())
    assert bg._depot() == "Etienne-Boursault/Reco"
    monkeypatch.setattr(bg, "Git", lambda racine: type(
        "G", (), {"url_distante": lambda self: "https://exemple.test/x/y"})())
    assert bg._depot() == ""


def test_un_git_qui_echoue_est_une_panne_sans_message(monkeypatch, bord):
    def echoue():
        raise publication.ErreurGit(f"git remote → 1 : https://{JETON}@github.com/x/y")
    monkeypatch.setattr(bg, "_depot", echoue)
    assert bg.rafraichir(maintenant=MAINTENANT) == "panne"
    entree = _cache(bord)["github"]
    assert entree["detail"] == "ErreurGit" and JETON not in json.dumps(entree)


def test_une_panne_garde_les_dernieres_donnees_et_leur_heure(monkeypatch, bord):
    _serveur(monkeypatch, *_tout(ouvertes=[_pr(1, "contenu/g")]))
    bg.rafraichir(maintenant=MAINTENANT)
    _serveur(monkeypatch, *[(500, {}, b"{}")] * 4)
    assert bg.rafraichir(maintenant=MAINTENANT + timedelta(minutes=11)) == "panne"
    entree = _cache(bord)["github"]
    assert entree["etat"] == "panne" and entree["lu"] == "2026-11-28T09:30:00+00:00"
    assert entree["essai"] == "2026-11-28T09:41:00+00:00"
    assert entree["donnees"]["ouvertes"]["episodes"][0]["numero"] == 1


# ---- Le jeton ----------------------------------------------------------------
def test_le_jeton_sert_aux_pr_seulement_et_jamais_dans_l_url(monkeypatch, bord):
    faux = _serveur(monkeypatch, *_tout())
    bg.rafraichir(maintenant=MAINTENANT)
    autorisations = [en_tetes.get("Authorization") for _, en_tetes in faux.requetes]
    assert autorisations == [f"Bearer {JETON}", f"Bearer {JETON}", None, None]
    assert all(JETON not in url for url, _ in faux.requetes)
    assert JETON not in (bord / "distant.json").read_text(encoding="utf-8")


def test_sans_jeton_l_appel_est_anonyme(monkeypatch, bord):
    monkeypatch.delenv("RECO_GITHUB_TOKEN")
    faux = _serveur(monkeypatch, *_tout())
    assert bg.rafraichir(maintenant=MAINTENANT) == "ok"
    assert all("Authorization" not in en_tetes for _, en_tetes in faux.requetes)


def test_le_jeton_n_entre_dans_aucun_journal_meme_si_l_appel_leve(monkeypatch, bord, capsys,
                                                                  caplog):
    caplog.set_level(logging.DEBUG)
    _serveur(monkeypatch, ValueError(f"Invalid header value {JETON}"))
    assert bg.main(["rafraichir"]) == 0
    sorties = capsys.readouterr()
    assert JETON not in sorties.out + sorties.err + caplog.text
    entree = _cache(bord)["github"]
    assert (entree["etat"], entree["detail"]) == ("panne", "ValueError")
    assert JETON not in json.dumps(entree)


def test_le_jeton_n_est_pas_dans_l_etat_rendu(monkeypatch, bord):
    _serveur(monkeypatch, *_tout())
    bg.rafraichir(maintenant=MAINTENANT)
    assert JETON not in repr(bg.lire(maintenant=MAINTENANT, relancer=False))


# ---- Le cache partagé et le verrou ---------------------------------------------
def test_le_cache_garde_la_cle_de_l_audience(monkeypatch, bord):
    audience = {"etat": "ok", "detail": None, "essai": "2026-11-28T09:00:00+00:00",
                "lu": "2026-11-28T09:00:00+00:00", "donnees": {"genere": "x"}}
    bord.mkdir(parents=True)
    (bord / "distant.json").write_text(json.dumps({"audience": audience}), encoding="utf-8")
    _serveur(monkeypatch, *_tout())
    assert bg.rafraichir(maintenant=MAINTENANT) == "ok"
    cache = _cache(bord)
    assert cache["audience"] == audience and cache["github"]["etat"] == "ok"


def test_un_cache_frais_n_appelle_rien(monkeypatch, bord):
    _ecrire_cache(bord, {"etat": "ok", "detail": None, "essai": "2026-11-28T09:25:00+00:00",
                         "lu": "2026-11-28T09:25:00+00:00", "donnees": _donnees()})
    faux = _serveur(monkeypatch)
    assert bg.rafraichir(maintenant=MAINTENANT) == "frais"
    assert faux.requetes == []


def test_un_verrou_tenu_rend_occupe(monkeypatch, bord):
    bord.mkdir(parents=True)
    faux = _serveur(monkeypatch)
    with filelock.FileLock(str(bord / "distant.lock")):
        assert bg.rafraichir(maintenant=MAINTENANT) == "occupe"
    assert faux.requetes == []


@pytest.mark.parametrize("contenu", ["pas du json", "[]", '{"github": 3}',
                                     '{"github": {"etat": "ok", "essai": "hier"}}'])
def test_cache_illisible_jamais_reecrit(monkeypatch, bord, contenu):
    bord.mkdir(parents=True)
    (bord / "distant.json").write_text(contenu, encoding="utf-8")
    faux = _serveur(monkeypatch)
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: lances.append(a))
    assert bg.rafraichir(maintenant=MAINTENANT) == "cache-illisible"
    etat = bg.lire(maintenant=MAINTENANT)
    assert (etat["etat"], etat["libelle"], etat["donnees"]) == (
        "cache-illisible", "cache illisible", None)
    assert faux.requetes == [] and lances == []
    assert (bord / "distant.json").read_text(encoding="utf-8") == contenu


# ---- La lecture pour la page -----------------------------------------------------
def _sans_reseau(monkeypatch):
    def interdit():
        raise AssertionError("lire() ne doit jamais ouvrir le réseau")
    monkeypatch.setattr(bd, "_ouvreur", interdit)
    monkeypatch.setattr(bg, "_depot", interdit)


def test_lire_un_cache_frais_rend_l_etat_sans_relancer(monkeypatch, bord):
    lu = (MAINTENANT - timedelta(minutes=3)).isoformat(timespec="seconds")
    _ecrire_cache(bord, {"etat": "ok", "detail": None, "essai": lu, "lu": lu,
                         "donnees": _donnees()})
    _sans_reseau(monkeypatch)
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: lances.append(a))
    assert bg.lire(maintenant=MAINTENANT) == {
        "source": "github", "etat": "ok", "libelle": "à jour", "detail": None,
        "donnees": _donnees(), "lu": lu, "essai": lu, "age": 180, "relance": False}
    assert lances == []


def test_lire_sans_cache_lance_le_rafraichissement_de_github(monkeypatch, bord):
    _sans_reseau(monkeypatch)
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda args, **k: lances.append((args, k)))
    etat = bg.lire(maintenant=MAINTENANT)
    assert (etat["etat"], etat["libelle"], etat["donnees"], etat["age"]) == (
        "inconnu", "inconnu", None, None)
    assert etat["relance"] is True
    ((args, options),) = lances
    assert args[1].endswith("bord_github.py") and args[-1] == "rafraichir"
    assert options["start_new_session"] is True
    assert JETON not in repr(args)


def test_lire_apres_une_panne_garde_les_donnees_et_relance_si_perime(monkeypatch, bord):
    lu = (MAINTENANT - timedelta(minutes=30)).isoformat(timespec="seconds")
    essai = (MAINTENANT - timedelta(minutes=11)).isoformat(timespec="seconds")
    _ecrire_cache(bord, {"etat": "limite", "detail": "HTTP 403", "essai": essai, "lu": lu,
                         "donnees": _donnees()})
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: None)
    etat = bg.lire(maintenant=MAINTENANT)
    assert (etat["etat"], etat["libelle"], etat["age"], etat["relance"]) == (
        "limite", "limite de débit atteinte", 1800, True)
    assert etat["donnees"] == _donnees()


def test_lire_ne_relance_pas_quand_on_ne_le_demande_pas(monkeypatch, bord):
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: lances.append(a))
    assert bg.lire(maintenant=MAINTENANT, relancer=False)["relance"] is False
    assert lances == []


def test_un_etat_inconnu_du_cache_se_lit_inconnu(monkeypatch, bord):
    essai = (MAINTENANT - timedelta(minutes=1)).isoformat(timespec="seconds")
    _ecrire_cache(bord, {"etat": "<script>", "detail": None, "essai": essai, "lu": None,
                         "donnees": None})
    etat = bg.lire(maintenant=MAINTENANT)
    assert (etat["etat"], etat["libelle"], etat["age"]) == ("inconnu", "inconnu", None)


def test_un_lancement_rate_ne_remonte_pas_a_la_page(monkeypatch, bord, caplog):
    def echoue(*_a, **_k):
        raise OSError("pas de python")
    monkeypatch.setattr(bd.subprocess, "Popen", echoue)
    assert bg.lire(maintenant=MAINTENANT)["relance"] is False
    assert "rafraîchissement non lancé pour github" in caplog.text


def test_main_rafraichir(monkeypatch, bord, capsys):
    _serveur(monkeypatch, *_tout())
    assert bg.main(["rafraichir"]) == 0
    assert capsys.readouterr().out.strip() == "github : ok"


def test_le_module_se_lance_comme_script(bord):
    sortie = subprocess.run([sys.executable, bg.__file__, "--help"], capture_output=True,
                            text=True, check=False)
    assert sortie.returncode == 0 and "rafraichir" in sortie.stdout


def test_deux_lectures_de_suite_ne_lancent_qu_un_processus_de_github(monkeypatch, bord):
    # Revue globale, M1 : le marqueur `lance-github` plafonne les lancements, comme celui de l'audience.
    _sans_reseau(monkeypatch)
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: lances.append(a))
    assert bg.lire(maintenant=MAINTENANT)["relance"] is True
    assert bg.lire(maintenant=MAINTENANT + timedelta(seconds=30))["relance"] is False
    assert bg.lire(maintenant=MAINTENANT + bd.LANCEMENT_MIN)["relance"] is True
    assert len(lances) == 2 and (bord / "lance-github").exists()
