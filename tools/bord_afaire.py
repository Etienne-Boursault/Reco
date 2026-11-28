"""bord_afaire.py — la liste « À faire d'abord » du tableau de bord, sans aucune I/O.

Décision : tableau de bord, R2 B du 27/11/2026 et TB-1 C du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 2 et § 7, relectures R3 et R15 ; tranche 3d-2 pour la
publication, les sorties et les liens morts).

La même liste fait la colonne « À faire d'abord » de `/bord` et le message du
dimanche soir : les deux disent donc toujours la même chose.

L'ordre est fixe : relecture, publication, réseaux, signalements, liens morts,
sorties. Une source qu'on n'a pas pu lire (None) donne une ligne « inconnu »,
jamais un silence qui passerait pour « rien à faire » (F11, F12).

Rien n'est recompté ici (R15) : une reco est à relire selon `entry_state`, le
même critère que l'accueil de la relecture ; l'état de la chaîne vient de
`_pipeline_state`, à travers `bord_reseaux.episodes_recents`.

LES LIGNES DE LA PR 3 (tranche 3d-2)
------------------------------------
- publication : les PR d'épisodes ouvertes sur GitHub (`bord_github.lire()`), quand le
  dernier essai a réussi ; sinon, l'état de la chaîne (`recents`), comme avant. Tour 1, E2 et F2
  (28/11/2026) : venus n'a pas de `RECO_GITHUB_TOKEN`, il pousse `contenu/<slugify(guid)>` sans
  ouvrir de PR. Chaque épisode récent se rapproche donc de sa branche : une PR ouverte donne
  « fusionner la PR de … », une PR fusionnée ne donne rien (seul le clone est en retard), ni l'une
  ni l'autre donne « ouvrir puis fusionner la PR de … » avec le lien de comparaison. Tour 2 (M-1,
  M-2) : une donnée non lue se dit « inconnu », jamais un fait ni une action : sans les PR
  fusionnées lues, pas de « ouvrir puis fusionner » mais une ligne grisée ; une PR `contenu/*`
  ouverte qui ne correspond à aucun épisode récent (faite à la main, épisode plus ancien) est une
  vraie tâche, « fusionner la PR #N », car une PR ouverte est à fusionner ou à fermer ;
- sorties : les PR ouvertes de sorties (`contenu/sorties-*`) à fusionner, lues de même ;
  « inconnu » si GitHub n'est pas lisible. Choix du 28/11/2026 : les recos « à relancer »
  se relancent seules chaque jour, il n'y a rien à faire pour Étienne ;
- liens morts : le résumé du contrôle du lundi (`bord_contenu.lire()`), « inconnu » sans
  rapport.
Une ligne peut porter `href` : le rendu ne le suit que pour `https://github.com/` (F21).

REVUE GLOBALE DU TABLEAU DE BORD (28/11/2026)
---------------------------------------------
- E1 : la publication regarde les `N_PUBLICATION` (10) derniers publiés (`publies`), les cases
  des réseaux seulement les 3 derniers (`recents`). La chaîne ne crée pas de PR : un épisode non
  fusionné au-delà des 3 derniers disparaissait. Les publiés plus anciens, absents du clone, sont
  comptés dans une note grisée (`non_verifies`, F23) ;
- M2 : des données `ok` dont `lire()["age"]` dépasse 2 fois la fraîcheur (`bord_distant.donnees_perimees`)
  ne sont plus réécrites. Leurs lignes (signalements, publication, sorties) restent des tâches :
  une PR ouverte vue il y a deux jours est probablement encore à fusionner. Mais elles portent
  « (données du jj/mm) » ; les notes grisées n'en portent pas ;
- D4 : si l'appel des PR fermées a échoué à la dernière lecture (`pannes`), la liste gardée
  d'avant ne dit pas que les PR fusionnées sont toutes connues : `branches_fusionnees` rend None.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import bord_distant
from bord_reseaux import LIBELLES, N_PUBLICATION, RESEAUX, branche_de
from date_sortie import jour_a_paris
from publication import lien_comparaison
from review_render_focus import _ep_label, entry_state, short_title

#: `propriétaire/nom` en caractères sûrs : seul un dépôt de cette forme entre dans un lien.
_DEPOT = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
#: Début de la ligne d'un épisode poussé sans PR : `bord_rendu_blocs` y règle son bouton « Créer la PR »
#: (revue globale, R12).
A_CREER = "ouvrir puis fusionner"


class Note(str):
    """Une ligne grisée qui ne compte pas comme tâche (comme « inconnu », mais qui dit autre chose)."""


def _item(bloc: str, texte: str, guid: str | None = None, *,
          inconnu: bool = False, href: str | None = None) -> dict[str, Any]:
    item = {"bloc": bloc, "texte": texte, "guid": guid, "inconnu": inconnu}
    if href:
        item["href"] = href
    return item


def _libelle(guid: str, episode: dict | None) -> str:
    """« S6·E11 », sinon le titre court, sinon le guid."""
    if not episode:
        return guid
    return _ep_label(episode) or short_title(episode.get("title")) or guid


def _relecture(episodes: dict[str, dict], groups: dict[str, list[dict]]) -> list[dict]:
    def cle(guid: str):
        ep = episodes[guid]
        return (ep.get("season") or 0, ep.get("number") or 9999)

    items = []
    for guid in sorted(episodes, key=cle, reverse=True):
        n = sum(1 for r in groups.get(guid, []) if entry_state(r) == "draft")
        if n:
            items.append(_item("relecture", f"relire {_libelle(guid, episodes[guid])} "
                                             f"({n} reco{'s' if n > 1 else ''})", guid))
    return items


def _publication(recents: list[dict] | None, lignes: list | None) -> list[dict]:
    if lignes is not None:
        return _textes("publication", "publication", lignes)
    if recents is None:
        return [_item("publication", "publication : inconnu", inconnu=True)]
    # Sans GitHub lisible : seule la fenêtre de publication est vue.
    return [_item("publication", f"fusionner la PR de {_libelle(r['guid'], r['episode'])}",
                  r["guid"])
            for r in recents if not r["fusionne"]]


def _reseaux(recents: list[dict] | None,
             coches: dict[str, dict[str, str]] | None) -> list[dict]:
    if recents is None or coches is None:
        return [_item("reseaux", "réseaux : inconnu", inconnu=True)]
    items = []
    for r in recents:
        manque = [LIBELLES[k] for k in RESEAUX if k not in coches.get(r["guid"], {})]
        if manque:
            items.append(_item("reseaux", f"réseaux de {_libelle(r['guid'], r['episode'])} : "
                                          + ", ".join(manque), r["guid"]))
    return items


def _textes(bloc: str, nom: str, textes: list | None) -> list[dict]:
    """Une ligne par texte ; un élément peut être `(texte, adresse)`. None : « inconnu »."""
    if textes is None:
        return [_item(bloc, f"{nom} : inconnu", inconnu=True)]
    items = []
    for t in textes:
        texte, href = (t, None) if isinstance(t, str) else t
        items.append(_item(bloc, texte, href=href, inconnu=isinstance(t, Note)))
    return items


def signalements_en_attente(audience: dict | None) -> list[dict] | None:
    """La liste lue par le site, ou None (inconnu) : pas de données, signalements non lus, ou
    forme inattendue (tour 1, M3 : un site qui répond de travers ne fait pas tomber `/bord`).
    """
    signalements = ((audience or {}).get("donnees") or {}).get("signalements")
    if not isinstance(signalements, dict) or signalements.get("etat") != "lu":
        return None
    liste = signalements.get("enAttente", [])
    if not isinstance(liste, list) or not all(isinstance(s, dict) for s in liste):
        return None
    return liste


def total_signalements(audience: dict | None) -> int | None:
    """Combien de signalements attendent, ou None (inconnu).

    Le site n'envoie que les 5 plus récents et leur total `total` (tableau de bord, revue
    globale, S4). Un cache d'avant ce champ, ou un total qui n'est pas un entier au moins égal
    à la liste envoyée, se rabat sur la longueur de la liste.
    """
    liste = signalements_en_attente(audience)
    if liste is None:
        return None
    total = audience["donnees"]["signalements"].get("total")
    if isinstance(total, int) and not isinstance(total, bool) and total >= len(liste):
        return total
    return len(liste)


def lignes_signalements(audience: dict | None) -> list[str] | None:
    """La ligne des signalements, depuis `bord_distant.lire()` ; None : inconnu.

    Tranche 2c (28/11/2026) : seul un dernier essai réussi (`ok`) dit ce qui attend
    maintenant ; des données gardées après une panne laissent la ligne « inconnu ».
    """
    donnees = (audience or {}).get("donnees")
    if not audience or audience.get("etat") != "ok" or not donnees:
        return None
    n = total_signalements(audience)
    if n is None:
        return None
    return [f"{n} signalement{'s' if n > 1 else ''} en attente"] if n else []


def _ouvertes(github: dict | None) -> dict | None:
    """Les PR ouvertes lues par GitHub, ou None (inconnu) : dernier essai en échec, bloc
    absent ou de forme inattendue. Des données gardées après une panne ne disent pas ce
    qui attend maintenant (même règle que les signalements)."""
    if not isinstance(github, dict) or github.get("etat") != "ok":
        return None
    ouvertes = (github.get("donnees") or {}).get("ouvertes")
    if not isinstance(ouvertes, dict):
        return None
    for groupe in ("episodes", "sorties"):
        liste = ouvertes.get(groupe)
        if not isinstance(liste, list) or not all(isinstance(p, dict) for p in liste):
            return None
    return ouvertes


def branches_fusionnees(github: dict | None) -> dict[str, Any] | None:
    """`{branche: date de fusion}` des PR fusionnées (`bord_github.lire()`), ou None si le bloc manque.

    Une PR fusionnée le reste : des données gardées après une panne de la source servent donc
    aussi. Mais si l'appel des PR fermées est en panne dans la dernière lecture (revue globale, D4),
    la liste gardée est celle d'avant : elle ne dit pas que toutes les fusions sont connues.
    """
    donnees = github.get("donnees") if isinstance(github, dict) else None
    liste = donnees.get("fusionnees") if isinstance(donnees, dict) else None
    pannes = donnees.get("pannes") if isinstance(donnees, dict) else None
    if not isinstance(liste, list) or (isinstance(pannes, dict) and "fusionnees" in pannes):
        return None
    return {pr["branche"]: pr.get("date") for pr in liste
            if isinstance(pr, dict) and pr.get("branche")}


def _comparaison(depot: Any, branche: str) -> str | None:
    """Le lien de comparaison de la branche poussée, seulement pour un dépôt `propriétaire/nom` sûr."""
    if not isinstance(depot, str) or not _DEPOT.fullmatch(depot):
        return None
    return lien_comparaison(*depot.split("/"), branche)


def lignes_publication(github: dict | None, recents: list[dict] | None,
                       non_verifies: int = 0) -> list | None:
    """Les PR d'épisodes à fusionner, depuis `bord_github.lire()` ; None : GitHub illisible.

    Chaque épisode récent se rapproche de sa branche `contenu/<slugify(guid)>` (tour 1, E2, F1) :
    PR ouverte, « fusionner la PR » ; PR fusionnée ou épisode revenu dans le clone, rien ;
    sinon « ouvrir puis fusionner la PR », avec le lien de comparaison, sauf si les PR fusionnées
    n'ont pas été lues : la ligne est alors grisée, « inconnu » (tour 2, M-1). Les autres PR de
    contenu ouvertes (faites à la main, épisode plus ancien) sont des tâches : « fusionner la PR #N »
    (tour 2, M-2). Sans état de la chaîne (`recents` à None), elles se listent aussi, avec une ligne
    grisée « publication des épisodes : inconnu ».
    Une liste coupée par l'API (100 PR) le dit, sans pouvoir dire combien de PR manquent.
    `non_verifies` : les publiés plus anciens que la fenêtre (revue globale, E1), dits « + N »
    par une note grisée (F23).
    """
    ouvertes = _ouvertes(github)
    if ouvertes is None:
        return None
    fusionnees = branches_fusionnees(github)      # None : les PR fusionnées n'ont pas été lues
    depot = github["donnees"].get("depot")
    par_branche = {pr.get("branche"): pr for pr in ouvertes["episodes"]}
    lignes: list = []
    vues = set()
    for r in recents or []:
        branche = branche_de(r["guid"])
        nom = _libelle(r["guid"], r["episode"])
        pr = par_branche.get(branche)
        if pr:
            vues.add(branche)
            lignes.append((f"fusionner la PR de {nom} (#{pr.get('numero')})", pr.get("adresse")))
        elif not r["fusionne"]:
            if fusionnees is None:     # tour 2, M-1 : « inconnu » n'est pas « aucune »
                lignes.append(Note(f"publication de {nom} : inconnu (PR fusionnées non lues)"))
            elif branche not in fusionnees:
                lignes.append((f"{A_CREER} la PR de {nom}",
                               _comparaison(depot, branche)))
    if recents is None:
        lignes.append(Note("publication des épisodes : inconnu"))
    for pr in ouvertes["episodes"]:    # tour 2, M-2 : une PR ouverte est toujours une vraie tâche
        if pr.get("branche") not in vues:
            lignes.append((f"fusionner la PR #{pr.get('numero')} : {pr.get('titre') or 'sans titre'}",
                           pr.get("adresse")))
    if ouvertes.get("coupee"):
        lignes.append(Note("d'autres PR ouvertes ne sont pas listées"))
    if non_verifies:
        s = "s" if non_verifies > 1 else ""
        lignes.append(Note(f"{non_verifies} épisode{s} plus ancien{s} non vérifié{s} "
                           f"(hors des {N_PUBLICATION} derniers publiés)"))
    return lignes


def lignes_sorties(github: dict | None) -> list | None:
    """Les PR de sorties à fusionner, depuis `bord_github.lire()` ; None : GitHub illisible."""
    ouvertes = _ouvertes(github)
    if ouvertes is None:
        return None
    lignes = []
    for pr in ouvertes["sorties"]:
        texte = f"fusionner la PR des sorties : {pr.get('titre') or 'sans titre'}"
        lignes.append((f"{texte} (#{pr.get('numero')})", pr.get("adresse")))
    return lignes


def lignes_liens(contenu: dict | None) -> list[str] | None:
    """La ligne des liens morts, depuis `bord_contenu.lire()` ; None : aucun rapport lisible.

    Un rapport « ancien » (plus de 8 jours) donne une ligne grisée qui ne compte pas, même à 0.
    """
    liens = (contenu or {}).get("liens")
    morts = liens.get("morts") if isinstance(liens, dict) else None
    if not isinstance(morts, int) or isinstance(morts, bool):
        return None
    if liens.get("ancien"):  # tour 1, F8 : un rapport de plus de 8 jours ne fait pas une tâche
        try:
            quand = f" du {date.fromisoformat(liens['date']):%d/%m}"
        except (TypeError, ValueError):
            quand = ""
        return [Note(f"liens morts : rapport ancien{quand}")]
    if not morts:
        return []
    return [f"{morts} lien{'s' if morts > 1 else ''} mort{'s' if morts > 1 else ''}"]


def _datees(lignes: list | None, source: dict | None) -> list | None:
    """Ajoute « (données du jj/mm) » aux lignes tirées d'une source `ok` périmée (revue globale, M2).

    Choix du 28/11/2026 : une ligne périmée reste une tâche (une PR ouverte vue il y a deux jours est
    probablement encore à fusionner), mais elle porte la date de ses données. Les notes grisées
    (`Note`) n'en portent pas. Le jour est celui de Paris.
    """
    if lignes is None or not bord_distant.donnees_perimees(source):
        return lignes
    jour = jour_a_paris(bord_distant._date(source["lu"]))
    suffixe = f" (données du {jour:%d/%m})"
    datees: list = []
    for ligne in lignes:
        if isinstance(ligne, Note):
            datees.append(ligne)
        elif isinstance(ligne, str):
            datees.append(ligne + suffixe)
        else:
            datees.append((ligne[0] + suffixe, ligne[1]))
    return datees


def a_faire(*, episodes: dict[str, dict], groups: dict[str, list[dict]],
            recents: list[dict] | None, coches: dict[str, dict[str, str]] | None,
            signalements: list[str] | None = None, liens: list[str] | None = None,
            sorties: list | None = None, publication: list | None = None,
            publies: list[dict] | None = None) -> list[dict[str, Any]]:
    """La liste « À faire d'abord », dans l'ordre fixe ; `[]` s'il ne reste rien.

    - `episodes`, `groups` : ceux de `review_render._load_groups` ;
    - `recents` : `bord_reseaux.episodes_recents` (None : état de la chaîne illisible) ;
    - `coches` : `bord_reseaux.lire()` (None : `EtatIllisible`) ;
    - `signalements`, `liens`, `sorties` : les lignes déjà rédigées par leur source
      (PR 2 et 3), None tant qu'elle n'est pas lue ; `publication` : de même, avec le
      repli sur `publies` (la fenêtre de publication, `recents` à défaut) quand GitHub n'est pas lisible.

    Chaque élément : `{"bloc", "texte", "guid" (ou None), "inconnu"}`.
    """
    return (_relecture(episodes, groups)
            + _publication(recents if publies is None else publies, publication)
            + _reseaux(recents, coches)
            + _textes("signalements", "signalements", signalements)
            + _textes("liens", "liens morts", liens)
            + _textes("sorties", "sorties", sorties))


def a_faire_depuis(*, episodes: dict[str, dict], groups: dict[str, list[dict]],
                   recents: list[dict] | None, coches: dict[str, dict[str, str]] | None,
                   audience: dict | None, github: dict | None,
                   contenu: dict | None, publies: list[dict] | None = None,
                   non_verifies: int = 0) -> list[dict[str, Any]]:
    """La liste « À faire d'abord » depuis les sources lues (PR 4 : `/bord` et le rappel du
    dimanche l'appellent toutes deux, donc ne divergent jamais).

    `recents` : les 3 derniers publiés, pour les cases des réseaux ; `publies` : la fenêtre de
    publication (revue globale, E1), `recents` à défaut ; `non_verifies` : les plus anciens.
    """
    publies = recents if publies is None else publies
    return a_faire(
        episodes=episodes, groups=groups, recents=recents, coches=coches, publies=publies,
        signalements=_datees(lignes_signalements(audience), audience),
        publication=_datees(lignes_publication(github, publies, non_verifies), github),
        sorties=_datees(lignes_sorties(github), github), liens=lignes_liens(contenu))
