"""
fix_liens_verifies.py — liens issus de la recherche déléguée du 2026-08-17.

D'OÙ VIENNENT CES LIENS
-----------------------
Trois agents ont cherché en parallèle les familles manquantes (fiche,
visionnage, billetterie). Ils n'avaient PAS le droit d'écrire dans le corpus :
ils ont rendu des candidats sourcés, revérifiés ici un par un avant écriture.
Un rapport, même circonstancié, ne vaut pas vérification — un sous-agent a déjà
fabriqué des URL sur ce projet.

CE QUI A ÉTÉ VÉRIFIÉ, ET COMMENT
--------------------------------
Pour les vidéos, `yt-dlp` donne le titre, la DURÉE et la chaîne. La durée est
le contrôle décisif : elle distingue l'œuvre entière d'une bande-annonce, ce
qu'aucun code HTTP ne sait faire. « Les Clés de bagnole » dure 86 minutes,
« The Egg » 8 minutes — l'une est un long-métrage, l'autre un court, et les
deux sont conformes à leur fiche.

CE QUI A ÉTÉ ÉCARTÉ, ET POURQUOI
--------------------------------
La vérification a révélé ce que le rapport ne disait pas : plusieurs vidéos
sont des REMISES EN LIGNE NON OFFICIELLES d'œuvres protégées — « Les Clés de
bagnole » par un compte « pp contact », « Désiré » d'Albert Dupontel par
« Comby JB », le documentaire « NTM Authentiques » par « MrResktwo », de même
que huit épisodes d'« Inside Jamel Comedy Club » déposés sur archive.org.
Ce sont bien les œuvres, et elles sont bien regardables — mais les publier
reviendrait à faire du site un annuaire de copies non autorisées. La décision
revient à l'éditeur du site, pas à cette table.

Ne figurent donc ici que les CHAÎNES OFFICIELLES (celle de l'auteur ou du
producteur) et les plateformes légitimes.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from dataset_fixes import Change, add_common_args, run

#: `id de reco` → (titre ATTENDU, libellé, `kind`, URL, pourquoi).
#:
#: Le titre attendu est une GARDE : si le corpus a changé depuis la
#: vérification, l'entrée ne s'applique plus.
LIENS: dict[str, tuple[str, str, str, str, str]] = {
    # --- Visionnage : chaînes officielles ----------------------------------
    "ubm-0067": ("Fantasme", "YouTube", "streaming",
                 "https://www.youtube.com/watch?v=GVv_2O0yu58",
                 "52 min sur la chaîne d'Éléonore Costes, sa réalisatrice."),
    "ubm-0633": ("Chambre froide", "YouTube", "streaming",
                 "https://www.youtube.com/watch?v=nvcKYVtfOQI",
                 "32 min sur la chaîne de Swann Périssé, sa réalisatrice."),
    "ubm-0651": ("Putain de série", "YouTube", "streaming",
                 "https://www.youtube.com/@PutainDeSerie/videos",
                 "La chaîne de la série porte ses dix épisodes."),
    "ubm-0815": ("The Egg", "YouTube", "streaming",
                 "https://www.youtube.com/watch?v=h6fcK_fRYaI",
                 "8 min sur la chaîne du studio Kurzgesagt, qui l'a produit."),
    "ubm-1643": ("Minuit", "YouTube", "streaming",
                 "https://www.youtube.com/watch?v=8rs4c0vgUKg",
                 "« MINUIT 01 à 07 » sur la chaîne de Roman Frayssinet."),
    "ubm-1805": ("Exocet", "YouTube", "streaming",
                 "https://www.youtube.com/channel/UCN9Uz75ZMbRErdnYnOXR3dg/videos",
                 "« Exocet Replay » porte 37 émissions complètes de 2005 à 2008."),
    "ubm-2656": ("Les Voisins du dessus", "YouTube", "streaming",
                 "https://www.youtube.com/watch?v=Jv5X_Ca3UJs",
                 "Premier épisode, sur la chaîne qui porte la série."),
    "ubm-2707": ("Gus", "YouTube", "streaming",
                 "https://www.youtube.com/playlist?list=PL104EsRb09mW9L4mbUzxlv1Z-lk71Y9lN",
                 ("Playlist « GUS - LA SÉRIE » sur la chaîne de Jérémie "
                 "Dethelot, son auteur.")),
    "ubm-2709": ("Définition", "YouTube", "streaming",
                 "https://www.youtube.com/playlist?list=PLLrRB-vaZejRHfrnowoIoOBYBDyxXyt9i",
                 "Playlist de la saison 2 sur la chaîne de Shirley Souagnon."),
    "ubm-2956": ("Les Emmerdeurs", "YouTube", "streaming",
                 "https://www.youtube.com/watch?v=j4x2Jy1zSyw",
                 ("Épisode 1 (30 min) sur Golden Moustache, chaîne du "
                 "producteur (M6).")),
    "ubm-1045": ("Close Up", "YouTube", "streaming",
                 "https://www.youtube.com/@closeuplaserie7920/videos",
                 ("La chaîne de la websérie porte ses deux saisons. C'est la "
                 "reco dont l'identifiant TMDB ET l'identifiant IMDb "
                 "désignaient une émission américaine sans rapport.")),
    "ubm-1119": ("Crocodile Fury", "YouTube", "streaming",
                 "https://www.youtube.com/watch?v=soUa9p6u9o0",
                 ("87 min sur « Wu Tang Collection », chaîne de distribution "
                 "du catalogue ; la durée concorde avec la fiche TMDB.")),
    # --- Visionnage : plateformes ------------------------------------------
    "ubm-0187": ("Iris", "Canal+", "streaming",
                 ("https://www.canalplus.com/series/iris-saison-1-episode-1/h/"
                 "26903523_50001?episodeId=26734326_50001"),
                 ("Deux sources concordantes : TMDB `watch/providers` donne "
                 "Canal+ Séries pour la France, et JustWatch mène à la même "
                 "adresse.")),
    "ubm-0210": ("Iris", "Canal+", "streaming",
                 ("https://www.canalplus.com/series/iris-saison-1-episode-1/h/"
                 "26903523_50001?episodeId=26734326_50001"),
                 "Même œuvre que ubm-0187, mêmes preuves concordantes."),
    "ubm-1001": ("Bref 2", "Disney+", "streaming",
                 ("https://www.disneyplus.com/browse/"
                 "entity-b329134e-b113-49d6-827e-dd4e0616457f"),
                 ("Page relevée : « Bref », créateurs Kyan Khojandi et Bruno "
                 "Muschio, période 2011-2025 — donc la suite y figure.")),
    "ubm-1450": ("Un documentaire sur les baleines", "france.tv", "streaming",
                 ("https://www.france.tv/documentaires/documentaires-animaliers/"
                 "8242656-le-souffle-de-vie.html"),
                 ("« Le souffle de vie », 1 h 6 min, disponible jusqu'en 2028. "
                 "Le titre de la reco est une description, pas un nom.")),
    # --- Billetteries -------------------------------------------------------
    "ubm-1932": ("300000 ans", "Fnac Spectacles", "buy",
                 ("https://www.fnacspectacles.com/artist/manon-bril/"
                 "manon-bril-300-000-ans-tournee-3934964/"),
                 ("Tournée de novembre 2026 à juin 2027, quinze dates. Page "
                 "ouverte dans le navigateur, l'anti-bot bloquant le HTTP "
                 "simple.")),
    "ubm-2379": ("Kheiron", "Fnac Spectacles", "buy",
                 "https://www.fnacspectacles.com/artist/kheiron/",
                 ("« 60 Minutes avec Kheiron - Dragon », trois dates d'octobre "
                 "2026 à mars 2027.")),
    "ubm-2512": ("Céline", "Site officiel", "buy",
                 "https://paris.celinedion.com/",
                 ("Sous-domaine du site OFFICIEL de l'artiste, annonçant la "
                 "résidence à Paris La Défense Arena. À ne pas confondre avec "
                 "le « Tribute Céline Dion » que BilletRéduc propose, et qui "
                 "est un spectacle hommage.")),
}


def transform(reco: dict[str, Any]) -> list[Change]:
    """Ajoute le lien vérifié prévu pour cette reco. Mute `reco` en place.

    Trois refus, tous normaux : la reco n'est pas dans la table, son titre a
    changé depuis la vérification, ou le lien est déjà là.
    """
    entree = LIENS.get(reco.get("id") or "")
    if entree is None:
        return []
    titre_attendu, label, kind, url, _ = entree
    if reco.get("title") != titre_attendu:
        return []

    liens = list(reco.get("links") or [])
    if any(isinstance(lien, dict) and lien.get("url") == url for lien in liens):
        return []

    avant = [lien.get("url") for lien in liens if isinstance(lien, dict)]
    liens.append({"label": label, "url": url, "kind": kind, "ethics": "neutral"})
    reco["links"] = liens
    return [Change(field="links", before=avant, after=avant + [url])]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ajoute les liens de visionnage et de billetterie trouvés "
                    "par la recherche déléguée du 2026-08-17, après "
                    "revérification un par un.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(transform, args, extra_report={"liens": len(LIENS)})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
