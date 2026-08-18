"""
fusion_items_doublons.py — fusionne les items prouves identiques.

LE PROBLEME
-----------
La collection `items` porte l'oeuvre CANONIQUE : une entree par oeuvre, que
les galeries et les pages `/oeuvre/` affichent. Le releve du 2026-08-18 y a
trouve 211 entrees redondantes sur 179 titres. « Bref » y existait SIX fois,
et `/series` l'affichait quatre fois.

La consequence ne se limite pas aux galeries. Chaque doublon fabrique une page
`/oeuvre/` de plus, ne portant qu'une FRACTION des mentions — la page censee
tout rassembler est elle-meme eclatee. Et la recherche du site, dont 81 % des
entrees sont des pages d'oeuvre, propose ces doublons au visiteur.

CE QUE CET OUTIL TRAITE, ET CE QU'IL LAISSE
-------------------------------------------
Uniquement le palier PROUVE : deux items portant le meme identifiant TMDB
designent la meme oeuvre, sans jugement a rendre. Cela couvre 23 des 211
entrees redondantes.

Les 188 autres relevent du jugement — meme createur sans identifiant, ou
createurs divergents — et sortent volontairement du perimetre. Un outil qui
tranche a la place de l'editeur sur des cas douteux ne rend pas service : il
deplace l'erreur la ou personne ne la relira.

POURQUOI LE REFUS EST LE COMPORTEMENT PAR DEFAUT
------------------------------------------------
Fusionner est DESTRUCTEUR : on supprime des fichiers et on reporte les
references des mentions. Une erreur ne se voit pas le jour meme, elle se
decouvre des mois plus tard.

Or l'identifiant TMDB, cense etre la preuve, s'est revele faux dans deux cas
sur vingt-quatre :

    movie/1018  porte par « Drive » (Nicolas Winding Refn, 2011)
                ... alors que movie/1018 EST « Mulholland Drive » (Lynch, 2001)
    tv/60715    porte par « Bref 2 » (Kyan Khojandi)
                ... alors que tv/60715 EST « Bref » (2011)

Fusionner sur la seule foi de l'identifiant aurait confondu Drive avec
Mulholland Drive. L'outil refuse donc TOUT groupe dont les titres divergent
apres normalisation, sauf variante explicitement justifiee ci-dessous. Une
variante oubliee laisse un doublon ; une fusion abusive detruit. L'asymetrie
dicte le defaut.

IDENTIFIANTS FAUX RELEVES, A CORRIGER SEPAREMENT
------------------------------------------------
Ces items portent un identifiant qui designe une autre oeuvre. La fusion les
laisse tranquilles ; leur correction est un autre travail.

    « Drive »   -> movie/1018 est Mulholland Drive
    « Bref 2 »  -> tv/60715 est Bref (2011)
    « Bagar(re) » -> movie/49064 est « Une grande bagarre » (1933), alors que
                  la citation dit « aller voir Bagar le 15 avril », spectacle
                  de Julien Royal
    « Mortal »  -> tv/90591 est « Pecado Mortal », telenovela bresilienne
    « Iris »    -> tv/31505 est une serie coreenne de 2009, quand le corpus
                  lie cette reco a Canal+ France (a verifier)
"""
from __future__ import annotations

import argparse
import json
import logging
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import common  # type: ignore[attr-defined]

log = logging.getLogger("fusion_items")

#: Articles ignores : « The White Lotus » et « White Lotus » sont la meme
#: serie, et les deux graphies circulent dans les transcripts.
_ARTICLES = ("le ", "la ", "les ", "l'", "the ", "a ", "an ", "un ", "une ")

#: Groupes dont les titres divergent mais qu'on fusionne QUAND MEME, avec le
#: motif. Sans cette declaration, le groupe est refuse — c'est ce qui protege
#: « Drive » de « Mulholland Drive », volontairement absent de cette table.
VARIANTES_ADMISES: dict[tuple[str, str], str] = {
    ("movie", "1317288"): (
        "« Marty Suprem » est une coquille de « Marty Supreme » : l'API TMDB "
        "donne « Marty Supreme » (2025) pour cet identifiant."),
    ("movie", "467244"): (
        "« Zone of Interest » est le titre ANGLAIS de « La Zone d'intérêt » "
        "(2023) ; l'API TMDB rend le titre français pour cet identifiant."),
    ("movie", "49064"): (
        "« Bagar » et « Bagarre » portent la MEME citation — « aller voir "
        "Bagar le 15 avril » — donc la meme oeuvre. Leur identifiant TMDB est "
        "faux par ailleurs (movie/49064 = « Une grande bagarre », 1933), ce "
        "qui est un autre sujet."),
    ("tv", "60625"): (
        "« Rick et Morty » est le titre français de « Rick and Morty » ; les "
        "deux graphies circulent dans les transcripts."),
}


#: Titre a imposer, pour les variantes ou l'un des libelles est FAUTIF.
#:
#: Le survivant est choisi au nombre de mentions, pas a la justesse de son
#: titre : la premiere passe a promu « Marty Suprem » — la coquille — et
#: relegue l'orthographe correcte en alias. Le visiteur lisait la faute sur la
#: page de l'oeuvre. Ici, on sait quel titre est le bon.
TITRE_CANONIQUE: dict[tuple[str, str], str] = {
    ("movie", "1317288"): "Marty Supreme",
    # Site francophone : le titre français prime sur l'anglais.
    ("movie", "467244"): "La Zone d'intérêt",
}


def normaliser(titre: str) -> str:
    """Reduit un titre a ce qui le distingue vraiment.

    Casse, accents, ponctuation et article initial ne distinguent pas deux
    oeuvres. Tout le reste, si : c'est cette severite qui bloque « Drive »
    contre « Mulholland Drive ».

    L'apostrophe est SUPPRIMEE et non remplacee par une espace, sinon
    « Don't F**k with Cats » et « Dont F**k with Cats » — les deux graphies
    presentes dans le corpus — ne se rejoindraient pas.
    """
    t = unicodedata.normalize("NFKD", titre.strip().lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    # L'article part AVANT que l'apostrophe disparaisse, sans quoi « l'X »
    # deviendrait « lx » et l'article ne serait plus reconnaissable.
    for article in _ARTICLES:
        if t.startswith(article):
            t = t[len(article):]
            break
    t = t.replace("'", "").replace("’", "")
    t = "".join(c if c.isalnum() or c.isspace() else " " for c in t)
    return " ".join(t.split())

def fusionnable(cle: tuple[str, str], groupe: Sequence[dict[str, Any]]) -> bool:
    """Le groupe peut-il etre fusionne sans arbitrage humain ?"""
    titres = {normaliser(d.get("title") or "") for d in groupe}
    return len(titres) == 1 or cle in VARIANTES_ADMISES


def choisir_survivant(groupe: Sequence[dict[str, Any]],
                      mentions: dict[str, int]) -> dict[str, Any]:
    """Le mieux etabli l'emporte : celui que le plus de mentions designent.

    A egalite, l'identifiant le plus petit tranche. Sans cette regle, deux
    executions produiraient deux corpus differents et le diff deviendrait
    illisible.
    """
    return min(groupe, key=lambda d: (-mentions.get(d.get("id") or "", 0),
                                      d.get("id") or ""))


def _fusionner_listes(survivant: dict, perdant: dict, champ: str,
                      cle) -> None:
    """Reunit deux listes sans doublon, en gardant l'ordre du survivant."""
    a = list(survivant.get(champ) or [])
    vus = {cle(x) for x in a}
    for x in (perdant.get(champ) or []):
        if cle(x) not in vus:
            a.append(x)
            vus.add(cle(x))
    if a:
        survivant[champ] = a


def fusionner(survivant: dict[str, Any],
              perdants: Sequence[dict[str, Any]]) -> None:
    """Verse dans `survivant` ce que les perdants ont en plus. Mute en place.

    Le survivant n'est JAMAIS ecrase : on ne comble que ses manques. Un champ
    present des deux cotes et divergent est un desaccord qu'un script n'a pas
    a arbitrer.
    """
    for perdant in perdants:
        for champ in ("creator", "year", "recommendedBy"):
            if survivant.get(champ) in (None, "") and perdant.get(champ) not in (None, ""):
                survivant[champ] = perdant[champ]
        _fusionner_listes(survivant, perdant, "types", lambda x: x)
        _fusionner_listes(survivant, perdant, "customLinks",
                          lambda x: x.get("url") if isinstance(x, dict) else x)
        _fusionner_listes(survivant, perdant, "watchProviders",
                          lambda x: x.get("url") if isinstance(x, dict) else x)
        for champ in ("externalIds", "linkOverrides", "enrichedAt"):
            fusion = dict(perdant.get(champ) or {})
            fusion.update(survivant.get(champ) or {})
            if fusion:
                survivant[champ] = fusion
        # Le titre du perdant devient un alias : sans cela, une recherche sur
        # l'ancien libelle ne trouverait plus rien.
        alias = [a for a in (survivant.get("aliases") or [])]
        for candidat in [perdant.get("title")] + list(perdant.get("aliases") or []):
            if candidat and candidat != survivant.get("title") and candidat not in alias:
                alias.append(candidat)
        if alias:
            survivant["aliases"] = alias
    survivant["types"] = sorted(set(survivant.get("types") or []))


def _imposer_titre(cle: tuple[str, str], item: dict[str, Any]) -> bool:
    """Remplace le titre par le bon, l'ancien devenant un alias. Renvoie
    `True` si quelque chose a change."""
    vise = TITRE_CANONIQUE.get(cle)
    if not vise or item.get("title") == vise:
        return False
    ancien = item.get("title")
    item["title"] = vise
    alias = [a for a in (item.get("aliases") or []) if a != vise]
    if ancien and ancien not in alias:
        alias.append(ancien)
    if alias:
        item["aliases"] = alias
    return True


def executer(items_dir: Path, mentions_dir: Path, *, apply: bool) -> dict[str, Any]:
    """Fusionne les groupes prouves. Renvoie un rapport chiffre."""
    items: dict[str, tuple[Path, dict]] = {}
    for chemin in sorted(items_dir.rglob("*.json")):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if doc.get("id"):
            items[doc["id"]] = (chemin, doc)

    mentions: dict[str, tuple[Path, dict]] = {}
    compte: Counter[str] = Counter()
    for chemin in sorted(mentions_dir.rglob("*.json")):
        try:
            doc = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        mentions[chemin.name] = (chemin, doc)
        compte[doc.get("itemId") or ""] += 1

    groupes: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for _, doc in items.values():
        ext = doc.get("externalIds") or {}
        if ext.get("tmdb"):
            groupes[(str(ext.get("tmdbType") or ""), str(ext["tmdb"]))].append(doc)

    fusions = reportees = supprimes = 0
    refuses: list[str] = []
    for cle, groupe in sorted(groupes.items()):
        if len(groupe) < 2:
            # Un groupe deja fusionne n'a plus qu'un membre, mais son titre
            # peut rester a corriger : la passe doit rester rejouable.
            if cle in TITRE_CANONIQUE and _imposer_titre(cle, groupe[0]) and apply:
                items[groupe[0]["id"]][0].write_text(
                    json.dumps(groupe[0], ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
            continue
        if not fusionnable(cle, groupe):
            titres = sorted({d.get("title") or "" for d in groupe})
            refuses.append(f"{cle[0]}/{cle[1]} : titres divergents {titres}")
            continue
        survivant = choisir_survivant(groupe, compte)
        perdants = [d for d in groupe if d is not survivant]
        fusionner(survivant, perdants)
        _imposer_titre(cle, survivant)
        fusions += 1
        ids_perdants = {d.get("id") for d in perdants}
        for chemin, mention in mentions.values():
            if mention.get("itemId") in ids_perdants:
                mention["itemId"] = survivant["id"]
                reportees += 1
                if apply:
                    chemin.write_text(
                        json.dumps(mention, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        if apply:
            items[survivant["id"]][0].write_text(
                json.dumps(survivant, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            for d in perdants:
                items[d["id"]][0].unlink()
        supprimes += len(perdants)
        log.info("fusion %s/%s -> %s (%d perdant·s)", cle[0], cle[1],
                 survivant["id"], len(perdants))

    for motif in refuses:
        log.warning("REFUS %s", motif)
    return {"fusions": fusions, "items_supprimes": supprimes,
            "mentions_reportees": reportees, "refuses": refuses}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fusionne les items portant le meme identifiant TMDB. "
                    "Refuse tout groupe aux titres divergents non justifies.")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Chemins resolus A L'APPEL : les figer a l'import ferait ecrire les tests
    # dans le vrai corpus (cf. le meme piege dans match_audit/sidecar).
    rapport = executer(common.ITEMS_DIR, common.MENTIONS_DIR, apply=args.apply)
    log.info("%d fusion(s), %d item(s) supprime(s), %d mention(s) reportee(s), "
             "%d refus", rapport["fusions"], rapport["items_supprimes"],
             rapport["mentions_reportees"], len(rapport["refuses"]))
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
