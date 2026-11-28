"""bord_rendu_systeme.py — les blocs « Système » et « Sorties à venir » de la page `/bord`.

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 5, § 6, § 9 et § 14, tranches 3d-1 et 3d-2).

Rendu pur : il reçoit l'état de `bord_github.lire()` (le cache, jamais le réseau) et
celui de `bord_systeme.lire(source_id)`, tous deux en dictionnaires, et rend du HTML.
La route les lit une fois chacun ; `None` vaut « inconnu ».

CE QUE DIT « SANTÉ ET VERSIONS »
--------------------------------
- L'état du dernier essai auprès de GitHub et l'âge des données ; après une panne, les
  dernières données restent, marquées par leur âge (même conduite que l'audience). Tour 1, F9 :
  au-delà de 2 fois `bord_distant.FRAICHEUR`, un essai réussi dit « Périmé », pas « À jour ».
- Tour 1, lot A : `pannes` dit « inconnu (panne : <type>) » pour la CI et le déploiement ;
  `jeton: "refuse"` donne « Jeton GitHub refusé : lecture anonyme ». Les anciens caches n'ont
  ni l'un ni l'autre : tout se lit avec `.get`. Les pannes des PR vont dans « À faire d'abord »,
  qui dit « inconnu » sans en donner la cause (le plus simple).
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

CE QUE DISENT « SORTIES À VENIR », « GRAPHIES APPRISES » ET « LIENS MORTS » (3d-2)
-------------------------------------------------------------------------------
Ils viennent de `bord_contenu.lire(source_id)` ; une partie `None` s'affiche « inconnu »,
jamais « aucun » (F22). Chaque liste coupée dit « + N autres » (F23). Les liens morts disent
la date du rapport, son âge, et « ancien » au-delà de 8 jours.

LES LIENS (F21, R10)
--------------------
Une adresse n'entre dans un `href` que si c'est du `https` vers `github.com` (GitHub), ou
si elle commence par `http://` ou `https://` (liens morts) ; sinon elle s'affiche en texte
échappé et coupé, sans lien. Tout texte venu des données est échappé.
"""
from __future__ import annotations

import html
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import bord_distant
import bord_rendu_blocs as blocs
from bord_rendu_blocs import _carte, _depuis, _est_github, _texte

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
        perime = bord_distant.donnees_perimees(github)
        message = (f"{'Périmé' if perime else 'À jour'} · lu {quand}." if etat == "ok"
                   else f"{message} Ce sont les données d'{quand}.")
    return (f'<p class="bord-audience-etat" data-etat="{html.escape(etat)}">'
            f'<span class="bord-pastille" aria-hidden="true"></span><span>{message}</span></p>')


def _course(nom: str, course: Any, panne: Any = None, *, masculin: bool = False) -> str:
    """Une ligne de CI ou de déploiement ; une forme inattendue est « inconnu » (avec sa panne, si connue).

    `masculin` : le déploiement est « réussi » et « annulé », la CI « réussie » et « annulée » (revue
    globale, accord).
    """
    if not isinstance(course, dict):
        cause = ""
        if isinstance(panne, dict) and (panne.get("detail") or panne.get("etat")):
            cause = f" (panne : {_texte(panne.get('detail') or panne.get('etat'), 40)})"
        return f'<li><span>{nom}</span><span class="bord-mut">inconnu{cause}</span></li>'
    conclusion = course.get("conclusion")
    cle, texte = _CONCLUSIONS.get(conclusion, (None, None)) if isinstance(conclusion, str) \
        else (None, None)
    if cle is not None and masculin:
        texte = texte.removesuffix("e")
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
    pannes = _dict(donnees.get("pannes"))
    jeton = ('<p class="bord-mut">Jeton GitHub refusé : lecture anonyme.</p>'
             if donnees.get("jeton") == "refuse" else "")
    version = (f"Image de la chaîne : {_texte(image, 80)} (selon compose.yml)" if image
               else "Image de la chaîne : inconnue")
    return _carte('<span class="bord-etiquette">Santé et versions</span>' + _etat(github)
                  + '<ul class="bord-signalements">'
                  + _course("CI de main", donnees.get("ci"), pannes.get("ci"))
                  + _course("Dernier déploiement", donnees.get("deploiement"),
                            pannes.get("deploiement"), masculin=True)
                  + f'</ul>{jeton}<p class="bord-mut">{version}.</p>')


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


# ---- Sorties à venir, graphies apprises, liens morts (3d-2) -------------------

def _partie(contenu: Any, nom: str) -> dict | None:
    """Une partie de `bord_contenu.lire()`, ou None (inconnu) : absente ou de forme fausse."""
    partie = _dict(contenu).get(nom)
    return partie if isinstance(partie, dict) else None


def _entier(valeur: Any) -> bool:
    return isinstance(valeur, int) and not isinstance(valeur, bool)


def _inconnu(titre: str) -> str:
    return _carte(f'<span class="bord-etiquette">{titre}</span>'
                  f'<p class="bord-mut">{titre} : inconnu.</p>')


def _jj_mm(iso: Any) -> str:
    try:
        return f"{date.fromisoformat(iso):%d/%m}"
    except (TypeError, ValueError):
        return _texte(iso, 30)


def _autres(reste: int) -> str:
    return f'<p class="bord-mut">+ {reste} autres</p>' if reste > 0 else ""


def _nombre(n: int, singulier: str, pluriel: str) -> str:
    return f"{n} {singulier if n <= 1 else pluriel}"


def _echeance(jours: Any, relancee: Any = None) -> str:
    """Tour 1, F7 : « en relance » n'est dit que si le registre le dit (`relancee` : True, False, None)."""
    if not _entier(jours):
        return "jours inconnus"
    if jours <= 0:
        suite = ("en relance" if relancee is True else "pas de relance" if relancee is False
                 else "relance : inconnu")
        return f"déjà sortie, {suite}"
    return "demain" if jours == 1 else f"dans {jours} jours"


def _note(n: Any, singulier: str, pluriel: str) -> str:
    """Une ligne de remarque (« 2 fichiers … ») quand `n` est un entier positif."""
    return (f'<p class="bord-mut">{_nombre(n, singulier, pluriel)}.</p>'
            if _entier(n) and n > 0 else "")


def bloc_sorties(contenu: dict | None) -> str:
    """« Sorties à venir » : titre, date et jours restants ; `contenu` = `bord_contenu.lire()`."""
    titre = "Sorties à venir"
    sorties = _partie(contenu, "sorties")
    liste = sorties.get("liste") if sorties else None
    total = sorties.get("total") if sorties else None
    if not isinstance(liste, list) or not _entier(total):
        return _inconnu(titre)
    lignes = "".join(
        f'<li><span>{_texte(_dict(s).get("titre"))}</span><span class="bord-mut">'
        f'{_jj_mm(_dict(s).get("date"))} · {_echeance(_dict(s).get("jours"), _dict(s).get("relancee"))}</span></li>'
        for s in liste)
    corps = (f'<ul class="bord-signalements">{lignes}</ul>' if liste
             else '<p class="bord-vide">Aucune sortie dans les 30 jours.</p>')
    note = _note(sorties.get("illisibles"), "fichier de recos illisible",
                 "fichiers de recos illisibles")
    return _carte(f'<span class="bord-etiquette">{titre}</span>{corps}'
                  f'{_autres(total - len(liste))}{note}')


def bloc_graphies(contenu: dict | None) -> str:
    """« Graphies apprises » : les plus vues et le total ; `contenu` = `bord_contenu.lire()`."""
    titre = "Graphies apprises"
    graphies = _partie(contenu, "graphies")
    plus = graphies.get("plus_vues") if graphies else None
    total = graphies.get("total") if graphies else None
    if not isinstance(plus, list) or not _entier(total):
        return _inconnu(titre)
    if total == 0:
        corps = '<p class="bord-vide">Aucune graphie apprise.</p>'
    else:
        lignes = "".join(
            f'<li><span>{_texte(_dict(g).get("fausse"), 60)} → {_texte(_dict(g).get("juste"), 60)}'
            f'</span><span class="bord-mut">vu {_texte(_dict(g).get("vu"), 10)} fois'
            "</span></li>" for g in plus)
        corps = (f'<p class="bord-cout"><strong>'
                 f'{_nombre(total, "graphie apprise", "graphies apprises")}</strong></p>'
                 f'<ul class="bord-signalements">{lignes}</ul>{_autres(total - len(plus))}')
    note = _note(graphies.get("ecartees"), "entrée mal formée ignorée",
                 "entrées mal formées ignorées")
    return _carte(f'<span class="bord-etiquette">{titre}</span>{corps}{note}')


def _est_http(adresse: Any) -> bool:
    """Vrai si l'adresse commence par `http://` ou `https://` (F21) : jamais `javascript:`."""
    return isinstance(adresse, str) and adresse.startswith(("http://", "https://"))


def _lien_mort(lien: Any) -> str:
    lien = _dict(lien)
    url = lien.get("url")
    texte = _texte(url, 80)
    cible = (f'<a href="{html.escape(url)}" rel="noreferrer">{texte}</a>'
             if _est_http(url) else texte)
    recos = lien.get("recos")
    n = f" · {_nombre(len(recos), 'reco', 'recos')}" if isinstance(recos, list) else ""
    return (f'<li><span>{cible}</span>'
            f'<span class="bord-mut">{_texte(lien.get("reponse"), 60)}{n}</span></li>')


def _age(age: Any) -> str:
    if not _entier(age) or age < 0:
        return ""
    return " · aujourd'hui" if age == 0 else f" · il y a {_nombre(age, 'jour', 'jours')}"


def bloc_liens(contenu: dict | None) -> str:
    """« Liens morts » du dernier rapport du lundi ; `contenu` = `bord_contenu.lire()`."""
    titre = "Liens morts"
    liens = _partie(contenu, "liens")
    liste = liens.get("liste") if liens else None
    morts = liens.get("morts") if liens else None
    if not isinstance(liste, list) or not _entier(morts):
        return _inconnu(titre)
    nombre = _nombre(morts, "lien mort", "liens morts") if morts else "Aucun lien mort"
    ancien = " · ancien" if liens.get("ancien") else ""
    tete = (f'<p class="bord-cout"><strong>{nombre}</strong> · rapport du '
            f'{_jj_mm(liens.get("date"))}{_age(liens.get("age"))}{ancien}</p>')
    corps = (f'<ul class="bord-signalements">{"".join(_lien_mort(m) for m in liste)}</ul>'
             if liste else "")
    return _carte(f'<span class="bord-etiquette">{titre}</span>{tete}{corps}'
                  f'{_autres(morts - len(liste))}')
