"""
youtube_autoriser.py — obtenir, une fois, le droit de commenter sur YouTube.

A lancer sur un poste avec navigateur, PAS sur venus :

    python youtube_autoriser.py chemin/vers/client_secret.json

Le fichier vient de Google Cloud (identifiants OAuth de type « Application de
bureau »). Le script ouvre la page de consentement de Google : choisir la
chaine « Une Bonne Reco », puis accepter. Il ecrit ensuite les trois lignes
`RECO_YT_*` dans un fichier hors du depot (par defaut `~/reco-youtube.env`),
a recopier dans le `.env` de venus. Rien n'est affiche a l'ecran : ce sont des
secrets.

Uniquement la bibliotheque standard : le script tourne sur n'importe quel
Python, sans installer l'outillage du projet.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

AUTORISATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
JETON_URL = "https://oauth2.googleapis.com/token"
#: Le seul droit qui permette de poster un commentaire.
PORTEE = "https://www.googleapis.com/auth/youtube.force-ssl"


def lire_client(chemin: Path) -> tuple[str, str]:
    doc = json.loads(chemin.read_text(encoding="utf-8"))
    bloc = doc.get("installed") or doc.get("web") or {}
    if not bloc.get("client_id") or not bloc.get("client_secret"):
        raise SystemExit("Fichier inattendu : il faut le client_secret.json d'une "
                         "« Application de bureau ».")
    return bloc["client_id"], bloc["client_secret"]


def defi_pkce() -> tuple[str, str]:
    verificateur = secrets.token_urlsafe(64)
    condense = hashlib.sha256(verificateur.encode()).digest()
    return verificateur, base64.urlsafe_b64encode(condense).rstrip(b"=").decode()


def adresse_consentement(client_id: str, retour: str, etat: str, defi: str) -> str:
    # `prompt=consent` et `access_type=offline` : sans eux, Google ne rend pas
    # de jeton de renouvellement, et l'acces expirerait au bout d'une heure.
    return AUTORISATION_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": retour, "response_type": "code",
        "scope": PORTEE, "access_type": "offline", "prompt": "consent",
        "state": etat, "code_challenge": defi, "code_challenge_method": "S256",
    })


def lignes_env(client_id: str, client_secret: str, jeton: str) -> str:
    return (f"RECO_YT_CLIENT_ID={client_id}\n"
            f"RECO_YT_CLIENT_SECRET={client_secret}\n"
            f"RECO_YT_REFRESH_TOKEN={jeton}\n")


def attendre_code(serveur: http.server.HTTPServer) -> dict[str, str]:  # pragma: no cover
    recu: dict[str, str] = {}

    class Retour(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            recu.update(dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query)))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"C'est fait, tu peux fermer cet onglet.")

        def log_message(self, *args: object) -> None:
            pass

    serveur.RequestHandlerClass = Retour
    serveur.handle_request()
    return recu


def echanger(client_id: str, client_secret: str, code: str, retour: str,
             verificateur: str) -> str:  # pragma: no cover — reseau
    donnees = urllib.parse.urlencode({
        "client_id": client_id, "client_secret": client_secret, "code": code,
        "redirect_uri": retour, "grant_type": "authorization_code",
        "code_verifier": verificateur,
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(JETON_URL, data=donnees), timeout=30) as r:
        reponse = json.load(r)
    if "refresh_token" not in reponse:
        raise SystemExit("Google n'a pas rendu de jeton de renouvellement : "
                         "retire l'acces dans le compte Google et recommence.")
    return reponse["refresh_token"]


def main(argv: list[str] | None = None) -> int:  # pragma: no cover — interactif
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("client_secret", type=Path)
    parser.add_argument("--sortie", type=Path, default=Path.home() / "reco-youtube.env")
    args = parser.parse_args(argv)

    client_id, client_secret = lire_client(args.client_secret)
    serveur = http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
    retour = f"http://127.0.0.1:{serveur.server_port}"
    verificateur, defi = defi_pkce()
    etat = secrets.token_urlsafe(16)
    adresse = adresse_consentement(client_id, retour, etat, defi)
    print("Ouverture du consentement Google. Choisis la chaine « Une Bonne Reco ».")
    print(f"Si rien ne s'ouvre : {adresse}")
    webbrowser.open(adresse)

    recu = attendre_code(serveur)
    if recu.get("state") != etat or "code" not in recu:
        raise SystemExit(f"Autorisation refusee ou interrompue : {recu.get('error', 'sans code')}")
    jeton = echanger(client_id, client_secret, recu["code"], retour, verificateur)
    args.sortie.write_text(lignes_env(client_id, client_secret, jeton), encoding="utf-8")
    print(f"Ecrit dans {args.sortie}. Recopie ces trois lignes dans le .env de venus,")
    print("ajoute RECO_YT_COMMENTAIRES=1, puis supprime ce fichier.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
