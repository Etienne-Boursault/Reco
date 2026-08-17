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
        "attendu": {"creator": "Panagiota Yotis-Pascault"},
        "creator": "Panayotis Pascot",
        "pourquoi": "Article Wikipédia « Panayotis Pascot ». La transcription a "
                    "coupé le prénom en deux et inventé un patronyme.",
    },
    "ubm-0734": {
        "attendu": {"creator": "Penelope Bajeux"},
        "creator": "Pénélope Bagieu",
        "pourquoi": "Article Wikipédia « Pénélope Bagieu » — accents compris.",
    },
    "ubm-0653": {
        "attendu": {"creator": "Yacine Bellous"},
        "creator": "Yacine Belhousse",
        "pourquoi": "Article Wikipédia « Yacine Belhousse ». « Bellous » est "
                    "la restitution phonétique de la transcription.",
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
    if "creator" in fix and doc.get("creator") != fix["creator"]:
        changes.append(Change(field="creator", before=doc.get("creator"),
                              after=fix["creator"]))
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
