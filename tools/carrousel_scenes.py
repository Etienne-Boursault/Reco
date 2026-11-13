"""
carrousel_scenes.py — le HTML des pages du carrousel, avec leurs visuels.

Modèle validé par Étienne le 2026-11-13 (« ça me va comme ça ») sur le
canevas Design « Carrousel avec visuels » : la moitié haute porte l'image,
posée sur un flou de ses propres couleurs ; la moitié basse le titre, le
créateur et la citation. Une mise en scène par cas (voir
`carrousel_images.mise_en_scene`) : affiche, carré, rond, deux images, photo
pleine largeur, tuile claire pour un logo, et un aplat jaune sans image.
Remplace les gabarits `tools/carrousel/*.dc.html`, qui n'avaient pas d'image.

La moitié basse n'a que la place qui reste sous l'image : un titre long et une
citation longue la feraient déborder, et « Reco de … » serait coupé sans
avertissement (revue de la PR #204). `ajuster` réduit donc la citation, puis
le titre, d'après une estimation de la hauteur du texte.
"""
from __future__ import annotations

import html
import math

ACCENT = "#ffd23f"
HEAD = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&amp;family=Inter:ital,wght@0,400;0,600;'
        '0,700;1,400&amp;display=swap" rel="stylesheet"><style>body{margin:0}</style>')
E = html.escape
BEBAS = "font-family: 'Bebas Neue', sans-serif"
OMBRE = "box-shadow: 0 24px 60px rgba(0,0,0,0.6)"
ETOILE = ('<path d="M12 4l2.2 4.9 5.3.5-4 3.6 1.2 5.2L12 15.9 7.3 18.7l1.2-5.2-4-3.6 5.3-.5z" '
          'fill="#0e0e10"></path>')
GUILLEMETS = ('<svg aria-hidden="true" width="64" height="48" viewBox="0 0 48 36"><path d="M0 36V22C0 9 6 2 18 '
              '0l2 5c-6 2-9 6-9 12h8v19zm28 0V22c0-13 6-20 18-22l2 5c-6 2-9 6-9 12h8v19z" '
              f'fill="{ACCENT}"></path></svg>')
MUSIQUE = {"Album", "Musique"}
#: Les mises en scène que `_scene` sait dessiner (et qu'`episode.json` peut forcer).
MISES = {"affiche", "carre", "rond", "double", "photo", "cadre", "tuile", "sans"}
#: Hauteur laissée au texte sous l'image (1 350 − 640 de scène − marges) quand elle diffère
#: des 606 px des autres mises en scène.
PLACE = {"photo": 690, "sans": 566}
CITATIONS = (42, 38, 34, 30)
#: Filet de sécurité : la police réelle peut être plus large que l'estimation. Une fois les
#: polices chargées, Edge réduit encore la citation (et une fois sur trois le titre) tant que
#: le bas de la page déborde.
AJUSTER_DANS_LE_NAVIGATEUR = (
    "<script>document.fonts.ready.then(() => {"
    "const bas = document.querySelector('[data-bas]'), titre = document.querySelector('[data-titre]'),"
    " citation = document.querySelector('[data-citation]');"
    "for (let i = 0; i < 24 && bas.scrollHeight > bas.clientHeight; i++) {"
    "const e = i % 3 === 2 ? titre : citation;"
    "e.style.fontSize = (parseFloat(getComputedStyle(e).fontSize) * 0.94) + 'px'; }});</script>")
TITRES = (150, 132, 116, 100, 88)


def _lignes(texte: str, par_ligne: int) -> tuple[int, int]:
    """Lignes d'un texte coupé aux mots, et longueur de la plus longue ligne."""
    lignes, courant, plus_longue = 1, 0, 0
    for mot in texte.split():
        if courant and courant + 1 + len(mot) > par_ligne:
            lignes, courant = lignes + 1, len(mot)
        else:
            courant += len(mot) + (1 if courant else 0)
        plus_longue = max(plus_longue, courant)
    return lignes, plus_longue


def _signes_titre(corps: int) -> int:
    return int(904 / (0.4 * corps))  # Bebas Neue : ~0,4 em par signe sur 904 px


def taille(titre: str) -> int:
    """Plus grande taille où le titre tient en deux lignes (une seule à 150 px)."""
    for corps in TITRES[:-1]:
        lignes, plus_longue = _lignes(titre, _signes_titre(corps))
        if lignes <= (1 if corps == 150 else 2) and plus_longue <= _signes_titre(corps):
            return corps
    return TITRES[-1]


def hauteur_du_texte(r: dict, titre: int, citation: int) -> float:
    """Estimation, en px, de la hauteur du titre, du créateur et du bloc de citation."""
    lignes_titre = _lignes(r["titre"], _signes_titre(titre))[0]
    lignes_citation = math.ceil(len(r["citation"]) * 1.1 / (900 / (0.5 * citation)))  # Inter italique ~0,5 em
    createur = 58 if r.get("createur") else 0
    return lignes_titre * titre * 0.88 + createur + 40 + 48 + 28 + lignes_citation * citation * 1.3 + 28 + 64


def place(mise: str) -> int:
    """Hauteur, en px, laissée au texte sous la scène."""
    return PLACE.get(mise, 606)


def trop_long(r: dict, mise: str) -> bool:
    """Le texte déborde-t-il même aux plus petites tailles ? (à signaler à l'éditeur)"""
    return hauteur_du_texte(r, TITRES[-1], CITATIONS[-1]) > place(mise)


def ajuster(r: dict, mise: str) -> tuple[int, int]:
    """Tailles du titre et de la citation qui tiennent dans la place : la citation baisse d'abord.
    Ce n'est qu'une estimation : le script de la page finit l'ajustement dans le navigateur."""
    titres = [t for t in TITRES if t <= taille(r["titre"])]
    for titre in titres:
        for citation in CITATIONS:
            if hauteur_du_texte(r, titre, citation) <= place(mise):
                return titre, citation
    return titres[-1], CITATIONS[-1]


def _flou(uri: str) -> str:
    return (f'<img src="{uri}" alt="" aria-hidden="true" style="position: absolute; left: -80px; top: -80px; '
            'width: 1240px; height: 860px; object-fit: cover; filter: blur(46px) brightness(0.45) saturate(1.3)">')


def _fondu(hauteur: int = 200) -> str:
    return (f'<div style="position: absolute; left: 0; bottom: 0; width: 1080px; height: {hauteur}px; '
            'background: linear-gradient(to bottom, rgba(14,14,16,0), #0e0e10)"></div>')


def _entete(type_: str, rang: int, total: int, *, pastille: bool = False, sur_jaune: bool = False) -> str:
    fond, texte = ("#0e0e10", ACCENT) if sur_jaune else (ACCENT, "#0e0e10")
    compteur = ("background: rgba(14,14,16,0.7); border-radius: 999px; padding: 8px 16px; color: #f6f4ee"
                if pastille else ("color: #0e0e10" if sur_jaune else "color: #c9c7c0"))
    return ('<div style="position: absolute; left: 88px; right: 88px; top: 88px; display: flex; '
            'align-items: center; justify-content: space-between">'
            f'<span style="font-size: 26px; font-weight: 700; color: {texte}; background: {fond}; '
            'border-radius: 999px; padding: 12px 26px; text-transform: uppercase; letter-spacing: 0.06em">'
            f'{E(type_)}</span><div style="font-size: 24px; font-weight: 600; {compteur}">{rang} / {total}</div></div>')


def _img(image: tuple[str, str], style: str) -> str:
    return f'<img src="{image[0]}" alt="{E(image[1])}" style="{style}">'


def _sans(type_: str, rang: int, total: int) -> str:
    if type_ in MUSIQUE:
        sillons = "".join(f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="#2a2a30" stroke-width="0.6">'
                          '</circle>' for r in (38, 30, 22))
        dessin = ('<svg aria-hidden="true" width="560" height="560" viewBox="0 0 100 100" style="position: '
                  'absolute; right: -90px; bottom: -120px"><circle cx="50" cy="50" r="48" fill="#0e0e10"></circle>'
                  f'{sillons}<circle cx="50" cy="50" r="14" fill="{ACCENT}"></circle>'
                  '<circle cx="50" cy="50" r="2.2" fill="#0e0e10"></circle></svg>')
    else:
        dessin = ('<svg aria-hidden="true" width="520" height="520" viewBox="0 0 24 24" style="position: '
                  f'absolute; right: -60px; bottom: -110px">{ETOILE}</svg>')
    return (f'<div style="position: relative; height: 640px; flex-shrink: 0; overflow: hidden; background: {ACCENT}">'
            + _entete(type_, rang, total, sur_jaune=True) + dessin + "</div>")


def _scene(mise: str, images: list[tuple[str, str]], type_: str, rang: int, total: int) -> str:
    if mise == "sans" or not images:
        return _sans(type_, rang, total)
    if mise == "photo":
        return ('<div style="position: relative; height: 640px; flex-shrink: 0; overflow: hidden">'
                + _img(images[0], "position: absolute; left: 0; top: 0; width: 1080px; height: 640px; "
                       "object-fit: cover")
                + _fondu(320) + _entete(type_, rang, total, pastille=True) + "</div>")
    if mise == "tuile":
        net = ('<div style="position: absolute; left: 88px; bottom: 60px; width: 360px; height: 360px; '
               'box-sizing: border-box; padding: 56px; background: #f6f4ee; border-radius: 40px; box-shadow: '
               '0 24px 60px rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center">'
               + _img(images[0], "width: 248px; height: 248px; object-fit: contain") + "</div>")
        return ('<div style="position: relative; height: 640px; flex-shrink: 0; overflow: hidden; '
                'background: #18181c">' + _fondu() + _entete(type_, rang, total) + net + "</div>")
    bas = "position: absolute; left: 88px; bottom: 36px; "
    if mise == "double":
        net = ('<div style="position: absolute; left: 88px; bottom: 36px; display: flex; gap: 32px">'
               + "".join(_img(i, f"width: 400px; height: 400px; object-fit: cover; border-radius: 14px; {OMBRE}")
                         for i in images[:2]) + "</div>")
    else:
        cadres = {"affiche": "height: 460px; width: 307px; border-radius: 14px",
                  "rond": f"width: 420px; height: 420px; border-radius: 50%; border: 8px solid {ACCENT}",
                  "cadre": "width: 660px; height: 440px; border-radius: 14px"}
        net = _img(images[0], f"{bas}{cadres.get(mise, 'width: 440px; height: 440px; border-radius: 14px')}; "
                              f"object-fit: cover; {OMBRE}")
    return ('<div style="position: relative; height: 640px; flex-shrink: 0; overflow: hidden">'
            + _flou(images[0][0]) + _fondu() + _entete(type_, rang, total) + net + "</div>")


def page_reco(r: dict, rang: int, total: int, images: list[tuple[str, str]], mise: str) -> str:
    """Une page de reco : `images` = [(adresse, texte alternatif)], `mise` = sa mise en scène."""
    titre, citation = ajuster(r, mise if images else "sans")
    marge = {"photo": "padding: 0 88px 80px; margin-top: -60px; position: relative",
             "sans": "padding: 64px 88px 80px"}.get(mise if images else "sans", "padding: 24px 88px 80px")
    createur = f'<div style="font-size: 36px; color: #c9c7c0">{E(r["createur"])}</div>' if r.get("createur") else ""
    qui = (f'<span>Reco de <strong>{E(r["qui"])}</strong></span><span aria-hidden="true" style="color: #6f6e78">·'
           f'</span><span style="color: #c9c7c0">à {E(r["moment"])}</span>' if r.get("qui")
           else f'<span style="color: #c9c7c0">À {E(r["moment"])}</span>')
    return ('<div style="position: relative; width: 1080px; height: 1350px; overflow: hidden; background: #0e0e10; '
            "color: #f6f4ee; font-family: 'Inter', system-ui, sans-serif; display: flex; flex-direction: column\">"
            + _scene(mise, images, r["type"], rang, total)
            + f'<div data-bas style="flex: 1; min-height: 0; overflow: hidden; box-sizing: border-box; {marge}; '
            'display: flex; flex-direction: column; justify-content: space-between; gap: 40px">'
            '<div style="display: flex; flex-direction: column; gap: 14px">'
            f'<h2 data-titre style="margin: 0; {BEBAS}; font-weight: 400; font-size: {titre}px; line-height: 0.88; '
            f'letter-spacing: -0.005em; overflow-wrap: anywhere">{E(r["titre"])}</h2>{createur}</div>'
            f'<div style="display: flex; flex-direction: column; gap: 28px">{GUILLEMETS}'
            f'<p data-citation style="margin: 0; font-size: {citation}px; line-height: 1.3; font-style: italic; '
            'max-width: 900px; overflow-wrap: anywhere">'
            f'{E(r["citation"])}</p><div style="display: flex; align-items: center; gap: 16px; font-size: 28px; '
            f'border-top: 2px solid #2a2a30; padding-top: 28px">{qui}</div></div></div></div>'
            + AJUSTER_DANS_LE_NAVIGATEUR)


def couverture(ep: dict, total: int, vignette: str | None) -> str:
    """Couverture : la vignette de l'épisode fondue dans le noir, le nombre de recos par-dessus."""
    photo = (f'<img src="{vignette}" alt="Vignette de l’épisode" style="position: absolute; left: 0; top: 0; '
             'width: 1080px; height: 780px; object-fit: cover"><div style="position: absolute; left: 0; top: 430px; '
             'width: 1080px; height: 360px; background: linear-gradient(to bottom, rgba(14,14,16,0), #0e0e10)">'
             '</div>') if vignette else ""
    invites = "".join('<span style="font-size: 30px; font-weight: 600; border: 2px solid #3a3a40; border-radius: '
                      f'999px; padding: 10px 24px">{E(n)}</span>' for n in ep["invites"])
    return ('<div style="position: relative; width: 1080px; height: 1350px; overflow: hidden; background: #0e0e10; '
            f"color: #f6f4ee; font-family: 'Inter', system-ui, sans-serif\">{photo}"
            '<div style="position: absolute; left: 72px; right: 72px; top: 72px; display: flex; align-items: center; '
            'justify-content: space-between"><div style="display: flex; align-items: center; gap: 16px; background: '
            'rgba(14,14,16,0.82); border-radius: 18px; padding: 12px 22px 12px 12px">'
            f'<div style="width: 54px; height: 54px; border-radius: 13px; background: {ACCENT}; display: flex; '
            'align-items: center; justify-content: center"><svg aria-hidden="true" width="32" height="32" '
            f'viewBox="0 0 24 24">{ETOILE}</svg></div><div style="{BEBAS}; font-size: 36px; letter-spacing: 0.04em; '
            f'line-height: 1">Les recos de l’épisode</div></div><div style="{BEBAS}; font-size: 40px; letter-spacing: '
            f'0.04em; line-height: 1; color: #0e0e10; background: {ACCENT}; border-radius: 12px; padding: 10px 18px '
            f'6px">{E(ep["numero"])}</div></div><div style="position: absolute; left: 88px; right: 88px; bottom: 80px; '
            f'display: flex; flex-direction: column; gap: 30px"><div style="{BEBAS}; font-size: 230px; line-height: '
            f'0.8; color: {ACCENT}">{total}<span style="font-size: 96px; color: #f6f4ee"> recos</span></div>'
            '<h1 style="margin: 0; font-size: 54px; font-weight: 700; line-height: 1.1; letter-spacing: -0.01em; '
            f'max-width: 900px">{E(ep["titre"])}</h1><div style="display: flex; flex-wrap: wrap; gap: 14px; '
            f'align-items: center"><span style="font-size: 28px; color: #c9c7c0">Avec</span>{invites}</div>'
            '<div style="display: flex; align-items: center; justify-content: space-between; border-top: 2px solid '
            '#2a2a30; padding-top: 32px"><div style="font-size: 26px; color: #c9c7c0">Un Bon Moment · avec Kyan '
            'Khojandi et Navo</div><div style="display: flex; align-items: center; gap: 14px; font-size: 28px; '
            'font-weight: 700">Glisse<svg aria-hidden="true" width="40" height="40" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path '
            'd="M5 12h14"></path><path d="M13 6l6 6-6 6"></path></svg></div></div></div></div>')


def fin(ep: dict, total: int, credits: str) -> str:
    """Page de fin, avec la ligne qui nomme les sources des images."""
    sources = (f'<div style="font-size: 20px; text-align: center; color: #3a3520">{E(credits)}</div>'
               if credits else "")
    return (f'<div style="width: 1080px; height: 1350px; box-sizing: border-box; padding: 88px 88px 72px; '
            f"background: {ACCENT}; color: #0e0e10; font-family: 'Inter', system-ui, sans-serif; display: flex; "
            'flex-direction: column; justify-content: space-between"><div style="display: flex; align-items: center; '
            'justify-content: space-between"><svg aria-hidden="true" width="80" height="80" viewBox="0 0 24 24">'
            f'{ETOILE}</svg><div style="{BEBAS}; font-size: 40px; letter-spacing: 0.04em; line-height: 1; color: '
            f'{ACCENT}; background: #0e0e10; border-radius: 12px; padding: 10px 18px 6px">{E(ep["numero"])}</div>'
            '</div><div style="display: flex; flex-direction: column; gap: 40px"><h2 style="margin: 0; '
            f'{BEBAS}; font-weight: 400; font-size: 168px; line-height: 0.88; letter-spacing: -0.005em">Les {total} '
            'recos<br>de l’épisode</h2><p style="margin: 0; font-size: 40px; line-height: 1.3; max-width: 860px">'
            'Avec le moment exact où elles sont citées, et des liens pour les écouter, les voir ou les lire.</p></div>'
            '<div style="display: flex; flex-direction: column; gap: 18px"><div style="background: #0e0e10; color: '
            f'{ACCENT}; border-radius: 999px; padding: 26px 44px; display: flex; align-items: center; '
            f'justify-content: space-between"><span style="{BEBAS}; font-size: 72px; line-height: 1; letter-spacing: '
            '0.03em">unebonnere.co</span><span style="font-size: 30px; font-weight: 700; color: #f6f4ee">Lien en bio'
            '</span></div><div style="font-size: 24px; text-align: center">Site de fan, non officiel · Un Bon Moment, '
            f'avec Kyan Khojandi et Navo</div>{sources}</div></div>')
