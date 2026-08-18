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
from urllib.parse import urlparse

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
        "retirer_liens": ["cserie=1000000468"],
        "retirer_alias": ["bref 2"],
        "pourquoi": (
            "Le transcript (00:42:17) dit « la partie 1 de Bref » et « série à "
            "succès de Canal+ » : c'est « Bref » (2011). Or la reco portait la "
            "fiche AlloCiné 1000000468, qui est « Bref.2 » (2025), et l'alias "
            "« bref 2 » qui a produit cette confusion. "
            "L'entrée REDÉFINISSAIT la liste de liens ; elle retire désormais "
            "la seule fiche fautive. Le module met en garde contre la "
            "redéfinition (« la moindre évolution des autres invaliderait "
            "l'entrée ») et c'est exactement ce qui est arrivé : la fiche "
            "fautive étant partie, la redéfinition ne faisait plus qu'effacer "
            "IMDb tt2044128, TMDB 60715 et la page de visionnage — trois liens "
            "qui désignent le BON « Bref », celui de 2011."
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
        # « Hot Ones » est diffusée sur YouTube et sur son propre site : aucun
        # flux podcast, malgré le type. Arbitrage du 2026-08-17.
        "types": ["autre", "video"],
        "creator": "First We Feast",
        "retirer_liens": ["89Ri8OIjgxI"],
        "pourquoi": (
            "« Hot Ones » est produit par First We Feast, ce que confirment "
            "les deux premiers liens. Le champ valait « N/A ». "
            "DEUX ÉMISSIONS ÉTAIENT MÉLANGÉES : le troisième lien menait à "
            "« HOT ONES : Miki, ça pik pik fort » de Studio Bagel, l'adaptation "
            "FRANÇAISE animée par Kyan Khojandi — « basé sur le programme Hot "
            "Ones », donc une autre œuvre. La citation (« je suis un énorme fan "
            "de Hot Ones ») désigne l'originale : Kyan ne se dirait pas fan de "
            "sa propre émission."
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
    # ==================================================================
    # GRAPHIES DE NOMS PROPRES — vérifiées une par une, source citée.
    #
    # Toutes viennent de la même cause : `creator` est extrait de la
    # TRANSCRIPTION de l'épisode, donc de la parole. « Baffy » pour Baffie,
    # « Rallye » pour Rhali, « Honoré Cos » pour Éléonore Costes : ce sont des
    # restitutions phonétiques, pas des variantes d'écriture.
    #
    # La garde `attendu` porte ici sur `creator` lui-même : si quelqu'un a
    # déjà corrigé à la main, l'outil se tait.
    # ==================================================================
    "ubm-1544": {
        "attendu": {"creator": "Antoine Gouille"},
        "creator": "Antoine Gouy",
        "pourquoi": "Article Wikipédia « Antoine Gouy ». « Gouille » est la "
                    "restitution phonétique de la transcription.",
    },
    "ubm-2777": {
        "attendu": {"creator": "Clément Victorovitch"},
        "creator": "Clément Viktorovitch",
        "pourquoi": "Article Wikipédia « Clément Viktorovitch » — avec un k. "
                    "La transcription a francisé la graphie.",
    },
    "ubm-0067": {
        "attendu": {"creator": "Honoré Cos"},
        "creator": "Éléonore Costes",
        "pourquoi": "« Honoré Cos » est ce que l'oreille retient d'« Éléonore "
                    "Costes » dite vite. Article Wikipédia à ce nom.",
    },
    "ubm-0038": {
        "attendu": {"creator": "Laurent Baffy"},
        "creator": "Laurent Baffie",
        "pourquoi": "Article Wikipédia « Laurent Baffie ». « Baffy » n'existe pas.",
    },
    "ubm-2990": {
        "attendu": {"creator": "Laurent Baffy"},
        "creator": "Laurent Baffie",
        "pourquoi": "Même faute que ubm-0038 (article Wikipédia « Laurent Baffie »).",
    },
    "ubm-0279": {
        "attendu": {"types": ["spectacle", "livre"], "title": "Entre les deux"},
        "creator": "Panayotis Pascot",
        # « ton spectacle s'appelle ? Entre les deux » : c'est le SPECTACLE.
        # Son livre, « La prochaine fois que tu mordras la poussière », fait
        # l'objet d'une reco distincte (ubm-1737). Arbitrage du 2026-08-17.
        "types": ["spectacle"],
        "pourquoi": "Article Wikipédia « Panayotis Pascot ». La transcription a "
                    "coupé le prénom en deux et inventé un patronyme. La garde "
                    "portait sur ce `creator` déjà corrigé : l'entrée était "
                    "devenue inerte, et le retrait du type `livre` n'aurait "
                    "jamais pu s'y greffer. Elle porte désormais sur l'état "
                    "courant.",
    },
    "ubm-0734": {
        "attendu": {"creator": "Penelope Bajeux"},
        "creator": "Pénélope Bagieu",
        "pourquoi": "Article Wikipédia « Pénélope Bagieu » — accents compris.",
    },
    "ubm-0653": {
        "attendu": {"creator": "Yacine Belhousse", "types": ["autre"]},
        "creator": "Yacine Belhousse",
        # Même œuvre que ubm-0670 — les deux recos pointent la même page de
        # production, `empreintedigitale.net/rire` — et AlloCiné lui consacre
        # une fiche FILM. Le type divergent empêchait
        # `align_same_work_links` de les rapprocher : ubm-0670 restait sans le
        # lien Netflix que celle-ci portait déjà.
        "types": ["film"],
        "pourquoi": "Article Wikipédia « Yacine Belhousse ». « Bellous » est "
                    "la restitution phonétique de la transcription. La garde "
                    "portait sur ce `creator` DÉJÀ corrigé : l'entrée était "
                    "devenue muette, et le type n'aurait jamais pu s'y "
                    "greffer.",
    },
    "ubm-1323": {
        "attendu": {"creator": "Jean Jass"},
        "creator": "JeanJass",
        "pourquoi": "Les deux graphies mènent au MÊME article Wikipédia, "
                    "intitulé « JeanJass » : le nom de scène s'écrit en un mot.",
    },
    "ubm-2099": {
        "attendu": {"creator": "Manon"},
        "creator": "Manon Bril",
        "pourquoi": "Prénom seul complété : article Wikipédia « Manon Bril », "
                    "vulgarisatrice. « Manon » seul mène à la page du prénom.",
    },
    # --- Absentes de Wikipédia : vérifiées ailleurs, source citée ---------
    "ubm-1370": {
        "attendu": {"creator": "Anis Rallye"},
        "creator": "Anis Rhali",
        "pourquoi": "Aucun article Wikipédia. Vérifié sur BilletRéduc "
                    "(spectacle-anis-rhali), le Warehouse de Nantes et ses "
                    "comptes TikTok/Instagram @anisrhali. « Rallye » est la "
                    "restitution phonétique.",
    },
    "ubm-0506": {
        "attendu": {"creator": "Pierre Illéré"},
        "creator": "Pierre Hillairet",
        "pourquoi": "Aucun article Wikipédia. « Jour de pluie » est son "
                    "seul-en-scène : fiches BilletRéduc, Humorix et Théâtre du "
                    "Marais à ce nom. « Illéré » est la restitution phonétique.",
    },
    "ubm-0961": {
        "attendu": {"creator": "Blandine Lehoux"},
        "creator": "Blandine Lehout",
        "pourquoi": "Aucun article Wikipédia. Site officiel blandinelehout.com, "
                    "fiches Humorix et La Scène Barbès à ce nom.",
    },
    "ubm-1644": {
        "attendu": {"creator": "Tom Baletti"},
        "creator": "Tom Baldetti",
        "pourquoi": "Aucun article Wikipédia. Graphie « Baldetti » partout : "
                    "presse (moka-mag, gambin), Instagram, et la fiche IMDb "
                    "« Tom Baldetti et Yassir ».",
    },
    # ==================================================================
    # CRÉATEURS des œuvres à DEUX invités, que `fill_guest_creators` a
    # refusé de deviner. Chacune tranchée par une source, jamais par
    # déduction — c'est tout l'objet de son refus.
    # ==================================================================
    "ubm-1092": {
        "attendu": {"types": ["spectacle"]},
        "creator": "Alexandre Kominek",
        "pourquoi": "Le titre EST le nom de l'artiste, et le lien officiel "
                    "alexandrekominek.fr porte son spectacle « Bâtard "
                    "Sensible ». Bun Hay Mean, l'autre invité, le recommande.",
    },
    "ubm-1649": {
        "attendu": {"types": ["video"]},
        "creator": "Tom Baldetti & Yassir",
        "pourquoi": "Le compte @_colocs est tenu par les deux colocataires. La "
                    "citation le confirme (« vous avez fait rose-bleu, le même "
                    "code ») : le code couleur T/Y décrit par We Love Comedy.",
    },
    "ubm-1651": {
        "attendu": {"types": ["spectacle"]},
        "creator": "Tom Baldetti & Yassir",
        "pourquoi": "Le Plaisir Tour est un COLLECTIF dont le plateau réunit "
                    "Tom Baldetti et Yassir BNF (avec Léandre, Antony "
                    "Giuliani, Basile…). Les deux invités en font partie, d'où "
                    "`guestWork` ; le plateau varie selon les dates.",
    },
    "ubm-1663": {
        "attendu": {"types": ["podcast"]},
        "creator": "Alice Moitié",
        "recommande_par": "Alice Moitié",
        "pourquoi": "Apple Podcasts décrit « le Trippy-Talk-Show d'Alice "
                    "Moitié » : l'accent est le bon. `recommendedBy` portait "
                    "DEUX FOIS la même personne (« Alice Moitié & Alice "
                    "Moitie »), ce qui la faisait passer pour deux invitées.",
    },
    "ubm-2286": {
        "attendu": {"types": ["serie"]},
        "creator": "Jonathan Cohen & Jérémie Galan",
        "pourquoi": "« France Kbek » (OCS, 2014) est créée par Jonathan Cohen "
                    "et Jérémie Galan — article Wikipédia et presse. La "
                    "citation le dit aussi : « vous avez fait une série ».",
    },
    "ubm-3188": {
        "attendu": {"types": ["podcast"]},
        "creator": "Florent Bernard, Adrien Ménielle",
        "pourquoi": "Acast annonce « FloodCast — Animé par Florent Bernard, "
                    "Adrien Ménielle ». Les deux invités en sont les auteurs.",
    },
    # --- « Chedid » : trois recos, et AUCUNE faute de créateur ------------
    # Le détecteur les signalait parce qu'il compare `creator` à
    # `recommendedBy`. Ici c'est le RECOMMANDEUR qui est mal saisi.
    "ubm-2543": {
        "attendu": {"creator": "Matthieu Chedid", "recommendedBy": "Matthieu"},
        "recommande_par": "Matthieu Chedid",
        "pourquoi": "Le créateur est juste ; c'est le recommandeur qui était "
                    "réduit au prénom. Article Wikipédia « Matthieu Chedid ».",
    },
    "ubm-2551": {
        "attendu": {"creator": "Matthieu Chedid", "recommendedBy": "Matthieu"},
        "recommande_par": "Matthieu Chedid",
        "pourquoi": "Même cas que ubm-2543 : prénom seul complété, le créateur "
                    "n'est pas touché.",
    },
    "ubm-2544": {
        "attendu": {"creator": "Andrée Chedid",
                    "recommendedBy": "Matthieu Chédid"},
        "recommande_par": "Matthieu Chedid",
        "pourquoi": "DEUX PERSONNES DISTINCTES, et non deux graphies : Andrée "
                    "Chedid est la poétesse, Matthieu Chedid son petit-fils "
                    "qui la recommande. Le créateur reste inchangé ; seul "
                    "l'accent fautif du recommandeur est retiré — l'article "
                    "Wikipédia s'intitule « Matthieu Chedid », sans accent "
                    "(patronyme libanais).",
    },
    # ==================================================================
    # LIENS D'ÉCOUTE — 13 recos musicales qui n'en avaient aucun.
    #
    # L'outil automatique les avait toutes REFUSÉES, chacune pour une raison
    # juste : identifiant stocké d'un autre genre que la reco, titre qui
    # désigne l'artiste et non l'album, ou nom de scène que la comparaison ne
    # pouvait pas relier (« -M- » pour Matthieu Chedid). Résolues une par une
    # contre l'API Deezer.
    #
    # RÈGLE SUIVIE : quand l'œuvre précise n'est pas identifiable avec
    # certitude, on lie la PAGE ARTISTE — toujours juste, jamais trompeuse.
    # L'album n'est lié que lorsqu'il est nommé et confirmé. Poser un album au
    # jugé serait recommencer l'erreur des liens auto-générés par titre.
    # ==================================================================
    "ubm-0204": {
        "attendu": {"types": ["album"], "creator": "Getdown Service"},
        "creator": "Getdown Services",
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/artist/118628202"}],
        "pourquoi": "Le duo de Bristol s'appelle « Getdown ServiceS » au "
                    "pluriel (Deezer, artist/118628202) — le « s » manquant "
                    "faisait échouer l'appariement. L'identifiant stocké "
                    "pointait un single (« I Can't Die Like That »), pas "
                    "l'album : on lie la page artiste, la citation ne nommant "
                    "aucun titre précis.",
    },
    "ubm-0283": {
        "attendu": {"types": ["musique", "artiste"]},
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/artist/670"}],
        "pourquoi": "La citation (« j'ai le vinyle, je suis un grand fan de "
                    "Francis Cabrel ») porte sur l'ARTISTE, pas sur un titre. "
                    "L'identifiant stocké désignait un morceau isolé.",
    },
    "ubm-0558": {
        "attendu": {"types": ["album", "artiste"]},
        "creator": "Al'Tarba",
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/artist/201875"}],
        "pourquoi": "Créateur absent, alors que le titre le donne. "
                    "L'identifiant déjà stocké résout bien vers « Al'Tarba » "
                    "(artist/201875). La citation dit « le dernier album » sans "
                    "le nommer : page artiste.",
    },
    "ubm-0846": {
        "attendu": {"types": ["musique", "album", "artiste"],
                    "creator": "Sam Bean"},
        "creator": "Sam Beam",
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/artist/1653"}],
        "pourquoi": "Iron & Wine est le projet de Sam BEAM — « Sam Bean » est "
                    "une restitution phonétique. La citation confond le nom du "
                    "projet avec celui d'un album (« un nouvel album qui "
                    "s'appelle Iron and Wine ») : on lie la page artiste.",
    },
    "ubm-1081": {
        "attendu": {"types": ["album"]},
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/album/12191970"}],
        "pourquoi": "L'album éponyme « Clou » de Clou existe bien "
                    "(album/12191970). L'identifiant stocké pointait la page "
                    "artiste, d'où le refus « stored-kind-mismatch ».",
    },
    "ubm-1135": {
        "attendu": {"types": ["musique", "artiste"]},
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/artist/88895962"}],
        "pourquoi": "« Winter Zuko ? Très bonne artiste. » — la reco porte sur "
                    "l'artiste. L'identifiant stocké était déjà le bon, il "
                    "n'était simplement pas exposé en lien visible.",
    },
    "ubm-1143": {
        "attendu": {"types": ["album"]},
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/album/303859177"}],
        "pourquoi": "L'album « Rêvalité » est bien celui-là (album/303859177). "
                    "Le refus venait du NOM DE SCÈNE : Deezer crédite « -M- », "
                    "que la comparaison ne pouvait pas relier à « Matthieu "
                    "Chedid ».",
    },
    "ubm-1164": {
        "attendu": {"types": ["musique", "artiste"]},
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/artist/436163"}],
        "pourquoi": "« c'est un groupe qui s'appelle Jungle, c'est des anglais » "
                    "— la reco porte sur le groupe. L'identifiant stocké "
                    "désignait un morceau (« Back On 74 »).",
    },
    "ubm-1265": {
        "attendu": {"types": ["album"]},
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/album/711471"}],
        "pourquoi": "« Mister Mystère » est un album de -M- (album/711471). "
                    "Aucun identifiant n'était stocké, et le nom de scène "
                    "empêchait l'appariement automatique.",
    },
    "ubm-1487": {
        "attendu": {"types": ["artiste", "musique"]},
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/artist/14"}],
        "pourquoi": "La citation se réduit à « qui est Gorillaz » : c'est le "
                    "groupe qui est recommandé, pas un album. Page artiste "
                    "canonique (artist/14, 94 albums).",
    },
    "ubm-1708": {
        "attendu": {"types": ["album"]},
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/artist/259450"}],
        "pourquoi": "Le titre « Album de Mina Tindle » est une description, pas "
                    "un nom d'album, et la citation ne le nomme pas non plus "
                    "(« l'album qui vient de sortir »). Trois albums récents "
                    "existent : choisir au jugé serait inventer. Page artiste.",
    },
    "ubm-2482": {
        "attendu": {"types": ["artiste", "musique"]},
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/artist/4441488"}],
        "pourquoi": "« j'adore Vulfpeck » — le groupe, sans album désigné. "
                    "L'API Apple renvoyait un morceau isolé (« Dean Town »), "
                    "d'où le refus.",
    },
    "ubm-2776": {
        "attendu": {"types": ["musique", "artiste"]},
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/artist/10388918"}],
        "pourquoi": "J Lloyd est le projet solo de Josh Lloyd-Watson, "
                    "co-chanteur de Jungle — ce que dit la citation. Deezer "
                    "propose « Feelin' Good » là où la reco écrit « Feel "
                    "Good » : l'écart de titre ne permet pas d'affirmer qu'il "
                    "s'agit du même morceau, on lie donc l'artiste.",
    },
    # Trois cas que la premiere liste de plateformes ratait — trouves par le
    # garde-fou `tests/test_corpus_createurs.py` des sa premiere execution.
    "ubm-1166": {
        "attendu": {"creator": "Apple TV+"},
        "creator": "Dan Erickson",
        "pourquoi": ("Cree par Dan Erickson (TMDB tv/95396, champ "
                     "`created_by`). « Apple TV+ » est le diffuseur."),
    },
    "ubm-2275": {
        "attendu": {"creator": "Apple TV+"},
        "creator": "Brett Goldstein, Jason Segel, Bill Lawrence",
        "pourquoi": ("Les trois createurs credites par TMDB tv/136311, dont "
                     "Apple TV n'est que le diffuseur."),
    },
    "ubm-0294": {
        "attendu": {"creator": "TF1"},
        "creator": None,
        "pourquoi": ("« TF1 » est doublement faux : ce n'est pas un createur, "
                     "et ce n'est meme pas le diffuseur — la reco pointe "
                     "Netflix. TMDB ne credite personne pour cette "
                     "tele-realite, on retire donc sans remplacer."),
    },
    # --- Solde de la revue utilisateur (2026-08-18) ------------------------
    "ubm-0265": {
        "attendu": {"creator": "Non précisé", "title": "Un ours dans le Jura"},
        "creator": "Franck Dubosc",
        "pourquoi": ("« Non precise » n'est pas une donnee, c'est un aveu "
                     "d'echec de l'extraction — et il s'AFFICHE sur la carte. "
                     "TMDB movie/1210732, deja reference par la reco, credite "
                     "Franck Dubosc a la realisation."),
    },
    "ubm-1611": {
        "attendu": {"title": "Adèle Fugazi", "creator": "Adel Fugazi"},
        "titre": "Adel Fugazi",
        "pourquoi": ("Le titre gardait la graphie fautive apres correction du "
                     "createur, si bien que la meme reco portait les deux. "
                     "L'humoriste ecrit son nom « Adel Fugazi » — son site "
                     "`adelfugazi.fr` et sa page BilletReduc le disent."),
    },
    # --- Une PLATEFORME n'est pas un createur (2026-08-18) ------------------
    # Quinze recos creditaient leur diffuseur : « Netflix » pour « La Chute
    # de la maison Usher » (Mike Flanagan), « HBO » pour « Silicon Valley ».
    # C'est faux, c'est VISIBLE sur les cartes, et cela empechait au moins un
    # rapprochement d'œuvres identiques (cf. ubm-0670).
    # Les trois derniers cas sont RETIRES plutot que corriges : aucune source
    # consultee ne nomme l'auteur, et un faux createur vaut moins que rien.

    "ubm-0142": {
        "attendu": {"creator": 'YouTube'},
        "creator": 'Augustin Heliot',
        "pourquoi": "TheGreatReview est le pseudonyme d'Augustin Heliot — sa fiche Wikipedia, DEJA liee par la reco, le dit des sa premiere phrase.",
    },
    "ubm-0155": {
        "attendu": {"creator": 'Disney+'},
        "creator": 'Emma Moran',
        "pourquoi": 'Creee par Emma Moran (TMDB tv/47907, champ `created_by`).',
    },
    "ubm-0156": {
        "attendu": {"creator": 'Netflix'},
        "creator": 'Mike Flanagan',
        "pourquoi": 'Creee par Mike Flanagan (TMDB tv/157065, champ `created_by`).',
    },
    "ubm-0669": {
        "attendu": {"creator": 'HBO'},
        "creator": 'Mike Judge, John Altschuler, Dave Krinsky',
        "pourquoi": 'Les trois createurs credites par TMDB tv/60573 (`created_by`).',
    },
    "ubm-0670": {
        "attendu": {"creator": 'Netflix'},
        "creator": 'Yacine Belhousse',
        "pourquoi": "La reco JUMELLE ubm-0653 porte la meme œuvre — meme page de production `empreintedigitale.net/rire` — et le bon createur. C'est d'ailleurs ce `creator` fautif qui empechait `align_same_work_links` de rapprocher les deux, faute de createurs compatibles.",
    },
    "ubm-0696": {
        "attendu": {"creator": 'Netflix'},
        "creator": 'Greg Whiteley',
        "pourquoi": 'Realisee par Greg Whiteley (Wikidata Q25842244, propriete P57).',
    },
    "ubm-1043": {
        "attendu": {"creator": 'HBO'},
        "creator": 'Michael Lannan',
        "pourquoi": 'Creee par Michael Lannan (TMDB tv/57774, champ `created_by`).',
    },
    "ubm-1055": {
        "attendu": {"creator": 'Arte'},
        "creator": 'Jean-Pierre Thorn',
        "pourquoi": 'Documentaire de Jean-Pierre Thorn (Wikidata Q109024390, propriete P57).',
    },
    "ubm-2477": {
        "attendu": {"creator": 'Netflix'},
        "creator": 'Mark Lewis',
        "pourquoi": 'Ecrit et realise par Mark Lewis, sorti sur Netflix en decembre 2019 (article Wikipedia de la serie).',
    },
    "ubm-2529": {
        "attendu": {"creator": 'Netflix'},
        "creator": 'Smriti Mundhra',
        "pourquoi": 'Creee par Smriti Mundhra, presentee comme telle par Variety.',
    },
    "ubm-2528": {
        "attendu": {"creator": 'Netflix'},
        "creator": None,
        "pourquoi": "Ni TMDB ni Wikidata ne creditent de realisateur pour cette serie. Mieux vaut PAS de createur qu'un faux : « Netflix » est la plateforme de diffusion, et le corpus compte deja 902 recos sans createur connu.",
    },
    "ubm-2592": {
        "attendu": {"creator": 'Deezer'},
        "creator": None,
        "pourquoi": "« Deezer » est la plateforme d'ecoute, pas l'auteur du podcast, et aucune source consultee ne le nomme.",
    },
    # --- Fiches et types : solde des manques (2026-08-18) ------------------
    "ubm-0282": {
        "attendu": {"title": "Devil's Plan"},
        "ajouter_liens": [{"label": "TMDB", "kind": "info",
                           "ethics": "neutral",
                           "url": "https://www.themoviedb.org/tv/214582"}],
        "pourquoi": ("Télé-réalité coréenne de Netflix, que TMDB titre "
                     "« The Devil's Plan » — d'où le refus de la garde de "
                     "titre de la passe. L'identifiant Netflix 81653386 de la "
                     "reco tranche."),
    },
    "ubm-1106": {
        "attendu": {"title": "Coco Rico"},
        "ajouter_liens": [{"label": "TMDB", "kind": "info",
                           "ethics": "neutral",
                           "url": "https://www.themoviedb.org/tv/227640"}],
        "pourquoi": ("« Kôkôrikô ! » de Jean-Pascal Zadi, Canal+ 2023 : le "
                     "titre de la reco en est la transcription phonétique, et "
                     "le lien Apple TV déjà posé contient le slug "
                     "« kokoriko »."),
    },
    "ubm-0565": {
        "attendu": {"types": ["musique", "spectacle", "autre", "film",
                              "artiste"],
                    "title": "Michael Jackson"},
        "types": ["musique", "spectacle", "autre", "artiste"],
        "pourquoi": ("La reco porte sur la PERSONNE, pas sur une œuvre : "
                     "« je vous conseille Michael Jackson ». Le type `film` "
                     "réclamait une fiche d'œuvre et un moyen de la voir, "
                     "qu'aucun catalogue ne peut fournir pour un artiste. Les "
                     "types restants disent ce qu'il est."),
    },
    "ubm-1594": {
        "attendu": {"types": ["film"],
                    "title": "Les grands classiques d'Hitchcock"},
        "types": ["autre"],
        "pourquoi": ("« aller voir les grands classiques d'Hitchcock » "
                     "désigne un CORPUS, pas une œuvre : il n'existe ni fiche "
                     "ni page de visionnage pour une filmographie. Le seul "
                     "lien de la reco est d'ailleurs l'article Wikipédia du "
                     "réalisateur."),
    },
    # --- Fiches posées directement (2026-08-17) ---------------------------
    # La passe d'enrichissement refuse ces cas sur sa garde de titre, et
    # elle a raison : le titre de la reco est celui prononcé à l'antenne,
    # pas celui de la fiche. Chaque identifiant ci-dessous a néanmoins été
    # re-interrogé auprès de l'API TMDB avant d'être écrit.

    "ubm-1001": {
        "attendu": {"title": 'Bref 2'},
        "ajouter_liens": [{"label": "TMDB", "kind": "info", "ethics": "neutral",
                           "url": "https://www.themoviedb.org/tv/60715"}],
        "pourquoi": 'TMDB ne fait pas de fiche distincte pour « Bref 2 » : la saison 2 (diffusée en 2025) vit dans la fiche de « Bref ». Le lien est posé ici plutôt que par la passe, dont la garde de titre refusait — à raison, puisque les deux titres diffèrent.',
    },
    "ubm-1937": {
        "attendu": {"title": 'Bref 2'},
        "ajouter_liens": [{"label": "TMDB", "kind": "info", "ethics": "neutral",
                           "url": "https://www.themoviedb.org/tv/60715"}],
        "pourquoi": "Même œuvre que ubm-1001 : TMDB ne fait pas de fiche distincte pour "
                    "la saison 2 de « Bref », qui vit dans la fiche de la série.",
    },
    "ubm-1668": {
        "attendu": {"title": 'LOL'},
        "ajouter_liens": [{"label": "TMDB", "kind": "info", "ethics": "neutral",
                           "url": "https://www.themoviedb.org/tv/122228"}],
        "pourquoi": "« LOL : Qui rit, sort ! », que désigne le lien Prime Video de la reco. La reco porte le titre court employé à l'antenne.",
    },
    "ubm-1890": {
        "attendu": {"title": 'Jim and Andy'},
        "ajouter_liens": [{"label": "TMDB", "kind": "info", "ethics": "neutral",
                           "url": "https://www.themoviedb.org/movie/469019"}],
        "pourquoi": '« Jim & Andy: The Great Beyond », titré « Jim et Andy » en français.',
    },
    "ubm-2008": {
        "attendu": {"title": 'Loup-Garou Saison 2'},
        "ajouter_liens": [{"label": "TMDB", "kind": "info", "ethics": "neutral",
                           "url": "https://www.themoviedb.org/tv/270963"}],
        "pourquoi": '« Loups Garous », série Canal+ de 2024 dont la saison 2 existe bien.',
    },
    "ubm-2527": {
        "attendu": {"title": "QB1", "creator": "Netflix"},
        # « Netflix » est le diffuseur ; TMDB tv/70274 credite Peter Berg.
        "creator": "Peter Berg",
        "ajouter_liens": [{"label": "TMDB", "kind": "info", "ethics": "neutral",
                           "url": "https://www.themoviedb.org/tv/70274"}],
        "pourquoi": "« QB1: Beyond the Lights », titré « Apprentis quarterbacks » en français — d'où le refus de la garde de titre. L'identifiant Netflix 81003033 de la reco tranche.",
    },
    "ubm-3031": {
        "attendu": {"title": 'Inside'},
        "ajouter_liens": [{"label": "TMDB", "kind": "info", "ethics": "neutral",
                           "url": "https://www.themoviedb.org/movie/823754"}],
        "pourquoi": "« Bo Burnham: Inside », que désigne l'identifiant Netflix 81289483 de la reco.",
    },
    "ubm-3147": {
        "attendu": {"title": 'NTM Authentiques : Un an avec le suprême'},
        "ajouter_liens": [{"label": "TMDB", "kind": "info", "ethics": "neutral",
                           "url": "https://www.themoviedb.org/movie/95309"}],
        "pourquoi": '« Authentiques » (2000), documentaire suivant Suprême NTM pendant un an — ce que le titre de la reco décrit mot pour mot.',
    },
    # --- Fiches hors TMDB, page atteinte et titre relevé ------------------
    "ubm-0587": {
        "attendu": {"title": 'Invisible'},
        "ajouter_liens": [{"label": 'TheTVDB', "kind": "info",
                           "ethics": "neutral",
                           "url": 'https://www.thetvdb.com/series/invisible1'}],
        "pourquoi": "Absente de TMDB : vérifié sur la filmographie complète de Clément Cotentin. La page TheTVDB atteinte s'intitule bien « Invisible ».",
    },
    "ubm-0633": {
        "attendu": {"title": 'Chambre froide'},
        "ajouter_liens": [{"label": 'AlloCiné', "kind": "info",
                           "ethics": "neutral",
                           "url": 'https://www.allocine.fr/film/fichefilm_gen_cfilm=277971.html'}],
        "pourquoi": 'Page AlloCiné atteinte : « Chambre Froide - Court Métrage », de Swann Périssé et Nadja Anane.',
    },
    "ubm-1643": {
        "attendu": {"title": 'Minuit'},
        "ajouter_liens": [{"label": 'SensCritique', "kind": "info",
                           "ethics": "neutral",
                           "url": 'https://www.senscritique.com/serie/minuit/41777566'}],
        "pourquoi": 'Websérie de 2020 de Roman Frayssinet, absente de TMDB. Page atteinte : « Minuit - Websérie (2020) ».',
    },
    "ubm-2707": {
        "attendu": {"title": 'Gus'},
        "ajouter_liens": [{"label": 'SensCritique', "kind": "info",
                           "ethics": "neutral",
                           "url": 'https://www.senscritique.com/serie/GUS/38953092'}],
        "pourquoi": 'Websérie française, absente de TMDB, où « Gus » ne renvoie que des homonymes. Page atteinte : « GUS - Websérie ».',
    },
    "ubm-2898": {
        "attendu": {"title": 'Trilogie des Auberges espagnoles'},
        "ajouter_liens": [{"label": 'TMDB', "kind": "info",
                           "ethics": "neutral",
                           "url": 'https://www.themoviedb.org/collection/239766'}],
        "pourquoi": "Une COLLECTION TMDB, pas une fiche d'œuvre : le schéma n'accepte que `movie` ou `tv` en `tmdbType`, d'où un lien direct. Elle contient exactement les trois films des liens Sooner déjà posés.",
    },
    "ubm-1045": {
        "attendu": {"title": "Close Up"},
        "retirer_liens": ["themoviedb.org/tv/63498",
                          "imdb.com/title/tt4931888"],
        "retirer_external_ids": ["imdb"],
        "pourquoi": "Le pire cas de l'audit des identifiants TMDB du "
                    "2026-08-17. La reco parle de « Close-up », websérie "
                    "française — ses deux autres liens sont la chaîne YouTube "
                    "@closeuplaserie7920 et la citation dit « Close-up, c'est "
                    "vraiment, j'adore ». Or l'identifiant TMDB (tv/63498) ET "
                    "l'identifiant IMDb (tt4931888) désignent tous deux "
                    "« Close Up with The Hollywood Reporter », une émission "
                    "américaine sans rapport — l'un renvoyant à l'autre, ils "
                    "se confirmaient mutuellement. Le lien TMDB était DÉJÀ "
                    "VISIBLE sur le site : c'est le seul de l'audit à avoir "
                    "franchi le stade de l'identifiant invisible.",
    },
    "ubm-0588": {
        "attendu": {"types": ["livre", "video"], "title": "Fouloscopie"},
        "ajouter_liens": [{"label": "Place des Libraires", "kind": "buy",
                           "ethics": "indie",
                           "url": "https://www.placedeslibraires.fr/livre/"
                                  "9782290236161-fouloscopie-ce-que-la-foule-"
                                  "dit-de-nous-mehdi-moussaid/"}],
        "pourquoi": "La reco est typée `livre` sans aucun libraire : son seul "
                    "lien était la chaîne YouTube. « Fouloscopie — ce que la "
                    "foule dit de nous », de Mehdi Moussaïd, existe en deux "
                    "éditions ; on retient le poche J'ai Lu (9782290236161) "
                    "plutôt que l'originale HumenSciences, cohérent avec les "
                    "choix de la table `EDITIONS`, qui privilégie le format "
                    "abordable.",
    },
    # =======================================================================
    # TYPES CORRIGÉS — arbitrage du 2026-08-17
    #
    # Ces recos réclamaient un lien que leur type appelait mais que leur nature
    # rend introuvable : une chaîne YouTube n'a pas de flux podcast, une
    # émission de Prime Video ne se joue pas. Dans chaque cas la CITATION dit
    # de quoi il s'agit, et les liens déjà posés le confirment.
    # =======================================================================
    # --- Chaînes et émissions vidéo étiquetées `podcast` --------------------
    "ubm-0984": {
        "attendu": {"types": ["podcast"], "title": "M. Phi"},
        "types": ["chaine", "video"],
        "pourquoi": "« il fait des fausses interviews », et le seul lien est "
                    "la chaîne YouTube @MonsieurPhi. Aucun flux podcast.",
    },
    "ubm-0667": {
        "attendu": {"types": ["chaine", "video"], "title": "Gaming Historian",
                    "creator": "YouTube"},
        "types": ["chaine", "video"],
        # « YouTube » est la plateforme : la chaine est celle de Norman
        # Caruso, qui la tient depuis 2008 (article Wikipedia).
        "creator": "Norman Caruso",
        "pourquoi": "« c'est un gars qui fait l'histoire des jeux vidéo », "
                    "seul lien @GamingHistorian.",
    },
    "ubm-0647": {
        "attendu": {"types": ["autre", "video", "podcast"], "title": "ASKIP"},
        "types": ["autre", "video"],
        "pourquoi": "« c'est une émission sympa » : YouTube et Twitch, pas de "
                    "flux podcast.",
    },
    "ubm-2894": {
        "attendu": {"types": ["video", "podcast"], "title": "Bon bah Voilà"},
        "types": ["video"],
        "pourquoi": "« ils font vraiment des sketchs vidéos » — RTS Play et "
                    "une playlist YouTube.",
    },
    "ubm-2659": {
        "attendu": {"types": ["podcast", "video"], "title": "L'Épopée temporelle"},
        "types": ["video"],
        "pourquoi": "Série web de François Descraques, publiée en playlist "
                    "YouTube.",
    },
    # --- Émissions de plateforme étiquetées autrement -----------------------
    "ubm-2230": {
        "attendu": {"types": ["podcast"], "title": "True Story"},
        "types": ["serie"],
        "pourquoi": "« C'est un programme pour Amazon Prime qui consiste à "
                    "inviter des guests » : ses deux liens sont Prime Video et "
                    "une fiche série AlloCiné.",
    },
    "ubm-2892": {
        "attendu": {"types": ["serie"], "title": "LOL",
                    "creator": "Amazon Prime"},
        # Kyan Khojandi dit « j'ai fait un jeu qui s'appelle LOL », mais il y
        # a PARTICIPE comme candidat : « faire » ne dit pas s'il l'a cree. On
        # retire la plateforme sans lui substituer une attribution douteuse.
        "creator": None,
        # Le type est DÉJÀ corrigé — la ligne ci-dessous ne fait plus rien,
        # mais elle documente l'arbitrage et redeviendrait active si le type
        # régressait. La garde, elle, porte sur l'état COURANT : la laisser
        # sur `["jeu"]` aurait rendu l'entrée muette, et le lien ci-dessous
        # ne serait jamais posé.
        "types": ["serie"],
        "ajouter_liens": [{"label": "TMDB", "kind": "info",
                           "ethics": "neutral",
                           "url": "https://www.themoviedb.org/tv/122228"}],
        "pourquoi": "Le locuteur dit « un jeu », mais il parle de l'émission "
                    "« LOL : Qui rit, sort ! » qu'il a CONÇUE pour Prime "
                    "Video — on la regarde, on n'y joue pas.",
    },
    # --- `livre` en trop ----------------------------------------------------
    "ubm-0255": {
        "attendu": {"types": ["film", "livre"], "title": "Panique"},
        "types": ["film"],
        "pourquoi": "« je peux voir Panique de Duvivier » : la citation ne "
                    "parle que du film. Le roman de Simenon dont il est tiré "
                    "porte un autre titre et n'est pas recommandé ici.",
    },
    "ubm-2273": {
        "attendu": {"types": ["livre"], "title": "Les Femmes Marrantes"},
        "types": ["podcast"],
        "pourquoi": "Épisode du podcast « Désirer » de Louie Media : les deux "
                    "liens de la reco sont la page Louie Media et le podcast "
                    "sur Apple Podcasts.",
    },
    # --- Livres-jeux --------------------------------------------------------
    # Les Éditions du Trésor publient des chasses au trésor : ce sont des
    # livres autant que des jeux, et c'est chez l'éditeur qu'on les achète.
    "ubm-2860": {
        "attendu": {"types": ["jeu"], "title": "Le Trésor de l'Île au Crâne"},
        "types": ["jeu", "livre"],
        "pourquoi": "Chasse au trésor des Éditions du Trésor, vendue en "
                    "librairie (le lien Cultura de la reco le montre).",
    },
    # --- Un langage n'est pas une application -------------------------------
    "ubm-0826": {
        "attendu": {"types": ["application"], "title": "Python"},
        "types": ["autre"],
        "pourquoi": "« Je vais mettre en avant le langage Python » : un "
                    "langage de programmation ne s'installe pas depuis une "
                    "boutique d'applications, et `python.org` en est la "
                    "référence.",
    },
    "ubm-0985": {
        "attendu": {"title": "Le Précepteur"},
        "ajouter_liens": [{"label": "YouTube", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.youtube.com/@Le_Precepteur"}],
        "pourquoi": "La reco est typée `chaine` sans aucun lien de vidéo. "
                    "L'adresse ne vient pas d'une recherche mais du site "
                    "officiel `le-precepteur.fr`, qui l'annonce lui-même ; les "
                    "trois formes qu'il donne (@Le_Precepteur, deux variantes "
                    "en /c/) convergent vers la même chaîne "
                    "UCvRgiAmogg7a_BgQ_Ftm6fA, intitulée « Le Précepteur ». "
                    "Un code HTTP 200 ne prouve rien chez YouTube : c'est "
                    "cette convergence qui vaut vérification.",
    },
    # --- Billetteries relevées sur BilletRéduc le 2026-08-17 ---------------
    # Deux seulement, et c'est le résultat honnête : sur vingt spectacles
    # cherchés, le reste ne s'y trouve pas. BilletRéduc couvre surtout le
    # théâtre parisien à tarif réduit ; les humoristes en tournée vendent
    # ailleurs. Les faux positifs écartés méritent d'être nommés, parce qu'ils
    # auraient tous passé une vérification par le seul titre : « Tribute Céline
    # Dion » (un hommage, pas la chanteuse), « Art Fresca Concert spectacle »
    # (pas la pièce de Yasmina Reza), deux Barthélémy sans rapport avec
    # Maurice.
    "ubm-1514": {
        "attendu": {"title": "La tragédie du dossard 512"},
        "ajouter_liens": [{"label": "BilletRéduc", "kind": "buy",
                           "ethics": "neutral",
                           "url": "https://www.billetreduc.com/spectacle/"
                                  "la-tragedie-du-dossard-512-408258"}],
        "pourquoi": "Le spectacle tourne toujours : BilletRéduc l'affiche sous "
                    "« Yohann Métay dans La tragédie du dossard 512 », qui "
                    "nomme l'interprète porté par le champ créateur. La reco "
                    "n'avait que le site personnel de l'artiste.",
    },
    "ubm-2411": {
        "attendu": {"title": "Murmuration"},
        "ajouter_liens": [{"label": "BilletRéduc", "kind": "buy",
                           "ethics": "neutral",
                           "url": "https://www.billetreduc.com/spectacle/"
                                  "murmuration-404221"}],
        "pourquoi": "« Murmuration Level 2 », mis en scène par Sadeck "
                    "Berrabah — le metteur en scène est nommé sur la page de "
                    "BilletRéduc et c'est le créateur de la reco. Dates au "
                    "Dôme de Paris en décembre 2026.",
    },
    "ubm-0862": {
        "attendu": {"types": ["serie"], "title": "Documentaire sur Orelsan"},
        "titre": "Montre jamais ça à personne",
        "pourquoi": "Le titre était une DESCRIPTION, pas un nom d'œuvre. Les "
                    "deux liens de la reco le donnent eux-mêmes : l'URL Apple "
                    "TV contient « orelsan--montre-jamais-ca-a-personne », "
                    "celle de Prime Video « ORELSAN-Montre-jamais-ça-à-"
                    "personne ». Réalisé par Clément Cotentin, son frère, "
                    "déjà porté par le champ créateur.",
    },
    "ubm-1027": {
        "attendu": {"types": ["podcast", "video"]},
        "types": ["chaine", "video"],
        "creator": "Mehdi Moussaïd",
        "pourquoi": "Fouloscopie n'est PAS un podcast mais une chaîne YouTube "
                    "(et un livre) de Mehdi Moussaïd — c'est d'ailleurs le seul "
                    "lien de la reco, et la citation dit « sur sa chaîne "
                    "YouTube ». Les deux autres recos du même sujet "
                    "(ubm-0588, ubm-1958) portent déjà la bonne graphie, "
                    "confirmée par le lien Wikipédia de ubm-1958.",
    },
    "ubm-0772": {
        "attendu": {"types": ["artiste"], "creator": "Corey Wong"},
        "creator": "Cory Wong",
        "ajouter_liens": [{"label": "Deezer", "kind": "streaming",
                           "ethics": "neutral",
                           "url": "https://www.deezer.com/artist/8607980"}],
        "pourquoi": "Le TITRE portait déjà la bonne graphie, « Cory Wong » — "
                    "c'est le créateur qui suivait la transcription "
                    "(« Corey »). Guitariste de Vulfpeck, comme le dit la "
                    "citation ; Deezer artist/8607980, 76 albums.",
    },
    "ubm-1896": {
        "attendu": {"types": ["artiste", "autre"], "title": "Bobby"},
        "titre": "Odieux Boby",
        "creator": "Odieux Boby",
        "retirer_external_ids": ["deezer"],
        "pourquoi": "PAS UN MUSICIEN. La citation dit « une expo de Bobby le "
                    "PHOTOGRAPHE », et les deux liens de la reco pointent le "
                    "Musée National du Sport et la page Wikipédia « Odieux "
                    "Boby » — Boris Allin, photographe et photojournaliste. Un "
                    "`externalIds.deezer` avait pourtant été stocké : un faux "
                    "positif d'une passe automatique, qu'une prochaine aurait "
                    "promu en lien d'écoute vers un homonyme. Retiré.",
    },
    # --- Derniers liens redondants, vérifiés page par page ----------------
    # Ces trois-là échappaient aux règles automatiques : les identifiants
    # diffèrent, seule la page servie est la même. Il fallait la charger pour
    # le savoir.
    "ubm-0820": {
        "attendu": {"types": ["serie"]},
        "retirer_liens": ["browse/entity-8f8c5cbb"],
        "pourquoi": "Deux liens Disney+ aux identifiants différents servent la "
                    "MÊME page : « Regarder Loki | Épisodes complets », même "
                    "description. `/browse/entity-…` est une forme interne "
                    "redondante ; on garde `/series/loki/`, lisible et stable.",
    },
    "ubm-2285": {
        "attendu": {"types": ["serie"]},
        "retirer_liens": ["/-/nl/detail/0KVMM"],
        "pourquoi": "Le second lien Prime Video est une entrée du catalogue "
                    "NÉERLANDAIS (`/-/nl/`), avec un autre identifiant : rien "
                    "ne garantit sa disponibilité depuis la France. Le lien "
                    "français reste.",
    },
    "ubm-3197": {
        "attendu": {"types": ["serie"]},
        "retirer_liens": ["/-/nl/detail/0KVMM"],
        "pourquoi": "Même cas que ubm-2285 — catalogue néerlandais, "
                    "identifiant distinct, disponibilité non garantie ici.",
    },
    # --- « créateur = titre » : quatre vrais défauts, un cas légitime ------
    # `ubm-1081` (« Clou ») N'EST PAS dans cette liste : l'album éponyme d'une
    # artiste nommée Clou existe bel et bien, et la répétition y est juste.
    "ubm-2692": {
        "attendu": {"types": ["application"], "title": "Dailyo"},
        "titre": "Daylio",
        "creator": None,
        "pourquoi": "L'application s'appelle DAYLIO — ses deux liens le disent "
                    "(daylio.net, et l'App Store « daylio-journal-intime-"
                    "humeur »). « Dailyo » est la restitution phonétique de la "
                    "citation. Le créateur répétait le titre : une application "
                    "a un éditeur, pas un créateur homonyme.",
    },
    "ubm-0487": {
        "attendu": {"types": ["spectacle"], "title": "I Will Survive"},
        "titre": "I Will Survive",
        "retirer_liens": ["chiensdenavarre.com/spectacles"],
        "pourquoi": "La citation parle de « la dernière PIÈCE des Chiens de "
                    "Navarre », et le lien officiel pointe `/i-will-survive`. "
                    "Le titre nommait la troupe, pas le spectacle — le "
                    "créateur, lui, était déjà juste. "
                    "LE TITRE UNE FOIS CORRIGÉ, la garde a cessé de mordre et "
                    "le retrait de lien n'a jamais tourné : la page générique "
                    "`/spectacles` doublonnait toujours celle du spectacle. "
                    "La garde porte désormais sur l'état d'ARRIVÉE, de sorte "
                    "que les deux effets restent solidaires.",
    },
    "ubm-2719": {
        "attendu": {"types": ["lieu"], "creator": "Barbès Comedy Club"},
        "creator": None,
        "pourquoi": "Un LIEU n'a pas de créateur homonyme. La carte affichait "
                    "« Barbès Comedy Club » deux fois, en titre et en dessous.",
    },
    "ubm-2830": {
        "attendu": {"types": ["lieu"], "creator": "Kings of Comedy Club"},
        "creator": None,
        "pourquoi": "Même cas que ubm-2719 : le nom du club se répétait en "
                    "guise de créateur.",
    },
    "ubm-2409": {
        "attendu": {"types": ["autre"], "creator": "Le Gorafi"},
        "creator": None,
        "pourquoi": "Un journal satirique n'est pas son propre auteur. Le nom "
                    "se répétait sous le titre sans rien apprendre.",
    },
    "ubm-2593": {
        "attendu": {"types": ["autre"], "creator": "Anna Apter"},
        "types": ["artiste"],
        "pourquoi": "La reco porte sur une PERSONNE (lien Wikipédia à son "
                    "nom) : `artiste` est le type prévu pour cela, et la "
                    "répétition titre/créateur y devient normale. `autre` "
                    "était le type de repli faute de mieux.",
    },
    # --- Pages de listing et alias d'URL, vérifiés un par un --------------
    # Aucune règle générique ne les couvre : ce sont des sites d'artistes aux
    # chemins propres, et « /spectacles » n'est reconnaissable comme un listing
    # que si on connaît le site.
    "ubm-2154": {
        "attendu": {"types": ["serie"]},
        "retirer_liens": ["browse/entity-8f8c5cbb"],
        "pourquoi": "Même cas que ubm-0820 : les deux liens Disney+ servent la "
                    "MÊME page (« Regarder Loki | Épisodes complets », même "
                    "description), vérifié en la chargeant. `/browse/entity-…` "
                    "est une forme interne ; `/series/loki/` est lisible.",
    },
    "ubm-2861": {
        "attendu": {"types": ["jeu"], "title": "L'Ordre de Sipan"},
        "types": ["jeu", "livre"],
        "retirer_liens": ["editionsdutresor.com/lor-de-sipan"],
        "pourquoi": "L'éditeur sert le même ouvrage sous deux adresses — "
                    "`/catalogue/lor-de-sipan` et `/lor-de-sipan` répondent "
                    "toutes deux 200 avec le même titre. On garde la forme "
                    "`/catalogue/`, qui dit ce qu'elle est. "
                    "LA GARDE ÉTAIT FAUSSE : elle attendait `types: [livre]` "
                    "quand la reco porte `jeu`, si bien que l'entrée n'a "
                    "jamais tourné et que les deux adresses sont toujours là. "
                    "Le type est corrigé dans le même mouvement — une chasse "
                    "au trésor des Éditions du Trésor est un livre autant "
                    "qu'un jeu (arbitrage du 2026-08-17).",
    },
    "ubm-3128": {
        "attendu": {"types": ["spectacle"]},
        "retirer_liens": ["chiensdenavarre.com/saison-25-26"],
        "pourquoi": "`/saison-25-26` est le programme d'une saison, pas "
                    "l'œuvre. Il vieillira, `/i-will-survive` non.",
    },
    "ubm-3141": {
        "attendu": {"types": ["spectacle"]},
        "retirer_liens": ["chiensdenavarre.com/spectacles"],
        "pourquoi": "Même cas que ubm-0487 : la liste des spectacles doublait "
                    "le lien vers celui dont parle la reco.",
    },
}


def _hote(url: Any) -> str:
    """Hôte d'une URL, sans `www.` ni casse. Vide si l'URL est illisible.

    Sert à ne pas ajouter deux fois la même plateforme : c'est l'hôte, et non
    l'URL entière, qui dit « Deezer est déjà là ».
    """
    try:
        return (urlparse(str(url)).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


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
    #
    # Les listes sont comparées SANS ordre (`types` n'a pas d'ordre porteur de
    # sens), les autres valeurs telles quelles. Trier une chaîne comparerait
    # ses caractères : « Anis Rallye » et « Riens Allaye » passeraient pour
    # identiques, et la garde laisserait écrire sur une donnée qui a changé.
    attendu = fix.get("attendu") or {}
    for champ, valeur in attendu.items():
        actuel = doc.get(champ)
        if isinstance(valeur, list):
            if sorted(actuel or []) != sorted(valeur):
                return []
        elif actuel != valeur:
            return []
    changes: list[Change] = []
    if "types" in fix and sorted(doc.get("types") or []) != sorted(fix["types"]):
        changes.append(Change(field="types", before=doc.get("types"),
                              after=fix["types"]))
        doc["types"] = list(fix["types"])
    # Le TITRE est parfois une description (« Documentaire sur Orelsan ») là
    # où l'œuvre porte un nom. Le corriger change ce que le visiteur cherche.
    if "titre" in fix and doc.get("title") != fix["titre"]:
        changes.append(Change(field="title", before=doc.get("title"),
                              after=fix["titre"]))
        doc["title"] = fix["titre"]
    if "creator" in fix and doc.get("creator") != fix["creator"]:
        changes.append(Change(field="creator", before=doc.get("creator"),
                              after=fix["creator"]))
        if fix["creator"] is None:
            # RETIRER la clé, ne pas écrire `null` : la collection `recos`
            # déclare `creator: z.string().optional()` SANS `nullable`, et un
            # `null` y arrête le build. Cf. `fill_guest_creators`.
            doc.pop("creator", None)
        else:
            doc["creator"] = fix["creator"]
    # `recommendedBy` porte les mêmes fautes que `creator` — il vient parfois
    # de la même transcription. Le corriger ici plutôt que dans un outil à part
    # évite qu'une reco reste incohérente entre ses deux champs de personnes.
    if "recommande_par" in fix and doc.get("recommendedBy") != fix["recommande_par"]:
        changes.append(Change(field="recommendedBy",
                              before=doc.get("recommendedBy"),
                              after=fix["recommande_par"]))
        doc["recommendedBy"] = fix["recommande_par"]
    if "liens" in fix:
        avant = [link.get("url") for link in (doc.get("links") or [])
                 if isinstance(link, dict)]
        apres = [link["url"] for link in fix["liens"]]
        if avant != apres:
            changes.append(Change(field="links", before=avant, after=apres))
            doc["links"] = [dict(link) for link in fix["liens"]]
    # AJOUT de liens, sans toucher aux existants. Distinct de `liens`, qui
    # REDÉFINIT toute la liste : ici on complète une reco à qui il manque une
    # plateforme, sans risquer d'effacer un lien posé à la main.
    # Un lien dont l'hôte est DÉJÀ présent n'est jamais ajouté — sinon une
    # seconde exécution empilerait les doublons.
    if "ajouter_liens" in fix:
        existants = list(doc.get("links") or [])
        hotes = {_hote(link.get("url") or "") for link in existants
                 if isinstance(link, dict)}
        ajouts = [dict(link) for link in fix["ajouter_liens"]
                  if _hote(link["url"]) not in hotes]
        if ajouts:
            avant_urls = [link.get("url") for link in existants
                          if isinstance(link, dict)]
            doc["links"] = existants + ajouts
            changes.append(Change(
                field="links", before=avant_urls,
                after=[link.get("url") for link in doc["links"]
                       if isinstance(link, dict)]))
    # RETRAIT d'identifiants externes FAUX. Ils ne s'affichent nulle part —
    # et c'est précisément le danger : une passe d'enrichissement peut les
    # promouvoir en lien visible des mois plus tard. Un `externalIds.deezer`
    # posé sur un photographe finirait en lien d'écoute vers un homonyme.
    if "retirer_external_ids" in fix:
        ids = doc.get("externalIds")
        if isinstance(ids, dict):
            retires = {c: ids[c] for c in fix["retirer_external_ids"] if c in ids}
            if retires:
                for cle in retires:
                    del ids[cle]
                changes.append(Change(field="externalIds",
                                      before=retires, after=None))
                if not ids:
                    doc.pop("externalIds", None)
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
