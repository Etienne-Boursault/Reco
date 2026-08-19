"""
recuperer_favicons.py — remplacer les lettres par les vrais logos.

CE QUE LA RELECTURE A VU
------------------------
« L'icone de Molotov TV n'est pas la bonne, utilise la FAVicon » (2026-08-19).
Elle affichait un « m » blanc sur fond violet, en Arial. En verifiant, trente-
huit des soixante-cinq icones etaient dans ce cas : une lettre dans une police
systeme, posee faute de logo — « A » pour AlloCine, « F » pour la Fnac, « + »
pour Canal+.

Ces caracteres de remplacement disent au visiteur qu'il manque quelque chose.
Une favicon officielle, meme modeste, dit de quelle plateforme il s'agit.

AUCUNE REQUETE VERS UN TIERS
----------------------------
L'image est telechargee UNE FOIS, ici, et integree au SVG en data URI. Le site
n'appelle jamais le serveur de la plateforme : une favicon distante fuiterait
l'adresse IP et le referent de chaque visiteur (ADR 0034).

POURQUOI `curl` ET PAS `urllib`
-------------------------------
Huit hotes sur trente-huit refusaient urllib et repondaient a curl : blocage
sur l'en-tete, negociation TLS, redirection. Le sondage initial les donnait
pour morts alors que leur favicon existait.

AJOUTER, PAS SEULEMENT REMPLACER
--------------------------------
Un hote nomme en `--host` qui n'a pas encore de fichier est cree. Sans cela
l'outil ne savait que corriger des lettres, et les plateformes jamais
dessinees restaient sans icone : `www.imdb.com` apparaissait dans 353 liens
du corpus et n'en avait aucune.

CE QUI EST REFUSE
-----------------
Une image plus petite que 16 px, un fichier qui n'est pas une image — certains
hotes servent du HTML sur `/favicon.ico` —, et une image d'une seule couleur :
c'est le carre vide que renvoient les serveurs qui n'en ont pas.
"""
from __future__ import annotations

import argparse
import base64
import io
import logging
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))

log = logging.getLogger("favicons")

DOSSIER = Path(__file__).resolve().parent.parent / "public" / "icons" / "platforms"
#: Un en-tete de navigateur ordinaire. Le premier essai annoncait l'outil par
#: politesse — « RecoIcones/1.0 » — et six hotes le rejetaient : Canal+
#: repondait une erreur JSON, la Fnac une page HTML, NHK rien du tout. Le meme
#: appel avec cet en-tete les servait sans broncher. On telecharge une image
#: par plateforme, une seule fois : ce n'est pas de la collecte massive.
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

#: Au-dela, l'icone pese pour rien : elle est affichee entre 16 et 24 px.
TAILLE_CIBLE = 64
#: En deca, ce n'est pas un logo mais un artefact.
TAILLE_MINIMALE = 16


def est_placeholder(svg: str) -> bool:
    """Un SVG qui dessine une LETTRE plutot qu'un logo."""
    return "<text" in svg


def telecharger(url: str, *, timeout: int = 15) -> bytes | None:
    """Le contenu d'une URL, ou `None`. Passe par curl — voir l'en-tete."""
    try:
        fait = subprocess.run(
            ["curl", "-sL", "--max-time", str(timeout), "-A", UA, url],
            capture_output=True, timeout=timeout + 5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return fait.stdout or None


def pistes_favicon(host: str) -> list[str]:
    """Les URL a essayer, de la plus declaree a la plus conventionnelle."""
    trouvees: list[str] = []
    page = telecharger(f"https://{host}/")
    if page:
        html = page[:200_000].decode("utf-8", "ignore")
        for balise in re.finditer(r'<link[^>]+rel="[^"]*icon[^"]*"[^>]*>', html, re.IGNORECASE):
            href = re.search(r'href="([^"]+)"', balise.group(0))
            if href:
                trouvees.append(urljoin(f"https://{host}/", href.group(1)))
    trouvees.append(f"https://{host}/favicon.ico")
    # Dedoublonne en gardant l'ordre : le premier declare est le plus soigne.
    vues: dict[str, None] = {}
    for u in trouvees:
        vues.setdefault(u, None)
    return list(vues)


def en_png(brut: bytes) -> tuple[bytes, str] | None:
    """Convertit une image en PNG carre. `None` si elle n'est pas exploitable."""
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(brut))
        img.load()
    except Exception:  # noqa: BLE001 — Pillow leve tout et n'importe quoi sur
        # une entree corrompue (UnidentifiedImageError, OSError, SyntaxError,
        # struct.error selon le format). Enumerer serait une liste a trous : on
        # traite ici du contenu ARBITRAIRE renvoye par un serveur tiers, dont
        # certains servent du HTML sur `/favicon.ico`.
        return None
    if min(img.size) < TAILLE_MINIMALE:
        return None
    img = img.convert("RGBA")
    # Une image d'une seule couleur est le carre vide des serveurs sans icone.
    #
    # `getcolors(maxcolors=N)` rend `None` quand l'image en compte PLUS que N
    # — donc `None` signifie « riche », pas « vide ». La premiere version
    # lisait l'inverse et rejetait toutes les vraies icones.
    couleurs = img.getcolors(maxcolors=2)
    if couleurs is not None and len(couleurs) <= 1:
        return None
    # On n'agrandit jamais au-dela du double : au-dela c'est du flou.
    cible = min(TAILLE_CIBLE, max(TAILLE_MINIMALE * 2, min(img.size) * 2))
    img = img.resize((cible, cible), Image.LANCZOS)
    tampon = io.BytesIO()
    img.save(tampon, format="PNG", optimize=True)
    return tampon.getvalue(), f"{cible}x{cible}"


def svg_de_png(png: bytes, host: str, source: str) -> str:
    """Enveloppe le PNG dans un SVG carre, en data URI."""
    b64 = base64.b64encode(png).decode()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" '
        'height="24" role="img">'
        f'<!-- Favicon officielle de {host}, integree en data URI : le depot\n'
        f'     n\'appelle aucune ressource tierce, une favicon distante\n'
        f'     fuiterait l\'adresse IP du visiteur vers la plateforme.\n'
        f'     Source : {source} -->'
        f'<image href="data:image/png;base64,{b64}" width="24" height="24"/>'
        '</svg>'
    )


def executer(dossier: Path | None = None, *, apply: bool,
             seulement: Sequence[str] = ()) -> dict[str, object]:
    """Remplace les placeholders par les favicons trouvees.

    Un hote passe dans `seulement` mais qui n'a pas encore de fichier est
    CREE : c'est le geste qui etend la couverture. Il reste explicite — la
    passe ordinaire ne devine jamais d'elle-meme quelles plateformes meritent
    une icone.

    Le dossier est resolu A L'APPEL et non dans la signature : une valeur par
    defaut serait figee a l'import, et un test qui redefinit `DOSSIER`
    ecrirait dans le vrai `public/icons/platforms/`. Le depot s'est deja fait
    prendre a ce piege (cf. `match_audit`, 2026-08-18).
    """
    dossier = dossier if dossier is not None else DOSSIER
    rapport: dict[str, object] = {"remplaces": 0, "ajoutes": 0, "echecs": []}
    a_faire: list[str] = []
    for chemin in sorted(dossier.glob("*.svg")):
        host = chemin.stem
        if seulement and host not in seulement:
            continue
        if est_placeholder(chemin.read_text(encoding="utf-8")):
            a_faire.append(host)
    # Un hote demande explicitement mais sans fichier est un AJOUT. Sans cette
    # branche l'outil ne savait que remplacer une lettre par un logo, et les
    # plateformes jamais dessinees restaient invisibles : `www.imdb.com`
    # apparait dans 353 liens et n'avait aucune icone.
    nouveaux = {h for h in seulement if not (dossier / f"{h}.svg").exists()}
    a_faire += sorted(nouveaux)

    for host in a_faire:
        chemin = dossier / f"{host}.svg"
        for url in pistes_favicon(host):
            brut = telecharger(url)
            if not brut:
                continue
            converti = en_png(brut)
            if converti is None:
                continue
            png, taille = converti
            log.info("%-34s %s  (%s, %d octets)", host, taille, url[:60], len(png))
            cle = "ajoutes" if host in nouveaux else "remplaces"
            rapport[cle] += 1  # type: ignore[operator]
            if apply:
                chemin.write_text(svg_de_png(png, host, url), encoding="utf-8")
            break
        else:
            rapport["echecs"].append(host)  # type: ignore[union-attr]
    return rapport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remplace les icones de plateforme dessinees avec une "
                    "lettre par la favicon officielle du site.")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    parser.add_argument("--host", action="append", default=[],
                        help="limiter a cet hote, ou en AJOUTER un qui n'a pas "
                             "encore d'icone (repetable)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rapport = executer(apply=args.apply, seulement=args.host)
    log.info("%d icone(s) remplacee(s), %d ajoutee(s)",
             rapport["remplaces"], rapport["ajoutes"])
    for host in rapport["echecs"]:  # type: ignore[union-attr]
        log.warning("SANS FAVICON %s — la lettre reste", host)
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
