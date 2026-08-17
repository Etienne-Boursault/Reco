"""
fix_creator_aliases.py — fusionne les variantes d'un même `creator`.

Deux orthographes d'un même artiste scindent sa page en deux. Ce correctif
réécrit les variantes fautives vers la forme canonique — mais UNIQUEMENT
celles d'une table curée à la main, jamais par ressemblance automatique :
« Stephen Hawking » et « Stephen King » se ressemblent beaucoup et ne sont
pas la même personne.

Il fait donc DEUX choses distinctes :
  1. il applique `ALIASES` (table vérifiée, corrections sûres) ;
  2. il SIGNALE les groupes candidats (repli Unicode + distance d'édition)
     sans jamais les corriger — c'est à un humain de trancher.

TABLE VÉRIFIÉE — chaque ligne a été confrontée au titre d'article canonique
de Wikipédia FR (`action=query&redirects=1`), pas à une intuition.

RAPPORT DE VÉRIFICATION (2026-07-31) :
  - `Éléonore Costes`  : article « Éléonore Costes » → accents confirmés.
  - `Swann Périssé`    : article « Swann Périssé »   → accents confirmés.
  - `Vincent Delerm`   : article « Vincent Delerm »  → confirmé ; le lien
    Qobuz déjà présent sur ubm-0849 contient `vincent-delerm`.
  - `Nicolas Béguet`   : AUCUN article Wikipédia. La fiche TMDB/JustWatch du
    film qu'il a coréalisé (« Bref. De bons amis ») l'écrit « Nicolas Beguet »
    SANS accent — mais TMDB dépouille couramment les diacritiques français,
    donc cette source ne tranche pas. Ligne conservée telle que demandée,
    signalée comme non vérifiée.

  - `Matthieu Chedid`  : la consigne initiale demandait l'INVERSE
    (`Chedid → Chédid`). Elle était fautive : Wikipédia FR intitule l'article
    « Matthieu Chedid » SANS accent — comme « Louis Chedid » et « Andrée
    Chedid », c'est un patronyme d'origine libanaise — et les deux graphies
    accentuées y REDIRIGENT. Deezer enregistre la famille « Louis, Matthieu,
    Joseph & Anna Chedid ». La ligne a d'abord vécu dans `DISPUTED` le temps
    de la vérifier, puis a été appliquée dans le bon sens le 2026-07-31.

`DISPUTED` reste pour les groupes dont la forme canonique n'est pas tranchée :
signalés, jamais appliqués.

Usage :
    python fix_creator_aliases.py                      # dry-run (défaut)
    python fix_creator_aliases.py --json rapport.json  # + groupes candidats
    python fix_creator_aliases.py --apply              # écrit
"""
from __future__ import annotations

import argparse
import difflib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import dataset_fixes
from common import RECOS_DIR, log, read_json
from dataset_fixes import Change, add_common_args, iter_reco_files, run


def alias_roots() -> tuple[Path, ...]:
    """Collections balayées : `recos` ET `items`.

    `creator` vit dans les DEUX : une reco porte le nom, et l'item qu'elle
    référence le porte aussi. N'en corriger qu'une désynchronise le corpus — la
    page de l'œuvre et la carte afficheraient deux orthographes. Constaté le
    2026-07-31 : une première passe limitée aux recos a laissé 9 fichiers
    d'`items` sur l'ancienne graphie.

    FONCTION, et non constante de module : les chemins doivent être résolus À
    L'APPEL. Figés à l'import, ils ignorent la substitution que les tests font
    sur `dataset_fixes.RECOS_DIR` — et la suite écrit alors dans le VRAI corpus
    au lieu de son `tmp_path`. C'est arrivé le 2026-07-31, d'où ce commentaire.
    """
    return (dataset_fixes.RECOS_DIR, dataset_fixes.ITEMS_DIR)


#: Corrections appliquées. Clé = valeur fautive EXACTE, valeur = forme canonique.
ALIASES: dict[str, str] = {
    "Eleonore Costes": "Éléonore Costes",
    "Nicolas Beguet": "Nicolas Béguet",
    "Swann Perisse": "Swann Périssé",
    "Vincent Delherme": "Vincent Delerm",
    # Promu de `DISPUTED` le 2026-07-31, dans le sens INVERSE de la consigne
    # initiale (« Matthieu Chedid → Matthieu Chédid »), qui était fautive.
    # Contre-vérifié sur deux autorités indépendantes :
    #   - API Wikipédia FR : l'article canonique est « Matthieu Chedid », et
    #     « Mathieu Chédid » comme « Matthieu Chédid » y REDIRIGENT ;
    #   - API Deezer : la famille y est enregistrée « Louis, Matthieu, Joseph
    #     & Anna Chedid », sans accent (le nom de scène étant « -M- »).
    # Le corpus portait TROIS graphies sur des recos actives.
    "Mathieu Chédid": "Matthieu Chedid",
    "Matthieu Chédid": "Matthieu Chedid",
    # Mêmes graphies dans les libellés composés. « Grand-mère de … » désigne
    # Andrée Chedid et NON l'artiste : on corrige l'orthographe sans fusionner
    # les deux personnes.
    "M (Mathieu Chedid)": "M (Matthieu Chedid)",
    "Grand-mère de Mathieu Chédid": "Grand-mère de Matthieu Chedid",

    # --- Deuxième vague (2026-07-31) ------------------------------------
    # Trouvée en élargissant l'audit à `items` : la première passe, limitée aux
    # recos, ne voyait que 5 groupes sur 11. Chaque ligne ci-dessous a été
    # confrontée à l'article canonique de Wikipédia FR (redirections suivies) ;
    # la forme qui n'a PAS d'article est la fautive.
    #
    # Krief : les DEUX graphies du corpus étaient fausses. L'article s'intitule
    # « Bérengère Krief », avec un e — ce n'est pas un accent perdu mais une
    # faute, qu'aucune normalisation de diacritiques n'aurait détectée.
    "Bérangère Krief": "Bérengère Krief",
    "Bérangère Krièf": "Bérengère Krief",
    "BLACKPINK": "Blackpink",
    # Perel s'écrit SANS accent (comme Chedid, l'accent était l'erreur).
    "Esther Pérel": "Esther Perel",
    "Julia de Funes": "Julia de Funès",
    "Les inconnus": "Les Inconnus",
    "Rosalia": "Rosalía",
    "Tiesto": "Tiësto",
    # Troisième variante de Delerm rencontrée, après « Delherme ».
    "Vincent de Lerme": "Vincent Delerm",
    "Mehdi Moussaid": "Mehdi Moussaïd",
    # `Nassím` (accent aigu ibérique) n'a pas d'article ; `Nassim` en a un.
    "Nassím": "Nassim",

    # --- Troisième vague (2026-08-16) -----------------------------------
    # Sortie d'un angle NEUF : au lieu de comparer les noms entre eux, on a
    # cherché les TITRES identiques dont les liens n'avaient aucun hôte en
    # commun. Les variantes de nom qui restaient s'y sont révélées d'elles-
    # mêmes. Chacune est confrontée à l'article canonique de Wikipédia FR ;
    # la forme sans article est la fautive.
    "Ana Aptair": "Anna Apter",
    # « Luke Rhinehart » est le pseudonyme de George Cockcroft (article
    # « Luke Rhinehart (George Cockcroft) »). Deux fautes dans le corpus.
    "Luke Reinhardt": "Luke Rhinehart",
    "Luc Reinhardt": "Luke Rhinehart",
    "Morgan Cadignan": "Morgane Cadignan",
    # Cinq graphies pour Orelsan, dont des transcriptions phonétiques du nom
    # prononcé à l'oral. `Orel San` et `Aurel San` portent le MÊME lien Deezer
    # (artiste 259467) que `Orelsan`, ce qui lève tout doute ; les autres
    # n'apparaissent que sur des recos écartées, dont les titres — Civilisation,
    # Basic, Perdu d'avance, Comment c'est loin — ne laissent pas d'ambiguïté.
    # Vérification NÉCESSAIRE : « Aurel » est aussi le nom d'un dessinateur
    # français, et fusionner sans regarder aurait pu confondre deux personnes.
    "Orel San": "Orelsan",
    "Aurel San": "Orelsan",
    "Aurel Sann": "Orelsan",
    "Aurelsan": "Orelsan",
    "Aurel": "Orelsan",
    # `Mourad` seul ne porte qu'un titre, « L'amour c'est surcoté », qui est le
    # livre de Mourad Winter — vérifié avant de fusionner, l'article Wikipédia
    # « Mourad » existant par ailleurs pour d'autres personnes.
    "Mourad": "Mourad Winter",

    # --- Quatrième vague (2026-08-16) -----------------------------------
    # Issue des groupes que `align_same_work_links` avait REFUSÉ d'aligner
    # faute de créateurs concordants : le refus lui-même désignait les noms à
    # examiner. Chaque ligne est vérifiée auprès de TMDB ou de Wikipédia.
    #
    # Florence Longpré, créatrice ET scénariste d'« Empathie » (TMDB tv/284656).
    "Florence Lomp": "Florence Longpré",
    "Florence Lompré": "Florence Longpré",
    # Mélody Mourey — article Wikipédia avec l'accent.
    "Melody Mourey": "Mélody Mourey",
    # « Iris » (2024) est créée, réalisée et interprétée par Doria Tillier
    # (TMDB). « Doriane » est une transcription du prénom entendu à l'oral, et
    # n'apparaît que sur cette œuvre.
    "Doriane": "Doria Tillier",
    "Team Dup": "Tim Dup",
    # Un seul duo, cinq graphies. « Navo » est le NOM DE SCÈNE de Bruno
    # Muschio : « Bruno Muschio (Navo) » n'est donc pas un crédit différent.
    # TMDB donne « Kyan Khojandi, Bruno Muschio » comme créateurs de Bref.
    "Kyan Khojandi & Brunio Muschio": "Kyan Khojandi, Bruno Muschio",
    "Kyan Khojandi & Bruno Muschio": "Kyan Khojandi, Bruno Muschio",
    "Bruno Muschio, Kyan Khojandi": "Kyan Khojandi, Bruno Muschio",
    "Kyan Khojandi, Bruno Muschio (Navo)": "Kyan Khojandi, Bruno Muschio",
    # Le nom de la CHAÎNE mis à la place de son auteur. Le champ `creator`
    # désigne une personne ; le titre porte déjà le nom de la chaîne.
    "Peaceful Cuisine": "Ryoya Takashima",
}

#: Groupes réels mais dont la forme canonique est CONTESTÉE : signalés, jamais
#: appliqués. Les corriger demande un arbitrage humain, pas une heuristique.
#: VIDE aujourd'hui. Le groupe « Matthieu Chedid » y a séjourné le temps de
#: vérifier sa forme canonique, puis est passé dans `ALIASES` — une liste de
#: litiges qu'on ne vide jamais devient un cimetière qu'on cesse de lire.
DISPUTED: list[dict[str, Any]] = []

#: Valeurs qui ne désignent aucun artiste : elles polluent la détection de
#: doublons et relèvent d'un autre correctif (vider le champ).
PLACEHOLDERS = frozenset({"inconnu", "autre", "autres", "non specifie", "n/a", "?"})

_SPACES_RE = re.compile(r"[\s ]+")


def fold(value: str) -> str:
    """Forme repliée : sans diacritiques, casse repliée, espaces normalisés.

    Sert UNIQUEMENT à regrouper des candidats à soumettre à un humain.

    >>> fold("Éléonore  Costes")
    'eleonore costes'
    >>> fold("Section d’Assaut") == fold("section d'assaut")
    True
    """
    decomposed = unicodedata.normalize("NFD", value)
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    lowered = stripped.casefold().replace("’", "'").replace("ʼ", "'")
    return _SPACES_RE.sub(" ", lowered.replace("-", " ")).strip()


def transform(reco: dict[str, Any]) -> list[Change]:
    """Réécrit `creator` s'il figure dans `ALIASES`. Mute `reco` en place.

    Ne remplit JAMAIS un `creator` absent ou vide — le correctif ne fait que
    réécrire une valeur déjà présente. C'est ce qui le rend structurellement
    incapable de violer `tools/creators_exclusions.txt`, dont la règle est
    « ce creator doit rester VIDE ».
    """
    current = reco.get("creator")
    # `null` ou chaîne vide : ce n'est pas une absence, c'est une absence MAL
    # ÉCRITE. La collection `recos` déclare `creator: z.string().optional()`,
    # sans `nullable` : un `creator: null` y fait échouer le build Astro entier
    # (« Expected type string, received object », Zod rapportant `null` comme
    # un objet). La seule représentation valable est l'ABSENCE DE CLÉ — c'est
    # celle des 902 recos sans créateur connu.
    if "creator" in reco and (current is None
                              or (isinstance(current, str) and not current.strip())):
        del reco["creator"]
        return [Change(field="creator", before=current, after=None)]
    if not isinstance(current, str):
        return []
    if current in ALIASES:
        canonical = ALIASES[current]
        reco["creator"] = canonical
        return [Change(field="creator", before=current, after=canonical)]
    # PLACEHOLDER → champ VIDÉ. « N/A », « Inconnu », « ? » ne sont pas des
    # noms : ce sont des trous déguisés en valeurs. Les garder coûte deux fois
    # — ils s'affichent tels quels sur la carte, et ils font croire à des
    # dizaines d'œuvres qu'elles partagent un créateur, ce qui fausse toute
    # détection de doublons (33 occurrences relevées le 2026-08-16).
    # La table `ALIASES` est consultée AVANT : une valeur explicitement curée
    # l'emporte sur la règle générique.
    if fold(current) in PLACEHOLDERS:
        # RETIRÉ, pas mis à `null` : cf. la note en tête de fonction.
        del reco["creator"]
        return [Change(field="creator", before=current, after=None)]
    return []


def collect_creators(source: str | None = None) -> dict[str, list[str]]:
    """Toutes les valeurs `creator` du corpus → les ids qui les portent."""
    by_value: dict[str, list[str]] = defaultdict(list)
    # Même périmètre que la correction (cf. ALIAS_ROOTS) : auditer les seules
    # recos donnerait un diagnostic plus propre que la réalité, en masquant les
    # variantes qui ne subsistent que dans `items`.
    for path in iter_reco_files(source, alias_roots()):
        try:
            data = read_json(path)
        except (OSError, ValueError) as exc:
            log.warning("  Ignoré (lecture impossible) %s : %s", path.name, exc)
            continue
        creator = data.get("creator")
        if isinstance(creator, str) and creator.strip():
            by_value[creator].append(data.get("id") or path.stem)
    return dict(by_value)


def _entry(value: str, by_value: dict[str, list[str]]) -> dict[str, Any]:
    return {"valeur": value, "occurrences": len(by_value[value]), "ids": by_value[value][:8]}


def folding_groups(by_value: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Groupes dont les variantes ne diffèrent que par accents / casse / espaces."""
    buckets: dict[str, list[str]] = defaultdict(list)
    for value in by_value:
        buckets[fold(value)].append(value)
    groups = []
    for folded, variants in sorted(buckets.items()):
        if len(variants) < 2:
            continue
        groups.append({
            "cle": folded,
            "placeholder": folded in PLACEHOLDERS,
            "variantes": [_entry(v, by_value) for v in sorted(variants)],
        })
    return groups


def similarity_pairs(
    by_value: dict[str, list[str]], threshold: float
) -> list[dict[str, Any]]:
    """Paires proches par distance d'édition — bruit assumé, à filtrer à la main.

    C'est cette passe qui rattrape « Vincent Delherme » vs « Vincent Delerm » :
    le repli Unicode ne les regroupe pas (le `h` n'est pas un diacritique).
    """
    folded_map: dict[str, list[str]] = defaultdict(list)
    for value in by_value:
        folded_map[fold(value)].append(value)
    keys = sorted(k for k in folded_map if k not in PLACEHOLDERS)
    pairs = []
    for i, left in enumerate(keys):
        for right in keys[i + 1:]:
            if abs(len(left) - len(right)) > 3:
                continue
            ratio = difflib.SequenceMatcher(None, left, right).ratio()
            if ratio < threshold:
                continue
            pairs.append({
                "similarite": round(ratio, 3),
                "a": [_entry(v, by_value) for v in sorted(folded_map[left])],
                "b": [_entry(v, by_value) for v in sorted(folded_map[right])],
            })
    return sorted(pairs, key=lambda p: -p["similarite"])


def audit(source: str | None, threshold: float) -> dict[str, Any]:
    """Diagnostic complet : à corriger, contesté, à arbitrer."""
    by_value = collect_creators(source)
    return {
        "creators_distincts": len(by_value),
        "alias_appliques": ALIASES,
        "canoniques_contestees": DISPUTED,
        "groupes_repli_unicode": folding_groups(by_value),
        "paires_similaires": similarity_pairs(by_value, threshold),
    }


def log_audit(report: dict[str, Any]) -> None:
    """Rend le diagnostic lisible en console — les décisions restent humaines."""
    for item in report["canoniques_contestees"]:
        log.warning("CONTESTÉ · %s : %s", item["groupe"], item["constat"])
        log.warning("    non appliqué. Forme probable : %s", item["canonique_probable"])
    groups = [g for g in report["groupes_repli_unicode"] if not g["placeholder"]]
    log.info("À ARBITRER · %d groupe(s) accents/casse, %d paire(s) proches "
             "(détail dans --json).", len(groups), len(report["paires_similaires"]))
    for group in groups:
        variants = " | ".join(f"{v['valeur']!r} x{v['occurrences']}" for v in group["variantes"])
        log.info("    %s", variants)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fusionne les variantes orthographiques d'un même `creator` "
                    "(table curée) et signale les groupes candidats restants.")
    add_common_args(parser)
    parser.add_argument("--similarity", type=float, default=0.90,
                        help="Seuil de la passe distance d'édition (défaut : 0.90).")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = audit(args.source, args.similarity)
    log_audit(report)
    run(transform, args, roots=alias_roots(),
        extra_report={"audit": report, "recos_dir": RECOS_DIR.as_posix()})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
