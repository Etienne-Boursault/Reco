"""bord_rendu_audience.py — l'audience du site, au centre de la page `/bord`.

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026, l'audience
au centre (« l'audience est vraiment le point central du tableau de bord » ; plan
`pr-tableau-de-bord.md`, § 3, § 5 et § 6, tranche 2c).

Rendu pur : il reçoit l'état de `bord_distant.lire()` (le cache, jamais le réseau)
et rend du HTML. Il ne recompte rien : les chiffres sont ceux de `/api/bord`, donc
du tri de `classement.ts` (F2, F10).

CE QUE DIT LE BLOC
------------------
- L'état du dernier essai et l'âge des données (« lu il y a 12 min »). Après une
  panne, les dernières données restent, marquées par leur âge.
- Trois grands chiffres sur 7 jours, en visiteurs-jours (confirmés, incertains,
  robots), ceux de 30 jours en dessous. Avant la bascule (lue sur 30 jours, note
  2a-2 du journal), « ancien tri » : humains et passages de robots seulement.
- 7 barres, les 7 derniers jours calendaires jusqu'au jour du résumé : `jours` ne
  liste que les jours mesurés, un jour absent est « pas de mesure », jamais un zéro.
  Les barres sont en CSS (rien à télécharger, aucun script) et cachées au lecteur
  d'écran, qui lit le tableau qui les double.
- Les 5 premières pages et provenances, en texte seul, coupées à 80 signes et
  échappées (R10), dans l'ordre de l'API ; si le site en a plus (`pagesTotal`,
  `provenancesTotal`), la page dit « + N autres » (F23, tour 1, M5).
- Le lien vers `/audience`, sans la clé (« s'ouvre depuis ton signet »).

Une réponse de forme inattendue (un champ manquant) ne casse pas la page : le bloc
le dit, et l'erreur est journalisée.
"""
from __future__ import annotations

import html
import re
from datetime import date, timedelta
from typing import Any

import bord_distant
from bord_rendu_blocs import _JOURS, _depuis, _texte
from common import log

#: Longueur d'une page ou d'une provenance (§ 3).
LONGUEUR_CLE = 80
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_SERIES = (("confirmes", "Confirmés"), ("incertains", "Incertains"), ("robots", "Robots"))
_ANCIEN = (("humains", "Humains (ancien tri)", "visiteurs", "visiteurs"),
           ("robots", "Passages de robots", "robots", "visitesRobots"))
_MESSAGES = {
    "inconnu": "Pas encore lu : la première lecture est lancée, elle s'affiche au "
               "prochain rechargement.",
    "inconnu-sans-lancement": "Pas encore lu : la lecture n'a pas pu être lancée.",
    "cle-absente": "Clé absente sur venus : poser RECO_AUDIENCE_KEY dans le .env du "
                   "serveur de relecture, puis recréer le conteneur.",
    # Tour 1, F2 : le site répond 404 aussi quand il n'a pas la clé ou pas la route.
    "cle-refusee": "Le site répond « introuvable » : la clé de venus diffère de celle du "
                   "site, ou le site n'a pas la clé, ou il n'a pas encore la route /api/bord.",
    "panne": "Site injoignable.",
    "reponse-illisible": "Réponse illisible du site.",
    "cache-illisible": "Le cache de l'audience est illisible et n'est pas réécrit : "
                       "effacer {chemin} pour relancer la lecture.",
}


def _n(v: Any) -> str:
    """Un nombre à la française ; « ? » pour une valeur qui n'en est pas un."""
    if isinstance(v, bool) or not isinstance(v, int | float):
        return "?"
    if isinstance(v, float) and not v.is_integer():
        return f"{v:.1f}".replace(".", ",")
    return f"{int(v):,}".replace(",", " ")


def _jj_mm(iso: Any) -> str:
    """« jj/mm » d'une date ISO ; « ? » sinon : la valeur vient du site, elle n'entre pas telle quelle."""
    s = str(iso)
    return f"{s[8:10]}/{s[5:7]}" if _DATE.match(s) else "?"


def _etat(audience: dict) -> str:
    etat = str(audience.get("etat") or "inconnu")
    cle = "inconnu-sans-lancement" if etat == "inconnu" and not audience.get("relance") else etat
    message = _MESSAGES.get(cle, f"État : {_texte(audience.get('libelle') or etat, 40)}.")
    if etat == "cache-illisible":  # le chemin que lit `bord_distant`, pas un chemin fixe (F7)
        message = message.format(chemin=html.escape(str(bord_distant._chemin())))
    detail = audience.get("detail")
    if detail:
        message = f"{message.removesuffix('.')} ({_texte(detail, 40)})."
    age = audience.get("age")
    if audience.get("donnees") is not None and isinstance(age, int):
        quand = _depuis(timedelta(seconds=age))
        perime = bord_distant.donnees_perimees(audience)  # même seuil que Santé (revue globale, M2)
        message = (f"{'Périmé' if perime else 'À jour'} · lu {quand}." if etat == "ok"
                   else f"{message} Ce sont les données d'{quand}.")
    return (f'<p class="bord-audience-etat" data-etat="{html.escape(etat)}">'
            f'<span class="bord-pastille" aria-hidden="true"></span>'
            f"<span>{message}</span></p>")


def _chiffre(valeur: Any, nom: str, detail: str = "") -> str:
    return (f'<div class="bord-chiffre"><span class="bord-chiffre-valeur">{_n(valeur)}</span>'
            f'<span class="bord-chiffre-nom">{nom}{detail}</span></div>')


def _fenetre(titre: str, f: dict | None, erreur: Any, classe: str) -> str:
    if f is None:
        return (f'<p class="bord-alerte">{titre} : illisible sur le site'
                f"{' (' + _texte(erreur) + ')' if erreur else ''}.</p>")
    col = f["colonnes"]
    if col is None:
        tuiles = "".join(_chiffre(f[cle_f], nom) for _, nom, _, cle_f in _ANCIEN)
        note = " · ancien tri"
    else:
        tuiles = "".join(_chiffre(col[cle]["visiteursJours"], nom,
                                  f" · {_n(col[cle]['visites'])} visites")
                         for cle, nom in _SERIES)
        bascule, du = f.get("bascule"), f.get("du")
        depuis = f", depuis le {_jj_mm(bascule)}" if bascule and du and bascule > du else ""
        note = f" · visiteurs-jours{depuis}"
    return (f'<div class="bord-fenetre {classe}"><span class="bord-etiquette">{titre}{note}'
            f'</span><div class="bord-chiffres">{tuiles}</div></div>')


def _sept_jours(fin: date, jours: list[dict]) -> list[tuple[date, dict | None]]:
    par_jour = {str(j["jour"])[:10]: j for j in jours}
    dates = [fin - timedelta(days=k) for k in range(6, -1, -1)]
    return [(d, par_jour.get(d.isoformat())) for d in dates]


def _nom_jour(d: date) -> str:
    return f"{_JOURS[d.weekday()][:3]}. {d:%d/%m}"


def _court(d: date) -> str:
    """Sous une barre : « dim. » puis le jour du mois, sur deux lignes (7 barres au téléphone)."""
    return f"{_JOURS[d.weekday()][:3]}.<br>{d.day}"


def _graphe(titre: str, jours: list[tuple[date, dict | None]],
            series: list[tuple[str, str, Any]]) -> str:
    """Barres empilées des `series` (clé, nom, lecture d'un jour → valeur ou None)."""
    valeurs = [[lire(j) for _, _, lire in series] if j else None for _, j in jours]
    totaux = [sum(v) for v in valeurs if v and None not in v]
    plus = max(totaux, default=0) or 1
    barres, lignes = [], []
    for (d, j), v in zip(jours, valeurs, strict=True):
        if j is None:
            barres.append(f'<div class="bord-jour" data-mesure="non"><div class="bord-barre">'
                          f'</div><span>{_court(d)}</span></div>')
            lignes.append(f'<tr><th scope="row">{_nom_jour(d)}</th>'
                          f'<td colspan="{len(series)}">pas de mesure</td></tr>')
        elif None in v:
            barres.append(f'<div class="bord-jour" data-mesure="ancien"><div class="bord-barre">'
                          f'</div><span>{_court(d)}</span></div>')
            lignes.append(f'<tr><th scope="row">{_nom_jour(d)}</th>'
                          f'<td colspan="{len(series)}">ancien tri : {_n(j["visiteurs"])} '
                          f'humains, {_n(j["robots"])} passages de robots</td></tr>')
        else:
            segs = "".join(f'<i class="bord-seg" data-serie="{cle}" '
                           f'style="height:{round(x / plus * 100)}%"></i>'
                           for (cle, _, _), x in zip(series, v, strict=True))
            barres.append(f'<div class="bord-jour" data-mesure="oui"><div class="bord-barre">'
                          f'{segs}</div><span>{_court(d)}</span></div>')
            lignes.append(f'<tr><th scope="row">{_nom_jour(d)}</th>'
                          + "".join(f"<td>{_n(x)}</td>" for x in v) + "</tr>")
    legende = "".join(f'<li data-serie="{cle}">{nom}</li>' for cle, nom, _ in series)
    entete = "".join(f'<th scope="col">{nom}</th>' for _, nom, _ in series)
    return (f'<div class="bord-carte"><span class="bord-etiquette">{titre}</span>'
            f'<div class="bord-graphe" aria-hidden="true">{"".join(barres)}</div>'
            f'<ul class="bord-legende" aria-hidden="true">{legende}</ul>'
            f'<table class="bord-lecteur"><caption>{titre}, jour par jour</caption>'
            f'<thead><tr><th scope="col">Jour</th>{entete}</tr></thead>'
            f'<tbody>{"".join(lignes)}</tbody></table></div>')


def _graphes(d: dict, ancien: bool) -> str:
    fin = date.fromisoformat(str(d["genere"])[:10])
    jours = _sept_jours(fin, d["jours"])
    if ancien:
        return "".join(_graphe(f"{nom}, 7 jours", jours,
                               [(cle, nom, lambda j, c=cle_j: j[c])])
                       for cle, nom, cle_j, _ in _ANCIEN)

    def lecture(cle):
        return lambda j: j["colonnes"][cle]["visiteursJours"] if j["colonnes"] else None

    return _graphe("Visiteurs-jours, 7 jours", jours,
                   [(cle, nom, lecture(cle)) for cle, nom in _SERIES])


def _liste(titre: str, vide: str, comptes: list[dict], total: Any) -> str:
    if not comptes:
        corps = f'<p class="bord-mut">{vide}</p>'
    else:
        corps = ('<ol class="bord-classement">'
                 + "".join(f'<li><span>{_texte(c["cle"], LONGUEUR_CLE)}</span>'
                           f'<span class="bord-mut">{_n(c["n"])}</span></li>' for c in comptes)
                 + "</ol>")
        if isinstance(total, int) and not isinstance(total, bool) and total > len(comptes):
            corps += f'<p class="bord-mut bord-liste-coupee">+ {total - len(comptes)} autres</p>'
    return f'<div class="bord-carte"><span class="bord-etiquette">{titre}</span>{corps}</div>'


def _lien() -> str:
    try:
        site = bord_distant.adresse().removesuffix(bord_distant.CHEMIN)
    except ValueError:
        return '<p class="bord-mut bord-audience-lien">Lien vers /audience : adresse du site refusée.</p>'
    return (f'<p class="bord-audience-lien"><a href="{html.escape(site)}/audience" '
            'rel="noreferrer">Tout le détail sur /audience</a> '
            "<span class=\"bord-mut\">(s'ouvre depuis ton signet : le lien ne porte pas la clé)"
            "</span></p>")


def _chiffres(d: dict) -> str:
    sept, trente = d.get("sept"), d.get("trente")
    ancien = (trente or sept or {}).get("bascule") is None
    panne = (trente or sept or {}).get("panneSignal") or []
    haut = (_fenetre("7 derniers jours", sept, d.get("erreur"), "bord-fenetre-sept")
            + _fenetre("30 derniers jours", trente, d.get("erreur"), "bord-fenetre-trente"))
    if panne:
        haut += ('<p class="bord-alerte">Aucun signal reçu le '
                 + " et le ".join(_jj_mm(j) for j in panne)
                 + " alors que des visites ont été comptées : le script du signal est "
                   "peut-être en panne.</p>")
    # `null` : trop peu de visiteurs pour une part ; jamais écrit 0.
    clics = " · ".join(f"{nom} : {'—' if f['clicsPour100Visiteurs'] is None else _n(f['clicsPour100Visiteurs'])}"
                       for nom, f in (("7 jours", sept), ("30 jours", trente)) if f)
    if clics:
        haut += f'<p class="bord-clics">Clics pour 100 visiteurs · {clics}</p>'
    listes = ""
    if sept:
        listes = (_liste("Pages les plus vues, 7 jours", "Aucune page vue.", sept["pages"],
                         sept.get("pagesTotal"))
                  + _liste("Provenances, 7 jours", "Aucune provenance.", sept["provenances"],
                           sept.get("provenancesTotal")))
    return (f'<div class="bord-carte bord-audience-haut">{haut}</div>'
            + _graphes(d, ancien) + listes)


def bloc_audience(audience: dict | None) -> str:
    """Le contenu de la colonne « Audience », depuis `bord_distant.lire()` (None : inconnu)."""
    audience = audience or {"etat": "inconnu"}
    donnees = audience.get("donnees")
    corps = ""
    if donnees is not None:
        try:
            corps = _chiffres(donnees)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            log.warning("bord : lecture de l'audience abandonnée, réponse de forme "
                        "inattendue (%s)", type(exc).__name__)
            corps = ('<p class="bord-alerte">Réponse du site de forme inattendue : '
                     "les chiffres ne s'affichent pas.</p>")
    return _etat(audience) + corps + _lien()
