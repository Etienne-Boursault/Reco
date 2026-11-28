"""Tests de `tools/bord_distant.py` — la lecture distante de l'audience (tranche 2b).

Aucun appel réseau : l'ouvreur d'urllib est remplacé par un ouvreur construit
avec un faux gestionnaire HTTPS (`FauxHttps`), qui garde chaque requête reçue.
Le cache vit sous `RECO_BORD_DIR` (un dossier temporaire). La clé d'essai est
visiblement fausse, et chaque test de panne vérifie qu'elle ne sort nulle part.
"""
from __future__ import annotations

import email.message
import io
import json
import logging
import subprocess
import threading
import time
import types
import urllib.error
import urllib.request
import urllib.response
from datetime import UTC, datetime, timedelta

import filelock
import pytest

import bord_distant as bd

CLE = "FAUSSE-CLE-DESSAI-0000"
MAINTENANT = datetime(2026, 11, 28, 9, 30, tzinfo=UTC)
RESUME = {"genere": "2026-11-28T09:30:00.000Z", "perimetre": "tout le site",
          "sept": None, "trente": None, "jours": [], "erreur": "x",
          "signalements": {"etat": "lu", "enAttente": []}}


class FauxHttps(urllib.request.HTTPSHandler):
    """Rend les réponses prévues, dans l'ordre, et garde (url, en-têtes) de chaque requête."""

    def __init__(self, *reponses):
        super().__init__()
        self.reponses = list(reponses)
        self.requetes: list[tuple[str, dict[str, str]]] = []

    def https_open(self, req):
        self.requetes.append((req.full_url, dict(req.header_items())))
        reponse = self.reponses.pop(0)
        if isinstance(reponse, BaseException):
            raise reponse
        code, entetes, corps, url = (*reponse, None)[:4]
        message = email.message.Message()
        for nom, valeur in entetes.items():
            message[nom] = valeur
        flux = io.BytesIO(corps) if isinstance(corps, bytes) else corps
        rendu = urllib.response.addinfourl(flux, message, url or req.full_url, code)
        rendu.msg = "faux"
        return rendu


@pytest.fixture(autouse=True)
def bord(tmp_path, monkeypatch):
    d = tmp_path / "bord"
    monkeypatch.setenv("RECO_BORD_DIR", str(d))
    monkeypatch.setenv("RECO_AUDIENCE_KEY", CLE)
    monkeypatch.delenv("SITE_URL", raising=False)
    monkeypatch.setattr(bd, "_ATTENTE_VERROU", 0)       # les tests n'attendent pas 60 s
    return d


def _serveur(monkeypatch, *reponses) -> FauxHttps:
    faux = FauxHttps(*reponses)
    ouvreur = urllib.request.build_opener(bd._SansRedirection, faux)
    monkeypatch.setattr(bd, "_ouvreur", lambda: ouvreur)
    return faux


def _ok(corps=None):
    return (200, {"Content-Type": "application/json"}, json.dumps(corps or RESUME).encode())


def _cache(bord) -> dict:
    return json.loads((bord / "distant.json").read_text(encoding="utf-8"))


def _ecrire_cache(bord, entree) -> None:
    bord.mkdir(parents=True, exist_ok=True)
    (bord / "distant.json").write_text(json.dumps({"audience": entree}), encoding="utf-8")


# ---- L'adresse ---------------------------------------------------------------
def test_adresse_par_defaut_vient_de_commentaire_youtube():
    import commentaire_youtube
    assert bd.adresse() == commentaire_youtube.SITE_PAR_DEFAUT + "/api/bord"


def test_adresse_suit_site_url_sans_son_chemin(monkeypatch):
    monkeypatch.setenv("SITE_URL", "https://exemple.test/un-bon-moment/")
    assert bd.adresse() == "https://exemple.test/api/bord"


@pytest.mark.parametrize("site", ["http://exemple.test", "ftp://exemple.test", "https://",
                                  "https://moi@exemple.test", "exemple.test"])
def test_adresse_refuse_ce_qui_n_est_pas_un_https_net(monkeypatch, site):
    monkeypatch.setenv("SITE_URL", site)
    with pytest.raises(ValueError):
        bd.adresse()


def test_http_refuse_sans_aucun_appel(monkeypatch, bord):
    monkeypatch.setenv("SITE_URL", "http://exemple.test")
    faux = _serveur(monkeypatch, _ok())
    assert bd.rafraichir(maintenant=MAINTENANT) == "panne"
    assert faux.requetes == []
    assert _cache(bord)["audience"]["detail"] == "adresse refusée"


def test_l_ouvreur_du_module_refuse_les_redirections():
    assert any(isinstance(h, bd._SansRedirection) for h in bd._ouvreur().handlers)


# ---- La clé ------------------------------------------------------------------
def test_cle_dans_l_en_tete_jamais_dans_l_url(monkeypatch, bord):
    faux = _serveur(monkeypatch, _ok())
    assert bd.rafraichir(maintenant=MAINTENANT) == "ok"
    ((url, entetes),) = faux.requetes
    assert url == "https://unebonnere.co/api/bord"
    assert CLE not in url
    assert entetes["X-reco-cle"] == CLE
    entree = _cache(bord)["audience"]
    assert entree["donnees"] == RESUME
    assert entree["lu"] == entree["essai"] == MAINTENANT.isoformat(timespec="seconds")
    assert CLE not in (bord / "distant.json").read_text(encoding="utf-8")


def test_sans_cle_aucun_appel_et_cle_absente(monkeypatch, bord):
    monkeypatch.delenv("RECO_AUDIENCE_KEY")
    faux = _serveur(monkeypatch, _ok())
    assert bd.rafraichir(maintenant=MAINTENANT) == "cle-absente"
    assert faux.requetes == []
    assert _cache(bord)["audience"]["etat"] == "cle-absente"


# ---- Les redirections --------------------------------------------------------
@pytest.mark.parametrize("code", [301, 302, 307])
def test_redirection_refusee_la_cle_ne_part_pas_vers_la_cible(monkeypatch, bord, code):
    faux = _serveur(monkeypatch, (code, {"Location": "https://ailleurs.test/vol"}, b""), _ok())
    assert bd.rafraichir(maintenant=MAINTENANT) == "panne"
    assert [url for url, _ in faux.requetes] == ["https://unebonnere.co/api/bord"]
    assert _cache(bord)["audience"]["detail"] == f"HTTP {code}"


def test_reponse_venue_d_un_autre_hote_comptee_en_panne(monkeypatch, bord):
    _serveur(monkeypatch, (*_ok(), "https://ailleurs.test/api/bord"))
    assert bd.rafraichir(maintenant=MAINTENANT) == "panne"
    entree = _cache(bord)["audience"]
    assert entree["detail"] == "autre hôte"
    assert entree["donnees"] is None


# ---- Les pannes : un état lisible, jamais une exception, jamais la clé -------
@pytest.mark.parametrize(("reponse", "etat", "detail"), [
    ((404, {}, b"Page introuvable"), "cle-refusee", "HTTP 404"),
    ((500, {}, b"erreur"), "panne", "HTTP 500"),
    (urllib.error.URLError(f"echec {CLE}"), "panne", "URLError"),
    (TimeoutError(), "panne", "TimeoutError"),
    (ConnectionResetError(), "panne", "ConnectionResetError"),
    ((200, {}, b"{pas du json"), "reponse-illisible", "JSON invalide"),
    ((200, {}, b"\xff\xfe"), "reponse-illisible", "JSON invalide"),
    ((200, {}, b"[1, 2]"), "reponse-illisible", "forme inattendue"),
    ((200, {}, json.dumps({**RESUME, "jours": {}}).encode()), "reponse-illisible",
     "forme inattendue"),
    ((200, {}, json.dumps({k: v for k, v in RESUME.items() if k != "sept"}).encode()),
     "reponse-illisible", "forme inattendue"),
    ((200, {}, b" " * (bd._TAILLE_MAX + 1)), "reponse-illisible", "trop longue"),
])
def test_chaque_panne_donne_un_etat_lisible_sans_la_cle(monkeypatch, bord, caplog, reponse,
                                                        etat, detail):
    caplog.set_level(logging.DEBUG)
    _serveur(monkeypatch, reponse)
    assert bd.rafraichir(maintenant=MAINTENANT) == etat
    entree = _cache(bord)["audience"]
    assert (entree["etat"], entree["detail"]) == (etat, detail)
    assert CLE not in caplog.text
    assert CLE not in (bord / "distant.json").read_text(encoding="utf-8")
    assert CLE not in repr(bd.lire(maintenant=MAINTENANT, relancer=False))


def test_une_panne_garde_la_derniere_valeur_et_son_heure(monkeypatch, bord):
    avant = (MAINTENANT - timedelta(hours=1)).isoformat(timespec="seconds")
    _ecrire_cache(bord, {"etat": "ok", "detail": None, "essai": avant, "lu": avant,
                         "donnees": RESUME})
    _serveur(monkeypatch, (500, {}, b""))
    assert bd.rafraichir(maintenant=MAINTENANT) == "panne"
    entree = _cache(bord)["audience"]
    assert entree["donnees"] == RESUME
    assert entree["lu"] == avant
    assert entree["essai"] == MAINTENANT.isoformat(timespec="seconds")


def test_les_autres_sources_du_cache_sont_gardees(monkeypatch, bord):
    bord.mkdir(parents=True)
    (bord / "distant.json").write_text(json.dumps({"github": {"x": 1}}), encoding="utf-8")
    _serveur(monkeypatch, _ok())
    bd.rafraichir(maintenant=MAINTENANT)
    assert _cache(bord)["github"] == {"x": 1}


# ---- Le cache, le verrou, le rafraîchissement --------------------------------
def test_rafraichir_ne_rappelle_pas_un_cache_frais(monkeypatch, bord):
    recent = (MAINTENANT - timedelta(minutes=9)).isoformat(timespec="seconds")
    _ecrire_cache(bord, {"etat": "panne", "detail": "HTTP 500", "essai": recent, "lu": None,
                         "donnees": None})
    faux = _serveur(monkeypatch, _ok())
    assert bd.rafraichir(maintenant=MAINTENANT) == "frais"
    assert faux.requetes == []


def test_verrou_deja_tenu_aucun_appel(monkeypatch, bord):
    faux = _serveur(monkeypatch, _ok())
    bord.mkdir(parents=True)
    with filelock.FileLock(str(bord / "distant.lock")):
        assert bd.rafraichir(maintenant=MAINTENANT) == "occupe"
    assert faux.requetes == []
    assert not (bord / "distant.json").exists()


def test_un_verrou_tenu_plus_longtemps_que_l_attente_rend_toujours_occupe(monkeypatch, bord):
    monkeypatch.setattr(bd, "_ATTENTE_VERROU", 0.2)
    faux = _serveur(monkeypatch, _ok())
    bord.mkdir(parents=True)
    debut = time.monotonic()
    with filelock.FileLock(str(bord / "distant.lock")):
        assert bd.rafraichir(maintenant=MAINTENANT) == "occupe"
    assert time.monotonic() - debut >= 0.2               # il a bien attendu avant d'abandonner
    assert faux.requetes == []


def test_un_verrou_relache_pendant_l_attente_est_obtenu_par_le_second(monkeypatch, bord):
    # M1 du tour 1 : l'audience et GitHub périmés ensemble lancent deux processus ; le second
    # attend le premier au lieu de rendre « occupé » sans noter son essai.
    monkeypatch.setattr(bd, "_ATTENTE_VERROU", 10)
    faux = _serveur(monkeypatch, _ok())
    bord.mkdir(parents=True)
    pris, relache = threading.Event(), threading.Event()

    def tenir():
        with filelock.FileLock(str(bord / "distant.lock")):
            pris.set()
            relache.wait(10)

    premier = threading.Thread(target=tenir)
    premier.start()
    assert pris.wait(10)
    threading.Timer(0.3, relache.set).start()
    try:
        assert bd.rafraichir(maintenant=MAINTENANT) == "ok"
    finally:
        relache.set()
        premier.join(10)
    assert len(faux.requetes) == 1 and _cache(bord)["audience"]["etat"] == "ok"


@pytest.mark.parametrize("contenu", ["{tronqué", "[]", '{"audience": []}',
                                     '{"audience": {"essai": 3}}',
                                     '{"audience": {"etat": "ok", "essai": 3}}',
                                     '{"audience": {"etat": "ok", "essai": "hier"}}',
                                     '{"audience": {"etat": "ok", "essai": "2026-11-28T09:00"}}',
                                     ('{"audience": {"etat": "ok", "essai": "2026-11-28T09:00Z",'
                                      ' "donnees": []}}')])
def test_cache_illisible_jamais_reecrit(monkeypatch, bord, contenu):
    bord.mkdir(parents=True)
    (bord / "distant.json").write_text(contenu, encoding="utf-8")
    faux = _serveur(monkeypatch, _ok())
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: lances.append(a))
    assert bd.rafraichir(maintenant=MAINTENANT) == "cache-illisible"
    etat = bd.lire(maintenant=MAINTENANT)
    assert etat["etat"] == "cache-illisible"
    assert etat["donnees"] is None
    assert faux.requetes == [] and lances == []
    assert (bord / "distant.json").read_text(encoding="utf-8") == contenu


def test_lire_un_cache_frais_sans_relancer(monkeypatch, bord):
    lu = (MAINTENANT - timedelta(minutes=3)).isoformat(timespec="seconds")
    _ecrire_cache(bord, {"etat": "ok", "detail": None, "essai": lu, "lu": lu, "donnees": RESUME})
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: lances.append(a))
    etat = bd.lire(maintenant=MAINTENANT)
    assert etat == {"source": "audience", "etat": "ok", "libelle": "à jour", "detail": None,
                    "donnees": RESUME, "lu": lu, "essai": lu, "age": 180, "relance": False}
    assert lances == []


def test_lire_un_cache_perime_lance_le_rafraichissement_detache(monkeypatch, bord):
    vieux = (MAINTENANT - timedelta(minutes=11)).isoformat(timespec="seconds")
    _ecrire_cache(bord, {"etat": "ok", "detail": None, "essai": vieux, "lu": vieux,
                         "donnees": RESUME})
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda args, **k: lances.append((args, k)))
    etat = bd.lire(maintenant=MAINTENANT)
    assert etat["donnees"] == RESUME and etat["age"] == 660 and etat["relance"] is True
    ((args, options),) = lances
    assert args[-1] == "rafraichir"
    assert options["start_new_session"] is True
    assert CLE not in repr(args)


def test_lire_sans_cache_lance_et_dit_inconnu(monkeypatch, bord):
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: lances.append(a))
    etat = bd.lire(maintenant=MAINTENANT)
    assert (etat["etat"], etat["libelle"], etat["donnees"], etat["age"]) == (
        "inconnu", "inconnu", None, None)
    assert etat["relance"] is True and len(lances) == 1


def test_lire_sans_cle_ne_lance_rien(monkeypatch, bord):
    monkeypatch.delenv("RECO_AUDIENCE_KEY")
    lances = []
    monkeypatch.setattr(bd.subprocess, "Popen", lambda *a, **k: lances.append(a))
    etat = bd.lire(maintenant=MAINTENANT)
    assert (etat["etat"], etat["libelle"], etat["relance"]) == (
        "cle-absente", "clé absente", False)
    assert lances == []


def test_un_lancement_rate_ne_remonte_pas_a_la_page(monkeypatch, bord, caplog):
    def echoue(*_a, **_k):
        raise OSError("pas de python")
    monkeypatch.setattr(bd.subprocess, "Popen", echoue)
    etat = bd.lire(maintenant=MAINTENANT)
    assert etat["relance"] is False
    assert "rafraîchissement non lancé" in caplog.text


def test_main_rafraichir(monkeypatch, bord, capsys):
    _serveur(monkeypatch, _ok())
    assert bd.main(["rafraichir"]) == 0
    assert _cache(bord)["audience"]["etat"] == "ok"
    assert capsys.readouterr().out.strip() == "audience : ok"


# ---- Tour 1, M1 : le processus détaché garde son journal ---------------------
def _popen_espion(monkeypatch) -> list[dict]:
    appels: list[dict] = []

    def faux(args, **options):
        appels.append({"args": args, **options, "nom": options["stdout"].name})
    monkeypatch.setattr(bd.subprocess, "Popen", faux)
    return appels


def test_le_processus_detache_ecrit_dans_distant_log_en_ajout(monkeypatch, bord):
    appels = _popen_espion(monkeypatch)
    bord.mkdir(parents=True)
    (bord / "distant.log").write_text("avant\n", encoding="utf-8")
    assert bd._lancer() is True
    (appel,) = appels
    assert appel["nom"] == str(bord / "distant.log")
    assert appel["stderr"] == subprocess.STDOUT
    assert appel["stdout"].closed
    assert (bord / "distant.log").read_text(encoding="utf-8") == "avant\n"


def test_un_journal_de_plus_de_200_ko_repart_de_zero(monkeypatch, bord):
    _popen_espion(monkeypatch)
    bord.mkdir(parents=True)
    (bord / "distant.log").write_bytes(b"x" * (bd._JOURNAL_MAX + 1))
    assert bd._lancer() is True
    assert (bord / "distant.log").read_bytes() == b""


def test_un_journal_de_taille_normale_est_gardé(monkeypatch, bord):
    _popen_espion(monkeypatch)
    bord.mkdir(parents=True)
    (bord / "distant.log").write_bytes(b"x" * bd._JOURNAL_MAX)
    bd._lancer()
    assert (bord / "distant.log").stat().st_size == bd._JOURNAL_MAX


def test_le_vrai_processus_detache_ecrit_son_etat_dans_le_journal(monkeypatch, bord):
    monkeypatch.delenv("RECO_AUDIENCE_KEY")
    assert bd._lancer() is True
    journal = bord / "distant.log"
    fin = time.monotonic() + 30
    while time.monotonic() < fin and "audience : cle-absente" not in (
            journal.read_text(encoding="utf-8") if journal.exists() else ""):
        time.sleep(0.2)
    assert "audience : cle-absente" in journal.read_text(encoding="utf-8")


def test_la_cle_n_entre_dans_aucun_journal_meme_si_l_appel_leve(monkeypatch, bord, capsys,
                                                                caplog):
    caplog.set_level(logging.DEBUG)
    _serveur(monkeypatch, ValueError(f"Invalid header value {CLE}"))
    assert bd.main(["rafraichir"]) == 0
    sorties = capsys.readouterr()
    assert CLE not in sorties.out + sorties.err + caplog.text
    assert CLE not in (bord / "distant.json").read_text(encoding="utf-8")


# ---- Tour 1, M2 : une exception imprévue est une panne, et l'essai est noté ---
@pytest.mark.parametrize(("exception", "nom"), [
    (ValueError(f"cle {CLE}\r"), "ValueError"),
    (UnicodeEncodeError("latin-1", "é", 0, 1, "x"), "UnicodeEncodeError"),
    (RecursionError(), "RecursionError"),
])
def test_une_exception_imprevue_est_une_panne_avec_son_essai(monkeypatch, bord, exception, nom):
    _serveur(monkeypatch, exception)
    assert bd.rafraichir(maintenant=MAINTENANT) == "panne"
    entree = _cache(bord)["audience"]
    assert (entree["etat"], entree["detail"]) == ("panne", nom)
    assert entree["essai"] == MAINTENANT.isoformat(timespec="seconds")
    assert bd.rafraichir(maintenant=MAINTENANT + timedelta(minutes=1)) == "frais"


def test_un_json_tres_imbrique_est_une_panne(monkeypatch, bord):
    _serveur(monkeypatch, (200, {}, b"[" * 200_000 + b"]" * 200_000))
    assert bd.rafraichir(maintenant=MAINTENANT) == "panne"
    assert _cache(bord)["audience"]["detail"] == "RecursionError"


# ---- Tour 1, F3 : une échéance pour toute la lecture -------------------------
class _FluxLent(io.BytesIO):
    """Rend 1 octet par lecture, et chaque lecture avance l'horloge de 4 s."""

    def __init__(self, horloge):
        super().__init__(b"{" * 100_000)
        self.horloge = horloge
        self.lectures = 0

    def read(self, n=-1):
        self.lectures += 1
        self.horloge[0] += 4
        return super().read(min(n, 1))


def test_une_reponse_qui_arrive_goutte_a_goutte_est_coupee_a_l_echeance(monkeypatch, bord):
    horloge = [1000.0]
    monkeypatch.setattr(bd, "time", types.SimpleNamespace(monotonic=lambda: horloge[0]))
    flux = _FluxLent(horloge)
    _serveur(monkeypatch, (200, {}, flux))
    assert bd.rafraichir(maintenant=MAINTENANT) == "panne"
    assert _cache(bord)["audience"]["detail"] == "TimeoutError"
    assert flux.lectures <= bd._ECHEANCE / 4 + 2


def test_une_reponse_normale_passe_par_la_lecture_bornee(monkeypatch, bord):
    _serveur(monkeypatch, _ok())
    assert bd.rafraichir(maintenant=MAINTENANT) == "ok"

