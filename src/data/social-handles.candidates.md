# Comptes Instagram / TikTok officiels des créateurs — candidats

Rapport de la session du 2026-07-26. **Rien n'a été écrit dans les recos, rien n'a été commité.**
Données brutes exploitables : `src/data/social-handles.candidates.json`.

## Méthode

1. Extraction des créateurs distincts des 1211 recos actives de `un-bon-moment`
   (865 recos ont un `creator` renseigné, ~600 valeurs distinctes, dont 332 portent
   sur les types prioritaires artiste / musique / album / chaine / spectacle / video / podcast).
2. Traitement par ordre de fréquence décroissante, en écartant les œuvres, les
   entreprises et les chaînes génériques (Netflix, HBO, Arte, YouTube, Apple TV+,
   « autre », « N/A », « intervenant non précisé »…).
3. Une recherche web par créateur, parfois deux. Un handle n'est retenu (`"sur"`)
   que s'il satisfait **au moins un** de ces critères :
   - certification explicite / forte audience cohérente avec la notoriété ;
   - **recoupement croisé** : même handle sur X / Facebook / site officiel, ou bio
     citant précisément l'œuvre recommandée, ou compte officiel tiers qui le tague.

   Tout le reste est laissé vide et listé ci-dessous. Aucun handle n'a été deviné.

## Résultat

| | Nombre |
|---|---|
| Créateurs traités | 127 |
| Handles **sûrs** | **103** (102 Instagram, 4 TikTok) |
| Doutes / non trouvés | 24 |
| Recos actives couvertes par un handle sûr | 280 |

Un champ `variants` a été ajouté quand le même créateur apparaît sous plusieurs
orthographes dans les recos (« Orel San » / « Aurel San » / « Aurel » → Orelsan,
« Blandine Lehout » → Blandine Lehoux, « Pierre Illéré » / « Pierre-Hilaire » →
Pierre Hillairet, etc.). Toutes les valeurs `creator` et `variants` du fichier ont
été vérifiées : elles correspondent à un `creator` réellement présent dans les recos actives.

---

## 1. Trouvés — sûrs (103)

### Humoristes / scène (45)

| Créateur | Instagram | TikTok |
|---|---|---|
| Kyan Khojandi | `kyankhojandi` | |
| Thomas VDB | `thethomasvdb` | |
| Panayotis Pascot | `panayotispascot` | |
| Anna Apter | `annaapter` | |
| Rosa Bursztein | `rosabursztein` | |
| Fanny Ruwet | `fannyruwet` | |
| Marina Rollman | `marinarollman` | |
| Bérengère Krief | `berengerekrief` | |
| Florence Foresti | `madameforesti` | |
| Laura Felpin | `laura_felpin` | |
| Nordine Ganso | `nordine.ganso` | |
| Blandine Lehoux | `blandinelht` | |
| Marine Léonardi | `marineleonardi` | |
| Pierre Hillairet | `pierrehillairet_` | |
| Gad Elmaleh | `gadelmalehaccount` | |
| Laurent Baffie | `laurentbaffie` | |
| Paul Mirabel | `paulmirabel` | |
| Roman Frayssinet | `romanfrayssinet` | |
| Blanche Gardin | `blanche.gardin` | |
| Swann Périsse | `swannperisse` | `swann.perisse` |
| Alex Vizorek | `alexvizorek` | |
| Bertrand Usclat | `bertrand_usclat` | |
| Baptiste Lecaplain | `baptistelecaplain` | |
| Jérémy Ferrari | `jeremyferrarioff` | |
| Manu Payet | `manupayet` | |
| Fabrice Éboué | `ebouefabrice` | |
| Thomas Ngijol | `thomas_ngijol` | |
| Kheiron (fiché « Cairone ») | `kheiron_` | |
| Alex Lutz | `alexlutzofficiel` | |
| Éric Judor | `ericpointjudor` | |
| Yacine Belhousse | `yacinebelhousse` | |
| Charles Nouveau | `charlesnouveau` | |
| Laura Domenge | `laura_domenge` | |
| Ornella Fleury | `ornellafleury` | |
| Shirley Souagnon | `shirley_souagnon` | |
| Morgane Cadignan | `morgane_cadignan` | |
| Marc Fraize | `marcfraize` | |
| Yohann Métay | `yohann_metay` | |
| Merwane Benlazar | `merwaneb` | |
| Vérino (fiché « Olivier Balestrier ») | `verinaze` | |
| Sugar Sammy | `sugarsammyk` | |
| Jamel Debbouze | `jameldebbouze` | |
| Rudy Milstein | `rudymil` | |
| Maxime Gasteuil | `maxime.gasteuil` | |
| Xavier Lacaille | `xavier.lacaille` | |

### Musiciens (21)

| Créateur | Instagram |
|---|---|
| Orelsan | `orelsan` |
| Grand Corps Malade | `grandcorpsmaladeoff` |
| Eddy de Pretto | `eddydepretto` |
| Pomme | `pommeofficial` |
| Bigflo & Oli | `bigfloetoli` |
| Mathieu Chédid (-M-) | `m_chedid` |
| Ben Mazué | `benmazue` |
| Tim Dup | `_timdup_` |
| Vincent Delerm | `vincentdelerm` |
| Woodkid | `yoannwoodkid` |
| Stromae | `stromae` |
| Clara Luciani | `jesuisclaraluciani` |
| Zaho de Sagazan | `zahodesagazan` |
| Kemmler | `ke2mler` |
| Vald | `valdsullyvan` |
| Yann Tiersen | `yanntiersen` |
| Tessa B | `tessabmucho` |
| Nach | `nachmusicofficiel` |
| Adèle Castillon | `adelecastillon` |
| Sébastien Tellier | `sebastientellier` |
| Jain | `jainmusic` |

### YouTubeurs / vulgarisateurs / podcasteurs (20)

| Créateur | Instagram | TikTok |
|---|---|---|
| Cyprien | `6pri1` | |
| Patrick Baud (Axolot) | `patrick_baud` | |
| Charlie Danger (Les Revues du Monde) | `charlie__danger` | |
| Fabien Olicard | `fabienolicard` | `fabienolicard` |
| Feldup | `feldup_official` | |
| Mehdi Moussaïd (Fouloscopie) | `fouloscopie` | |
| Christophe Pauly (Balade Mentale) | `christophepauly.tv` | |
| Julien Ménielle (Dans ton corps) | `jmnl` | |
| Micode | `micode` | |
| François Descraques | `f_descraques` | |
| Éléonore Costes | `eleonorecostes` | |
| Seumboy (Histoires Crépues) | `seumboy` | |
| Monsieur Phi | `monsieur.phi` | |
| Manon Bril | `manonbrilcuah` | |
| McFly et Carlito | `mcflyetcarlitouniverse` | |
| Doc Géraud (Game Anatomy) | `docgeraud` | |
| Léa Rouaud | `learouaud` | |
| Les Parasites *(collectif)* | `lesparasites` | |
| Tev (Ici Japon) | — *(voir doutes)* | `tevjapon` |
| Noman Hosni | `nomanhosni` | |

### Réalisateurs / auteurs / autres (17)

| Créateur | Instagram | TikTok |
|---|---|---|
| Cédric Klapisch | `cedklap` | |
| Albert Dupontel | `albertdupontel` | |
| Alexandre Astier | `aastieroff` | |
| Pénélope Bagieu | `penelopeb` | |
| Mourad Winter | `mouradwinter` | |
| Clément Cotentin | `clementcotentin` | |
| Sonia Kronlund (Les Pieds sur terre) | `soniakronlund` | |
| Albert Moukheiber | `albert.moukheiber` | |
| Sophie-Marie Larrouy | `sophiemarielarrouy` | |
| Camille Combal | `camillecombal` | |
| Jimmy Mohamed | `dr.jimmy.mohamed` | `dr.jimmy.mohamed` |
| Sadeck Berrabah (Murmuration) | `sadeckwaff` | |
| Florence Longpré | `florencelongpre` | |
| Ricky Gervais | `rickygervais` | |
| Nathan Fielder | `nathanfielder` | |
| Bill Burr | `wilfredburr` | |
| John Mulaney | `johnmulaney` | |

**Comptes annexes relevés au passage** (utiles si tu veux lier l'œuvre plutôt que la personne) :
`levraimcfly` et `rafcarlito` (comptes individuels de McFly et Carlito),
`histoires_crepues` (415 K), `murmuration_concept` (343 K),
`yesvousaime` (collectif de Bertrand Usclat), `abientotdeterevoir` (48 K),
`ambroiseetxavier` (duo Ambroise Carminati / Xavier Lacaille),
`icijaponcorp` (société de Tev).

---

## 2. Doutes — comptes concurrents, à trancher à la main (13, plus le cas Tev dont seul le TikTok est retenu)

Ces créateurs **ont** un compte, mais deux candidats crédibles s'affrontent ou la
source est trop faible. Rien n'a été retenu.

| Créateur | Candidats | Pourquoi je n'ai pas tranché |
|---|---|---|
| **Julien Doré** | `jdoreofficiel` (824 K) / `juliendore` (~1 M) | Deux passes de recherche se contredisent. `jdoreofficiel` s'affiche « Julien Doré Øfficiel » (esthétique de l'artiste) → **le plus probable**. Le site juliendoreofficiel.com renvoie une 403. |
| **Vianney** | `vianneymusique` / `vianney` (1 M) | Sa page Facebook officielle annonçait « mon nom est vianneymusique », mais c'est `vianney` qui a l'audience. Renommage probable. |
| **Franck Dubosc** | `fdubosc_officiel` / `franckdubosc` | Aucun compteur d'abonnés pour départager. |
| **Damso** | `thedamso` / `damso_france` (120 K) / `damso___officiel_` | Il a désactivé son compte par le passé. `thedamso` correspond à son X @THEDAMSO. |
| **Booba** | `booba_officielb2o` / `boobaprtofficial` / `boobaofficial` | Trois comptes se disent « officiels ». |
| **MC Solaar** | `solaar.xw.officiel` / `mcsolaarofficiel` | Le premier est actif mais au handle atypique ; le second a 8 abonnés et 0 post. |
| **Iliona** | `iliona` (107 K) / `iliona.musique` | Risque de confusion avec la chanteuse ILONA (`ilona`, `iamilonamusic`). |
| **Emma Peters** | `emma.ptrs` | Annoncé comme officiel mais sans audience ni recoupement ; un `dj.emmapeters` (autre personne) existe. |
| **Doria Tillier** | `doriatillier` | 774 abonnés seulement : compte privé, secondaire ou homonyme. |
| **Maurice Barthélémy** | `barthelemymaurice` | Cité par un seul article Purepeople de 2019, non revérifiable. |
| **Tim Robinson** | `tsrobinson23` (655 K) | Probablement le bon, mais aucune source officielle ; le plus gros compte (`ithinkyoushouldreel`, 950 K) est un compte de fans. |
| **Renaud** | `renaud.officiel` (75 K) | Présenté comme « le merch officiel des 50 ans de carrière » : sent le compte de merchandising du label, pas celui de l'artiste. |
| **David Louapre** | `scienceetonnante` (2,5 K) | Compte de la chaîne, pas de la personne, et 2,5 K abonnés contre 1,5 M sur YouTube — non confirmé par son site ni par son X @dlouapre. |
| **Tev (Ici Japon)** | `icijapon` / `icijaponcorp` (59 K) | TikTok `tevjapon` retenu (sûr). Côté Instagram, `icijaponcorp` est le compte de la société ; `icijapon` est cité sans lien. |

## 3. Non trouvés (11)

Recherche menée, aucun handle exploitable remonté.

| Créateur | Note |
|---|---|
| **Jonathan Cohen** (4 recos) | Deux recherches. Trop d'homonymes : `jonathancohenofficial` = un Américain (podcast Bialik Breakdown), `jonathancohenstudio` = un styliste. |
| **Larry David** (4 recos) | Uniquement des fan pages, dont une explicitement « Not Larry David ». Il n'a vraisemblablement **pas** de compte Instagram. |
| **PNL** | Uniquement des comptes de fans / d'actu. Le duo est connu pour son absence des réseaux. |
| **Mika** | La recherche n'a remonté que des homonymes et fan pages. |
| **Ambroise Carminati** | `ambroisecarminati` était son handle, mais il aurait supprimé ses comptes début février 2025. Le duo `ambroiseetxavier` reste actif. |
| **Alexandre Kominek** | Son site alexandrekominek.fr pointe vers ses réseaux, mais le handle n'apparaît pas dans les résultats. |
| **Louis Dubourg** | Seule une page Facebook (`LouisComedy`) remonte. |
| **Audrey Vernon** | Site audreyvernon.com actif, pas de handle Instagram visible. |
| **Victoire Tuaillon** | Linktree `vtuaillon` et X `@vtuaillon`, mais pas de handle Instagram confirmé. |
| **Charlotte Pudlowski** | Identifiée via Louie Media, aucun compte personnel remonté. |
| **MrMeea** | Le handle `mrmeea` appartient à un joueur de rugby (Keven Mealamu). Son vrai nom est Damien Duvot. |

---

## 4. Quota WebSearch

**132 requêtes** consommées (22 lots de 6 en parallèle). Le quota n'a **pas** été
atteint — je me suis arrêté volontairement avec de la marge, une fois le rendement
devenu décroissant : les créateurs restants sont soit des réalisateurs/auteurs
d'œuvres (hors périmètre : « cible les personnes »), soit des artistes décédés ou
retirés (Barbara, Brel, Salvador, Michael Jackson, Amy Winehouse, Johnny Hallyday,
Diam's, Jean-Louis Murat…), soit des noms à une seule occurrence et faible
notoriété où le risque d'homonyme est le plus élevé.

### Restent à faire, par ordre d'intérêt

1. **Musiciens FR notoires non traités** : Disiz, Alpha Wann, Ichon, Julien Granel,
   Clou, Mina Tindle, Albin de la Simone, Philémon Cimon, Winnterzuko, James BKS,
   Francis Cabrel, Maxime Le Forestier, Patrick Bruel, Gérard Lenorman.
2. **Humoristes / scène** : Julien Santini, Enzo Ricci, Léopold Lemarchand,
   Greg Romano, Jordi Lebole, Melody Mourey, Théo Babac, Adèle Fugazi, Anis Rhali,
   Gabrielle Giraud, Louisa Lesage, Linda Fandel, Daniel Tirado, Peter Von Paul.
3. **Internationaux** : Michaela Coel, Phoebe Waller-Bridge, Richard Gadd,
   Taylor Tomlinson, Sam Morrill, Nate Bargatze (fiché « Nate Bergazzi »),
   George Carlin (décédé), Richard Pryor (décédé).
4. **Réalisateurs / auteurs** (si tu décides de les inclure) : Jean-Pierre Jeunet,
   Gilles Lellouche, Emmanuel Carrère, Damien Chazelle, Ari Aster, Denis Villeneuve.

### Deux avertissements pour la suite

- Beaucoup de valeurs `creator` sont des **transcriptions fautives** (« Cairone » =
  Kheiron, « Nate Bergazzi » = Nate Bargatze, « Grier Barnes » = Greer Barnes,
  « Winter Zuko » = Winnterzuko, « Sonia Croedland » = Sonia Kronlund, « Adèle
  Fougazi » / « Adel Fugazi », « Swan Périsset » = Swann Périssé, « Marc Fraise » =
  Marc Fraize). Elles sont traitées ici via `variants`, mais il en reste dans le lot
  non traité — vérifier le nom réel **avant** de chercher un compte, sinon le risque
  d'homonyme explose.
- Plusieurs entrées `creator` ne sont pas des personnes mais des chaînes ou des
  médias (Louie Media, Golden Moustache, Kurzgesagt, SNL, Balade Mentale, Peaceful
  Cuisine, Les Parasites). À décider si le site veut afficher un compte de média ou
  seulement des comptes de personnes.
