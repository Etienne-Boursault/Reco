#!/usr/bin/env python3
"""Construit la table « cette adresse appartient-elle à un hébergeur ? » de l'audience.

DÉCISION (AU-1 A, 2026-11-27)
-----------------------------
Le tableau `/audience` mélangeait robots et visiteurs. On repère, au moment de
la mesure, les adresses qui appartiennent à un hébergeur (centre de données,
VPN) : un navigateur d'humain y est rare. Le repère est un simple booléen
`hebergeur` écrit sur chaque ligne ; l'adresse, elle, n'est jamais conservée.
Aucun appel extérieur à la mesure : la table est embarquée, comme celle des
pays (`construire_table_pays.py`), et se met à jour à la main.

SOURCES ET LICENCES
-------------------
- X4BNet `lists_vpn`, fichier `input/datacenter/ASN.txt` : la liste des numéros
  d'ASN (réseaux) d'hébergeurs et de VPN. Licence MIT, d'après le README du
  dépôt (il n'a pas de fichier LICENSE). https://github.com/X4BNet/lists_vpn
- DB-IP « IP to ASN Lite » : les plages d'adresses de chaque ASN, mensuel.
  CC BY 4.0, attribution obligatoire. https://db-ip.com/db/download/ip-to-asn-lite

On n'utilise PAS `output/datacenter/ipv4.txt` de X4BNet : elle vient d'IPLocate
(CC BY-SA), dont la clause de partage à l'identique s'étendrait à la table du
dépôt. D'où le croisement de la liste d'ASN (MIT) avec DB-IP (CC BY 4.0).

CE QU'ON ÉCARTE (R-8)
---------------------
La liste de X4BNet contient des réseaux qui portent de VRAIS visiteurs :
Cloudflare (13335) est la sortie de WARP, Apple (714, 6185) celle d'iCloud
Private Relay, Akamai (20940, 36183) et Fastly (54113) en portent d'autres.
Mesuré le 2026-11-27 : la liste contient bien AS20940, AS36183 et AS54113. Les
classer « hébergeur » ferait sortir des lecteurs réels du compte des visiteurs,
sans que personne ne le voie. `ASN_EXCLUS` les retire ; `--relais-apple`, OBLIGATOIRE
(le script refuse de construire sans, tour 1 de revue du 27/11), retire en plus les
plages publiées par Apple pour iCloud Private Relay
(https://mask-api.icloud.com/egress-ip-ranges.csv), qui peuvent traîner dans
d'autres ASN.

IPv6 : tronqué au /48, et seuls les /48 ENTIÈREMENT couverts par une plage sont
écrits. Un /48 couvert à moitié appartient en partie à d'autres : l'étiqueter
reviendrait à classer d'éventuels visiteurs réels. Pour la même raison, tout
/48 touché par une plage d'Apple est retiré.

FORMAT PRODUIT (RECOHEB1)
-------------------------
Des paires début/fin, en colonnes séparées (deux suites homogènes se
compressent mieux qu'un entrelacement). Plages fusionnées, triées.

    magic    8o   RECOHEB1
    version  2o   uint16
    edition  8o   texte, ex. « 2026-11 »
    n4       4o   uint32
    debuts4  n4 × 4o   uint32 gros-boutiste, croissant
    fins4    n4 × 4o   uint32, fin incluse
    n6       4o   uint32
    debuts6  n6 × 6o   uint48 (préfixe /48), croissant
    fins6    n6 × 6o   uint48, fin incluse

Usage (les fichiers sont des DONNÉES téléchargées à la main, pas du code) :
    python tools/construire_table_hebergeurs.py --asn ASN.txt \\
        --dbip dbip-asn-lite-2026-11.csv.gz --relais-apple egress-ip-ranges.csv \\
        --edition 2026-11
"""

from __future__ import annotations

import argparse
import csv
import gzip
import ipaddress
import re
import struct
from datetime import UTC, datetime
from pathlib import Path

MAGIC = b"RECOHEB1"
VERSION = 1
BITS_IPV6 = 48
RACINE = Path(__file__).resolve().parent.parent
SORTIE = RACINE / "src" / "lib" / "audience" / "hebergeurs-ip.bin.gz"

# R-8 (2026-11-27) : réseaux qui portent de vrais visiteurs, même s'ils figurent
# dans la liste de X4BNet.
ASN_EXCLUS = {
    13335: "Cloudflare : sortie de WARP, donc de vrais visiteurs",
    36183: "Akamai : sortie d'iCloud Private Relay",
    20940: "Akamai : sortie d'iCloud Private Relay",
    54113: "Fastly : sortie d'iCloud Private Relay",
    714: "Apple : iCloud Private Relay",
    6185: "Apple : iCloud Private Relay",
}

_LIGNE_ASN = re.compile(r"^AS(\d+)\b")


def edition_courante() -> str:
    """Le mois en cours, format `AAAA-MM`."""
    aujourdhui = datetime.now(UTC).date()
    return f"{aujourdhui.year:04d}-{aujourdhui.month:02d}"


def lire_asn(chemin: Path) -> set[int]:
    """Les numéros d'ASN de la liste. Une ligne `-AS…` est un retrait : sautée."""
    asns = set()
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        trouve = _LIGNE_ASN.match(ligne)
        if trouve:
            asns.add(int(trouve.group(1)))
    return asns


def asn_retenus(chemin: Path) -> set[int]:
    """La liste de X4BNet moins les réseaux de vrais visiteurs (R-8)."""
    return lire_asn(chemin) - ASN_EXCLUS.keys()


def fusionner(plages: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Trie, puis joint les plages qui se chevauchent ou se touchent."""
    sortie: list[tuple[int, int]] = []
    for debut, fin in sorted(plages):
        if sortie and debut <= sortie[-1][1] + 1:
            sortie[-1] = (sortie[-1][0], max(sortie[-1][1], fin))
        else:
            sortie.append((debut, fin))
    return sortie


def soustraire(
    plages: list[tuple[int, int]], retraits: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Retire `retraits` de `plages`. Les deux listes sont triées et fusionnées."""
    sortie: list[tuple[int, int]] = []
    j = 0
    for debut, fin in plages:
        while j < len(retraits) and retraits[j][1] < debut:
            j += 1
        k = j
        while debut <= fin:
            if k >= len(retraits) or retraits[k][0] > fin:
                sortie.append((debut, fin))
                break
            retrait_debut, retrait_fin = retraits[k]
            if retrait_debut > debut:
                sortie.append((debut, retrait_debut - 1))
            debut = retrait_fin + 1
            k += 1
    return sortie


def lire_plages(
    chemin: Path, asns: set[int]
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Les plages IPv4 et IPv6 (préfixes /48 entièrement couverts) des ASN retenus."""
    v4: list[tuple[int, int]] = []
    v6: list[tuple[int, int]] = []
    decalage = 128 - BITS_IPV6
    with gzip.open(chemin, "rt", encoding="utf-8", newline="") as flux:
        for ligne in csv.reader(flux):
            if len(ligne) != 4 or not ligne[2].isdigit() or int(ligne[2]) not in asns:
                continue
            try:
                debut = ipaddress.ip_address(ligne[0])
                fin = ipaddress.ip_address(ligne[1])
            except ValueError:
                continue
            if debut.version != fin.version:
                continue
            if debut.version == 4:
                v4.append((int(debut), int(fin)))
                continue
            # Premier /48 qui commence dans la plage, dernier qui s'y termine.
            premier = (int(debut) + (1 << decalage) - 1) >> decalage
            dernier = ((int(fin) + 1) >> decalage) - 1
            if premier <= dernier:
                v6.append((premier, dernier))
    return fusionner(v4), fusionner(v6)


def lire_relais(
    chemin: Path,
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Les plages d'iCloud Private Relay (CSV d'Apple, réseau CIDR en 1re colonne).

    En IPv6, tout /48 touché est compté, pour le retirer en entier.
    """
    v4: list[tuple[int, int]] = []
    v6: list[tuple[int, int]] = []
    decalage = 128 - BITS_IPV6
    with chemin.open(encoding="utf-8", newline="") as flux:
        for ligne in csv.reader(flux):
            try:
                reseau = ipaddress.ip_network(ligne[0], strict=False)
            except (IndexError, ValueError):
                continue
            debut, fin = int(reseau.network_address), int(reseau.broadcast_address)
            if reseau.version == 4:
                v4.append((debut, fin))
            else:
                v6.append((debut >> decalage, fin >> decalage))
    return fusionner(v4), fusionner(v6)


def encoder(v4: list[tuple[int, int]], v6: list[tuple[int, int]], edition: str) -> bytes:
    """Assemble le format décrit en tête de fichier."""
    return b"".join(
        [
            MAGIC,
            struct.pack(">H", VERSION),
            edition.encode("ascii").ljust(8, b" ")[:8],
            struct.pack(">I", len(v4)),
            b"".join(struct.pack(">I", d) for d, _ in v4),
            b"".join(struct.pack(">I", f) for _, f in v4),
            struct.pack(">I", len(v6)),
            # uint48 : les deux octets de poids fort d'un uint64 sont nuls.
            b"".join(struct.pack(">Q", d)[2:] for d, _ in v6),
            b"".join(struct.pack(">Q", f)[2:] for _, f in v6),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parseur.add_argument("--asn", type=Path, required=True, help="ASN.txt de X4BNet")
    parseur.add_argument("--dbip", type=Path, required=True, help="CSV.gz DB-IP IP to ASN")
    parseur.add_argument(
        "--relais-apple",
        type=Path,
        required=True,
        help="egress-ip-ranges.csv d'Apple (obligatoire : R-8, sans lui des lecteurs réels "
        "d'iCloud Private Relay seraient classés hébergeur)",
    )
    parseur.add_argument("--edition", default=edition_courante(), help="AAAA-MM")
    parseur.add_argument("--sortie", type=Path, default=SORTIE)
    args = parseur.parse_args(argv)

    v4, v6 = lire_plages(args.dbip, asn_retenus(args.asn))
    relais4, relais6 = lire_relais(args.relais_apple)
    v4, v6 = soustraire(v4, relais4), soustraire(v6, relais6)
    if not v4 or not v6:
        raise SystemExit("[table-hebergeurs] sources illisibles ou vides : rien écrit")

    brut = encoder(v4, v6, args.edition)
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 : même source, mêmes octets, git ne voit pas de modification.
    # filename="" : sans cela l'en-tête gzip porte le nom du fichier écrit.
    with (
        args.sortie.open("wb") as cible,
        gzip.GzipFile(filename="", mode="wb", fileobj=cible, compresslevel=9, mtime=0) as flux,
    ):
        flux.write(brut)

    taille = args.sortie.stat().st_size
    print(
        f"[table-hebergeurs] {len(v4):,} plages IPv4 + {len(v6):,} plages IPv6 (/48)\n"
        f"[table-hebergeurs] {len(brut):,} octets bruts -> {taille:,} compresses "
        f"({taille / 1e6:.2f} Mo)",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
