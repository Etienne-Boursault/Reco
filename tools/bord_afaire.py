"""bord_afaire.py — la liste « À faire d'abord » du tableau de bord, sans aucune I/O.

Décision : tableau de bord, R2 B du 27/11/2026 et TB-1 C du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 2 et § 7, relectures R3 et R15).

La même liste fait la colonne « À faire d'abord » de `/bord` et le message du
dimanche soir : les deux disent donc toujours la même chose.

L'ordre est fixe : relecture, publication, réseaux, signalements, liens morts,
sorties. Une source qu'on n'a pas pu lire (None) donne une ligne « inconnu »,
jamais un silence qui passerait pour « rien à faire » (F11, F12).

Rien n'est recompté ici (R15) : une reco est à relire selon `entry_state`, le
même critère que l'accueil de la relecture ; l'état de la chaîne vient de
`_pipeline_state`, à travers `bord_reseaux.episodes_recents`.
"""
from __future__ import annotations

from typing import Any

from bord_reseaux import LIBELLES, RESEAUX
from review_render_focus import _ep_label, entry_state, short_title


def _item(bloc: str, texte: str, guid: str | None = None, *,
          inconnu: bool = False) -> dict[str, Any]:
    return {"bloc": bloc, "texte": texte, "guid": guid, "inconnu": inconnu}


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


def _publication(recents: list[dict] | None) -> list[dict]:
    if recents is None:
        return [_item("publication", "publication : inconnu", inconnu=True)]
    # shortcut: seuls les 3 derniers publiés sont vus ; la PR 3 lira les PR ouvertes sur GitHub.
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


def _textes(bloc: str, nom: str, textes: list[str] | None) -> list[dict]:
    if textes is None:
        return [_item(bloc, f"{nom} : inconnu", inconnu=True)]
    return [_item(bloc, t) for t in textes]


def lignes_signalements(audience: dict | None) -> list[str] | None:
    """La ligne des signalements, depuis `bord_distant.lire()` ; None : inconnu.

    Tranche 2c (28/11/2026) : seul un dernier essai réussi (`ok`) dit ce qui attend
    maintenant ; des données gardées après une panne laissent la ligne « inconnu ».
    """
    donnees = (audience or {}).get("donnees")
    if not audience or audience.get("etat") != "ok" or not donnees:
        return None
    signalements = donnees.get("signalements") or {}
    if signalements.get("etat") != "lu":
        return None
    n = len(signalements.get("enAttente") or [])
    return [f"{n} signalement{'s' if n > 1 else ''} en attente"] if n else []


def a_faire(*, episodes: dict[str, dict], groups: dict[str, list[dict]],
            recents: list[dict] | None, coches: dict[str, dict[str, str]] | None,
            signalements: list[str] | None = None, liens: list[str] | None = None,
            sorties: list[str] | None = None) -> list[dict[str, Any]]:
    """La liste « À faire d'abord », dans l'ordre fixe ; `[]` s'il ne reste rien.

    - `episodes`, `groups` : ceux de `review_render._load_groups` ;
    - `recents` : `bord_reseaux.episodes_recents` (None : état de la chaîne illisible) ;
    - `coches` : `bord_reseaux.lire()` (None : `EtatIllisible`) ;
    - `signalements`, `liens`, `sorties` : les lignes déjà rédigées par leur source
      (PR 2 et 3), None tant qu'elle n'est pas lue.

    Chaque élément : `{"bloc", "texte", "guid" (ou None), "inconnu"}`.
    """
    return (_relecture(episodes, groups)
            + _publication(recents)
            + _reseaux(recents, coches)
            + _textes("signalements", "signalements", signalements)
            + _textes("liens", "liens morts", liens)
            + _textes("sorties", "sorties", sorties))
