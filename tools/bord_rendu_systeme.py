"""bord_rendu_systeme.py — « Santé et versions » et « Coûts et modèles » de la page `/bord`.

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 5, § 6, § 9 et § 14, tranche 3d-1).

Rendu pur : il reçoit l'état de `bord_github.lire()` (le cache, jamais le réseau) et
celui de `bord_systeme.lire(source_id)`, tous deux en dictionnaires, et rend du HTML.
La route les lit une fois chacun ; `None` vaut « inconnu ».

CE QUE DIT « SANTÉ ET VERSIONS »
--------------------------------
- L'état du dernier essai auprès de GitHub et l'âge des données ; après une panne, les
  dernières données restent, marquées par leur âge (même conduite que l'audience).
- La CI de `main` et le dernier déploiement : conclusion, date (heure de Paris) et lien
  vers l'exécution. Un bloc absent est « inconnu », jamais « verte ».
- L'image du conteneur, « selon compose.yml » : le conteneur ne voit pas ce qui tourne.
- Les PR ouvertes (publication) vont dans « À faire d'abord » (3d-2) ; les PR fusionnées
  ne servent qu'à savoir si un épisode publié est fusionné : le plan ne les met pas ici.

CE QUE DIT « COÛTS ET MODÈLES »
-------------------------------
- Les 7 derniers jours et les 7 d'avant : coût par devise, nombre d'appels, détail par
  modèle (les 5 plus chers, le reste en « + N autres », F23). `known: None` : « inconnu »,
  jamais 0 $ ; des appels sans coût connu font un minimum (« au moins », R20, F12).
- Le modèle d'extraction (mesuré, ou « .env au démarrage ») et le modèle de secours.

LES LIENS (F21, R10)
--------------------
Une adresse n'entre dans un `href` que si c'est du `https` vers `github.com` ; sinon elle
s'affiche en texte échappé et coupé, sans lien. Tout texte venu des données est échappé.
"""
from __future__ import annotations

import html
from datetime import timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

import bord_distant
import bord_rendu_blocs as blocs
from bord_rendu_blocs import _carte, _depuis, _texte

#: Modèles montrés dans le détail d'une fenêtre ; au-delà, « + N autres » (F23).
MODELES_MAX = 5
#: GitHub : (clé de style, texte) de chaque conclusion connue ; le reste est « autre ».
_CONCLUSIONS = {"success": ("ok", "réussie"), "failure": ("echec", "échec"),
                "cancelled": ("annule", "annulée")}
_MESSAGES = {
    "inconnu": "GitHub : pas encore lu ; la première lecture est lancée, elle s'affiche "
               "au prochain rechargement.",
    "inconnu-sans-lancement": "GitHub : pas encore lu ; la lecture n'a pas pu être lancée.",
    "panne": "GitHub injoignable.",
    "limite": "GitHub : limite de débit atteinte.",
    "reponse-illisible": "Réponse illisible de GitHub.",
    "cache-illisible": "Le cache de GitHub est illisible et n'est pas réécrit : "
                       "effacer {chemin} pour relancer la lecture.",
}


def _dict(valeur: Any) -> dict:
    return valeur if isinstance(valeur, dict) else {}


def _jour(iso: Any) -> str | None:
    t = blocs._instant(iso)
    return f"{t.astimezone(blocs._fuseau()):%d/%m}" if t else None


def _quand(iso: Any) -> str:
    jour = _jour(iso)
    return f"{jour} {blocs._heure(iso)}" if jour else "date inconnue"


def _est_github(adresse: Any) -> bool:
    """Vrai pour `https://github.com/…` seulement (F21)."""
    try:
        u = urlparse(adresse) if isinstance(adresse, str) else None
        return u is not None and u.scheme == "https" and u.hostname == "github.com"
    except ValueError:
        return False


# ---- Santé et versions -------------------------------------------------------

def _etat(github: dict) -> str:
    etat = str(github.get("etat") or "inconnu")
    cle = "inconnu-sans-lancement" if etat == "inconnu" and not github.get("relance") else etat
    message = _MESSAGES.get(cle, f"GitHub : {_texte(github.get('libelle') or etat, 40)}.")
    if etat == "cache-illisible":
        message = message.format(chemin=html.escape(str(bord_distant._chemin())))
    detail = github.get("detail")
    if detail:
        message = f"{message.removesuffix('.')} ({_texte(detail, 40)})."
    age = github.get("age")
    if github.get("donnees") is not None and isinstance(age, int):
        quand = _depuis(timedelta(seconds=age))
        message = (f"À jour · lu {quand}." if etat == "ok"
                   else f"{message} Ce sont les données d'{quand}.")
    return (f'<p class="bord-audience-etat" data-etat="{html.escape(etat)}">'
            f'<span class="bord-pastille" aria-hidden="true"></span><span>{message}</span></p>')


def _course(nom: str, course: Any) -> str:
    """Une ligne de CI ou de déploiement ; une forme inattendue est « inconnu »."""
    if not isinstance(course, dict):
        return f'<li><span>{nom}</span><span class="bord-mut">inconnu</span></li>'
    conclusion = course.get("conclusion")
    cle, texte = _CONCLUSIONS.get(conclusion, (None, None)) if isinstance(conclusion, str) \
        else (None, None)
    if cle is None:
        cle = "autre"
        texte = f"autre : {_texte(conclusion, 40)}" if conclusion else "conclusion inconnue"
    adresse = course.get("adresse")
    if _est_github(adresse):
        lien = (f'<a href="{html.escape(adresse)}" rel="noreferrer" '
                f'aria-label="Détail : {nom}">détail</a>')
    else:
        lien = f'<span class="bord-mut">{_texte(adresse, 80)}</span>' if adresse else ""
    return (f'<li data-conclusion="{cle}"><span>{nom}</span><span>{texte}</span>'
            f'<span class="bord-mut">{_quand(course.get("date"))}</span>{lien}</li>')


def bloc_sante(github: dict | None, systeme: dict | None) -> str:
    """« Santé et versions », depuis `bord_github.lire()` et `bord_systeme.lire()` (None : inconnu)."""
    github = _dict(github)
    donnees = _dict(github.get("donnees"))
    image = _dict(systeme).get("image")
    version = (f"Image de la chaîne : {_texte(image, 80)} (selon compose.yml)" if image
               else "Image de la chaîne : inconnue")
    return _carte('<span class="bord-etiquette">Santé et versions</span>' + _etat(github)
                  + '<ul class="bord-signalements">'
                  + _course("CI de main", donnees.get("ci"))
                  + _course("Dernier déploiement", donnees.get("deploiement"))
                  + f'</ul><p class="bord-mut">{version}.</p>')


# ---- Coûts et modèles ------------------------------------------------------

def _decimal(valeur: Any) -> Decimal | None:
    try:
        d = Decimal(str(valeur))
    except ArithmeticError:
        return None
    return d if d.is_finite() else None


def _montant(devise: str, valeur: Any) -> str:
    d, nom = _decimal(valeur), _texte(devise, 10)
    if d is None:
        return f"{nom} ?"
    texte = (f"{d:.2f}" if d == 0 or abs(d) >= Decimal("0.01") else f"{d:.4f}").replace(".", ",")
    return f"{texte} $" if devise == "USD" else f"{texte} {nom}"


def _cout(cout: Any) -> str:
    """Un coût : « inconnu » sans coût connu, « au moins … » s'il manque des appels (R20)."""
    known = _dict(cout).get("known")
    if not isinstance(known, dict) or not known:
        return "inconnu"
    texte = " + ".join(_montant(d, v) for d, v in sorted(known.items()))
    n = cout.get("unknownCostCalls")
    if isinstance(n, int) and not isinstance(n, bool) and n > 0:
        return f"au moins {texte} ({n} appel{'s' if n > 1 else ''} sans coût connu)"
    return texte


def _ordre(nom: str, cout: Any) -> tuple:
    """Les plus chers d'abord, les coûts inconnus à la fin, puis l'ordre des noms."""
    known = _dict(_dict(cout).get("known"))
    montants = [d for d in map(_decimal, known.values()) if d is not None]
    return (not montants, -sum(montants, Decimal(0)), nom)


def _par_modele(par_modele: Any) -> str:
    if not isinstance(par_modele, dict) or not par_modele:
        return ""
    lignes = sorted(par_modele.items(), key=lambda kv: _ordre(*kv))
    corps = "".join(f'<li><span>{_texte(nom, 60)}</span>'
                    f'<span class="bord-mut">{_cout(cout)}</span></li>'
                    for nom, cout in lignes[:MODELES_MAX])
    reste = len(lignes) - MODELES_MAX
    autres = f'<p class="bord-mut">+ {reste} autres</p>' if reste > 0 else ""
    return f'<ul class="bord-signalements">{corps}</ul>{autres}'


def _fenetre(titre: str, fenetre: Any) -> str:
    appels = _dict(fenetre).get("appels")
    if not isinstance(appels, int) or isinstance(appels, bool):
        return f'<p class="bord-mut">{titre} : inconnu.</p>'
    cout = _cout(fenetre.get("cout"))
    if appels == 0 and cout == "inconnu":
        return f'<p class="bord-cout">{titre} : aucun appel.</p>'
    nb = f"{appels} appel{'s' if appels > 1 else ''}"
    return (f'<p class="bord-cout">{titre} : <strong>{cout}</strong> · {nb}</p>'
            + _par_modele(fenetre.get("par_modele")))


def _modele(nom: str, m: Any) -> str:
    """« Extraction : nom (mesuré le 27/11) » ; `nom` vide pour le secours : « aucun »."""
    if not isinstance(m, dict) or "nom" not in m or (m["nom"] is None and nom == "Extraction"):
        return f"{nom} : inconnu"
    if m["nom"] is None:
        return f"{nom} : aucun"
    source = m.get("source")
    if source == "mesure":
        jour = _jour(m.get("date"))
        precision = f" (mesuré le {jour})" if jour else " (mesuré, date inconnue)"
    else:
        precision = " (.env au démarrage)" if source == "env" else ""
    return f"{nom} : {_texte(m['nom'], 60)}{precision}"


def bloc_couts(systeme: dict | None) -> str:
    """« Coûts et modèles », depuis `bord_systeme.lire()` (None : inconnu)."""
    couts, modeles = _dict(_dict(systeme).get("couts")), _dict(_dict(systeme).get("modeles"))
    return (_carte('<span class="bord-etiquette">Coûts et modèles</span>'
                   + _fenetre("7 derniers jours", couts.get("semaine"))
                   + _fenetre("7 jours d'avant", couts.get("precedente")))
            + _carte('<span class="bord-etiquette">Modèles</span>'
                     f'<p>{_modele("Extraction", modeles.get("extraction"))}</p>'
                     f'<p>{_modele("Secours", modeles.get("secours"))}</p>'))
