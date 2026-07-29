# EPIC « stabilité » — rapport

**2026-07-29** · 30 commits · 594 fichiers · +30 360 / −5 628 lignes

---

## Ce qui était demandé

1. Trouver toutes les favicons ; à défaut, un symbole adapté au type de lien plutôt qu'un globe lu comme une erreur.
2. Doubler la surface des icônes.
3. Placer le lien *Signaler* au même niveau que les icônes, ou en dessous.
4. Retirer l'année parasite à côté du titre.
5. Compléter les créateurs manquants.
6. Retirer uTip (service fermé).
7. Mettre la qualité de code au niveau : couverture ≥ 95 % sur **toutes** les métriques, 100 % sur les nouveaux fichiers, TDD, SOLID, clean architecture.
8. Vérifier que **tous** les jobs GitHub passent.

Tout est fait. Le détail des points 1 à 6 est en fin de document ; l'essentiel de ce rapport porte sur ce que le point 7 a mis au jour.

---

## Le résultat qui compte

**Le projet croyait tenir 95 % de couverture. Rien ne le vérifiait.**

Ce n'était pas une négligence isolée mais un motif, rencontré **cinq fois** :
une vérification écrite, visible dans le dépôt, rassurante à la lecture — et
neutralisée par une autre ligne de configuration.

| # | La garantie affichée | Ce qui l'annulait |
|---|---|---|
| 1 | seuils de couverture dans `vitest.config.ts` | la CI lançait `vitest run` **sans** `--coverage` |
| 2 | `fail_under = 95` dans `pyproject.toml` | la CI lançait `pytest` **sans** `--cov`, et `pytest-cov` n'était pas installé |
| 3 | `[tool.coverage]` dans `pyproject.toml` | deux `.coveragerc` prenaient silencieusement le pas dessus |
| 4 | `include: [".astro/types.d.ts"]` dans `tsconfig.json` | `exclude: [".astro"]` filtrait le résultat de `include` |
| 5 | `astro check` et `ruff` rendus bloquants | `ci-summary` ne les testait pas dans sa condition d'échec |

Le cinquième est le plus instructif : il annulait, **le jour même**, les 1 117
corrections de lint et de typage qui venaient d'être payées. Les deux jobs
pouvaient virer au rouge pendant que le check requis par la protection de
branche passait au vert.

Deux de ces mécanismes cachaient du code de production : `tools/.coveragerc`
excluait `tools/cache/` et `tools/dispatch/`, testés ; et trois scripts figuraient
dans la liste d'exclusion alors qu'ils avaient chacun leur suite de tests —
l'exclusion empêchait purement et simplement de la mesurer.

**Tout est désormais mesuré et bloquant.** La condition de `ci-summary` itère sur
les résultats au lieu de les énumérer : ajouter un job le rend bloquant sans
qu'on ait à y penser.

---

## Couverture

### Frontend

| métrique | avant | après |
|---|---|---|
| lignes | 67,5 % | **99,71 %** |
| instructions | 65,8 % | **99,70 %** |
| fonctions | 59,1 % | **100 %** |
| branches | 61,6 % | **99,00 %** |

41 fichiers sur 97 n'étaient jamais exécutés, dont 32 `.astro`. **666 → 1 856 tests.**

Le périmètre a changé autant que le chiffre : `coverage.include` était une **liste
blanche curée**, agrandie fichier par fichier, qui affichait 80 % pendant que le
dépôt réel était à 67 %. Un commentaire écartait explicitement le glob large au
motif qu'il « ferait chuter le seuil global » — ce qui était précisément
l'information à ne pas masquer. La mesure porte maintenant sur tout `src/`.

### Python

| métrique | avant | après |
|---|---|---|
| instructions | 96,82 % | **96,83 %** |
| branches | **94,83 %** | **96,00 %** |

Les branches **n'étaient pas mesurées du tout**, et elles étaient **sous** la barre
que le projet croyait tenir.

Le chiffre d'instructions semble stagner : c'est parce que **la liste d'exclusion a
été supprimée**. Il porte désormais sur l'intégralité de `tools/`, sans qu'aucun
fichier ne soit soustrait à la mesure. La règle est inscrite dans `pyproject.toml` :
si la mesure repasse un jour sous 95 %, on écrit des tests, on ne rouvre pas la liste.

### Une réserve à connaître

v8 **n'instrumente pas** les `<script>` client des fichiers `.astro`. Le 99,71 %
exclut donc la logique client encore inline. Ce n'est pas « 99,71 % du code exécuté
par le visiteur ». La parade est structurelle : extraire cette logique dans des
modules `.ts` testables — c'est ce qui a été fait pour `gridFilter.ts`.

---

## Défauts réels corrigés — 18

Aucun n'était visible avant qu'on écrive les tests ou qu'on lise la configuration.

### Sécurité

| défaut | conséquence |
|---|---|
| La queue d'administration des signalements était **pré-rendue et publiée** | nom, **adresse e-mail** et texte libre des signalants lisibles par quiconque, sans authentification. `robots.txt` publiait même le motif d'URL |
| Le rate-limit lisait le **premier** élément de `X-Forwarded-For` | celui que le client écrit : faire varier l'en-tête donnait un bucket neuf à chaque requête, et **chaque requête acceptée écrit un fichier sur le serveur** |
| `new Response(body, { status: 204 })` | la spec Fetch interdit un corps sur un 204 : le bot qui remplissait le piège anti-spam recevait un **500**, soit le signal exact que le 204 silencieux devait lui refuser |
| Le message d'erreur système renvoyé au client | `ENOSPC … open '/srv/reco/tools/output/reports/…'` livré à un visiteur anonyme |
| `link_check` ouvrait les URLs des données sans filtrer le schéma | un `file://` glissé dans une reco était **lu** |
| 8 XSS ouvertes dans Astro 5 | corrigées par la migration ; `npm audit` passe de **7 à 0** |

### Correction fonctionnelle

- Un `try/catch` **contourné par une déstructuration** : la propriété était lue avant l'entrée dans le `try`, rendant la garde inopérante.
- Le jeton captcha **consommé avant** la vérification du rate-limit : après une simple faute de saisie, le visiteur recevait un message l'accusant de rejeu, formulaire bloqué jusqu'à rechargement.
- `sourceId` non borné côté validation : **500 au lieu de 400, et jeton captcha brûlé** pour une faute de saisie.
- **Neuf accords singulier/pluriel**, dont six dans la balise `<meta name="description">` — donc **visibles dans les résultats Google**. Trois clés de traduction codaient « 1 » en dur : un épisode sans recommandation titrait « 1 recommandation » juste au-dessus de « Aucune recommandation extraite de cet épisode ».
- L'**année affichée à la place du créateur** sur les cartes de galerie, dans un élément nommé `gcard-creator` — un lecteur d'écran annonçait « 2016 » là où il attend un auteur.
- **Fuseau horaire non épinglé** dans deux composants : la date affichée dépendait de la machine de build.
- L'ordre des recommandations dépendait de l'**ordre d'énumération du chargeur de fichiers**. Bug latent depuis toujours, révélé par la migration. L'ordre est désormais chronologique et explicite.
- `t()` levait une exception sur une clé absente, **en plein rendu de page**.
- Un `try/catch` mort qui affichait « Invalid Date » là où la valeur brute est exploitable.

---

## Ce que les tests ne prouvaient pas

Un chiffre de couverture ne dit rien de la qualité des tests. Une revue dédiée a
échantillonné environ la moitié de la suite.

**Verdict : 90 à 93 % des tests échantillonnés prouvent réellement quelque chose.**
C'est très au-dessus de ce qu'on attend d'une campagne écrite *pour* la couverture,
et le risque principal — le sur-mockage des pages — ne s'est pas matérialisé : le
harnais rend de vraies pages et les alimente avec les props réellement produites
par le routage, si bien que les deux moitiés ne peuvent pas diverger.

Les défaillances trouvées, toutes corrigées :

- **Un test strictement infalsifiable** : il cherchait un identifiant qui n'existe nulle part, donc son assertion se réduisait à « zéro ≤ un ». Monter trois palettes de recherche l'aurait laissé vert.
- **Neuf tests gravaient un défaut** : leur nom annonçait le comportement souhaité pendant que leur assertion vérifiait le comportement bugué. Ils auraient **bloqué la correction**. Deux se contredisaient frontalement sur la même phrase.

---

## Deux incidents pendant l'EPIC

**45 tests ont disparu, suite verte.** `happy-dom` n'était déclaré nulle part : il
arrivait par transitivité. Une mise à jour l'a élagué et vitest a **silencieusement
omis** les deux fichiers qui en dépendaient. 1 815 → 1 770, sans un échec ni un
avertissement. Seul le compte avait bougé, et rien ne le surveillait. C'est le pire
mode de défaillance d'une suite de tests : elle ne ment pas sur ce qu'elle vérifie,
elle ment sur ce qu'elle vérifie **encore**. La dépendance est maintenant explicite,
et un garde-fou tourne dans un environnement qui reste collecté même si elle
disparaît.

**Le tri d'imports a cassé un script.** `isort` a permuté deux imports dont l'ordre
était **porteur** : le premier met la racine du dépôt sur le chemin de recherche, et
c'est lui qui rend le second résolvable. Le commentaire qui documentait la
contrainte disait « ci-dessus » et a été **déplacé avec l'import** — il décrivait
alors l'inverse de ce que faisait le code. Aucun lint, aucune relecture de diff
n'aurait signalé ça : le code restait valide, c'est l'*ordre* qui ne l'était plus.
Seul un test qui lance réellement chaque script l'a attrapé.

---

## Un motif récurrent : le correctif jamais reporté sur le jumeau

Cinq défauts de cette EPIC ont la même origine — un raisonnement mené une fois,
conclu, écrit… et appliqué à un seul des deux modules concernés :

- la parade sur `clientAddress` documentée dans un endpoint, absente de l'autre ;
- le refus de divulguer `err.message`, documenté dans un gestionnaire, absent du jumeau ;
- la lecture fautive de `X-Forwarded-For`, recopiée à l'identique dans les deux endpoints ;
- le gabarit de carte dupliqué entre deux branches — **le défaut de l'année existait en double parce que le gabarit l'était** ;
- la boucle de filtrage écrite deux fois dans un script client qu'aucun test n'exécutait.

Chaque fois, la duplication a été supprimée plutôt que le seul symptôme corrigé.

---

## Jobs GitHub

**CI et A11y vertes.** Le seul job durablement rouge était `Dependency Review` — et
**pas à cause des dépendances** : il voulait écrire un commentaire sur la PR, une
permission que le workflow ne lui accordait pas. Il échouait donc quel que soit le
verdict, depuis sa mise en place.

Migration **Astro 5 → 7** (`npm audit` 7 → 0), CI et Docker alignés sur **Node 24**
— la version réellement servie en production. Quatre pièges qu'aucune porte de
validation ne voyait ont été traités au passage, dont `compressHTML` qui **collait
le texte sur 1 123 pages** sans qu'aucun test, ni l'accessibilité, ni le build ne
bronchent.

Les mises à jour dependabot ont été absorbées après validation locale de chaque
version, en respectant la règle que le fichier de dépendances documente lui-même
(« le plancher est la version réellement testée »). Deux montées majeures d'images
Docker sont refusées avec leur raison inscrite dans la configuration.

---

## Les demandes visuelles — vérifiées sur le site construit

Neuf contrôles sur les **2 660 pages réellement produites**, pas sur des tests
unitaires. Zéro échec.

| demande | résultat |
|---|---|
| favicons | **84,3 %** des 2 954 liens en ont une |
| symbole par type | **410 symboles** répartis sur 7 natures de lien ; plus aucune référence au globe générique |
| icônes agrandies | 20 → 28 px, soit une surface **×1,96** |
| lien *Signaler* | rendu après la rangée d'icônes |
| année retirée | zéro année à la place d'un créateur |
| créateurs | **70,4 % → 75,4 %** ; films 30 → 15 manquants, séries 61 → 15 |
| uTip | plus aucune trace |
| accords | zéro accord fautif |
| texte collé | zéro page |

Sur les favicons, le choix a été de **ne pas** couvrir la traîne : les 463 liens
restants se répartissent sur 325 hôtes dont **251 n'apparaissent qu'une seule fois**
(sites personnels d'artistes, petites salles, libraires indépendants). Trois icônes
de marques identifiables ont été ajoutées. Pour le reste, un logo inventé
« plausible » serait pire qu'un symbole honnête.

Sur les créateurs, la règle « zéro invention » a été tenue : chaque valeur provient
d'une API, jamais d'une déduction. La stratégie de recherche par titre — la seule
risquée, sans identifiant pour ancrer le résultat — a reçu deux garde-fous de
popularité **calibrés sur mesure réelle**. Ils ont écarté quatre vrais mauvais
matchs, dont « Amélie » qui ramenait un homonyme obscur au lieu d'*Amélie Poulain*,
au prix de trois bons matchs perdus. Arbitrage assumé : un faux positif coûte plus
cher qu'une case vide. Les 205 créateurs encore manquants portent sur des types où
le créateur *serait* le titre lui-même (artiste, chaîne, lieu).

---

## Ce qui reste

**Une décision qui t'appartient** — `faster-whisper` : dependabot propose de relever
le plancher, mais le paquet n'est pas installé sur cette machine (la transcription
tourne ailleurs). Le fichier impose que le plancher soit une version *réellement
testée* ; il faut valider sur la machine de transcription.

**Dette identifiée, non traitée** — chacune est documentée là où elle vit :

- `tests/` est hors du contrôle de types, donc les ~28 000 lignes de tests ajoutées ne sont vérifiées par rien — y compris le harnais qui manipule des internes d'Astro ;
- `scripts/` est linté mais hors couverture ;
- deux pages de statistiques partagent ~90 % de leur gabarit — la situation que le projet a déjà résolue ailleurs avec un composant partagé ;
- douze chaînes existent en double : une clé de traduction que personne ne lit, un littéral en dur qui s'affiche. Éditer le catalogue ne change rien à l'écran ;
- `tools/enrich_creators.py` fait 1 044 lignes contre une règle de projet à 500, alors que ses propres tests sont déjà découpés selon ses quatre couches ;
- deux règles de lint désactivées sont des dettes de *comportement* (hiérarchie d'exceptions, passage en UTC), sans échéance.

**Migrations à traiter pour elles-mêmes** : Python 3.12 → 3.14 et Node 24 → 26 sur
les images Docker, qui exigent de bouger la matrice CI en même temps.
