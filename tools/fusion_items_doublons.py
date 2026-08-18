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

def partitionner(cle: tuple[str, str],
                 groupe: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Decoupe un groupe en sous-ensembles de MEME titre.

    Le refus etait auparavant GLOBAL : un seul intrus bloquait tout le groupe.
    Sur tv/60715, deux items « Bref » parfaitement fusionnables restaient
    separes parce qu'un troisieme, « Bref 2 », faisait diverger l'ensemble.

    Partitionner traite chaque sous-ensemble pour ce qu'il est, sans jamais
    fusionner par-dessus une divergence : « Drive » et « Mulholland Drive »
    tombent dans deux partitions d'un membre chacune, donc rien ne bouge.

    Une variante declaree reunit volontairement tout le groupe : c'est la que
    « Rick and Morty » rejoint « Rick et Morty ».
    """
    if cle in VARIANTES_ADMISES:
        return [list(groupe)]
    parts: dict[str, list[dict[str, Any]]] = {}
    for doc in groupe:
        parts.setdefault(normaliser(doc.get("title") or ""), []).append(doc)
    return list(parts.values())


def noms_createur(item: dict[str, Any]) -> set[str]:
    """Les noms cites par `creator`, normalises.

    Le champ est une chaine libre : « Kyan Khojandi, Navo », « Baptiste
    Lecaplain, Florent Bernard, Xavier Maingon ». On la decoupe pour pouvoir
    comparer des listes PARTIELLES de la meme equipe.
    """
    brut = (item.get("creator") or "").replace("&", ",")
    return {normaliser(x) for x in brut.split(",") if normaliser(x)}


def _noyau_commun(groupe: Sequence[dict[str, Any]]) -> set[str]:
    """Les noms que TOUTES les listes renseignees partagent.

    Vide s'il y a moins de deux listes renseignees : un seul createur ne
    prouve aucun recoupement, et fusionner sur cette base reviendrait a se
    fier au seul titre.
    """
    listes = [n for n in (noms_createur(d) for d in groupe) if n]
    if len(listes) < 2:
        return set()
    return set.intersection(*listes)


def _types_compatibles(groupe: Sequence[dict[str, Any]]) -> bool:
    """Tous les items partagent-ils au moins un type ?

    Meme titre et meme auteur ne suffisent pas : un livre et son adaptation
    resteraient deux oeuvres. Le type les separe.
    """
    ensembles = [set(d.get("types") or []) for d in groupe]
    return bool(set.intersection(*ensembles)) if ensembles else False


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


def _libelle_du_noyau(docs: Sequence[dict[str, Any]], noyau: set[str]) -> str:
    """Ecrit le noyau avec l'orthographe des libelles d'origine.

    Un item porte peut-etre exactement le noyau — on prend alors sa chaine
    telle quelle. Sinon on la reconstruit fragment par fragment, en gardant
    la casse et les accents tels qu'ils ont ete saisis : « Kyan Khojandi »
    et non « kyan khojandi ».
    """
    for doc in docs:
        if noms_createur(doc) == noyau and doc.get("creator"):
            return doc["creator"]
    fragments: dict[str, str] = {}
    for doc in docs:
        brut = (doc.get("creator") or "").replace("&", ",")
        for morceau in brut.split(","):
            cle = normaliser(morceau)
            if cle in noyau and cle not in fragments:
                fragments[cle] = morceau.strip()
    return ", ".join(fragments[c] for c in sorted(noyau) if c in fragments)


def _completer_createur(survivant: dict[str, Any],
                        perdants: Sequence[dict[str, Any]],
                        a_arbitrer: list[str]) -> None:
    """Retient la liste de createurs la plus complete — si elle est unique.

    Une liste qui CONTIENT celle du survivant n'est pas un desaccord, c'est un
    complement : « Kyan Khojandi » face a « Kyan Khojandi, Bruno Muschio ».

    Mais « Bref » portait AUSSI « Kyan Khojandi, Alain Chabat ». Deux
    sur-ensembles du meme noyau qui ne s'emboitent pas : en retenir un revient
    a trancher au hasard, et le premier jet a retenu Chabat — qui a PRODUIT la
    serie sans la creer. On garde alors le noyau, seul fait etabli, et on
    signale le cas pour arbitrage humain.
    """
    tous = [survivant, *perdants]
    listes = [n for n in (noms_createur(d) for d in tous) if n]
    if not listes:
        return
    # Les listes maximales : celles qu'aucune autre ne contient strictement.
    maximales = [n for n in listes if not any(m > n for m in listes)]
    distinctes = {frozenset(n) for n in maximales}
    if len(distinctes) > 1:
        noyau = set.intersection(*listes)
        if not noyau:
            # Aucun nom commun : ce n'est plus une liste tronquee mais un
            # desaccord franc. La regle « le survivant n'est jamais ecrase »
            # s'applique, et ecrire le noyau vide effacerait son createur.
            a_arbitrer.append(
                f"« {survivant.get('title')} » : createurs sans nom commun "
                f"{[sorted(n) for n in distinctes]}")
            return
        a_arbitrer.append(
            f"« {survivant.get('title')} » : createurs concurrents "
            f"{[sorted(n) for n in distinctes]}, noyau conserve {sorted(noyau)}")
        survivant["creator"] = _libelle_du_noyau(tous, noyau)
        return
    # Un seul ensemble maximal : la liste la plus complete n'a rien
    # d'arbitraire. Elle vient forcement d'un document qui la porte — un
    # ensemble non vide implique un `creator` non vide — d'ou l'absence de
    # repli ici : en ecrire un serait du code inatteignable.
    survivant["creator"] = _libelle_du_noyau(tous, maximales[0])


def fusionner(survivant: dict[str, Any],
              perdants: Sequence[dict[str, Any]],
              a_arbitrer: list[str] | None = None) -> None:
    """Verse dans `survivant` ce que les perdants ont en plus. Mute en place.

    Le survivant n'est JAMAIS ecrase : on ne comble que ses manques. Un champ
    present des deux cotes et divergent est un desaccord qu'un script n'a pas
    a arbitrer.
    """
    a_arbitrer = a_arbitrer if a_arbitrer is not None else []
    # Un createur plus COMPLET remplace celui du survivant — mais seulement
    # s'il le CONTIENT. « Kyan Khojandi » face a « Kyan Khojandi, Bruno
    # Muschio » n'est pas un desaccord, c'est une liste tronquee, et la page
    # doit crediter toute l'equipe.
    #
    # Deux noms qui ne s'emboitent pas restent un desaccord, qu'un script n'a
    # pas a trancher : la regle « le survivant n'est jamais ecrase » tient
    # pour eux.
    _completer_createur(survivant, perdants, a_arbitrer)
    for perdant in perdants:
        # `creator` est EXCLU : `_completer_createur` s'en charge, et le
        # combler ici ecraserait le noyau qu'elle vient de trancher.
        for champ in ("year", "recommendedBy"):
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


def executer(items_dir: Path, mentions_dir: Path, *, apply: bool,
             palier2: bool = False,
             palier3: bool = False) -> dict[str, Any]:
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
        # Seules les mentions PUBLIEES designent le survivant : le corpus en
        # porte 1 799 ecartees pour 1 211 publiees, et les compter reviendrait
        # a trancher sur des donnees que personne ne voit.
        if doc.get("status") != "discarded":
            compte[doc.get("itemId") or ""] += 1

    groupes: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for _, doc in items.values():
        ext = doc.get("externalIds") or {}
        if ext.get("tmdb"):
            groupes[(str(ext.get("tmdbType") or ""), str(ext["tmdb"]))].append(doc)

    fusions = reportees = supprimes = 0
    refuses: list[str] = []
    a_arbitrer: list[str] = []
    for cle, groupe in sorted(groupes.items()):
        if len(groupe) < 2:
            # Un groupe deja fusionne n'a plus qu'un membre, mais son titre
            # peut rester a corriger : la passe doit rester rejouable.
            if cle in TITRE_CANONIQUE and _imposer_titre(cle, groupe[0]) and apply:
                items[groupe[0]["id"]][0].write_text(
                    json.dumps(groupe[0], ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
            continue
        parts = partitionner(cle, groupe)
        if len(parts) > 1:
            # La divergence reste SIGNALEE meme quand on fusionne a
            # l'interieur : elle revele souvent un identifiant fautif — c'est
            # ainsi que « Drive » a ete pris avec celui de Mulholland Drive.
            titres = sorted({d.get("title") or "" for d in groupe})
            refuses.append(f"{cle[0]}/{cle[1]} : titres divergents {titres}")
        for part in parts:
            if len(part) < 2:
                continue
            _fusionner_partition(cle, part, compte, items, mentions, apply,
                                 a_arbitrer)
            fusions += 1
            supprimes += len(part) - 1
            reportees += _reporter_mentions(part, compte, mentions, apply)
        continue

    if palier2:
        # Sans identifiant TMDB, le titre seul ne prouve rien : deux oeuvres
        # peuvent le partager. Le CREATEUR ajoute la contrainte qui manque.
        # On repart des items ENCORE PRESENTS, pour ne pas retomber sur ceux
        # que le premier palier vient de supprimer.
        vivants = [d for i, (chemin, d) in items.items() if chemin.exists()]
        par_couple: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for doc in vivants:
            titre = normaliser(doc.get("title") or "")
            createur = normaliser(doc.get("creator") or "")
            # Les DEUX doivent etre presents : un createur absent n'est pas un
            # createur identique.
            if titre and createur:
                par_couple[(titre, createur)].append(doc)
        for _couple, part in sorted(par_couple.items()):
            if len(part) < 2:
                continue
            ids = {str((d.get("externalIds") or {}).get("tmdb")) for d in part
                   if (d.get("externalIds") or {}).get("tmdb")}
            if len(ids) > 1:
                # Meme titre, meme createur, mais deux fiches distinctes : ce
                # sont deux oeuvres (une serie et son adaptation, par exemple).
                refuses.append(
                    f"« {part[0].get('title')} » / {part[0].get('creator')} : "
                    f"identifiants TMDB divergents {sorted(ids)}")
                continue
            _fusionner_partition(("titre", "createur"), part, compte, items,
                                 mentions, apply, a_arbitrer)
            fusions += 1
            supprimes += len(part) - 1
            reportees += _reporter_mentions(part, compte, mentions, apply)

    if palier3:
        # Les createurs sont des chaines libres, souvent PARTIELLES : « Bref »
        # existait en cinq exemplaires credites « Kyan Khojandi », « Kyan
        # Khojandi, Navo », « Kyan Khojandi, Alain Chabat »… Le palier 2, qui
        # exige l'egalite stricte, les laissait tous en place.
        vivants = [d for i, (chemin, d) in items.items() if chemin.exists()]
        par_titre: dict[str, list[dict]] = defaultdict(list)
        for doc in vivants:
            titre = normaliser(doc.get("title") or "")
            if titre:
                par_titre[titre].append(doc)
        for titre, part in sorted(par_titre.items()):
            if len(part) < 2:
                continue
            # `_noyau_commun` est l'intersection de TOUTES les listes
            # renseignees : elle est vide des qu'une seule est disjointe des
            # autres. Aucune garde supplementaire n'est donc necessaire — j'en
            # avais ecrit une, elle etait inatteignable.
            #
            # Un item SANS createur rejoint le groupe : son silence ne
            # contredit rien, des lors que le noyau est prouve par ailleurs.
            if not _noyau_commun(part):
                continue
            if not _types_compatibles(part):
                refuses.append(f"« {titre} » : aucun type commun")
                continue
            ids = {str((d.get("externalIds") or {}).get("tmdb")) for d in part
                   if (d.get("externalIds") or {}).get("tmdb")}
            if len(ids) > 1:
                refuses.append(
                    f"« {titre} » : identifiants TMDB divergents {sorted(ids)}")
                continue
            _fusionner_partition(("titre", "createur-recoupe"), part, compte,
                                 items, mentions, apply, a_arbitrer)
            fusions += 1
            supprimes += len(part) - 1
            reportees += _reporter_mentions(part, compte, mentions, apply)

    for motif in refuses:
        log.warning("REFUS %s", motif)
    for motif in a_arbitrer:
        log.warning("A ARBITRER %s", motif)
    return {"fusions": fusions, "items_supprimes": supprimes,
            "mentions_reportees": reportees, "refuses": refuses,
            "a_arbitrer": a_arbitrer}


def _fusionner_partition(cle, part, compte, items, mentions, apply,
                         a_arbitrer=None):
    """Fusionne une partition et ecrit le survivant. Renvoie son identifiant."""
    survivant = choisir_survivant(part, compte)
    perdants = [d for d in part if d is not survivant]
    fusionner(survivant, perdants, a_arbitrer)
    _imposer_titre(cle, survivant)
    if apply:
        items[survivant["id"]][0].write_text(
            json.dumps(survivant, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        for d in perdants:
            items[d["id"]][0].unlink()
    log.info("fusion %s/%s -> %s (%d perdant·s)", cle[0], cle[1],
             survivant["id"], len(perdants))
    return survivant


def _reporter_mentions(part, compte, mentions, apply):
    """Repointe vers le survivant les mentions des perdants.

    Sans ce report, la suppression d'un item laisserait des mentions
    ORPHELINES : elles designeraient une oeuvre qui n'existe plus.
    """
    survivant = choisir_survivant(part, compte)
    ids_perdants = {d.get("id") for d in part if d is not survivant}
    n = 0
    for chemin, mention in mentions.values():
        if mention.get("itemId") in ids_perdants:
            mention["itemId"] = survivant["id"]
            n += 1
            if apply:
                chemin.write_text(
                    json.dumps(mention, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return n



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fusionne les items portant le meme identifiant TMDB. "
                    "Refuse tout groupe aux titres divergents non justifies.")
    parser.add_argument("--apply", action="store_true",
                        help="ecrit reellement (defaut : simulation)")
    parser.add_argument("--palier3", action="store_true",
                        help="fusionne aussi les items dont les listes de "
                             "createurs se RECOUPENT (listes partielles)")
    parser.add_argument("--palier2", action="store_true",
                        help="fusionne aussi les items de meme titre ET "
                             "meme createur, sans identifiant TMDB")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    # Chemins resolus A L'APPEL : les figer a l'import ferait ecrire les tests
    # dans le vrai corpus (cf. le meme piege dans match_audit/sidecar).
    rapport = executer(common.ITEMS_DIR, common.MENTIONS_DIR,
                       apply=args.apply, palier2=args.palier2,
                       palier3=args.palier3)
    log.info("%d fusion(s), %d item(s) supprime(s), %d mention(s) reportee(s), "
             "%d refus", rapport["fusions"], rapport["items_supprimes"],
             rapport["mentions_reportees"], len(rapport["refuses"]))
    if not args.apply:
        log.info("SIMULATION — aucune ecriture (ajoute --apply pour ecrire).")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
