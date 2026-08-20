"""
sonder_api_infomaniak.py — trouver comment redemarrer le site Node.js.

POURQUOI CE SCRIPT
------------------
Le deploiement de Reco est manuel : console SSH du Manager, `git reset --hard`,
`npm run build`, puis clic sur « Redemarrer ». GitHub Actions ne peut pas
cliquer sur un bouton, et l'API Infomaniak ne DOCUMENTE pas publiquement
d'endpoint de redemarrage pour les sites Node.js (verifie le 2026-08-20 :
FAQ 2535, 2537, portail developpeur). Il faut donc la sonder.

CE QU'IL FAIT — ET CE QU'IL NE FAIT PAS
---------------------------------------
Uniquement des GET. Aucun POST, aucune ecriture : le script CHERCHE les
chemins qui existent, il ne redemarre rien et ne modifie rien.

LE TOKEN NE S'AFFICHE JAMAIS
----------------------------
Il est lu dans la variable d'environnement `IK_TOKEN` et n'apparait ni dans la
sortie, ni dans les URL affichees. Ne le passe pas en argument : la ligne de
commande est visible par les autres processus et reste dans l'historique.

    IK_TOKEN="ton-token" python scripts/sonder_api_infomaniak.py
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE = "https://api.infomaniak.com"


def appel(chemin: str, token: str) -> tuple[int, object]:
    """Un GET. Rend (code HTTP, corps decode) — jamais d'exception."""
    # S310 : le schema est fige par `BASE`, une constante https de ce fichier.
    # `chemin` ne fournit que le suffixe et ne peut pas reecrire le schema.
    requete = urllib.request.Request(  # noqa: S310
        f"{BASE}{chemin}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(requete, timeout=20) as reponse:  # noqa: S310
            return reponse.status, json.loads(reponse.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            return err.code, json.loads(err.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 — un corps d'erreur n'est pas toujours du JSON
            return err.code, None
    except Exception as err:  # noqa: BLE001 — reseau, DNS, TLS, JSON : tout se vaut ici
        return 0, str(err)


def resume(corps: object, taille: int = 260) -> str:
    """Un apercu court : la reponse complete peut faire des milliers de lignes."""
    return json.dumps(corps, ensure_ascii=False)[:taille] if corps else "—"


def main() -> int:
    token = os.environ.get("IK_TOKEN", "").strip()
    if not token:
        print("IK_TOKEN absent. Lance :\n"
              '  IK_TOKEN="ton-token" python scripts/sonder_api_infomaniak.py')
        return 2

    # Le test de vie porte sur le PERIMETRE demande, pas sur le profil : un
    # token de portee `web` repond 403 sur `/1/profile` (« require this
    # specific scope: user_info ») alors qu'il est parfaitement valide.
    print("=== 1. Le token repond-il ? ===")
    code, corps = appel("/1/products?service=hosting", token)
    print(f"GET /1/products?service=hosting -> {code}")
    if code != 200:
        print(f"   {resume(corps)}")
        print("\nLe token ne passe pas. Verifie que la portee `web` est cochee.")
        return 1

    print("\n=== 2. Les produits du compte ===")
    hebergements: list[int] = []
    for chemin in ("/1/products", "/1/products?service=hosting", "/2/products"):
        code, corps = appel(chemin, token)
        print(f"GET {chemin} -> {code}")
        if code == 200 and isinstance(corps, dict):
            data = corps.get("data") or []
            for produit in data if isinstance(data, list) else []:
                if not isinstance(produit, dict):
                    continue
                nom = produit.get("service_name") or produit.get("type") or "?"
                pid = produit.get("id") or produit.get("account_id")
                print(f"   - {nom:<22} id={pid}  {produit.get('customer_name', '')}")
                if "host" in str(nom).lower() and isinstance(pid, int):
                    hebergements.append(pid)

    if not hebergements:
        print("\nAucun hebergement reconnu automatiquement.")
        print("Recopie-moi la liste ci-dessus : j'en deduirai l'identifiant.")
        return 0

    print(f"\n=== 3. Les sites de l'hebergement {hebergements[0]} ===")
    hid = hebergements[0]
    for chemin in (f"/1/web/{hid}/sites", f"/2/web/{hid}/sites",
                   f"/1/hosting/{hid}/sites", f"/2/hosting/{hid}/sites"):
        code, corps = appel(chemin, token)
        marque = "  <-- EXISTE" if code == 200 else ""
        print(f"GET {chemin} -> {code}{marque}")
        if code == 200:
            print(f"   {resume(corps, 600)}")

    print("\n=== 4. Les chemins plausibles pour un site Node.js ===")
    # Aucun n'est documente : on regarde lesquels ne repondent pas 404.
    for chemin in (f"/1/web/{hid}/nodejs", f"/2/web/{hid}/nodejs",
                   f"/1/web/{hid}/applications", f"/2/web/{hid}/applications",
                   f"/1/web/{hid}/node_js", f"/2/hosting/{hid}/nodejs"):
        code, corps = appel(chemin, token)
        if code != 404:
            print(f"GET {chemin} -> {code}   {resume(corps)}")

    print("\nColle-moi cette sortie : elle ne contient aucun secret.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
