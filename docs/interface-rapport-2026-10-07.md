# Rapport — refonte de l'interface du 2026-10-07

Une journée de travail sur l'interface publique d'Une Bonne Reco : deux audits
menés avec la grille *apple-design* (réponse au toucher, cibles, hiérarchie,
typographie), six maquettes soumises à l'éditeur puis intégrées, une carte de
partage pour chaque œuvre, et quelques corrections de données relevées en
chemin.

Trois branches portent le travail, chacune réduite à un seul commit posé sur
`main` :

| Branche | Contenu |
|---|---|
| `design/integration-2026-10-07` | code : audits, maquettes, cartes de partage, cette documentation |
| `contenu/citations-et-minutages` | données : minutages, citations, noms, invités, titres (§6) ; garde de CI |
| `pipeline/caler-citations` | chaîne venus : calage des citations de chaque nouvel épisode (§6) |

Elles ne se recouvrent pas et peuvent être fusionnées dans n'importe quel
ordre ; le contenu de préférence d'abord, sa garde de CI arrivant avec les
données qu'elle protège. L'interface **attend** ce contenu : sans lui, la
saison 6 n'a pas d'invités, la page de Florent Bernard ne montre pas La Flamme
et le découpage en chapitres de l'épisode #10 renonce (minutages hors durée).

---

## 1. Premier audit et ses corrections

Seize constats, corrigés en parallèle par lots puis raccordés. Les plus
visibles :

| Constat | Correction |
|---|---|
| Pictogramme de signalement de 13 × 24 px, liens « retour » de 16 px de haut | zone sensible de 44 px par pseudo-élément, sans décaler la mise en page |
| Aucun état `:active` dans tout le site ; survols « collés » au doigt | appui en 80 ms partout ; survols réservés à `(hover: hover) and (pointer: fine)` ; écouteur `touchstart` passif pour Safari iOS |
| `grid-auto-rows: 1fr` alignait 1 259 cartes sur la plus haute | égalisation **par rangée** seulement (revient en partie sur la demande du 2026-08-17) |
| Accueil mobile de 27 000 px (une vignette par ligne) | deux colonnes sous 560 px, chiffres-clés à deux de front |
| Galeries et statistiques publiques mais sans aucun lien d'accès | onglet « Par type » à côté de « Par épisode » / « Toutes les recos », lien « Statistiques » dans le pied de page |
| Aucune carte de reco ne menait à la fiche de son œuvre | le **titre** devient le lien (la carte porte déjà les liens plateformes) |
| « Reco de Kyan » sous une œuvre d'invité | « Présentée par X » seulement si X est créateur de l'œuvre (voir §4) |
| Formulaire de signalement hors charte, recherche en bas de page, croix d'effacement absente, numéro d'épisode écrit de deux façons, compteurs au vocabulaire flottant, deux commandes d'écoute par mention | une correction chacun |

Décisions de l'éditeur prises en route : la hauteur par rangée est acceptée ;
l'accès aux galeries passe par un 3ᵉ onglet + le pied de page.

## 2. Les maquettes retenues

Six directions, chacune proposée en plusieurs variantes sur une page de
maquettes, puis intégrée par un agent dédié dans son propre arbre de travail
et raccordée aux autres.

| Page | Direction retenue | Ce qui change |
|---|---|---|
| Cartes de partage | **B « Étiquette »** | panneau couleur d'accent, un chiffre géant, titre en Bebas Neue ; pour l'accueil, les galeries, les épisodes et les œuvres |
| Onglet « Par type » | **Variante 4** (après les variantes 1 à 3, 2 bis, 5 et 6) | carte simple de la variante 2 + grand nombre de la variante 3 ; icône au trait jaune, trois titres les plus cités sans doublon, « Voir la galerie → » ; une ligne par galerie sur téléphone |
| Fiche œuvre | **B « La récurrence »** | titre en grand + trois chiffres (mentions, recos, depuis quand) ; frise des mentions (`WorkFrise`), « Qui en parle » (`WorkVoix`), « Où la trouver » (`WorkLiens`) ; mentions par année |
| Page invité | **B « Bibliothèque »** + entrée depuis l'épisode | résumé, passages en pastilles, « Ses œuvres » d'abord, recommandations groupées par type, œuvres évoquées en une ligne ; les invités d'un épisode mènent à leur page |
| Statistiques | **A « Un constat par écran »** | grand chiffre jaune, une phrase, un graphique à l'échelle (barres HTML, valeurs écrites) ; les chiffres détaillés restent dessous |
| Page épisode | **B « Les chapitres »** | recos dans l'ordre de l'écoute, en moments séparés par des creux d'au moins 12 min ; renonce (sections par nature) dès qu'un minutage manque, est ambigu ou dépasse la durée |

La variante 4 réservait d'abord le jaune à l'icône et au lien ; le second
audit l'a étendu aux grands nombres (décision de l'éditeur, §5).

## 3. Une carte de partage pour chaque œuvre

Demande de l'éditeur : une carte par œuvre, « avoir un build long n'est pas un
souci ». Le seuil de deux mentions (`MENTIONS_MIN_CARTE_OEUVRE`) passe à 1 :
**1 073 cartes d'œuvre, 1 202 PNG en tout, 53 Mo**.

L'architecture a été revue en même temps (ADR [0050](adr/0050-cartes-partage-cache-persistant.md)) :

- le cache des cartes vivait dans `dist/.cache/og`, qu'`astro build` vide au
  début de chaque build — il n'avait **jamais** servi d'un build à l'autre
  (vérifié avec un fichier témoin) ; il passe à la racine, `.cache/og`,
  ignoré par git, qui survit au `git reset --hard` du déploiement ;
- la clé portait sur les données de la carte : persistant, le cache aurait
  resservi d'anciennes images après une retouche du gabarit. Elle porte
  désormais sur l'arbre rendu et l'empreinte des polices.

Mesuré sur la machine de développement : build à froid **299 s**, build
suivant **21 s** (51 s avant les cartes : le cache évite aussi l'accueil et
les galeries).

## 4. Le vocabulaire des mentions

`guestWork` ne veut pas dire « œuvre de la personne qui en parle » mais
« œuvre de quelqu'un présent dans l'épisode » : Pulsions, le spectacle de
Kyan, le porte dans ses neuf épisodes, y compris quand un invité le
recommande. La première correction avait produit « Présentée par Kheiron »
sous le spectacle de Kyan, relevé le jour même.

Règle en vigueur (`src/utils/verbeMention.ts`) :

- « Présentée par X » si X est parmi les créateurs de l'œuvre
  (`parleDeSonOeuvre`) ; un nom d'un seul mot est comparé au prénom des
  créateurs (« Babor ») ;
- sinon « Reco de X » sur les cartes, « Recommandée par X » dans la
  chronologie de la fiche œuvre ;
- la même règle définit « Ses œuvres » sur la page invité.

## 5. Second audit et ses corrections

Mené après l'intégration des six directions :

| Constat | Correction | Mesure |
|---|---|---|
| « Tous les films » en grille de vignettes sur téléphone | une ligne par œuvre, icône au trait jaune | 30 631 → 18 391 px |
| Pastilles « Avec » empilées, légende des chapitres sur trois lignes | pastilles en ligne, légende raccourcie au téléphone | 1ʳᵉ reco de S6·E3 : y 745 → 650 px |
| Frise de Bref : six voies de 40 px sur 315 px de large | aperçu compact (voies de 22 px), sans cibles au doigt ; la liste par année dessous garde les liens | carte de 331 px |
| Grands chiffres tantôt jaunes, tantôt blancs | **jaunes partout** (décision de l'éditeur) : « Par type », fiche œuvre, galeries, stats | — |
| « Ses œuvres » bordées de jaune, comme un survol | fond teinté, bordure neutre | — |
| Interlettrage positif sur les années de la fiche et les légendes des constats | interlettrage nul | — |
| Instagram de Bref affiché deux fois | lien social dédoublonné | 1 lien |
| « ▶ YouTube » de la chronologie sous 44 px (règle scopée sans effet sur `OutboundLink`) | `:global` ancré | 44 px |
| Chiffre des stats à 220 px, « 1 075 » lu « 1075 » en Inter | plafond à 160 px, insécable ordinaire au lieu de l'espace fine | — |

Puis, à la relecture de l'éditeur :

- « retour au podcast » n'était plus cliquable sur la page invité : le nom
  en Bebas sur 7 rem, interligne 0,88, débordait vers le haut et captait les
  clics. Les liens de retour passent au-dessus de ce qui suit, sur toutes les
  pages ;
- les cartes de reco, dernier endroit à afficher des emojis de type, passent
  aux icônes au trait jaunes, agrandies à 28 px, 24 sur
  téléphone. La classe `type-emoji` est gardée : l'outil de
  relecture s'en sert.

Les conventions qui en ressortent sont fixées dans l'ADR
[0051](adr/0051-conventions-interface.md).

## 6. Corrections de données

Sur `contenu/citations-et-minutages`, mesuré puis corrigé les 2026-10-07 et 08
(1 259 recos publiées) :

- **Minutages** : le modèle d'extraction recopiait le `[hh:mm:ss]` de la
  transcription, et rien ne le vérifiait. Chaque citation a été retrouvée
  dans la transcription — calée sur YouTube à ±1,2 s, vérifié sur 106 épisodes
  contre les sous-titres automatiques — et prend le minutage de sa ligne :
  78 recos et 79 mentions recalées (*Mortel* 00:13:21 → 00:58:15, quatre
  recos à 00:00:00), 9 minutages `mm:ss` réécrits `hh:mm:ss`, l'épisode #10
  (« 11:12:00 » pour 1 h 23) corrigé.
- **Noms dans les citations** : Whisper écorche les noms propres (« Camelot »
  pour Kaamelott, « Aurel San » pour Orelsan). 368 passages relevés, tranchés
  un par un : environ 260 citations corrigées sur la graphie de leur fiche,
  sans réécrire ce que l'invité a dit (titre français, titre mal retenu).
- **Fiches fausses**, vérifiées sur Wikipédia ou à la source : Anthony
  Marciano, Stefan Zweig, Seb Mellia, GetBackers, Disiz, Coline Rio, Clément
  Viktorovitch, Sofia Belabbes, Getdown Services, Mélie Hirtz… ; un même nom
  écrit d'une seule façon partout (Matthieu Chedid, Alex Ramirès, Jason
  Brokerss…) ; titres de films et séries comparés à Wikidata par leur
  identifiant TMDB (*La Soupe aux choux*, *Mignonnes*, *FranceKbek*…), une
  fiche en double fusionnée, *John Wick* rattaché au film de 2014.
- **Invités** : dix épisodes ne les nommaient que par le prénom (« avec
  Cédric ») ; ceux de la saison 6 manquaient. Pages invité et pastilles
  « Avec » se retrouvent.
- **Attributions** : « Bloqués » et deux recos attribuées au créateur de
  l'œuvre plutôt qu'à l'orateur, laissées sans attribution (politique de
  relecture) ; trois recos publiées sans citation en ont une ; une mention
  qui affichait une phrase sur *Euphoria* sur la fiche d'*Empathie* reprend
  celle de sa reco.
- **Garde de CI** (`tests/test_corpus_minutages_citations.py`) : minutage
  hors `hh:mm:ss`, à 00:00:00 ou au-delà de l'épisode, reco publiée sans
  citation, mention en désaccord avec sa reco.

Sur `pipeline/caler-citations` : `tools/caler_citations.py` fait la même
chose pour chaque nouvel épisode, après l'extraction ; le message Matrix cite
chaque nom rétabli (ancien → nouveau) pour que la relecture tranche. Essayé
sur l'ancien corpus : les minutages recalés sont ceux de la passe manuelle,
environ 3 % des noms rétablis sont fautifs (titre français dit par l'invité
remplacé par l'original : *Hérédité* → *Hereditary*).

Laissé en l'état, volontairement : six recos **écartées** portent encore un
minutage hh:mm:00 ; non affichées, elles ne sont pas touchées.

## 7. Ce qui a été vérifié

- Tests : 2 684 tests vitest (164 fichiers), 58 tests des cartes de partage,
  pytest vert ; a11y sur 2 685 pages, 0 violation, contraste compris.
- Build de production avec `SITE_URL=https://unebonnere.co`.
- 3 765 liens de titre de carte → tous mènent à une fiche existante.
- 1 073 fiches œuvre → toutes ont leur image de partage.
- Liens « retour » atteints par `elementFromPoint` sur sept gabarits de page,
  ordinateur et téléphone ; liens du pied de page agrandis de ±10 px sans
  déplacer leur soulignement.

## 8. Ce qu'il reste à vérifier

À faire par un humain ; aucun outil ne remplace ces regards-là.

**Avant de fusionner** (aperçu local des trois branches réunies)

- [ ] Page épisode, ordinateur et téléphone : chapitres de S6·E3 et de
      l'épisode #10, pastilles « Avec », « Leurs œuvres » ;
- [ ] Page invité : Florent Bernard (La Flamme dans « Ses œuvres »), Babor,
      Kheiron (Pulsions **pas** dans ses œuvres) ; lien « retour » cliquable ;
- [ ] Fiche œuvre : Bref (frise, Instagram une seule fois), La Flamme (trois
      créateurs), Bloqués (« Sans attribution »), une œuvre à une seule
      mention ;
- [ ] Onglet « Par type » et galeries sur téléphone : une ligne par œuvre,
      icônes et nombres jaunes ;
- [ ] Statistiques : lisibilité des constats, graphiques sur téléphone ;
- [ ] Cartes de reco : taille des icônes, lien du titre (souligné au survol,
      jaune à l'appui) ;
- [ ] Un vrai téléphone, pas seulement l'émulation : appui (`:active`) sur
      Safari iOS, aucun survol resté collé, cibles de 44 px ;
- [ ] Données, par sondage : *Kaamelott* (plus de « Camelot »), « écouter »
      de *Mortel* (58:15), `/invite/cedric-klapisch` et
      `/invite/matthieu-chedid` reliées à leur épisode, une seule fiche
      *La Soupe aux choux*.

**Au premier déploiement**

- [ ] Le build à froid prend ~5 min chez l'hébergeur (1 202 cartes) : ne pas
      le prendre pour un build bloqué ; un build **raté** laisse le site mort ;
- [ ] Au déploiement suivant, vérifier que `.cache/og` a survécu (build de
      l'ordre de la minute) ;
- [ ] Partager une fiche œuvre et une page épisode (Signal, Mastodon,
      validateur Open Graph) : la carte « Étiquette » apparaît ;
- [ ] CI Linux verte, `astro check` et la garde des minutages compris ;
- [ ] Adresses disparues (doublons) : `/invite/matthieu`, `/invite/jason-brokers`,
      `/invite/cedric`, `/invite/paul`, la fiche `f57684db` — 404 attendus ;
- [ ] Au prochain épisode sur venus : relire les noms rétablis annoncés par
      le message Matrix.

**À trancher plus tard**

- [ ] Le cache des cartes ne se purge pas : les images d'un gabarit abandonné
      s'accumulent. `rm -rf .cache/og` remet à zéro (le build suivant est à
      froid) ;
- [ ] Les six recos écartées aux minutages hh:mm:00 ;
- [ ] Graphie de « Jenny Letellier » (pas d'article Wikipédia ; forme du titre
      officiel) ;
- [ ] Linter du corpus : 15 attributions et 20 titres signalés, surtout des
      recos écartées ou des titres courts justes ; 5 doublons d'œuvres
      invisibles (*South Park*, *Paname*…).
