"""rappel_dimanche.py — le message Matrix du dimanche soir : ce qu'il reste à faire.

Décision : tableau de bord, R2 B du 27/11/2026 ; TB-1 C et TB-2 B du 28/11/2026 (plan
`pr-tableau-de-bord.md`, § 7 ; PR 4). Appelé par `deploy/venus/tick.sh`
(`python rappel_dimanche.py --notifier matrix`) le dimanche à partir de 20 h ; le script
revérifie lui-même le jour et l'heure (Paris), et reste inerte sans `RECO_RAPPEL_DIMANCHE=1`.

- Le texte vient de `bord_afaire.a_faire_depuis`, que la colonne « À faire d'abord » de
  `/bord` appelle aussi : les deux disent la même chose.
- Il relit lui-même l'audience et GitHub, de façon synchrone et sous le même verrou que la
  page (rien ne presse dans ce conteneur). Une source qui ne répond pas donne « inconnu »,
  avec la date des dernières données gardées, jamais un silence (F22).
- Une fois par semaine : `rappel.json` (dossier de `RECO_BORD_DIR`) garde la semaine ISO
  envoyée. Un état illisible n'envoie rien, n'écrit rien et sort en erreur. Rien à dire, ou
  un envoi raté : la semaine n'est pas marquée, le passage suivant revérifie.
- Des lignes « inconnu » seules ne font pas un message (rien de concret à faire), mais
  elles sont journalisées : ni « rien à faire » dit à tort, ni message qui n'apprend rien.
- `--apercu` affiche le texte, sans rien envoyer ni écrire de l'état, et ignore le jour,
  l'heure et l'interrupteur.
- L'envoi passe par le `MatrixSender` de la chaîne (`poll_rss._build_sender`) et non par
  `build_notify`, qui avale l'échec d'un envoi ; non configuré, il compte comme raté.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import bord_afaire
import bord_contenu
import bord_distant
import bord_github
import bord_reseaux
import common
import review_render
import review_render_page
from bord_rendu_blocs import _fuseau
from common import log

VARIABLE = "RECO_RAPPEL_DIMANCHE"
HEURE = 20
#: Les lignes « inconnu » qui citent la date des dernières données gardées, par bloc.
_SOURCES_DATEES = {"signalements": "audience", "sorties": "github"}


def _sender():
    from poll_rss import _build_sender
    return _build_sender("matrix")


def _etat_chemin():
    return bord_reseaux.dossier() / "rappel.json"


def _semaine_envoyee() -> str | None:
    """La semaine ISO déjà envoyée ; None sans fichier ; `EtatIllisible` s'il est abîmé."""
    chemin = _etat_chemin()
    if not chemin.exists():
        return None
    try:
        semaine = common.read_json(chemin)["semaine"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise bord_reseaux.EtatIllisible(f"{chemin.name} illisible ({type(exc).__name__})") from exc
    if not isinstance(semaine, str):
        raise bord_reseaux.EtatIllisible(f"{chemin.name} : semaine n'est pas un texte")
    return semaine


def _rafraichir() -> None:
    """Relit l'audience et GitHub ; l'un en panne n'empêche pas l'autre. Jamais le message
    de l'exception : la clé a pu y passer (même règle que `bord_distant`)."""
    for nom, module in (("audience", bord_distant), ("github", bord_github)):
        try:
            log.info("rappel : %s relu, état %s", nom, module.rafraichir())
        except Exception as exc:  # noqa: BLE001
            log.warning("rappel : %s non relu (%s)", nom, type(exc).__name__)


def _lignes(source_id: str, fuseau) -> tuple[list[str], int]:
    """Les lignes du message (celles de la colonne « À faire d'abord ») et leur nombre de vraies tâches.

    Une ligne « inconnu » d'audience ou de GitHub cite la date des dernières données gardées.
    """
    _, episodes, groups = review_render._load_groups(source_id)
    recents = bord_reseaux.episodes_recents(
        source_id, review_render_page._pipeline_state(source_id), episodes)
    try:
        coches = bord_reseaux.lire()
    except bord_reseaux.EtatIllisible as exc:
        log.warning("rappel : %s", exc)
        coches = None
    lus = {"audience": bord_distant.lire(relancer=False),
           "github": bord_github.lire(relancer=False)}
    items = bord_afaire.a_faire_depuis(
        episodes=episodes, groups=groups, recents=recents, coches=coches,
        audience=lus["audience"], github=lus["github"], contenu=bord_contenu.lire(source_id))
    lignes, taches = [], 0
    for item in items:
        texte, lu = item["texte"], (lus.get(_SOURCES_DATEES.get(item["bloc"], "")) or {}).get("lu")
        if item["inconnu"] and lu and texte.endswith("inconnu"):
            texte += f" (données du {bord_distant._date(lu).astimezone(fuseau):%d/%m})"
        lignes.append(texte)
        taches += not item["inconnu"]
    return lignes, taches


def _message(lignes: list[str]) -> str:
    """Le texte, avec le lien de `/bord` si `RECO_REVIEW_URL` est posée."""
    texte = "🗒️ Il te reste : " + " · ".join(lignes)
    url = os.environ.get("RECO_REVIEW_URL", "").rstrip("/")
    return f"{texte}\n{url}/bord" if url else texte


def main(argv: list[str] | None = None, *, maintenant: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(description="Le message du dimanche soir : ce qu'il reste à faire.")
    parser.add_argument("--source", default="un-bon-moment")
    parser.add_argument("--notifier", choices=("matrix",))
    parser.add_argument("--apercu", action="store_true",
                        help="affiche le message : ni envoi, ni état ; ignore le jour, l'heure et l'interrupteur")
    args = parser.parse_args(argv)
    if not (args.apercu or args.notifier):
        parser.error("--notifier matrix (ou --apercu) est requis")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    fuseau = _fuseau()
    paris = (maintenant or datetime.now(UTC)).astimezone(fuseau)
    annee, semaine_iso, jour = paris.isocalendar()
    semaine = f"{annee}-W{semaine_iso:02d}"
    if not args.apercu:
        if os.environ.get(VARIABLE) != "1" or jour != 7 or paris.hour < HEURE:
            return 0
        try:
            if _semaine_envoyee() == semaine:
                return 0
        except bord_reseaux.EtatIllisible as exc:
            log.error("rappel : %s, rien n'est envoyé ni écrit", exc)
            return 1
    _rafraichir()
    lignes, taches = _lignes(args.source, fuseau)
    if not taches:
        log.info("rappel : rien à dire (%s), semaine %s non marquée", " · ".join(lignes) or "aucune ligne",
                 semaine)
        if args.apercu:
            print("rien à dire : aucun message ne partirait")
        return 0
    texte = _message(lignes)
    if args.apercu:
        print(texte)
        return 0
    return _envoyer(texte, semaine, paris)


def _envoyer(texte: str, semaine: str, paris: datetime) -> int:
    sender: Any = _sender()
    if sender is None or not sender.send({"msgtype": "m.text", "body": texte}):
        log.error("rappel : message non envoyé (Matrix absent ou en échec), semaine %s non marquée",
                  semaine)
        return 1
    try:
        common.atomic_write_text(_etat_chemin(), json.dumps(
            {"semaine": semaine, "envoye": paris.isoformat(timespec="seconds")}) + "\n")
    except OSError as exc:
        log.error("rappel : message envoyé mais %s non écrit (%s) : il repartira au prochain passage",
                  _etat_chemin().name, type(exc).__name__)
        return 1
    log.info("rappel : message envoyé, semaine %s marquée", semaine)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
