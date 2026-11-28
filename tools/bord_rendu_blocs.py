"""bord_rendu_blocs.py — les blocs HTML de la page `/bord` du tableau de bord.

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026, vue
39 pouces par défaut (plan `pr-tableau-de-bord.md`, § 5 et § 6, relectures R10
et R22).

Rendu pur, sans disque ni réseau : chaque bloc reçoit les données déjà lues par
`bord_afaire`, `bord_chaine`, `bord_reseaux` et, pour les signalements,
`bord_distant` (tranche 2c), et rend du HTML.

L'ÉCHAPPEMENT (R10)
-------------------
La CSP du serveur admet les scripts en ligne, et rien n'est authentifié : tout
texte passe par `_texte` (échappé, coupé à `LONGUEUR` signes), une valeur mise
en attribut est échappée ou prise dans une liste fixe. Une adresse venue des données
n'entre dans un `href` qu'en `https://github.com/` (`_est_github`, la PR d'une ligne
d'« À faire d'abord ») ; l'autre lien, vers la relecture, est un chemin du serveur dont le
guid est encodé.

Une donnée absente s'affiche « inconnu », jamais « rien » ni « aucune » (F11).
"""
from __future__ import annotations

import html
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from bord_afaire import _libelle, signalements_en_attente
from bord_reseaux import LIBELLES, RESEAUX
from review_render_focus import short_title

#: Longueur maximale d'un texte venu des données (messages d'erreur, titres).
LONGUEUR = 160
#: Au-delà, la chaîne est « en retard » : le même seuil que le moniteur Kuma.
RETARD = timedelta(hours=2, minutes=30)

_JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
         "septembre", "octobre", "novembre", "décembre")
_BLOCS = {"relecture": "Relecture", "publication": "Publication", "reseaux": "Réseaux",
          "signalements": "Signalements", "liens": "Liens morts", "sorties": "Sorties"}
_ETATS = ("fait", "a_venir", "inconnu")


def _fuseau():
    """L'heure de Paris ; repli sur UTC sans `tzdata` (même choix que `date_sortie`)."""
    try:
        return ZoneInfo("Europe/Paris")
    except ZoneInfoNotFoundError:
        return UTC


def _texte(valeur: Any, n: int = LONGUEUR) -> str:
    """Un texte des données, coupé à `n` signes puis échappé."""
    s = "" if valeur is None else str(valeur)
    return html.escape(s if len(s) <= n else s[:n] + "…")


def _instant(iso: Any) -> datetime | None:
    """Un horodatage ISO ; sans fuseau, il est en UTC (télémétrie) ; None s'il est illisible."""
    try:
        t = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _heure(iso: Any, *, jour: bool = False) -> str | None:
    """« 10 h 04 », ou « dim. 10 h 04 » ; None si l'horodatage est illisible."""
    t = _instant(iso)
    if t is None:
        return None
    t = t.astimezone(_fuseau())
    debut = f"{_JOURS[t.weekday()][:3]}. " if jour else ""
    return f"{debut}{t.hour:02d} h {t.minute:02d}"


def date_du_jour(maintenant: datetime) -> str:
    """« dimanche 29 novembre »."""
    t = maintenant.astimezone(_fuseau())
    return f"{_JOURS[t.weekday()]} {t.day} {_MOIS[t.month - 1]}"


def _depuis(ecart: timedelta) -> str:
    minutes = int(ecart.total_seconds() // 60)
    if minutes < 1:
        return "à l'instant"
    if minutes < 60:
        return f"il y a {minutes} min"
    return f"il y a {minutes // 60} h {minutes % 60:02d}"


def _duree(debut: Any, fin: Any) -> str:
    a, b = _instant(debut), _instant(fin)
    if a is None or b is None:
        return "?"
    s = int((b - a).total_seconds())
    return f"{s} s" if s < 60 else f"{s // 60} min {s % 60:02d}"


def _noms(valeur: Any) -> list[str]:
    """Les noms d'étapes d'un passage ; une valeur qui n'est pas une liste n'en a aucun."""
    return [_texte(v, 40) for v in valeur] if isinstance(valeur, list) else []


def etat_entete(passages: list[dict] | None, maintenant: datetime,
                en_cours: str | None = None) -> tuple[str, str]:
    """`(état, texte)` de la pastille d'en-tête ; état : `ok`, `alerte` ou `inconnu`.

    `en_cours` est le début du passage qui tourne (fichier `en-cours` de `tick.sh`).
    Tour 1, F8 repris (28/11/2026) : `tick.sh` ne note un passage qu'à sa fin ; sans
    ce fichier, une longue transcription faisait crier au retard une chaîne qui tourne.
    Il ne compte que s'il est lisible et plus récent que la fin du dernier passage noté
    (sinon il est périmé) ; passé `RETARD`, le passage est dit bloqué.
    """
    debut = _instant(en_cours)
    dernier = passages[0] if passages else None
    fin = _instant(dernier.get("fin")) if dernier else None
    if dernier is None and debut is None:
        return "inconnu", "Chaîne : état inconnu" if passages is None else "Chaîne : aucun passage noté"
    if dernier is not None:
        if fin is None:
            return "inconnu", "Chaîne : état inconnu"
        quand = "passage " + _depuis(maintenant - fin)
        echecs = _noms(dernier.get("echecs"))
        if echecs:
            pluriel = "s" if len(echecs) > 1 else ""
            return "alerte", f"Chaîne : {len(echecs)} étape{pluriel} en échec · {quand}"
    if debut is not None and (fin is None or debut > fin):
        ecart = maintenant - debut
        depuis = _depuis(max(ecart, timedelta(minutes=1))).removeprefix("il y a ")
        if ecart > RETARD:
            return "alerte", f"Chaîne en retard · passage bloqué depuis {depuis}"
        return "ok", f"Chaîne : passage en cours depuis {depuis}"
    if maintenant - fin > RETARD:
        return "alerte", f"Chaîne en retard · {quand}"
    return "ok", f"Chaîne en marche · {quand}"


def _est_github(adresse: Any) -> bool:
    """Vrai pour `https://github.com/…` seulement (F21).

    Revue globale, S2 : une adresse « evil.com, barre oblique inverse, @github.com » se lit
    `github.com` pour `urlparse`, mais le navigateur ouvre evil.com. Toute adresse qui porte une
    barre oblique inverse ou un `@` est donc refusée, et `netloc`
    doit être exactement `github.com` (ni port, ni identifiants).
    """
    if not isinstance(adresse, str) or "\\" in adresse or "@" in adresse:
        return False
    try:
        u = urlparse(adresse)
    except ValueError:
        return False
    return u.scheme == "https" and u.netloc == "github.com"


def _carte(contenu: str, classe: str = "bord-carte") -> str:
    return f'<div class="{classe}">{contenu}</div>'


# ---- À faire d'abord -------------------------------------------------------

def bloc_afaire(items: list[dict]) -> tuple[str, int]:
    """La liste de `bord_afaire.a_faire` ; le compte exclut les lignes « inconnu »."""
    if not items:
        return '<p class="bord-vide">Rien à faire.</p>', 0
    lignes = []
    for item in items:
        bloc = str(item.get("bloc"))
        inconnu = " data-inconnu" if item.get("inconnu") else ""
        lien = ""
        if bloc == "relecture" and item.get("guid"):
            href = "/ep?guid=" + urllib.parse.quote(str(item["guid"]), safe="")
            lien = f'<a class="bord-bouton" href="{html.escape(href)}">Ouvrir la relecture</a>'
        elif _est_github(item.get("href")):  # une PR : jamais un autre hôte (F21)
            lien = (f'<a class="bord-bouton" href="{html.escape(item["href"])}" '
                    'rel="noreferrer">Ouvrir la PR</a>')
        lignes.append(
            f'<li class="bord-tache" data-bloc="{html.escape(bloc)}"{inconnu}>'
            f'<span class="bord-tache-bloc">{_texte(_BLOCS.get(bloc, bloc), 40)}</span>'
            f'<span class="bord-tache-texte">{_texte(item.get("texte"))}</span>{lien}</li>')
    nb = sum(1 for i in items if not i.get("inconnu"))
    return f'<ul class="bord-taches">{"".join(lignes)}</ul>', nb


# ---- Chaîne ---------------------------------------------------------------

def _etape(e: dict) -> str:
    etat = e.get("etat") if e.get("etat") in _ETATS else "inconnu"
    if etat == "fait":
        quand = _heure(e.get("heure"), jour=True) if e.get("heure") else None
        quand = quand or "fait"
    else:
        quand = "à venir" if etat == "a_venir" else "inconnu"
    return (f'<li class="bord-etape" data-etat="{etat}" '
            f'title="source : {_texte(e.get("source"), 40)}">'
            f'<span class="bord-etape-nom">{_texte(e.get("libelle"), 40)}</span>'
            f'<span class="bord-etape-quand">{html.escape(quand)}</span></li>')


def _passage(p: dict) -> str:
    lancees, echecs = _noms(p.get("lancees")), _noms(p.get("echecs"))
    texte = (_heure(p.get("debut")) or "?") + " · "
    texte += ("lancé : " + ", ".join(lancees)) if lancees else "rien de neuf"
    if echecs:
        texte += " · en échec : " + ", ".join(echecs)
    return (f'<li data-echec="{1 if echecs else 0}"><span>{texte}</span>'
            f'<span class="bord-mut">{_duree(p.get("debut"), p.get("fin"))}</span></li>')


def bloc_chaine(chaine: dict) -> str:
    """Le bloc de `bord_chaine.etat_chaine` : épisode, étapes, erreurs, passages."""
    episode = chaine.get("episode")
    etapes = chaine.get("etapes") or []
    if episode is None:
        tete = '<p class="bord-vide">Aucun épisode en cours.</p>'
    else:
        nom = short_title(episode.get("titre")) or episode.get("guid")
        tete = (f'<span class="bord-etiquette">L\'épisode de la semaine</span>'
                f'<h3 class="bord-episode">{_texte(nom)}</h3>'
                f'<ol class="bord-etapes">{"".join(_etape(e) for e in etapes)}</ol>')
    illisibles = chaine.get("fiches_illisibles")
    if isinstance(illisibles, int) and illisibles > 0:  # revue globale, D9 (F22)
        s = "s" if illisibles > 1 else ""
        tete += (f'<p class="bord-alerte" role="alert">{illisibles} fiche{s} d\'épisode '
                 f'illisible{s} : l\'épisode montré peut ne pas être le dernier.</p>')
    erreurs = chaine.get("erreurs") or []
    etat_lu = bool(chaine.get("etat_lu"))
    if erreurs:
        bas = ('<ul class="bord-erreurs">'
               + "".join(f"<li>{_texte(m)}</li>" for m in erreurs) + "</ul>")
    else:
        bas = (f'<p class="bord-mut">Erreurs en cours : '
               f'{"aucune" if etat_lu else "inconnu"}.</p>')
    passages = chaine.get("passages")
    if passages is None:
        liste = '<p class="bord-mut">Derniers passages : inconnu.</p>'
    elif not passages:
        liste = '<p class="bord-mut">Aucun passage noté.</p>'
    else:
        liste = f'<ul class="bord-passages">{"".join(_passage(p) for p in passages)}</ul>'
    return (_carte(tete)
            + _carte(f'<span class="bord-etiquette">Derniers passages</span>{liste}{bas}'))


# ---- Réseaux --------------------------------------------------------------

def _case(guid: str, nom: str, reseau: str, date: str | None) -> str:
    fait = date is not None
    quand = _instant(date) if fait else None
    titre = f' title="coché le {quand.astimezone(_fuseau()):%d/%m}"' if quand else ""
    action = "décocher" if fait else "marquer comme fait"
    # Tour 1, F5 : on coupe le nom, jamais l'action ; le script relit `data-nom`.
    nom_lu = _texte(f"{LIBELLES[reseau]}, {nom}", 60)
    libelle = f"{nom_lu} : {action}"
    return ('<form method="post" action="/bord/reseau" class="bord-case-form">'
            f'<input type="hidden" name="guid" value="{html.escape(guid)}">'
            f'<input type="hidden" name="reseau" value="{reseau}">'
            f'<input type="hidden" name="fait" value="{0 if fait else 1}">'
            f'<button type="submit" class="bord-case" data-fait="{1 if fait else 0}"'
            f'{titre} aria-label="{libelle}" data-nom="{nom_lu}">'
            f'{"✓" if fait else "À faire"}</button></form>')


def bloc_reseaux(recents: list[dict] | None,
                 coches: dict[str, dict[str, str]] | None) -> tuple[str, int | None]:
    """Les six cases des 3 derniers publiés ; le compte des cases à faire (None : inconnu)."""
    if recents is None:
        return '<p class="bord-mut">Épisodes publiés : inconnu.</p>', None
    if not recents:
        return '<p class="bord-vide">Aucun épisode publié.</p>', 0
    alerte = ""
    if coches is None:
        alerte = ('<p class="bord-alerte" role="alert">Le fichier des cases est illisible : '
                  "il n'est pas réécrit, et les cases sont refusées.</p>")
    noms = [str(_libelle(str(r["guid"]), r.get("episode"))) for r in recents]
    entete = "".join(f'<th scope="col">{_texte(n, 40)}</th>' for n in noms)
    lignes, nb = [], 0
    for reseau in RESEAUX:
        cellules = []
        for r, nom in zip(recents, noms, strict=True):
            if coches is None:
                cellules.append('<td class="bord-mut">inconnu</td>')
                continue
            date = coches.get(r["guid"], {}).get(reseau)
            nb += date is None
            cellules.append(f"<td>{_case(str(r['guid']), nom, reseau, date)}</td>")
        lignes.append(f'<tr><th scope="row">{LIBELLES[reseau]}</th>{"".join(cellules)}</tr>')
    table = (f'<table class="bord-reseaux"><thead><tr><th scope="col">Réseau</th>{entete}'
             f'</tr></thead><tbody>{"".join(lignes)}</tbody></table>')
    return alerte + _carte(table, "bord-carte bord-carte-table"), (None if coches is None else nb)


# ---- Signalements ---------------------------------------------------------

#: Les signalements montrés ; au-delà, « + N autres » (F23). L'API les trie du
#: plus récent au plus ancien : ce sont donc les derniers arrivés.
SIGNALEMENTS_MAX = 5
_CATEGORIES = {"error": "Erreur", "inappropriate": "Contenu inapproprié",
               "suggestion": "Suggestion", "broken-link": "Lien mort"}


def _signalement(s: dict) -> str:
    quand = _instant(s.get("date"))
    jour = f"{quand.astimezone(_fuseau()):%d/%m}" if quand else _texte(s.get("date"), 30)
    categorie = str(s.get("categorie"))
    return (f'<li><span>reco {_texte(s.get("recoId"), 60)}</span>'
            f'<span>{_texte(_CATEGORIES.get(categorie, categorie), 40)}</span>'
            f'<span class="bord-mut">{jour}</span></li>')


def bloc_signalements(audience: dict | None) -> str:
    """Les signalements en attente, lus avec l'audience (`bord_distant.lire()`).

    Tranche 2c (28/11/2026) : la reco, la catégorie et la date, jamais plus (F15 :
    le fichier d'un signalement porte le nom, l'adresse et le texte de la personne).
    Des données gardées après une panne restent, marquées par leur âge.
    """
    titre = '<span class="bord-etiquette">Signalements</span>'
    liste = signalements_en_attente(audience)
    if liste is None:
        return _carte(titre + '<p class="bord-mut">Signalements : inconnu.</p>')
    age = audience.get("age")
    perime = ""
    if audience.get("etat") != "ok" and isinstance(age, int):
        perime = (f'<p class="bord-mut">Liste des données d\'{_depuis(timedelta(seconds=age))}'
                  " : l'audience n'a pas pu être relue.</p>")
    if not liste:
        return _carte(titre + '<p class="bord-vide">Aucun signalement en attente.</p>' + perime)
    reste = len(liste) - SIGNALEMENTS_MAX
    autres = f'<p class="bord-mut">+ {reste} autres</p>' if reste > 0 else ""
    lignes = "".join(_signalement(s) for s in liste[:SIGNALEMENTS_MAX])
    return _carte(f'{titre}<ul class="bord-signalements">{lignes}</ul>{autres}{perime}')
