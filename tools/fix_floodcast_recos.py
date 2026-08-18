"""
fix_floodcast_recos.py — arbitrage de l'episode Floodcast du 17 fevrier 2020.

D'OU VIENT CE FICHIER
---------------------
L'episode « Special FLOODCAST avec FLORENT BERNARD et ADRIEN MENIELLE »
(guid c950798f-1d99-45a5-bed7-b1b0a61ba7ea) a vu deux de ses recos ECARTEES le
2026-07-18 avec le meme motif : « Transcript inexploitable : inverifiable ».
Leurs notes ajoutaient « a re-arbitrer si transcript complet » et « a
restaurer/re-attribuer ».

Les deux motifs invoques sont caducs. Le transcript existe — 196 Ko, 4722
lignes, source YouTube (large-v3-turbo). Et la note disait « guests reels
absents des metadonnees » : ils y figurent desormais.

QUI PARLE, ET COMMENT ON LE SAIT
--------------------------------
Les transcripts ne sont pas diarizes. Chaque attribution repose donc sur un
ancrage TEXTUEL dur, verifie dans le transcript puis reecoute par l'editeur du
site. Les timecodes sont sur la timeline YOUTUBE — la version Acast dure 56 s
de moins, et les recos portaient a tort l'etiquette `transcriptSource: acast`
alors que leurs timestamps collent au transcript YouTube a 2 s pres.

  ubm-0599 (Alain Souchon, 00:07:20)
      Segment photos ouvert par « tu es alle au concert de Souchon ». Dans son
      anecdote, le locuteur raconte avoir texte sa comptable par erreur, et
      ELLE LE NOMME : « Priez de m'excuser, monsieur Bernard » (00:10:26).
      L'animateur ne bascule sur l'autre invite qu'apres : « Adrien Meignel.
      Je suis alle voir tes trois dernieres photos » (00:11:05). Le segment
      est donc borne, et il revient a Florent Bernard.

  ubm-1023 (Derby Girl, 01:50:40)
      « La serie Derby Girl dans laquelle J'AI JOUE ». L'ancrage decisif est
      deux minutes plus loin : a 01:52:28, un locuteur parle d'Adrien A LA
      TROISIEME PERSONNE (« sur lequel Adrien a travaille ») puis revendique
      l'ecriture (« et moi j'ai coecrit tous les episodes »). Celui-la est donc
      Florent Bernard, et ses actus sont Pitch et La Flamme, qu'il ECRIT. Le
      « j'ai JOUE » de Derby Girl revient a l'autre : Adrien Menielle.

CE QUI EST CREE, ET POURQUOI CA MANQUAIT
----------------------------------------
Dans la meme sequence d'actus, Florent Bernard presente deux series qu'il a
ecrites. Aucune reco ne les portait POUR CET EPISODE : `ubm-3071` (Pitch) et
`ubm-3072` (La Flamme) existent, mais viennent d'un AUTRE episode (celui avec
Baptiste Lecaplain). Leurs liens sont repris a l'identique, sur decision de
l'editeur.

Le transcript ecrit « Peach » et « Baptiste Le Gaplin » : ce sont des erreurs
de transcription automatique. « Peach » = « Pitch » n'est pas une supposition,
c'est une identification deja actee sur ce corpus — `ubm-3075`, intitulee
« Peach », a ete ecartee comme doublon de `ubm-3071` (Pitch) pour cette raison.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import common  # type: ignore[attr-defined]
from dataset_fixes import Change, add_common_args, run

EPISODE_GUID = "c950798f-1d99-45a5-bed7-b1b0a61ba7ea"

#: `id` -> (titre ATTENDU, recommandeur, est-ce une oeuvre de l'invite ?).
#: Le titre attendu est une GARDE : si le corpus a bouge depuis la reecoute,
#: l'entree ne s'applique plus.
RESTAURATIONS: dict[str, tuple[str, str, bool]] = {
    # Florent Bernard parle d'Alain Souchon en FAN, pas en auteur : ce n'est
    # pas une oeuvre d'invite, juste une recommandation.
    "ubm-0599": ("Souchon", "Florent Bernard", False),
    # Adrien Menielle a JOUE dans Derby Girl : c'est son oeuvre.
    "ubm-1023": ("Derby Girl", "Adrien Ménielle", True),
}

#: `id` -> liens a AJOUTER (sans toucher aux existants).
#:
#: Restauree, Derby Girl n'affichait qu'un lien de RECHERCHE JustWatch — le
#: resolveur automatique n'avait rien de mieux a proposer. Elle porte pourtant
#: `externalIds.tmdb = 112390`, verifie contre l'API : « Derby Girl », 2020,
#: creee par Charlotte Vecchiet et Nikola Lange. La paire fiche + « Où
#: regarder » est la convention du corpus, que 269 recos portent deja.
#:
#: Souchon n'y figure PAS, volontairement : le resolveur lui donne « Foule
#: sentimentale » sur Deezer, precisement la chanson citee a 00:07:27.
LIENS_A_POSER: dict[str, list[dict[str, str]]] = {
    "ubm-1023": [
        {"ethics": "neutral", "kind": "info", "label": "TMDB",
         "url": "https://www.themoviedb.org/tv/112390"},
        {"ethics": "neutral", "kind": "streaming", "label": "Où regarder",
         "url": "https://www.themoviedb.org/tv/112390-derby-girl/watch?locale=FR"},
    ],
}

_LIENS_PITCH = [
    {"ethics": "neutral", "kind": "streaming",
     "label": "YouTube — tous les épisodes (chaîne officielle)",
     "url": "https://www.youtube.com/playlist?list=PL_34KZvppjDi7Pkxvbq77Ufo9qdm6GKNG"},
    {"ethics": "neutral", "kind": "official",
     "label": "Chaîne officielle PITCH",
     "url": "https://www.youtube.com/@pitch5351"},
    {"ethics": "neutral", "kind": "info", "label": "AlloCiné",
     "url": "https://www.allocine.fr/series/ficheserie_gen_cserie=24718.html"},
]
_LIENS_LA_FLAMME = [
    {"ethics": "avoid", "kind": "streaming", "label": "Canal+",
     "url": "https://www.canalplus.com/series/la-flamme/h/14787365_50001"},
    {"ethics": "neutral", "kind": "info", "label": "JustWatch (où voir)",
     "url": "https://www.justwatch.com/fr/serie/la-flamme"},
    {"ethics": "neutral", "kind": "info", "label": "AlloCiné",
     "url": "https://www.allocine.fr/series/ficheserie_gen_cserie=25777.html"},
    {"ethics": "neutral", "kind": "social", "label": "Instagram",
     "url": "https://www.instagram.com/jonathancohens/"},
]

#: Les recos a CREER. Identifiants pris APRES le maximum du corpus (3206) et
#: non dans l'un des 198 trous : un trou peut resulter d'une suppression voulue.
CREATIONS: list[dict[str, Any]] = [
    {
        "id": "ubm-3207", "fichier": "3207.json",
        "title": "Pitch",
        "creator": "Baptiste Lecaplain, Florent Bernard, Xavier Maingon",
        "types": ["serie"], "timestamp": "01:51:54",
        "quote": ("Pitch, c'est terminé mais tout est visible sur la chaîne "
                  "YouTube. C'est le programme court de Baptiste Lecaplain et "
                  "sur lequel j'écris avec lui."),
        "recommendedBy": "Florent Bernard", "guestWork": True,
        "links": _LIENS_PITCH,
        "externalIds": {"youtubeChannelId": "UCBTDgthuMxXF0HoBJypd1hA"},
        "pourquoi": ("Florent Bernard presente une serie qu'il ECRIT, dans la "
                     "sequence d'actus. Liens repris de ubm-3071, qui porte la "
                     "meme oeuvre pour un autre episode."),
    },
    {
        "id": "ubm-3208", "fichier": "3208.json",
        "title": "La Flamme", "creator": "Jonathan Cohen",
        "types": ["serie"], "timestamp": "01:52:10",
        "quote": "La Flamme en tout cas, ça sort cette année.",
        "recommendedBy": "Florent Bernard", "guestWork": True,
        "links": _LIENS_LA_FLAMME,
        "externalIds": {"instagram": "jonathancohens"},
        "pourquoi": ("Meme sequence : « et moi j'ai coecrit tous les episodes "
                     "avec eux deux » (01:52:32). Liens repris de ubm-3072, "
                     "qui porte la meme oeuvre pour un autre episode."),
    },
]


def transform(reco: dict[str, Any]) -> list[Change]:
    """Restaure les deux recos ecartees a tort. Mute `reco` en place."""
    entree = RESTAURATIONS.get(reco.get("id") or "")
    if entree is None:
        return []
    titre_attendu, recommandeur, oeuvre_invite = entree
    if reco.get("title") != titre_attendu:
        return []

    changes: list[Change] = []
    if reco.get("status") != "validated":
        changes.append(Change(field="status", before=reco.get("status"),
                              after="validated"))
        reco["status"] = "validated"
    if reco.get("recommendedBy") != recommandeur:
        changes.append(Change(field="recommendedBy",
                              before=reco.get("recommendedBy"),
                              after=recommandeur))
        reco["recommendedBy"] = recommandeur
    # `guestWork` est `optional()` SANS `nullable()` : ne JAMAIS ecrire `null`.
    # Absent vaut « pas une oeuvre d'invite ».
    if oeuvre_invite and reco.get("guestWork") is not True:
        changes.append(Change(field="guestWork", before=reco.get("guestWork"),
                              after=True))
        reco["guestWork"] = True

    for lien in LIENS_A_POSER.get(reco.get("id") or "", []):
        liens = [x for x in (reco.get("links") or []) if isinstance(x, dict)]
        if any(x.get("url") == lien["url"] for x in liens):
            continue
        avant_urls = [x.get("url") for x in liens]
        reco["links"] = liens + [dict(lien)]
        changes.append(Change(field="links", before=avant_urls,
                              after=avant_urls + [lien["url"]]))
    return changes


def creer(racine: Path, *, apply: bool) -> list[Path]:
    """Cree les recos manquantes. Renvoie les chemins concernes.

    Sans `apply`, annonce ce qui serait ecrit sans rien ecrire.

    Un fichier DEJA PRESENT sous le meme nom arrete tout : ecrire par-dessus
    effacerait une reco sans laisser de trace. Seul est saute le cas ou la
    reco a deja ete creee PAR CETTE PASSE, reconnue a son identifiant ET son
    titre.
    """
    dossier = racine / "un-bon-moment"
    faits: list[Path] = []
    for entree in CREATIONS:
        chemin = dossier / entree["fichier"]
        if chemin.exists():
            doc = json.loads(chemin.read_text(encoding="utf-8"))
            if doc.get("id") == entree["id"] and doc.get("title") == entree["title"]:
                continue  # deja creee par cette passe
            sys.exit(
                f"REFUS : {chemin} existe deja et porte « {doc.get('title')} » "
                f"(id {doc.get('id')}). Ecrire par-dessus effacerait une reco. "
                f"Choisis un autre identifiant que {entree['id']}.")
        faits.append(chemin)
        if not apply:
            continue
        doc = {
            "creator": entree["creator"],
            "episodeGuid": EPISODE_GUID,
            "externalIds": entree["externalIds"],
            "guestWork": True,
            "id": entree["id"],
            "kind": "reco",
            "links": entree["links"],
            "quote": entree["quote"],
            "recommendedBy": entree["recommendedBy"],
            "sourceId": "un-bon-moment",
            "status": "validated",
            "timestamp": entree["timestamp"],
            "title": entree["title"],
            "transcriptSource": "youtube",
            "types": entree["types"],
        }
        dossier.mkdir(parents=True, exist_ok=True)
        chemin.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return faits


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Restaure les deux recos du Floodcast ecartees pour un "
                    "motif caduc, et cree les deux oeuvres de Florent Bernard "
                    "qui manquaient pour cet episode.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # `common.RECOS_DIR` est lu A L'APPEL : le figer a l'import ferait ecrire
    # les tests dans le vrai corpus (cf. le meme piege dans match_audit).
    crees = creer(common.RECOS_DIR, apply=args.apply)
    run(transform, args, extra_report={"creees": [str(c) for c in crees]})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
