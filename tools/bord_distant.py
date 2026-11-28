"""bord_distant.py — l'audience du site, lue depuis venus pour le tableau de bord.

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026, l'audience
au centre (plan `pr-tableau-de-bord.md`, § 2 « Le local et le distant », § 3 et
relectures R1, R11).

Le site rend son résumé d'audience par `GET /api/bord` (forme : `src/lib/bord/resume.ts`),
avec la clé `RECO_AUDIENCE_KEY` dans l'en-tête `X-Reco-Cle`, jamais dans l'URL.

POURQUOI LA PAGE NE LIT QUE LE CACHE
------------------------------------
Le serveur de relecture n'a qu'un fil, et le délai d'urllib ne borne pas la
résolution DNS : un appel réseau dans le rendu figerait toute la relecture.
`lire()` lit donc `<RECO_BORD_DIR>/distant.json` et, quand le dernier essai a
plus de 10 min, lance `python bord_distant.py rafraichir` détaché, sans l'attendre.
Le rafraîchissement prend `distant.lock` sans attendre : deux ne tournent jamais
ensemble. Après un échec, on ne réessaie pas avant 10 min (F6), et la dernière
valeur lue reste, avec son heure.

POURQUOI AUCUNE REDIRECTION
---------------------------
urllib recopie les en-têtes, `X-Reco-Cle` compris, vers la cible d'une
redirection. `_SansRedirection` les refuse toutes : un 3xx compte comme une panne.
L'adresse exige `https://`, et la réponse doit venir exactement de l'hôte du site.

La clé n'apparaît dans aucun journal, message, état ni cache (F15) : les erreurs
ne sont décrites que par leur type ou leur code HTTP. Un cache illisible n'est
jamais pris pour un cache vide, donc jamais réécrit (F22).
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import filelock

import common
from bord_reseaux import dossier
from commentaire_youtube import SITE_PAR_DEFAUT
from common import log

SOURCE = "audience"
CHEMIN = "/api/bord"
VARIABLE_CLE = "RECO_AUDIENCE_KEY"
#: Au-delà, le cache est relu sur le site (succès comme échec : F6).
FRAICHEUR = timedelta(minutes=10)
_DELAI = 10
#: Échéance de toute la lecture de la réponse (F3 du tour 1, 28/11/2026) : `_DELAI`
#: ne vaut que pour chaque lecture, donc une réponse goutte à goutte tiendrait le verrou.
_ECHEANCE = 30
_TAILLE_MAX = 2_000_000
#: Au-delà, `distant.log` repart de zéro (M1 du tour 1).
_JOURNAL_MAX = 200_000
LIBELLES = {"ok": "à jour", "inconnu": "inconnu", "cle-absente": "clé absente",
            "cle-refusee": "clé refusée", "panne": "panne",
            "reponse-illisible": "réponse illisible", "cache-illisible": "cache illisible"}


class CacheIllisible(Exception):
    """`distant.json` existe mais ne se lit pas : on ne l'écrase pas."""


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    """Refuse toute redirection : urllib lève alors une `HTTPError` 3xx."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _ouvreur() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_SansRedirection)


def adresse() -> str:
    """`https://<hôte du site>/api/bord` ; `ValueError` si le site n'est pas un https:// net."""
    parts = urlsplit((os.environ.get("SITE_URL") or SITE_PAR_DEFAUT).strip())
    if (parts.scheme != "https" or not parts.hostname
            or parts.username is not None or parts.password is not None):
        raise ValueError("SITE_URL doit être une adresse https:// sans identifiant")
    port = f":{parts.port}" if parts.port else ""
    return f"https://{parts.hostname}{port}{CHEMIN}"


def _forme_attendue(donnees: Any) -> bool:
    return (isinstance(donnees, dict) and isinstance(donnees.get("genere"), str)
            and all(k in donnees and (donnees[k] is None or isinstance(donnees[k], dict))
                    for k in ("sept", "trente"))
            and isinstance(donnees.get("jours"), list)
            and isinstance(donnees.get("signalements"), dict))


def _lire_borne(reponse: Any) -> bytes:
    """Le corps, par morceaux : au plus `_TAILLE_MAX` + 1 octets, en `_ECHEANCE` s.

    `TimeoutError` (une `OSError`) à l'échéance. Ne couvre pas la résolution DNS,
    qui précède l'ouverture : seul le délai de chaque lecture borne la suite.
    """
    fin = time.monotonic() + _ECHEANCE
    morceaux: list[bytes] = []
    total = 0
    while total <= _TAILLE_MAX:
        if time.monotonic() > fin:
            raise TimeoutError("échéance de lecture dépassée")
        morceau = reponse.read(min(8192, _TAILLE_MAX + 1 - total))
        if not morceau:
            break
        morceaux.append(morceau)
        total += len(morceau)
    return b"".join(morceaux)


def _appeler() -> tuple[str, str | None, dict[str, Any] | None]:
    """Un appel au site : (état, détail sans secret, résumé ou None)."""
    cle = os.environ.get(VARIABLE_CLE)
    if not cle:
        return "cle-absente", None, None
    try:
        url = adresse()
    except ValueError:
        return "panne", "adresse refusée", None
    # `adresse()` n'admet que https:// : ni file:, ni schéma maison.
    requete = urllib.request.Request(url, headers={  # noqa: S310
        "X-Reco-Cle": cle, "Accept": "application/json"})
    try:
        with _ouvreur().open(requete, timeout=_DELAI) as reponse:
            if urlsplit(reponse.geturl()).hostname != urlsplit(url).hostname:
                return "panne", "autre hôte", None
            corps = _lire_borne(reponse)
    except urllib.error.HTTPError as exc:
        exc.close()
        return ("cle-refusee" if exc.code == 404 else "panne"), f"HTTP {exc.code}", None
    except (OSError, http.client.HTTPException) as exc:
        return "panne", type(exc).__name__, None
    if len(corps) > _TAILLE_MAX:
        return "reponse-illisible", "trop longue", None
    try:
        donnees = json.loads(corps)
    except ValueError:
        return "reponse-illisible", "JSON invalide", None
    if not _forme_attendue(donnees):
        return "reponse-illisible", "forme inattendue", None
    return "ok", None, donnees


def _chemin() -> Path:
    return dossier() / "distant.json"


def _date(valeur: Any) -> datetime:
    if not isinstance(valeur, str):
        raise ValueError("date absente")
    date = datetime.fromisoformat(valeur)
    if date.tzinfo is None:
        raise ValueError("date sans fuseau")
    return date


def _lire_cache() -> dict[str, Any]:
    """Tout `distant.json` ; `{}` sans fichier ; `CacheIllisible` s'il est abîmé."""
    chemin = _chemin()
    if not chemin.exists():
        return {}
    try:
        cache = common.read_json(chemin)
        entree = cache.get(SOURCE) if isinstance(cache, dict) else None
        if not isinstance(cache, dict) or (entree is not None and not (
                isinstance(entree, dict) and isinstance(entree.get("etat"), str)
                and _date(entree.get("essai"))
                and (entree.get("lu") is None or _date(entree["lu"]))
                and (entree.get("donnees") is None or isinstance(entree["donnees"], dict)))):
            raise ValueError("forme inattendue")
    except (OSError, ValueError) as exc:
        raise CacheIllisible(f"{chemin.name} illisible ({type(exc).__name__})") from exc
    return cache


def _perime(entree: dict[str, Any] | None, maintenant: datetime) -> bool:
    return entree is None or maintenant - _date(entree["essai"]) >= FRAICHEUR


def rafraichir(*, maintenant: datetime | None = None) -> str:
    """Relit le site si le cache est périmé, sous verrou ; rend l'état obtenu.

    Rend aussi `occupe` (un autre rafraîchissement tient le verrou), `frais` (un
    essai de moins de 10 min) ou `cache-illisible` (rien n'est écrit).
    """
    maintenant = maintenant or datetime.now(UTC)
    dossier().mkdir(parents=True, exist_ok=True)
    try:
        with filelock.FileLock(str(dossier() / "distant.lock"), timeout=0):
            try:
                cache = _lire_cache()
            except CacheIllisible as exc:
                log.warning("bord : %s, rafraîchissement de %s abandonné", exc, SOURCE)
                return "cache-illisible"
            avant = cache.get(SOURCE)
            if not _perime(avant, maintenant):
                return "frais"
            try:
                etat, detail, donnees = _appeler()
            except Exception as exc:  # noqa: BLE001
                # Tour 1, M2 : une `ValueError` (clé finie par un retour chariot), une `RecursionError`
                # (JSON très imbriqué)... Jamais le message (la clé a pu y passer), et
                # `essai` s'écrit toujours : sinon chaque affichage relancerait un processus.
                etat, detail, donnees = "panne", type(exc).__name__, None
            quand = maintenant.isoformat(timespec="seconds")
            avant = avant or {}
            cache[SOURCE] = {"etat": etat, "detail": detail, "essai": quand,
                             "lu": quand if etat == "ok" else avant.get("lu"),
                             "donnees": donnees if etat == "ok" else avant.get("donnees")}
            common.write_json_if_changed(_chemin(), cache)
            log.info("bord : %s relue sur le site, état %s (%s)", SOURCE, etat, detail or "-")
            return etat
    except filelock.Timeout:
        return "occupe"


def _lancer() -> bool:
    """Lance `rafraichir` dans un processus détaché, sans l'attendre.

    Ses sorties vont dans `distant.log`, en ajout (tour 1, M1 : sinon une erreur
    imprévue ne se voyait nulle part). Il ne reçoit la clé que par l'environnement,
    et `rafraichir` ne laisse sortir aucun message d'exception : la clé n'y entre pas.
    Au-delà de 200 Ko, le journal repart de zéro.
    """
    try:
        dossier().mkdir(parents=True, exist_ok=True)
        with open(dossier() / "distant.log", "ab") as journal:
            if os.fstat(journal.fileno()).st_size > _JOURNAL_MAX:
                journal.truncate(0)
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "rafraichir"],
                             stdin=subprocess.DEVNULL, stdout=journal,
                             stderr=subprocess.STDOUT, close_fds=True, start_new_session=True)
    except OSError as exc:
        log.warning("bord : rafraîchissement non lancé pour %s (%s)", SOURCE, type(exc).__name__)
        return False
    return True


def lire(*, maintenant: datetime | None = None, relancer: bool = True) -> dict[str, Any]:
    """L'état de l'audience pour la page, sans jamais attendre le réseau.

    `{"source", "etat", "libelle", "detail", "donnees", "lu", "essai", "age", "relance"}` :
    `donnees` est le dernier résumé lu (gardé après une panne), `lu` son heure et
    `age` ses secondes ; `essai` l'heure du dernier appel ; `relance` dit si un
    rafraîchissement vient d'être lancé.
    """
    maintenant = maintenant or datetime.now(UTC)
    try:
        entree = _lire_cache().get(SOURCE)
    except CacheIllisible as exc:
        log.warning("bord : %s", exc)
        entree, etat = None, "cache-illisible"
    else:
        etat = (entree or {}).get("etat", "inconnu")
        if not os.environ.get(VARIABLE_CLE):
            etat = "cle-absente"
    entree = entree or {}
    relance = (relancer and etat not in ("cache-illisible", "cle-absente")
               and _perime(entree or None, maintenant) and _lancer())
    lu = entree.get("lu")
    return {"source": SOURCE, "etat": etat, "libelle": LIBELLES.get(etat, etat),
            "detail": entree.get("detail"), "donnees": entree.get("donnees"), "lu": lu,
            "essai": entree.get("essai"),
            "age": int((maintenant - _date(lu)).total_seconds()) if lu else None,
            "relance": relance}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lecture distante du tableau de bord.")
    parser.add_argument("commande", choices=["rafraichir"])
    parser.parse_args(argv)
    print(f"{SOURCE} : {rafraichir()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
