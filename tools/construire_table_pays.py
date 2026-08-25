#!/usr/bin/env python3
"""Construit la table IP → pays embarquée par le tableau de bord d'audience.

POURQUOI UNE TABLE LOCALE
-------------------------
Le pays ne se déduit que d'un en-tête posé en amont par l'hébergeur. Vérifié
le 2026-08-25 en production : Infomaniak n'en pose aucun. Tout ce qui arrive
est `accept`, `host`, `user-agent`, `x-envoy-external-address`,
`x-forwarded-for`, `x-forwarded-port`, `x-forwarded-proto`, `x-request-id`.

Interroger un service tiers à chaque visite reviendrait à lui confier les
adresses IP des visiteurs — exactement ce que le reste du dispositif refuse.
D'où une table embarquée : aucune requête sortante, aucun tiers, la mesure
reste dans le processus.

CE QUE CETTE TABLE VAUT
-----------------------
Une géolocalisation par IP donne le pays, pas la personne, et se trompe sur un
VPN ou certains opérateurs mobiles. C'est assez pour savoir si l'audience
dépasse les pays francophones ; ce n'est pas une donnée à traiter comme sûre.

L'IPv6 est tronquée à /48 : à ce niveau, 0,64 % des plages partagent un
préfixe avec un autre pays (contre 50 % à /32 — mesuré sur la base d'août
2026). La dernière plage d'un préfixe partagé l'emporte. Le gain est décisif :
2,4 Mo au lieu de 3,1, et surtout une borne qui tient sur 6 octets.

SOURCE ET LICENCE
-----------------
DB-IP « IP to Country Lite », CC BY 4.0 — l'attribution est obligatoire et
figure sur la page `/audience`. Aucun compte à créer, contrairement à
GeoLite2. https://db-ip.com/db/download/ip-to-country-lite

FORMAT PRODUIT
--------------
Bornes de DÉBUT seulement : la base ne comporte aucune discontinuité (vérifié
à chaque construction), le pays d'une adresse est donc celui de la plus grande
borne qui lui est inférieure ou égale. Bornes et index sont écrits en colonnes
séparées — deux suites homogènes se compressent bien mieux qu'un entrelacement.

    magic    8o   RECOGEO1
    version  2o   uint16
    edition  8o   texte, ex. « 2026-08 »
    nbPays   2o   uint16
    pays     nbPays × 2o   codes ISO, ASCII
    n4       4o   uint32
    bornes4  n4 × 4o   uint32 gros-boutiste, croissant
    index4   n4 × 1o
    n6       4o   uint32
    bornes6  n6 × 6o   uint48 gros-boutiste (préfixe /48), croissant
    index6   n6 × 1o

Usage :
    python tools/construire_table_pays.py                 # télécharge le mois courant
    python tools/construire_table_pays.py --csv fichier.csv.gz
    python tools/construire_table_pays.py --edition 2026-07
"""

from __future__ import annotations

import argparse
import gzip
import ipaddress
import struct
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

MAGIC = b"RECOGEO1"
VERSION = 1
BITS_IPV6 = 48
RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "src" / "lib" / "audience" / "pays-ip.bin.gz"
URL = "https://download.db-ip.com/free/dbip-country-lite-{edition}.csv.gz"


def edition_courante() -> str:
    """Le mois en cours, format `AAAA-MM` — celui que DB-IP publie."""
    aujourdhui = datetime.now(UTC).date()
    return f"{aujourdhui.year:04d}-{aujourdhui.month:02d}"


def telecharger(edition: str, vers: Path) -> Path:
    """Récupère l'édition demandée, en repliant sur le mois précédent."""
    for candidate in (edition, mois_precedent(edition)):
        url = URL.format(edition=candidate)
        # `urlopen` accepte `file:` et les schémas exotiques : une URL mal
        # modifiée lirait un fichier local et le prendrait pour la base.
        if not url.startswith("https://"):
            raise SystemExit(f"[table-pays] schéma refusé : {url}")
        try:
            with urllib.request.urlopen(url, timeout=120) as reponse:  # noqa: S310
                if reponse.status != 200:
                    continue
                vers.write_bytes(reponse.read())
            print(f"[table-pays] {candidate} téléchargée ({vers.stat().st_size:,} octets)")
            return vers
        except OSError as err:  # pragma: no cover - dépend du réseau
            print(f"[table-pays] {candidate} indisponible : {err}", file=sys.stderr)
    raise SystemExit("[table-pays] aucune édition récupérable")


def mois_precedent(edition: str) -> str:
    """`2026-01` → `2025-12`. DB-IP publie en début de mois, avec du retard."""
    annee, mois = (int(x) for x in edition.split("-"))
    return f"{annee - 1:04d}-12" if mois == 1 else f"{annee:04d}-{mois - 1:02d}"


def lire_plages(chemin: Path) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """Rend les bornes de début IPv4 et IPv6, dédupliquées par pays consécutif.

    Vérifie au passage que les plages ne laissent aucun trou : sans quoi ne
    stocker que les débuts attribuerait à une adresse non couverte le pays de
    la plage précédente, silencieusement.
    """
    v4: list[tuple[int, str]] = []
    v6: list[tuple[int, str]] = []
    fin_v4 = fin_v6 = None
    vus_v6: dict[int, str] = {}

    with gzip.open(chemin, "rt", encoding="utf-8") as flux:
        for ligne in flux:
            morceaux = ligne.rstrip("\n").split(",")
            if len(morceaux) != 3:
                continue
            debut_txt, fin_txt, pays = morceaux
            if len(pays) != 2 or not pays.isalpha():
                continue
            pays = pays.upper()

            if ":" in debut_txt:
                debut = int(ipaddress.IPv6Address(debut_txt))
                fin = int(ipaddress.IPv6Address(fin_txt))
                if fin_v6 is not None and debut != fin_v6 + 1:
                    raise SystemExit(
                        f"[table-pays] trou IPv6 avant {debut_txt} : "
                        "les bornes de début ne suffiraient plus"
                    )
                fin_v6 = fin
                prefixe = debut >> (128 - BITS_IPV6)
                # Un préfixe déjà vu appartient à une plage plus fine que /48 :
                # la dernière l'emporte, en écrasant l'entrée précédente.
                if prefixe in vus_v6:
                    if vus_v6[prefixe] != pays and v6 and v6[-1][0] == prefixe:
                        v6[-1] = (prefixe, pays)
                    vus_v6[prefixe] = pays
                    continue
                vus_v6[prefixe] = pays
                if not v6 or v6[-1][1] != pays:
                    v6.append((prefixe, pays))
            else:
                debut = int(ipaddress.IPv4Address(debut_txt))
                fin = int(ipaddress.IPv4Address(fin_txt))
                if fin_v4 is not None and debut != fin_v4 + 1:
                    raise SystemExit(
                        f"[table-pays] trou IPv4 avant {debut_txt} : "
                        "les bornes de début ne suffiraient plus"
                    )
                fin_v4 = fin
                if not v4 or v4[-1][1] != pays:
                    v4.append((debut, pays))

    if not v4 or not v6:
        raise SystemExit("[table-pays] base illisible ou vide")
    return v4, v6


def encoder(v4: list[tuple[int, str]], v6: list[tuple[int, str]], edition: str) -> bytes:
    """Assemble le format décrit en tête de fichier."""
    pays = sorted({p for _, p in v4} | {p for _, p in v6})
    if len(pays) > 0xFFFF:  # pragma: no cover - impossible avec des codes ISO
        raise SystemExit("[table-pays] trop de pays")
    rang = {code: i for i, code in enumerate(pays)}
    if len(pays) > 255:
        raise SystemExit(
            f"[table-pays] {len(pays)} pays : l'index ne tient plus sur un octet"
        )

    morceaux = [
        MAGIC,
        struct.pack(">H", VERSION),
        edition.encode("ascii").ljust(8, b" ")[:8],
        struct.pack(">H", len(pays)),
        b"".join(c.encode("ascii") for c in pays),
        struct.pack(">I", len(v4)),
        b"".join(struct.pack(">I", b) for b, _ in v4),
        bytes(rang[p] for _, p in v4),
        struct.pack(">I", len(v6)),
        # uint48 : les deux octets de poids fort d'un uint64 sont toujours nuls
        # pour un préfixe /48, autant ne pas les écrire.
        b"".join(struct.pack(">Q", b)[2:] for b, _ in v6),
        bytes(rang[p] for _, p in v6),
    ]
    return b"".join(morceaux)


def main() -> int:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--csv", type=Path, help="CSV.gz déjà téléchargé")
    parseur.add_argument("--edition", default=edition_courante(), help="AAAA-MM")
    parseur.add_argument("--sortie", type=Path, default=SORTIE)
    args = parseur.parse_args()

    source = args.csv
    temporaire = None
    if source is None:
        temporaire = args.sortie.parent / f".dbip-{args.edition}.csv.gz"
        temporaire.parent.mkdir(parents=True, exist_ok=True)
        source = telecharger(args.edition, temporaire)

    v4, v6 = lire_plages(source)
    brut = encoder(v4, v6, args.edition)

    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 : sans cela l'horodatage change à chaque construction et git voit
    # un fichier modifié même quand la table est identique.
    with gzip.GzipFile(args.sortie, "wb", compresslevel=9, mtime=0) as flux:
        flux.write(brut)

    if temporaire is not None and temporaire.exists():
        temporaire.unlink()

    taille = args.sortie.stat().st_size
    print(
        f"[table-pays] {len(v4):,} bornes IPv4 + {len(v6):,} bornes IPv6 (/48)\n"
        f"[table-pays] {len(brut):,} octets bruts -> {taille:,} compresses "
        f"({taille / 1e6:.2f} Mo)\n"
        f"[table-pays] écrit dans {args.sortie.relative_to(RACINE)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
