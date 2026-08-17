"""
fix_reco_anomalies.py — corrections ponctuelles, vérifiées une par une.

Chaque ligne de `CORRECTIONS` a été lue AVEC SA CITATION avant d'être écrite :
c'est la parole de l'épisode qui dit ce que la reco désigne, pas le type qu'un
script a deviné ni l'hôte du lien. Aucune heuristique ici — une table curée, et
un motif `attendu` qui refuse d'écrire si la donnée a changé depuis la
vérification.

ORIGINE (audit du 2026-08-16)
-----------------------------
Un croisement type ↔ hôte du lien sur les 1209 recos actives a relevé 78
contradictions. La plupart sont LÉGITIMES — un spectacle filmé sur YouTube, une
bande originale sur Bandcamp — et ne sont pas touchées. Restent les cas où le
type contredit ce que la reco dit d'elle-même.

Le cas fondateur est `ubm-1531` : la reco pointait le site d'un chef étoilé
belge et son restaurant, alors qu'elle parle du vulgarisateur YouTube du même
nom. Deux personnes distinctes, confondues par un homonyme.
"""
from __future__ import annotations

import argparse
from collections.abc import Sequence
from typing import Any

import dataset_fixes
from dataset_fixes import Change, add_common_args, run

__all__ = ["CORRECTIONS", "transform"]

#: Corrections vérifiées. Pour chaque reco :
#:   `attendu`  — état AVANT, tel que constaté. Sert de garde : si la donnée a
#:                changé depuis, on n'écrit rien plutôt que d'écraser à l'aveugle.
#:   `types`    — nouveaux types (facultatif).
#:   `liens`    — nouvelle liste de liens, REMPLACE l'existante (facultatif).
#:   `creator`  — nouveau créateur (facultatif).
#:   `pourquoi` — la citation ou le fait qui tranche. Ce champ n'est pas
#:                décoratif : sans lui, personne ne peut rejuger la décision.
CORRECTIONS: dict[str, dict[str, Any]] = {
    "ubm-0214": {
        "attendu": {"types": ["spectacle", "video"]},
        "types": ["spectacle"],
        "pourquoi": (
            "« C'est une pièce exceptionnelle qu'on peut voir d'ailleurs » — "
            "« Art » de Yasmina Reza est une pièce de théâtre. Le type `video` "
            "était faux ; le lien vers le texte publié reste, c'est une façon "
            "légitime d'accéder à l'œuvre."
        ),
    },
    "ubm-1349": {
        "attendu": {"types": ["autre", "musique"]},
        "types": ["album"],
        "creator": "Vincent Delerm",
        "pourquoi": (
            "« Je recommande Vincent Delerm, la BO du film qu'il a fait » — "
            "c'est une bande originale, donc un album (le lien Spotify pointe "
            "bien un `/album/`). Le créateur portait « Vincent Delerme », "
            "TROISIÈME graphie fautive rencontrée après « Delherme » et "
            "« de Lerme » : l'article Wikipédia s'intitule « Vincent Delerm »."
        ),
    },
    "ubm-1450": {
        "attendu": {"types": ["video"]},
        "types": ["film"],
        "pourquoi": (
            "« j'ai sorti un doc sur les baleines » — un documentaire doté "
            "d'une fiche AlloCiné est un film. Conforme à l'arbitrage du "
            "2026-07-31 : le type suit la NATURE de l'œuvre, pas son canal."
        ),
    },
    "ubm-1531": {
        "attendu": {"types": ["video"]},
        "types": ["chaine"],
        "creator": "Christophe Pauly",
        "liens": [{
            "label": "Chaîne YouTube",
            "url": "https://www.youtube.com/@Christophe_Pauly",
            "kind": "official",
            "ethics": "neutral",
        }],
        "pourquoi": (
            "HOMONYMES CONFONDUS. La reco pointait `christophepauly.com` et "
            "`lecoqauxchamps.be` — le chef étoilé belge — alors qu'elle parle "
            "du vulgarisateur YouTube du même nom, que `ubm-1828` référence "
            "correctement en `@Christophe_Pauly`. Arbitré par l'utilisateur, "
            "qui connaît le contexte de l'épisode."
        ),
    },
    # --- Créateurs FAUX (et non mal orthographiés) ----------------------
    # Relevés le 2026-08-16 parmi les groupes que `align_same_work_links` a
    # refusé d'aligner. Ces valeurs ne vont PAS dans la table d'alias : les
    # noms écartés désignent de vraies personnes, simplement pas l'auteur de
    # cette œuvre-là. Les fusionner globalement serait une erreur.
    "ubm-0519": {
        "attendu": {"types": ["film"]},
        "creator": "Chad Stahelski",
        "pourquoi": (
            "Le créateur valait « N/A » — un trou, pas un nom. L'autre reco de "
            "John Wick crédite Chad Stahelski, son réalisateur."
        ),
    },
    "ubm-0860": {
        "attendu": {"types": ["podcast"]},
        "creator": "Ambroise Carminati, Baptiste Pignon, Nicolas Roux",
        "pourquoi": (
            "« Philippe Léon » n'est pas l'auteur de ce podcast : l'API Apple "
            "Podcasts (id 1549461850) donne Ambroise Carminati, et une "
            "troisième reco du même flux crédite les trois auteurs."
        ),
    },
    "ubm-2981": {
        "attendu": {"types": ["podcast"]},
        "creator": "Ambroise Carminati, Baptiste Pignon, Nicolas Roux",
        "pourquoi": "Prénoms seuls (« Ambroise, Baptiste, Nicolas ») complétés.",
    },
    "ubm-1121": {
        "attendu": {"types": ["spectacle"]},
        "creator": "Mélody Mourey",
        "pourquoi": (
            "« La Course des Géants » est écrite et mise en scène par Mélody "
            "Mourey (article Wikipédia). « Jordi Lebole » y est comédien."
        ),
    },
    "ubm-1361": {
        "attendu": {"types": ["film"]},
        "creator": "Aurélien Peyre",
        "pourquoi": (
            "TMDB : « L'Épreuve du feu » (2025) est réalisé par Aurélien Peyre. "
            "Anja Verderosa figure à sa distribution — actrice, pas autrice."
        ),
    },
    "ubm-1683": {
        "attendu": {"types": ["serie"]},
        "creator": "Rodrigo Sorogoyen, Sara Cano, Paula Fabra",
        "pourquoi": (
            "« Netflix (série espagnole) » désigne un diffuseur, pas un auteur. "
            "TMDB donne les trois créateurs, déjà présents sur ubm-0289."
        ),
    },
    "ubm-0924": {
        "attendu": {"types": ["film"]},
        "creator": "Patrice Leconte",
        "pourquoi": (
            "Le champ portait la distribution (Rochefort, Noiret, Marielle) au "
            "lieu du réalisateur. TMDB : « Les Grands Ducs » est de Patrice "
            "Leconte, valeur déjà portée par ubm-0857."
        ),
    },
    "ubm-0660": {
        "attendu": {"types": ["serie"]},
        "creator": "Yacine Belhousse",
        "pourquoi": (
            "« Golden Moustache » est le studio producteur. TMDB crédite Yacine "
            "Belhousse comme auteur du « Trône des Frogz », valeur déjà portée "
            "par ubm-3073. Le studio n'est pas retiré de la table d'alias : il "
            "peut légitimement être l'auteur d'autres œuvres."
        ),
    },
    "ubm-2396": {
        "attendu": {"types": ["serie"]},
        "creator": "Les Parasites",
        "pourquoi": (
            "« L'Effondrement » est signée du collectif Les Parasites, dont "
            "Guillaume Desjardins, Jérémy Bernard et Bastien Ughetto sont les "
            "membres. C'est le collectif qui est crédité publiquement."
        ),
    },
    # « Validé » : les DEUX recos divergentes reçoivent le crédit complet.
    # TMDB donne bien les trois créateurs. Xavier Lacaille avait été signalé
    # comme une erreur lors d'un audit précédent — c'était FAUX, il est
    # co-créateur de la série.
    "ubm-2694": {
        "attendu": {"types": ["serie"]},
        "creator": "Franck Gastambide, Giulio Callegari, Xavier Lacaille",
        "pourquoi": "TMDB : « Validé » est créée par ces trois auteurs.",
    },
    "ubm-2984": {
        "attendu": {"types": ["serie"]},
        "creator": "Franck Gastambide, Giulio Callegari, Xavier Lacaille",
        "pourquoi": (
            "Idem. Cette reco ne créditait que Xavier Lacaille — un crédit "
            "partiel, pas une erreur : il est bien l'un des trois créateurs."
        ),
    },
    # « Iris » : les liens IMDb ET TMDB pointaient la série CORÉENNE de 2009,
    # homonyme de la série française de 2024 dont parle la reco. Un match par
    # titre seul, comme celui qui avait donné « Gli intoccabili » pour
    # « Intouchables ». Identifiants corrects relevés sur TMDB.
    "ubm-0187": {
        "attendu": {"types": ["serie"]},
        "liens": [
            {"label": "AlloCiné", "kind": "info", "ethics": "neutral",
             "url": "https://www.allocine.fr/series/ficheserie_gen_cserie=35910.html"},
            {"label": "IMDb", "kind": "info", "ethics": "neutral",
             "url": "https://www.imdb.com/title/tt31262444/"},
            {"label": "TMDB", "kind": "info", "ethics": "neutral",
             "url": "https://www.themoviedb.org/tv/271593"},
        ],
        "pourquoi": (
            "IMDb tt1757202 et TMDB tv/31505 désignent « Iris » (2009), série "
            "SUD-CORÉENNE. La reco parle d'« Iris » (2024) de Doria Tillier, "
            "que la fiche AlloCiné 35910 identifie correctement."
        ),
    },
    "ubm-0210": {
        "attendu": {"types": ["serie"]},
        "creator": "Doria Tillier",
        "liens": [
            {"label": "AlloCiné", "kind": "info", "ethics": "neutral",
             "url": "https://www.allocine.fr/series/ficheserie_gen_cserie=35910.html"},
            {"label": "IMDb", "kind": "info", "ethics": "neutral",
             "url": "https://www.imdb.com/title/tt31262444/"},
            {"label": "TMDB", "kind": "info", "ethics": "neutral",
             "url": "https://www.themoviedb.org/tv/271593"},
        ],
        "pourquoi": "Mêmes liens erronés que ubm-0187, plus le prénom seul.",
    },
    # RÉGRESSION QUE J'AI INTRODUITE, puis corrigée (2026-08-16).
    # `align_same_work_links` unifie les liens des recos partageant un titre.
    # « Bref » (2011, Canal+) et « Bref.2 » (2025, Disney+) portent presque le
    # MÊME titre et le MÊME créateur : aucun des trois garde-fous d'alors n'a vu
    # la différence, et mon alignement a écrasé les liens de cette reco.
    # Le garde-fou manquant est ajouté dans `align_same_work_links` : deux recos
    # ne sont alignées que si leurs liens d'IDENTIFIANT ne se contredisent pas.
    #
    # ATTENTION — j'ai d'abord réparé cette reco DANS LE MAUVAIS SENS. L'alias
    # « bref 2 » m'a fait conclure qu'elle parlait de la saison 2, et j'ai donc
    # rétabli la fiche AlloCiné de « Bref.2 ». Le transcript dit l'inverse, à
    # 00:42:17 : « j'ai passé des essais pour Bref, c'est une série à succès de
    # Canal+ […] pour la PARTIE 1 de Bref ». Vérifié ensuite pièce par pièce :
    #   - AlloCiné 10520      → « Bref - Série TV 2011 »       (le bon)
    #   - AlloCiné 1000000468 → « Bref.2 - Série TV 2025 »     (celui posé)
    #   - Disney+ b329134e…   → « bref. », description de 2011 (donc correct)
    #   - TMDB tv/60715       → « Bref » (2011)                (déjà correct)
    # Seule la fiche AlloCiné était fausse ; l'alias qui l'a causée part avec.
    "ubm-1547": {
        "attendu": {"types": ["serie"]},
        "liens": [
            {"label": "Disney+", "kind": "streaming", "ethics": "avoid",
             "url": "https://www.disneyplus.com/fr-fr/browse/"
                    "entity-b329134e-b113-49d6-827e-dd4e0616457f"},
            {"label": "AlloCiné", "kind": "info", "ethics": "neutral",
             "url": "https://www.allocine.fr/series/"
                    "ficheserie_gen_cserie=10520.html"},
        ],
        "retirer_alias": ["bref 2"],
        "pourquoi": (
            "Le transcript (00:42:17) dit « la partie 1 de Bref » et « série à "
            "succès de Canal+ » : c'est « Bref » (2011). Or la reco portait la "
            "fiche AlloCiné 1000000468, qui est « Bref.2 » (2025), et l'alias "
            "« bref 2 » qui a produit cette confusion."
        ),
    },
    # « The Office » : la MÊME régression que Bref, sur cinq recos.
    # Le corpus portait déjà deux fiches AlloCiné contradictoires — 564 pour la
    # version BRITANNIQUE (2001), 199 pour l'AMÉRICAINE (2005) — réparties au
    # hasard ; mon alignement les a propagées toutes les deux partout.
    # Les citations tranchent : « Steve Carell » y est nommé trois fois, et
    # « Parks and Recreation » une quatrième. Ce sont des recos de la version
    # américaine, que confirment IMDb tt0386676, TMDB 2316, Netflix et
    # JustWatch. Seule la fiche britannique est de trop.
    **{
        rid: {
            "attendu": {"types": ["serie"]},
            "retirer_liens": ["ficheserie_gen_cserie=564"],
            "pourquoi": (
                "Fiche AlloCiné 564 = « The Office » (UK, 2001). Cette reco "
                "parle de la version américaine — tous ses autres liens et sa "
                "citation le disent."
            ),
        }
        for rid in ("ubm-0676", "ubm-0741", "ubm-1538", "ubm-1837", "ubm-3101")
    },
    # Seule reco ACTIVE dont le créateur valait « N/A ». Les 32 autres
    # occurrences sont sur des recos écartées ou dans `items` : elles sont
    # simplement VIDÉES par `fix_creator_aliases` (un trou reste un trou).
    # Ici, le producteur est identifiable — les deux liens de la reco pointent
    # `@FirstWeFeast` et `firstwefeast.com`, et la chaîne s'intitule
    # « First We Feast ». Autant renseigner que vider.
    "ubm-0520": {
        "attendu": {"types": ["podcast", "autre", "video"]},
        "creator": "First We Feast",
        "pourquoi": (
            "« Hot Ones » est produit par First We Feast, ce que confirment "
            "les deux liens de la reco. Le champ valait « N/A »."
        ),
    },
    "ubm-2791": {
        "attendu": {"types": ["spectacle"]},
        "types": ["serie"],
        "pourquoi": (
            "« il a joué dans le Cher Journal », et le lien pointe "
            "`justwatch.com/fr/serie/`. Les deux autres recos du même titre "
            "(ubm-0739, ubm-2743) sont typées `serie` : celle-ci était seule "
            "à diverger."
        ),
    },
}


def _replier(valeur: Any) -> str:
    """Forme comparable d'un alias : les alias sont saisis à la main, et
    « Bref 2 », « bref 2 » et « bref 2  » désignent la même chose."""
    return " ".join(str(valeur).split()).casefold()


def transform(doc: dict[str, Any]) -> list[Change]:
    """Applique la correction curée de cette reco, si l'état d'avant correspond."""
    fix = CORRECTIONS.get(doc.get("id") or "")
    if not fix:
        return []
    # Garde : la donnée a-t-elle bougé depuis la vérification manuelle ?
    attendu = fix.get("attendu") or {}
    for champ, valeur in attendu.items():
        if sorted(doc.get(champ) or []) != sorted(valeur):
            return []
    changes: list[Change] = []
    if "types" in fix and sorted(doc.get("types") or []) != sorted(fix["types"]):
        changes.append(Change(field="types", before=doc.get("types"),
                              after=fix["types"]))
        doc["types"] = list(fix["types"])
    if "creator" in fix and doc.get("creator") != fix["creator"]:
        changes.append(Change(field="creator", before=doc.get("creator"),
                              after=fix["creator"]))
        doc["creator"] = fix["creator"]
    if "liens" in fix:
        avant = [link.get("url") for link in (doc.get("links") or [])
                 if isinstance(link, dict)]
        apres = [link["url"] for link in fix["liens"]]
        if avant != apres:
            changes.append(Change(field="links", before=avant, after=apres))
            doc["links"] = [dict(link) for link in fix["liens"]]
    # RETRAIT ciblé, par fragment d'URL. Distinct de `liens`, qui redéfinit
    # toute la liste : quand un seul lien est fautif parmi sept, redéfinir les
    # sept obligerait à tous les recopier dans la table — verbeux, et surtout
    # fragile, puisque la moindre évolution des six autres invaliderait
    # l'entrée sans qu'on s'en aperçoive.
    if "retirer_liens" in fix:
        garder = [link for link in (doc.get("links") or [])
                  if not (isinstance(link, dict)
                          and any(frag in (link.get("url") or "")
                                  for frag in fix["retirer_liens"]))]
        if len(garder) != len(doc.get("links") or []):
            avant = [link.get("url") for link in (doc.get("links") or [])
                     if isinstance(link, dict)]
            doc["links"] = garder
            changes.append(Change(
                field="links", before=avant,
                after=[link.get("url") for link in garder
                       if isinstance(link, dict)]))
    # RETRAIT d'alias. Un alias FAUX est plus nuisible qu'un alias manquant :
    # c'est lui que lisent les outils d'appariement, et il fait revenir l'erreur
    # à chaque passe. Sur ubm-1547, « bref 2 » a suffi pour attribuer la fiche
    # de « Bref.2 » (2025) à une reco parlant de « Bref » (2011).
    if "retirer_alias" in fix:
        indesirables = {_replier(a) for a in fix["retirer_alias"]}
        avant = list(doc.get("aliases") or [])
        garder = [a for a in avant if _replier(a) not in indesirables]
        if len(garder) != len(avant):
            changes.append(Change(field="aliases", before=avant, after=garder))
            # Pas de liste vide : l'absence d'alias et « aucun alias retenu »
            # doivent se lire de la même façon dans le fichier.
            if garder:
                doc["aliases"] = garder
            else:
                doc.pop("aliases", None)
    return changes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Corrige les recos dont le type contredit leur contenu.")
    add_common_args(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - E/S
    args = build_parser().parse_args(argv)
    run(transform, args, roots=(dataset_fixes.RECOS_DIR,),
        extra_report={"corrections": {k: v["pourquoi"]
                                      for k, v in CORRECTIONS.items()}})
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
