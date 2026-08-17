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


def transform(reco: dict[str, Any]) -> list[Change]:
    """Pose `externalIds.tmdb` et `tmdbType`. Mute `reco` en place.

    Trois refus, tous silencieux parce qu'ils sont normaux :

    - la reco n'est pas dans la table ;
    - son titre n'est plus celui pour lequel la décision a été prise ;
    - elle porte DÉJÀ un identifiant TMDB, qu'on n'écrase jamais — il peut
      venir d'une relecture humaine, mieux informée que cette table.
    """
    changes = _identifier(reco)
    # L'ORDRE COMPTE. `RECTIFICATIONS` corrige le titre de « Mister Nobody » en
    # « Mr. Nobody », alors que la garde d'`IDENTIFIANTS` attend l'ancien : les
    # inverser empêcherait la pose de l'identifiant sur un corpus neuf, et le
    # module ne ferait plus la moitié de son travail sans rien signaler.
    return changes + _rectifier(reco)


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
