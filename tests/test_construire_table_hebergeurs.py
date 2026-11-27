"""Tests de `tools/construire_table_hebergeurs.py` (AU-1 A, 2026-11-27).

Ce qu'ils gardent, par ordre d'importance :

1. R-8 : les réseaux qui portent de vrais visiteurs (WARP de Cloudflare,
   iCloud Private Relay d'Apple, Akamai, Fastly) ne doivent JAMAIS entrer dans
   la table, même quand la liste de X4BNet les contient. Un visiteur réel
   classé « hébergeur » sort du compte des visiteurs sans que personne ne le
   voie.
2. La table n'étiquette pas plus large que la source : un /48 IPv6 qui n'est
   couvert qu'en partie n'est pas écrit.
3. La disposition binaire, relue ici par un décodeur indépendant.
"""

from __future__ import annotations

import gzip
import struct
from pathlib import Path

import pytest

import construire_table_hebergeurs as cth

ASN_TXT = """\
# commentaire de tête
AS100 # hébergeur A
AS200 # hébergeur B, avec une virgule
AS13335 # Cloudflare
AS36183 # Akamai
AS20940 # Akamai
AS54113 # Fastly
AS714 # Apple
AS6185 # Apple
-AS12360 # retiré à la source
ASxyz # pas un numéro
n'importe quoi
"""

# Le CSV de DB-IP : `début,fin,asn,"nom"`. Les noms contiennent des virgules.
LIGNES_DBIP = [
    ("10.0.0.0", "10.0.0.255", 100, "Hébergeur A, Inc."),
    ("10.0.1.0", "10.0.1.255", 200, "Hébergeur B"),  # collée à la précédente
    ("10.0.5.0", "10.0.5.255", 999, "Un opérateur résidentiel"),
    ("10.0.9.0", "10.0.9.255", 100, "Hébergeur A, Inc."),  # séparée : un trou
    ("1.0.0.0", "1.0.0.255", 13335, "Cloudflare, Inc."),
    ("2.16.0.0", "2.16.2.255", 20940, "Akamai International B.V."),
    ("3.0.0.0", "3.0.0.255", 36183, "Akamai"),
    ("4.0.0.0", "4.0.0.255", 54113, "Fastly"),
    ("17.0.0.0", "17.0.0.255", 714, "Apple"),
    ("18.0.0.0", "18.0.0.255", 6185, "Apple"),
    # Un /48 entier, puis un /48 couvert à moitié seulement.
    ("2001:db8:1::", "2001:db8:1:ffff:ffff:ffff:ffff:ffff", 100, "Hébergeur A, Inc."),
    ("2001:db8:2::", "2001:db8:2:7fff:ffff:ffff:ffff:ffff", 200, "Hébergeur B"),
    # Deux /48 voisins, d'ASN différents : fusionnés.
    ("2001:db8:3::", "2001:db8:3:ffff:ffff:ffff:ffff:ffff", 100, "Hébergeur A, Inc."),
    ("2001:db8:4::", "2001:db8:4:ffff:ffff:ffff:ffff:ffff", 200, "Hébergeur B"),
    ("2600::", "2600:ffff:ffff:ffff:ffff:ffff:ffff:ffff", 13335, "Cloudflare"),
]


def _ecrire_dbip(chemin: Path, lignes=LIGNES_DBIP, extra: str = "") -> Path:
    corps = "".join(f'{d},{f},{a},"{n}"\n' for d, f, a, n in lignes) + extra
    with gzip.open(chemin, "wt", encoding="utf-8") as flux:
        flux.write(corps)
    return chemin


def _ip4(texte: str) -> int:
    a, b, c, d = (int(x) for x in texte.split("."))
    return ((a * 256 + b) * 256 + c) * 256 + d


@pytest.fixture
def sources(tmp_path):
    asn = tmp_path / "ASN.txt"
    asn.write_text(ASN_TXT, encoding="utf-8")
    return asn, _ecrire_dbip(tmp_path / "dbip.csv.gz")


def _decoder(brut: bytes):
    """Relecture indépendante du format RECOHEB1 : (édition, v4, v6)."""
    assert brut[:8] == b"RECOHEB1"
    (version,) = struct.unpack(">H", brut[8:10])
    assert version == 1
    edition = brut[10:18].decode("ascii").strip()
    pos = 18
    resultat = []
    for taille in (4, 6):
        (n,) = struct.unpack(">I", brut[pos : pos + 4])
        pos += 4
        colonnes = []
        for _ in range(2):  # débuts, puis fins
            colonnes.append(
                [
                    int.from_bytes(brut[pos + i * taille : pos + (i + 1) * taille], "big")
                    for i in range(n)
                ]
            )
            pos += n * taille
        resultat.append(list(zip(*colonnes, strict=True)))
    assert pos == len(brut)
    return edition, resultat[0], resultat[1]


# ===== La liste d'ASN ======================================================
def test_lire_asn_ignore_commentaires_retraits_et_bruit(sources):
    asns = cth.lire_asn(sources[0])
    assert {100, 200, 13335, 36183, 20940, 54113, 714, 6185} == asns


def test_r8_exclusions_sont_exactement_celles_decidees():
    # R-8 : WARP, Akamai, Fastly et Apple. Retirer un numéro d'ici est une
    # décision à documenter, pas un détail.
    assert set(cth.ASN_EXCLUS) == {13335, 36183, 20940, 54113, 714, 6185}
    assert all(raison for raison in cth.ASN_EXCLUS.values())


def test_r8_aucun_reseau_exclu_n_entre_dans_la_table(sources):
    v4, v6 = cth.lire_plages(sources[1], cth.asn_retenus(sources[0]))
    for exclu in ("1.0.0.1", "2.16.1.1", "3.0.0.1", "4.0.0.1", "17.0.0.1", "18.0.0.1"):
        n = _ip4(exclu)
        assert not any(d <= n <= f for d, f in v4), exclu
    assert not any(d <= 0x2600 << 32 <= f for d, f in v6)


# ===== Les plages ==========================================================
def test_ipv4_fusionne_les_plages_collees_et_garde_les_trous(sources):
    v4, _ = cth.lire_plages(sources[1], {100, 200})
    assert v4 == [
        (_ip4("10.0.0.0"), _ip4("10.0.1.255")),
        (_ip4("10.0.9.0"), _ip4("10.0.9.255")),
    ]


def test_ipv6_tronque_au_48_et_ignore_un_48_a_moitie_couvert(sources):
    _, v6 = cth.lire_plages(sources[1], {100, 200})
    base = 0x2001_0DB8 << 16
    # /48 n°1 seul ; le /48 n°2 n'est couvert qu'à moitié : écarté ; n°3 et n°4
    # sont voisins et fusionnés.
    assert v6 == [(base + 1, base + 1), (base + 3, base + 4)]


def test_lignes_illisibles_sont_sautees(tmp_path):
    dbip = _ecrire_dbip(
        tmp_path / "x.csv.gz",
        lignes=[("10.0.0.0", "10.0.0.255", 100, "A")],
        extra='trop,court\n10.0.3.0,2001:db8::,100,"mixte"\nzzz,10.0.0.9,100,"B"\n10.0.2.0,10.0.2.255,pas-un-asn,"C"\n',
    )
    v4, v6 = cth.lire_plages(dbip, {100})
    assert v4 == [(_ip4("10.0.0.0"), _ip4("10.0.0.255"))]
    assert v6 == []


def test_fusionner_gere_le_chevauchement_et_l_absence():
    assert cth.fusionner([]) == []
    assert cth.fusionner([(5, 9), (1, 3), (2, 6), (11, 12)]) == [(1, 9), (11, 12)]


# ===== Les relais d'Apple ==================================================
def test_relais_apple_en_plages(tmp_path):
    csv = tmp_path / "egress.csv"
    csv.write_text(
        "10.0.0.0/25,GB,GB-EN,London,\n"
        "10.0.0.128/25,GB,GB-EN,London,\n"
        "2001:db8:1:5::/64,FR,FR-IDF,Paris,\n"
        "pas-un-reseau,FR,,,\n"
        "\n",
        encoding="utf-8",
    )
    v4, v6 = cth.lire_relais(csv)
    assert v4 == [(_ip4("10.0.0.0"), _ip4("10.0.0.255"))]
    assert v6 == [((0x2001_0DB8 << 16) + 1,) * 2]


def test_soustraire_coupe_et_efface():
    plages = [(0, 100), (200, 300)]
    assert cth.soustraire(plages, []) == plages
    assert cth.soustraire(plages, [(10, 20), (30, 40)]) == [
        (0, 9),
        (21, 29),
        (41, 100),
        (200, 300),
    ]
    assert cth.soustraire(plages, [(0, 100)]) == [(200, 300)]
    assert cth.soustraire(plages, [(50, 250)]) == [(0, 49), (251, 300)]
    assert cth.soustraire(plages, [(300, 400), (500, 600)]) == [(0, 100), (200, 299)]


def test_les_plages_d_apple_sont_ecartees_de_la_table(tmp_path):
    dbip = _ecrire_dbip(
        tmp_path / "x.csv.gz",
        lignes=[
            ("10.0.0.0", "10.0.0.255", 100, "A"),
            ("2001:db8:1::", "2001:db8:2:ffff:ffff:ffff:ffff:ffff", 100, "A"),
        ],
    )
    asn = tmp_path / "ASN.txt"
    asn.write_text("AS100 # A\n", encoding="utf-8")
    relais = tmp_path / "egress.csv"
    relais.write_text("10.0.0.64/26,GB,,,\n2001:db8:1::/48,FR,,,\n", encoding="utf-8")
    sortie = tmp_path / "t.bin.gz"

    assert (
        cth.main(
            [
                "--asn",
                str(asn),
                "--dbip",
                str(dbip),
                "--relais-apple",
                str(relais),
                "--edition",
                "2026-11",
                "--sortie",
                str(sortie),
            ]
        )
        == 0
    )
    _, v4, v6 = _decoder(gzip.decompress(sortie.read_bytes()))
    assert v4 == [
        (_ip4("10.0.0.0"), _ip4("10.0.0.63")),
        (_ip4("10.0.0.128"), _ip4("10.0.0.255")),
    ]
    assert v6 == [((0x2001_0DB8 << 16) + 2,) * 2]


# ===== Le fichier ==========================================================
def test_encoder_ecrit_le_format_recoheb1():
    v4 = [(1, 5), (10, 20)]
    v6 = [(7, 9)]
    edition, lu4, lu6 = _decoder(cth.encoder(v4, v6, "2026-11"))
    assert (edition, lu4, lu6) == ("2026-11", v4, v6)


def test_main_ecrit_une_table_reproductible(sources, tmp_path):
    argv = ["--asn", str(sources[0]), "--dbip", str(sources[1]), "--edition", "2026-11"]
    a, b = tmp_path / "a.bin.gz", tmp_path / "b.bin.gz"
    assert cth.main([*argv, "--sortie", str(a)]) == 0
    assert cth.main([*argv, "--sortie", str(b)]) == 0
    # mtime=0 : la même source donne les mêmes octets, git ne voit rien changer.
    assert a.read_bytes() == b.read_bytes()
    _, v4, v6 = _decoder(gzip.decompress(a.read_bytes()))
    assert len(v4) == 2
    assert len(v6) == 2


def test_main_refuse_une_source_sans_plage(tmp_path):
    asn = tmp_path / "ASN.txt"
    asn.write_text("AS13335 # Cloudflare\n", encoding="utf-8")
    dbip = _ecrire_dbip(tmp_path / "x.csv.gz")
    with pytest.raises(SystemExit):
        cth.main(["--asn", str(asn), "--dbip", str(dbip), "--sortie", str(tmp_path / "s")])
    assert not (tmp_path / "s").exists()


def test_edition_par_defaut_est_le_mois_courant():
    assert len(cth.edition_courante()) == 7
