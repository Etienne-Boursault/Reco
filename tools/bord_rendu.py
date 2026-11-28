"""bord_rendu.py — la page `/bord`, le tableau de bord d'admin de Reco V1.

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026, vue
39 pouces par défaut (plan `pr-tableau-de-bord.md`, § 1 et § 5, relectures R13
et R22). « L'audience est vraiment le point central » : elle est la troisième
des cinq colonnes, au centre.

Rendu pur : la route (`review_routes_bord`, tranche 1e) lit les données et les
passe ici ; aucune lecture de disque, sauf le style et le script de la page.
L'audience (tranche 2c) arrive de même : la route appelle une seule fois
`bord_distant.lire()`, qui sert aussi à la ligne « signalements » d'À faire.

LA VUE
------
`<html data-vue="auto">` : sans script, ou sans `localStorage`, la mise en page
suit la largeur de l'écran (39 pouces, puis 13 pouces sous 2 200 px, puis
téléphone sous 900 px). Le petit script de `<head>` pose le réglage gardé
(`localStorage["bord-vue"]`, dans un `try`) avant l'affichage ; le choix des
vues reste `hidden` tant que le script de la page ne l'a pas révélé.

LE STYLE ET LE SCRIPT EN LIGNE
------------------------------
La CSP du serveur n'admet styles et scripts qu'en ligne (`'unsafe-inline'`,
sans `'self'`) : `review_bord.css` et `bord_client.js` sont donc lus à chaque
rendu et recopiés dans la page. Un fichier absent donne une page sans style ni
script, pas une erreur. La page n'inclut pas le script de la relecture : elle
n'envoie donc pas le battement `/activite` (le temps passé ici n'est pas du
temps de relecture).
"""
from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path

import bord_rendu_audience
import bord_rendu_blocs as blocs
from review_render_common import _flash_banner

_ICI = Path(__file__).parent
_CSS = _ICI / "review_bord.css"
_JS = _ICI / "bord_client.js"

#: Les vues du réglage, dans l'ordre du choix ; « auto » suit la largeur.
VUES = ("auto", "39", "13", "telephone")
_NOMS_VUES = {"auto": "auto", "39": "39\"", "13": "13\"", "telephone": "téléphone"}
#: Pose la vue gardée avant l'affichage ; une valeur hors de la liste est ignorée.
_SCRIPT_VUE = ('try{var v=localStorage.getItem("bord-vue");'
               'if(["39","13","telephone"].indexOf(v)>=0)'
               'document.documentElement.setAttribute("data-vue",v);}catch(e){}')
#: Le rechargement, pour l'écran de 39 pouces qui reste ouvert (§ 1) ; vers
#: `/bord` nu, pour ne pas réafficher le message d'un `?flash=` (tranche 1d-2).
_RECHARGE_S = 300


def _lire(chemin: Path) -> str:
    try:
        return chemin.read_text(encoding="utf-8")
    except OSError:
        return ""


def _nb(nb: int | None) -> str:
    """Le compteur d'une colonne ; rien quand il n'y a rien à faire ou qu'on ne sait pas."""
    return f'<span class="bord-nb">{nb}</span>' if nb else ""


def _colonne(cle: str, titre: str, contenu: str, nb: int | None = None) -> str:
    return (f'<section class="bord-col" id="bord-{cle}" data-col="{cle}" '
            f'aria-labelledby="bord-t-{cle}"><div class="bord-col-tete">'
            f'<h2 id="bord-t-{cle}">{titre}</h2>{_nb(nb)}</div>{contenu}</section>')


def _entete(titre: str, chaine: dict, maintenant: datetime) -> str:
    etat, texte = blocs.etat_entete(chaine.get("passages"), maintenant, chaine.get("en_cours"))
    vues = "".join(f'<button type="button" data-vue-choix="{v}">{html.escape(_NOMS_VUES[v])}'
                   "</button>" for v in VUES)
    return ('<header class="bord-entete"><div class="bord-marque">'
            f'<h1 class="bord-titre">{html.escape(titre)}</h1>'
            '<span class="bord-sous-titre">Tableau de bord</span></div>'
            '<div class="bord-infos">'
            f'<span class="bord-etat-chaine" data-etat="{etat}">'
            f'<span class="bord-pastille" aria-hidden="true"></span>'
            f'<span>{html.escape(texte)}</span></span>'
            f'<span class="bord-date">{blocs.date_du_jour(maintenant)}</span>'
            '<a class="bord-relecture" href="/">Relecture</a>'
            f'<div class="bord-vues" role="group" aria-label="Vue" hidden>{vues}</div>'
            '</div></header>')


def rendre_bord(*, titre: str, afaire: list[dict], chaine: dict,
                recents: list[dict] | None, coches: dict[str, dict[str, str]] | None,
                maintenant: datetime | None = None, flash: str | None = None,
                flash_kind: str = "info", audience: dict | None = None) -> str:
    """La page entière.

    - `titre` : le titre de la source ;
    - `afaire` : `bord_afaire.a_faire(...)` ;
    - `chaine` : `bord_chaine.etat_chaine(source_id)` ;
    - `recents` : `bord_reseaux.episodes_recents(...)` (None : état illisible) ;
    - `coches` : `bord_reseaux.lire()` (None : `EtatIllisible`) ;
    - `flash`, `flash_kind` : le message après une case cochée (redirection 303) ;
    - `audience` : `bord_distant.lire()`, qui ne lit que le cache (None : inconnu).
    """
    maintenant = maintenant or datetime.now(UTC)
    contenu_afaire, nb_afaire = blocs.bloc_afaire(afaire)
    contenu_reseaux, nb_reseaux = blocs.bloc_reseaux(recents, coches)
    colonnes = [
        ("afaire", "À faire d'abord", contenu_afaire, nb_afaire),
        ("chaine", "Chaîne", blocs.bloc_chaine(chaine), None),
        ("audience", "Audience", bord_rendu_audience.bloc_audience(audience), None),
        ("reseaux", "Réseaux", contenu_reseaux + blocs.bloc_attente("Sorties à venir")
         + blocs.bloc_signalements(audience), nb_reseaux),
        ("systeme", "Système", blocs.bloc_attente("Santé et versions")
         + blocs.bloc_attente("Coûts et modèles") + blocs.bloc_attente("Liens morts")
         + blocs.bloc_attente("Graphies apprises"), None),
    ]
    nav = "".join(f'<a href="#bord-{cle}">{titre_col}{" " + _nb(nb) if nb else ""}</a>'
                  for cle, titre_col, _, nb in colonnes)
    grille = "".join(_colonne(*c) for c in colonnes)
    return (
        '<!doctype html><html lang="fr" data-vue="auto"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="refresh" content="{_RECHARGE_S};url=/bord">'
        f"<title>Tableau de bord — {html.escape(titre)}</title>"
        f"<script>{_SCRIPT_VUE}</script><style>{_lire(_CSS)}</style></head>"
        f'<body class="bord">{_entete(titre, chaine, maintenant)}'
        f'{_flash_banner(flash, flash_kind)}'
        f'<nav class="bord-nav" aria-label="Sections">{nav}</nav>'
        f'<main class="bord-grille">{grille}</main>'
        f"<script>{_lire(_JS)}</script></body></html>")
