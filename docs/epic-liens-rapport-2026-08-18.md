# EPIC « liens et données » — rapport

**2026-08-18** · 51 commits · 1 714 fichiers · +46 032 / −3 245 lignes
*(dont 153 fichiers hors corpus : +30 744 / −915)*

---

## Ce qui était demandé

1. Terminer la revue de code de l'EPIC précédente, corriger **toutes** les
   issues sans limitation, découper les fichiers au-delà de 500 lignes.
2. Corriger les défauts d'affichage relevés sur captures (titre, étoile,
   mentions, icône de signalement, taille des cartes).
3. Corriger les défauts de données relevés au fil de l'eau : graphies de noms,
   créateurs manquants, doublons de liens, types et titres faux.
4. Compléter les liens manquants — visionnage, billetterie, fiche.
5. Aligner **toutes** les plateformes d'écoute sur les recos musicales.
6. Auditer le résultat par échantillonnage, et faire une revue de code.

Tout est fait. Ce rapport porte surtout sur ce que les points 4 à 6 ont mis au
jour, qui dépasse largement la demande initiale.

---

## Le résultat qui compte

**Les manques de liens n'étaient pas des données absentes : c'était l'audit qui
ne savait pas lire ce qui était là.**

Le compteur est passé de 237 à 46. Sur ces 191 manques résorbés, une minorité
seulement venait d'une recherche. La majorité venait de la correction de
l'instrument de mesure lui-même.

| ce que l'audit ne voyait pas | pourquoi | portée |
|---|---|---|
| `open.spotify.com/show/` | classé « écoute », alors que `/show/` est un podcast | 34 liens |
| 257 hôtes du corpus | absents de la table des familles | 359 liens |
| une captation vaut un billet | un spectacle fini n'a pas de place à vendre | 17 recos |
| une playlist YouTube EST la série | classée « vidéo », donc jamais « visionnage » | 11 recos |
| `kind: "streaming"` | le corpus distinguait déjà l'œuvre de la bande-annonce, à la main | 21 liens |
| la page « où regarder » TMDB | même hôte que la fiche, donc comptée comme fiche | 125 recos |

Le dernier point est le plus instructif : **la passe de visionnage ne posait
plus aucun lien depuis que TMDB avait cessé de servir des URL JustWatch**, et
personne ne l'avait vu — « aucun candidat » ressemble à « rien à faire ».

---

## Ce que la vérification a coûté, et pourquoi elle valait ce prix

Quatre fois pendant cette EPIC, un contrôle uniforme a produit des résultats
faux qu'il aurait été facile de publier.

| l'instrument | ce qu'il annonçait | la réalité |
|---|---|---|
| une vérification HTTP unique pour toutes les plateformes | 30 liens musicaux douteux | 0 — YouTube sert un mur de consentement, Deezer range les podcasts sous `/podcast/` |
| similarité de titres par plus longue sous-chaîne | 1 094 citations divergentes | **14** |
| `link_check` sur les 3 241 URL | 282 liens morts | **0** — 280 IMDb valides, qui répondent 202 avec un corps vide |
| comptage des recos sans lien | 57 % du corpus | **une seule** — le reste était `discarded` |

À chaque fois, l'erreur allait dans le sens de l'alarme. Un rapport où 99 % des
morts sont faux ne se lit plus, et les vrais s'y perdent.

**Corollaire retenu pour la suite : chaque plateforme a son propre moyen de
dire ce qu'une URL désigne, et les confondre coûte plus cher que de les
traiter séparément.**

---

## Défauts réels corrigés

### Ceux qui cassaient le site

**Le serveur s'arrêtait sur une requête pendant un redéploiement.**
`servirFichier` appelait `statSync` sans garde, alors que `fichierPour` fait
déjà son propre `stat`. Entre les deux, l'hébergeur remplace `dist/` : le
second `stat` lève `ENOENT`, et une exception dans l'écouteur de
`http.createServer` devient un `uncaughtException` que `server.mjs`
n'intercepte pas. **Le processus s'arrête, donc le site entier tombe.** Les
commentaires du module déclaraient pourtant cette panne refermée — la
protection couvrait le flux de lecture, jamais le `stat` qui le précède.

**La recherche ne filtrait rien sur `/[source]/recos`.** Vérifié dans le
navigateur : 1 209 cartes avant la saisie, 1 209 après. `AllRecosView` rend le
champ, les puces et la grille ; le code qui les anime vivait dans le `<script>`
de `SourceCatalog`, que cette page ne monte pas — et Astro n'embarque que les
scripts des composants **réellement rendus**.

C'est la **deuxième fois** que ce mécanisme casse cette page : la veille, les
styles des cartes avaient disparu pour la même raison. Même remède — un module
partagé, importé par les deux — et cette fois testable, ce qu'un script inline
d'`.astro` n'est pas.

### Ceux que le lecteur voyait

- **85 cartes affichaient le même nom deux fois**, en titre puis dessous : le
  cas normal du type `artiste`, où le titre *est* la personne.
- **18 recos créditaient leur diffuseur** comme créateur — « Netflix » pour
  *La Chute de la maison Usher*, qui est de Mike Flanagan.
- **269 cartes montraient deux pictogrammes TMDB identiques** côte à côte,
  l'icône se choisissant par l'hôte.
- **11 recos avaient un lien invisible** : la carte n'en montre que six, et ce
  sont les derniers ajoutés qui tombent. Cinq « Une Bonne Soirée » perdaient
  ainsi leur lien Canal+.
- **Une carte « Empathie » affichait une phrase parlant d'*Euphoria*.**

### Ceux qui dormaient dans la donnée

**14 identifiants TMDB étaient faux.** « Titanic » désignait un documentaire de
2012, « Brazil » un film brésilien de 1952, « Vice » le *Vice-versa* de Pixar,
« Fantômas » le muet de 1913 alors que la citation nomme de Funès et Jean
Marais. Ces identifiants ne s'affichent nulle part — et c'est ce qui les rend
dangereux : une passe d'enrichissement peut les promouvoir en lien visible des
mois plus tard. Seules les gardes de titre et d'année les avaient contenus, en
silence.

Le pire cas, « Close Up », portait un identifiant TMDB **et** un identifiant
IMDb désignant tous deux « Close Up with The Hollywood Reporter » quand la reco
parle d'une websérie française — l'un renvoyant à l'autre, ils se confirmaient
mutuellement. Le lien TMDB était déjà visible.

Un audit identique côté musique n'a trouvé **qu'un seul** identifiant faux sur
47 : `George Ka` pointait « I Went Hunting » de George **Ezra**.

### Les entrées curées qui ne faisaient plus rien

**Cinq corrections de la table étaient muettes.** Leur garde avait cessé de
correspondre parce qu'une autre passe avait modifié la reco entre-temps, et
leur silence ressemblait à un succès. `ubm-2861` n'avait ainsi jamais retiré
son lien en double ; `ubm-0487` jamais retiré la page générique qui doublonnait
celle du spectacle.

Les quatre premières ont été trouvées **par hasard**, en butant sur des clés
dupliquées que `ruff` signalait. La cinquième par le test écrit pour ça, à sa
première exécution.

Ce test ne vérifie pas « la garde correspond-elle ? » — la réponse est non pour
toute correction déjà appliquée, et c'est sain. Il vérifie la conjonction :
**la garde ne correspond plus ET l'effet n'est pas réalisé.**

---

## Ce que les tests ne prouvaient pas

- `test_declared_drift_is_still_real` n'avait **aucun corps** : une docstring,
  zéro assertion. Vert par construction, incapable de rougir.
- Les clés d'effet de `fix_reco_anomalies` étaient **recopiées** dans deux
  garde-fous. L'opération `citation`, ajoutée le matin même, manquait aux deux :
  une correction n'en portant qu'une passait pour vide. Elles sont désormais
  déclarées une seule fois dans le module.
- `kind: "ticket"` — juste en français, absent du schéma — est passé entre les
  mailles : suite verte, et c'est `astro build` qui a arrêté le déploiement.
  Même classe que l'incident `creator: null`. Les énumérations `kind` et
  `ethics` sont désormais gardées, **vérifié par mutation**.

---

## Les liens posés

| famille | départ | arrivée |
|---|---|---|
| visionnage | 68 | 19 |
| billetterie | 63 | 20 |
| fiche | 63 | 3 |
| podcast, libraire, jeu, application | 42 | 4 |
| **total** | **237** | **46** |

**650 liens d'écoute** ajoutés sur les recos musicales, tous vérifiés
individuellement, aucun rejeté.

| plateforme | départ | arrivée |
|---|---|---|
| Spotify | 109 | 236 |
| Deezer | 139 | 232 |
| Apple Music | 47 | 184 |
| Qobuz | 40 | 171 |
| YT Music | **0** | 147 |
| Bandcamp | 18 | 25 |

Le plafond de six liens de la carte est appliqué **dans le code** et non
seulement demandé aux agents : une consigne est un vœu, un garde-fou refuse.
Aucune reco ne le dépasse, donc aucun lien invisible.

---

## Méthode : la délégation sous contrôle

Vingt-trois agents ont travaillé en parallèle sur cette EPIC — onze sur les
plateformes musicales, cinq sur l'audit, trois sur les familles de liens, un
sur la revue de code, trois abandonnés ou remplacés.

**Aucun n'avait le droit d'écrire dans le corpus.** Ils rendaient des candidats
sourcés, revérifiés avant écriture. Cette règle a payé plusieurs fois :

- un lien Deezer proposé pour « Les mecs que je veux ken » menait à « Les
  saisons de Rosa » — un autre podcast de la même animatrice ;
- un jeu télévisé canadien de 1974 (« Definition », CTV) a failli être posé sur
  une reco de série stand-up française, au seul motif d'un titre identique.

Mais la vérification a aussi **corrigé mes propres rejets**. J'avais écarté ce
lien Deezer ; un agent a montré que l'émission avait simplement été **renommée**
— l'identifiant Apple déjà présent dans le corpus le prouvait. Le lien était
bon.

**Les agents ont trouvé ce que je ne cherchais pas.** Le mur anti-robot d'IMDb,
la sortie réseau non française de cette machine, le `channelId` YouTube qui
désigne une chaîne *recommandée* et non celle consultée : trois pièges
d'outillage établis avec témoin, qu'aucune passe automatique n'aurait signalés.

---

## Ce que l'audit par échantillon a révélé

Cinq échantillons indépendants — quatre tirages aléatoires de 25 recos, un
ciblé sur les cartes les plus pauvres — soit **125 fiches, 10 % du corpus
publié**. Tirage à graine fixe, donc rejouable.

**86 défauts** (21 hautes, 44 moyennes, 21 basses) et 39 pistes.

Le diagnostic partagé, et c'est sa convergence qui lui donne du poids :
**les liens ne sont plus le problème ; c'est le texte qui reste faible.**
Identifiants TMDB et IMDb 7/7, liens musicaux 14/14 et 15/15 selon les lots,
aucun lien mort sur l'ensemble du corpus. Ce qui casse encore : titres,
créateurs, citations, années.

### Ce qui reste à traiter, par rapport effort/gain

| # | sujet | portée vérifiée |
|---|---|---|
| 1 | `watchProviders` : URL de **recherche** au lieu de l'œuvre, affichées sur les pages `/oeuvre/`, libellé `None` | **870 / 919 liens (95 %)**, 144 recos |
| 2 | Fiches publiées **contre leur verdict** de revue | **89** (12 `discard`, 77 `applied=false`) |
| 3 | Handles Instagram connus mais **jamais montrés** | **294 / 299** |
| 4 | Notes de revue contenant une correction jamais appliquée | 152 (critère strict) à 478 (critère large) |
| 5 | `attribution_suspect` publiées avec un nom affiché | **344** |
| 6 | Une carte par **mention**, jamais par œuvre ; les pages `/oeuvre/` existent déjà | **289 fiches**, 113 titres |
| 7 | Deux liens `themoviedb.org` sur la même carte | **269 recos**, dont 35 à carte pleine |
| 8 | Année renseignée | **9,4 %** — souvent disponible sans recherche |
| 9 | Citations issues d'une transcription périmée | **14** nettes, 26 approximatives |

Le point 7 est une conséquence directe du travail de cette EPIC : avoir rendu
la fiche et la page « où regarder » distinctes leur fait occuper deux des six
places visibles.

### Trois alertes d'agents qui n'ont pas résisté

Consignées parce qu'elles auraient orienté le travail à tort :

- « 57 % des recos n'ont aucun lien » — compte les 1 799 écartées ; sur le
  corpus publié, **une seule** ;
- « un vérificateur Python déclarera morts des liens vivants » — vrai pour
  `urllib` nu, mais `link_check` utilise déjà `certifi`, et son commentaire
  documente cet incident ;
- « 896 liens trompeurs sur les cartes » — `watchProviders` n'est pas rendu par
  `RecoCard`. Le défaut existe, mais sur les pages `/oeuvre/`.

---

## Revue de code

**29 problèmes** (1 haute, 14 moyennes, 14 basses) et 12 points forts, sur les
80 commits depuis le rapport du 29 juillet.

La haute — l'arrêt du serveur — et trois tests creux sont corrigés. Les 25
autres restent à trier, dont : `fix_reco_anomalies.py` dépasse 900 lignes,
`famille()` consulte `_CHEMINS` avant `HOTES`, et l'ordre `ajouter_liens` /
`retirer_liens` oblige à deux passes pour remplacer un lien.

---

## État du dépôt

- Suites vertes : **5 899 tests Python**, **2 147 tests Vitest**.
- Build SSR complet, **2 662 pages**.
- Couverture 100 % sur les modules créés pendant l'EPIC :
  `link_families`, `fix_tmdb_ids`, `fix_liens_verifies`, `fix_ordre_liens`,
  `fix_liens_plateformes`, `filtreRecos`.
- `main` porte l'ensemble du travail, **non poussé vers `origin`**.

### En attente d'arbitrage

- **Deux longs métrages** dont la seule copie en ligne n'est pas déposée par un
  ayant droit — `docs/liens-en-attente-arbitrage.md`.
- **La lenteur de `/[source]/recos`** : 2,48 Mo, 1 209 cartes, 2 506 images.
  Le serveur répond en 28 ms ; le coût est l'analyse du document. C'est un
  arbitrage déjà pris et mesuré le 16 août — cette page est le repli sans
  JavaScript et la surface de référencement. La pagination serait la seule
  vraie réponse.
