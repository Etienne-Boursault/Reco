"""
fix_tmdb_ids.py — pose l'identifiant TMDB des œuvres que la recherche a laissées.

POURQUOI CE MODULE EXISTE
-------------------------
`enrich_video_links --search` exige l'égalité stricte du titre PUIS l'unicité du
résultat. C'est une bonne règle : elle refuse « Friends » parce que TMDB en
renvoie vingt, et un mauvais choix vaudrait pire que l'absence. Mais elle laisse
sans fiche des œuvres que personne n'hésiterait à identifier — Friends, Drive,
La Chèvre, Before Sunrise.

Ce module ne remplace pas ce garde-fou : il tranche les cas où l'ambiguïté est
levée par une information que la machine n'avait pas. Chaque entrée a été
décidée en regardant les candidats TMDB ET les liens déjà posés sur la reco :
`sooner.fr/films/mr-nobody` désigne le film de 2009, `lacinetek.com/…/panique-
julien-duvivier` celui de 1947, l'identifiant Netflix 70184207 la version
américaine de Shameless. Le lien existant sert de témoin.

CE QUE CE MODULE N'ÉCRIT PAS
----------------------------
Aucun lien. On pose l'IDENTIFIANT, puis `enrich_video_links` fait le reste — et
au passage revérifie le titre contre la fiche complète. Une entrée fautive de la
table ci-dessous ressort donc en `title-mismatch` au lieu de devenir un lien
visible : la décision reste réfutable après coup, ce qu'une URL écrite à la main
n'aurait pas été.

Les cas ÉCARTÉS le sont à dessein et le restent : « L'agence » (le seul candidat
au titre exact est *The Adjustment Bureau*, dont c'est le titre français —
l'œuvre recommandée est la télé-réalité Netflix), « Définition » (chaîne de
Shirley Souagnon, absente de TMDB), « L'Avare » (aucun candidat en 1980, l'année
du film de Louis de Funès), « Takeshi Castle » (l'original de 1986 et la reprise
de 2002 sont deux fiches, et le lien Pluto.tv ne dit pas laquelle).
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

from dataset_fixes import Change, add_common_args, run

#: `id de reco` → (titre ATTENDU, type TMDB, identifiant TMDB).
#:
#: Le titre attendu est une GARDE, pas une donnée : si le corpus a changé
#: depuis la décision, l'entrée ne s'applique plus. Une reco renommée peut
#: désigner une autre œuvre, et poser sur elle un identifiant décidé pour
#: l'ancienne serait exactement l'erreur que ce module cherche à éviter.
IDENTIFIANTS: dict[str, tuple[str, str, str]] = {
    # --- Séries -----------------------------------------------------------
    "ubm-0058": ("Genre Humaine", "tv", "96581"),
    "ubm-0862": ("Montre jamais ça à personne", "tv", "135184"),
    "ubm-1043": ("Looking", "tv", "57774"),
    "ubm-1258": ("Selon Thomas", "tv", "99978"),
    # Netflix 70184207 est la version AMÉRICAINE : tv/34307, pas la
    # britannique de 2004 (tv/1906), qui porte le même titre.
    "ubm-1473": ("Shameless", "tv", "34307"),
    "ubm-1530": ("Friends", "tv", "1668"),
    "ubm-2296": ("Family Business", "tv", "89785"),
    # Klapisch, 2023 : une SÉRIE, bien que la reco la type `film`.
    "ubm-2333": ("Salade grecque", "tv", "121459"),
    # Titre français « Apprentis quarterbacks » — d'où l'échec de la
    # comparaison stricte, alors que l'identifiant Netflix 81003033 tranche.
    "ubm-2527": ("QB1", "tv", "70274"),
    # Titre français « Histoires d'amour et d'autisme ». Netflix 81265493 est
    # la déclinaison américaine (2022), non l'australienne de 2019.
    "ubm-2667": ("Love on the Spectrum", "tv", "200731"),
    "ubm-3016": ("Sport Science", "tv", "18820"),
    "ubm-3154": ("The Curse", "tv", "114655"),
    # --- Films ------------------------------------------------------------
    # Duvivier, 1947 — confirmé par le lien LaCinetek déjà posé.
    # Identifies par l'agent visionnage, et non par l'agent fiches : c'est la
    # recherche d'un moyen de VOIR l'œuvre qui a fini par l'identifier.
    # Le precedent identifiant de « Run » etait faux et a ete retire ; celui-ci
    # est la serie HBO de 2020, diffusee en France par Lionsgate+.
    "ubm-0715": ("Run", "tv", "87393"),
    # Court-metrage de Cedric Klapisch (1986), disponible chez LaCinetek et
    # Sooner — ce que la reco ne disait pas, ses deux liens etant des fiches.
    "ubm-2332": ("In Transit", "movie", "352038"),
    "ubm-0255": ("Panique", "movie", "43462"),
    "ubm-0291": ("The Legend of Hei", "movie", "620249"),
    "ubm-0339": ("Bref. De bons amis", "movie", "1437733"),
    "ubm-0777": ("This is John", "movie", "275061"),
    # Lubitsch, 1942 ; TMDB le titre « Jeux dangereux » en français.
    "ubm-1000": ("To Be or Not to Be", "movie", "198"),
    "ubm-1787": ("House of Dynamite", "movie", "1290159"),
    "ubm-1788": ("Irréversible", "movie", "979"),
    # `sooner.fr/films/mr-nobody` désigne le film de 2009.
    "ubm-1804": ("Mister Nobody", "movie", "31011"),
    "ubm-2081": ("Bref. De bons amis", "movie", "1437733"),
    "ubm-2330": ("En corps", "movie", "771077"),
    # Grand Corps Malade, 2017 — pas l'homonyme de 2004.
    "ubm-2518": ("Patients", "movie", "434616"),
    # `sooner.fr/films/mignonnes` : le titre de la reco est au singulier.
    "ubm-2639": ("Mignonne", "movie", "582885"),
    # De Funès, 1966 — pas les homonymes de 2010 et 2011.
    "ubm-2921": ("Le Grand Restaurant", "movie", "19548"),
    "ubm-2928": ("Man on the Moon", "movie", "1850"),
    "ubm-2970": ("La règle du jeu", "movie", "776"),
    # 1981. La reco porte 1985, qui est une erreur de date, pas une autre
    # œuvre : `universcine.com/films/la-chevre` ne connaît que celui-là.
    "ubm-3109": ("La Chèvre", "movie", "19123"),
    "ubm-3121": ("Crazy, Stupid, Love", "movie", "50646"),
    "ubm-3122": ("God Bless America", "movie", "74306"),
    # Refn, 2011 — pas la série homonyme de 2007.
    "ubm-3134": ("Drive", "movie", "64690"),
    "ubm-3179": ("Before Sunrise", "movie", "76"),
    "ubm-3180": ("Before Midnight", "movie", "132344"),

    # =======================================================================
    # Télé-réalité coréenne de Netflix, titrée « À l'épreuve du diable » en
    # français : la recherche par titre exact ne pouvait pas la trouver.
    "ubm-0282": ("Devil's Plan", "tv", "214582"),
    # PAS « The Adjustment Bureau », dont « L'Agence » est le titre français —
    # c'est le piège de ce cas. L'identifiant Netflix 81417684 de la reco mène
    # à la télé-réalité sur la famille Kretz, que TMDB titre « The Parisian
    # Agency ».
    "ubm-0294": ("L'agence", "tv", "112747"),
    # TMDB ne fait pas de fiche distincte pour « Bref 2 » : la saison 2 vit
    # dans la fiche de « Bref ». C'est donc bien elle qu'on désigne.
    "ubm-1001": ("Bref 2", "tv", "60715"),
    # « Kôkôrikô ! » de Jean-Pascal Zadi : le titre de la reco est une
    # transcription phonétique.
    "ubm-1106": ("Coco Rico", "tv", "227640"),
    "ubm-1668": ("LOL", "tv", "122228"),
    "ubm-1890": ("Jim and Andy", "movie", "469019"),
    "ubm-1937": ("Bref 2", "tv", "60715"),
    # L'ORIGINAL japonais de 1986, pas la reprise de 2002 : tranché par le
    # transcript, où l'animateur parle de Takeshi Kitano lui-même.
    "ubm-1951": ("Takeshi Castle", "tv", "106964"),
    "ubm-2008": ("Loup-Garou Saison 2", "tv", "270963"),
    # La citation tranche : « une émission que j'adore, QUI EST EN FRANCE
    # MAINTENANT ÉGALEMENT ». C'est l'originale américaine qui est
    # recommandée, la déclinaison française n'étant mentionnée qu'en surcroît.
    "ubm-2094": ("Drag Race", "tv", "8514"),
    "ubm-2286": ("FranceKebek", "tv", "88192"),
    "ubm-2528": ("Sunderland Till I Die", "tv", "84777"),
    "ubm-2745": ("Ça sera (peut-être) mieux après", "tv", "137117"),
    "ubm-2892": ("LOL", "tv", "122228"),
    "ubm-2925": ("La Soupe au Chou", "movie", "9317"),
    # De Funès, 1980 — l'année qu'aucune recherche par titre ne remontait.
    "ubm-2926": ("L'Avare", "movie", "11680"),
    "ubm-3031": ("Inside", "movie", "823754"),
    "ubm-3147": ("NTM Authentiques : Un an avec le suprême", "movie", "95309"),
}


#: Corrections que la fiche TMDB, une fois l'identifiant confirmé, révèle dans
#: la reco elle-même. Elles ne viennent pas d'un jugement sur le goût : la
#: passe d'enrichissement a REFUSÉ de poser un lien parce que la reco
#: contredisait la fiche, et c'est la reco qui avait tort.
#:
#: Format : `id` → (champ, valeur ATTENDUE avant, valeur après). La valeur
#: attendue est la garde : si quelqu'un a corrigé entre-temps, on ne touche à
#: rien.
RECTIFICATIONS: dict[str, tuple[str, Any, Any]] = {
    # Le film de Jaco Van Dormael s'intitule « Mr. Nobody ». La reco écrivait
    # le mot en toutes lettres, ce qui n'est le titre d'aucune œuvre.
    "ubm-1804": ("title", "Mister Nobody", "Mr. Nobody"),
    # « La Chèvre » de Francis Veber est de 1981. 1985 est l'année du
    # troisième film du duo Richard/Depardieu, « Les Compères » étant de 1983 :
    # une date glissée, pas une autre œuvre.
    "ubm-3109": ("year", 1985, 1981),
}


#: Identifiants FAUX déjà présents dans le corpus — `id` → (identifiant
#: ACTUEL attendu, nouvel identifiant ou `None` pour retirer, nouveau type).
#:
#: POURQUOI CETTE TABLE EXISTE
#: `_identifier` refuse d'écraser un identifiant en place, et c'est la bonne
#: règle : il peut venir d'une relecture humaine. Mais elle laissait donc
#: intacts des identifiants FAUX, et un audit des 221 recos qui en portent un
#: en a trouvé quatorze : « Titanic » désignait un documentaire de 2012,
#: « Brazil » un film brésilien de 1952, « Vice » le « Vice-versa » de Pixar,
#: « To Be or Not to Be » le remake de 1983 au lieu du Lubitsch de 1942.
#:
#: Ces identifiants ne s'affichent NULLE PART, et c'est ce qui les rend
#: dangereux : une passe d'enrichissement peut les promouvoir en lien visible
#: des mois plus tard. Seules les gardes de titre et d'année de
#: `enrich_video_links` les avaient contenus jusqu'ici — silencieusement.
#:
#: L'identifiant actuel sert de garde : si quelqu'un a corrigé entre-temps,
#: on ne touche à rien.
REMPLACEMENTS: dict[str, tuple[str, str | None, str | None]] = {
    # Le lien LaCinetek de la reco nomme le réalisateur et tranche à lui seul.
    "ubm-0255": ("96903", "43462", "movie"),      # « Panique! » 2009 -> Duvivier 1947
    "ubm-0397": ("818681", "10531", "movie"),     # homonyme 1990 -> Polanski 1994
    "ubm-0966": ("386948", "68", "movie"),        # « Beautiful Brazil » -> Gilliam 1985
    # La citation nomme « deux Funès et Jean Marais » : c'est le film de 1964,
    # pas le muet de 1913.
    "ubm-0666": ("319287", "1871", "movie"),
    # La citation dit « de Lubitsch » : 1942, pas le remake de 1983.
    "ubm-1000": ("22998", "198", "movie"),
    # Un documentaire de 2012 SUR le Titanic, au lieu du film de Cameron.
    "ubm-0546": ("102041", "597", "movie"),
    # « Vice-versa » de Pixar au lieu du « Vice » d'Adam McKay (2018), que
    # désignent pourtant les liens Sooner et AlloCiné de la reco.
    "ubm-0797": ("150540", "429197", "movie"),
    "ubm-1138": ("150540", "429197", "movie"),
    # « Papa » avec Alain Chabat est de 2005, pas l'homonyme de 2018.
    "ubm-0827": ("523926", "59163", "movie"),
    # « Looking up to Magical Girls » (2024) au lieu de la série HBO de 2014,
    # que le lien HBO Max de la reco désigne pourtant.
    "ubm-1043": ("236338", "57774", "tv"),
    # « The Legend of Brown Sugar Chivalries » au lieu du film de 2019 :
    # l'API d'ADN, dont la reco porte le lien, le donne comme un FILM.
    "ubm-0291": ("16339", "620249", "movie"),
    # --- Retraits sans remplacement ----------------------------------------
    # Aucun candidat ne s'impose, et un identifiant faux vaut moins que pas
    # d'identifiant du tout.
    "ubm-0715": ("11912", None, None),            # « Sauve qui peut » 1965
    "ubm-1363": ("49064", None, None),            # « Une grande bagarre » 1933
    # Le pire cas de l'audit : l'identifiant TMDB **et** l'identifiant IMDb
    # désignent « Close Up with The Hollywood Reporter », alors que la reco
    # parle d'une websérie française — et le lien TMDB était DÉJÀ VISIBLE sur
    # le site. Le lien et l'identifiant IMDb partent via `fix_reco_anomalies`.
    "ubm-1045": ("63498", None, None),
}


def transform(reco: dict[str, Any]) -> list[Change]:
    """Pose `externalIds.tmdb` et `tmdbType`. Mute `reco` en place.

    Trois refus, tous silencieux parce qu'ils sont normaux :

    - la reco n'est pas dans la table ;
    - son titre n'est plus celui pour lequel la décision a été prise ;
    - elle porte DÉJÀ un identifiant TMDB, qu'on n'écrase jamais — il peut
      venir d'une relecture humaine, mieux informée que cette table.
    """
    changes = _remplacer(reco)
    changes += _identifier(reco)
    # L'ORDRE COMPTE. `RECTIFICATIONS` corrige le titre de « Mister Nobody » en
    # « Mr. Nobody », alors que la garde d'`IDENTIFIANTS` attend l'ancien : les
    # inverser empêcherait la pose de l'identifiant sur un corpus neuf, et le
    # module ne ferait plus la moitié de son travail sans rien signaler.
    return changes + _rectifier(reco)


def _remplacer(reco: dict[str, Any]) -> list[Change]:
    """Corrige ou retire un identifiant TMDB faux. Mute `reco` en place.

    Tourne AVANT `_identifier`, pour que la reco se retrouve sans identifiant
    et puisse en recevoir un par la voie normale si `IDENTIFIANTS` en prévoit
    un — sinon un retrait ici serait aussitôt inutile.
    """
    entree = REMPLACEMENTS.get(reco.get("id") or "")
    if entree is None:
        return []
    actuel, nouveau, genre = entree
    ids = reco.get("externalIds")
    if not isinstance(ids, dict) or str(ids.get("tmdb") or "") != actuel:
        return []

    if nouveau is None:
        ids.pop("tmdb", None)
        ids.pop("tmdbType", None)
        if not ids:
            reco.pop("externalIds", None)
        return [Change(field="externalIds.tmdb", before=actuel, after=None)]

    ids["tmdb"] = nouveau
    ids["tmdbType"] = genre
    return [Change(field="externalIds.tmdb", before=actuel,
                   after=f"{genre}/{nouveau}")]


def _identifier(reco: dict[str, Any]) -> list[Change]:
    """Pose `externalIds.tmdb` et `tmdbType` si la table le prévoit."""
    entree = IDENTIFIANTS.get(reco.get("id") or "")
    if entree is None:
        return []
    titre_attendu, genre, tmdb_id = entree
    if reco.get("title") != titre_attendu:
        return []

    ids = reco.get("externalIds")
    if not isinstance(ids, dict):
        ids = {}
    if ids.get("tmdb"):
        return []

    ids["tmdb"] = tmdb_id
    ids["tmdbType"] = genre
    reco["externalIds"] = ids
    return [Change(field="externalIds.tmdb", before=None,
                   after=f"{genre}/{tmdb_id}")]


def _rectifier(reco: dict[str, Any]) -> list[Change]:
    """Applique la rectification prévue pour cette reco, s'il y en a une.

    Séparée de la pose d'identifiant parce qu'elle survit à celle-ci : une
    reco déjà pourvue d'un `externalIds.tmdb` sort tôt de `transform`, et sa
    rectification doit tout de même s'appliquer.
    """
    entree = RECTIFICATIONS.get(reco.get("id") or "")
    if entree is None:
        return []
    champ, avant, apres = entree
    if reco.get(champ) != avant:
        return []
    reco[champ] = apres
    return [Change(field=champ, before=avant, after=apres)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pose l'identifiant TMDB des œuvres que la recherche "
                    "automatique laisse sans fiche, faute de pouvoir lever "
                    "l'ambiguïté. N'écrit AUCUN lien : "
                    "`enrich_video_links` s'en charge et revérifie le titre.")
    return add_common_args(parser)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run(transform, args, extra_report={"entrees": len(IDENTIFIANTS)})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
