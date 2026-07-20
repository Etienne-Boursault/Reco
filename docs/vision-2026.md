# Vision Reco — 2026

> **Statut** : brouillon à compléter. Document destiné à devenir la **boussole stratégique** du projet — toutes les décisions techniques en découlent.
> Les questions ci-dessous sont les **2 décisions structurelles** identifiées par l'archi-pass. Tant qu'elles ne sont pas tranchées, le code paie le coût des deux directions à chaque fois.

---

## Décision 1 — Outil personnel OU produit public ?

### Les deux options en clair

| Critère | Outil personnel | Produit public |
|---|---|---|
| **Cible** | Toi seul (+ démos ponctuelles) | Visiteurs anonymes du web |
| **Optimise pour** | Ta vélocité, ton confort | Audience, SEO, partage, rétention |
| **Auth** | Aucune (localhost) | Magic link / OAuth dès le départ |
| **i18n** | FR-only, jamais | À prévoir (au moins EN) |
| **A11y** | "Suffisamment" | WCAG AA strict |
| **Mobile** | Optionnel | Obligatoire |
| **Modération** | Inutile | Inévitable si UGC un jour |
| **Stack** | Minimal, ad-hoc | Plus structuré (API + frontend découplé) |
| **Données privées** | Notes perso, drafts visibles | Tout est "presse-papier public" |

### Indicateurs pour décider

Réponds à toi-même :

- [x] **Combien de visiteurs/mois je vise dans 12 mois ?** : `100-10k`
  - < 100 → personnel
  - 100-10k → ambigu (publication light)
  - > 10k → produit public

- [x] **Est-ce que je veux que des gens cherchent "tous les films recommandés par Navo" sur Google ?** : oui 

- [x] **Est-ce que j'ai envie d'investir en SEO, OG cards, RSS, newsletter ?** : Oui mais pas les newsletter

- [x] **Mon objectif principal cette année est** :
  - [x] traiter le backlog de 110 épisodes correctement
  - [x] lancer un site public avec audience
  - [x] faire un cadeau aux fans du podcast
  - [x] valider un modèle qui scalera à 10+ podcasts
  - [x] explorer l'IA + curation, peu importe l'audience

- [x] **Si demain on me dit que ça ne sera jamais public, est-ce que je continue le projet ?** : oui

### Ma réponse

> **Direction choisie** : ☐ personnel · [x] public · ☐ hybride explicite (description ci-dessous)

> **Description** : Ce projet vise à être un outil pour que les gens puissent le host de leur côté et trouver les recommandations dans leurs podcast favoris. La partie traitement des recommandations peut-être privée ou exposée à un nombre limité de personne alors que la partie affichage des recommandations est publique et accessible à tous. Le code doit être opensource, ou (sous licence), chacun doit être libre de le reproduire mais doit citer mon nom. Le projet doit être facilement implémentable pour quelqu'un qui ne sait pas coder. Et le site généré devra être ajouté au site global. Probablement source-intern.et ou source-internet.fr/com/org/te/etc... Il faut que le tout puisse être self-host.

> **Date de décision** : _2026-06-10_

### Implications immédiates si « public »

- Bascule schéma Item / Mention / Source AVANT d'ajouter des features (sinon migration lourde plus tard)
- Auth dès la 2ème route mutante
- OG cards, RSS, sitemap, meta tags soignés
- Performance Lighthouse > 90
- Accessibilité WCAG AA

### Implications immédiates si « personnel »

- Pas de friction d'auth, pas de SEO
- Polish UX à fond (raccourcis clavier, mode focus, bulk actions)
- Pipeline observabilité + golden set = priorité (qualité dataset)
- On peut hardcoder ce qu'on veut

### Implications si « hybride »

- Définis **précisément** la frontière. Sinon = pire des deux mondes (cf. archi-pass).
- Ex. : "Site public en lecture seule pour les recos déjà validées. Outil de relecture privé sans intention d'ouvrir."
- Si frontière claire → ça peut marcher.

---

## Décision 2 — Personnel-only OU kit open-source ?

(Indépendante de la décision 1 — un outil personnel peut être open-source, un produit public peut rester closed.)

### Les deux options en clair

| Critère | Personnel-only | Kit open-source |
|---|---|---|
| **Optimise pour** | Vélocité personnelle | Réutilisabilité par d'autres podcasts |
| **Config** | Hardcodée pour "Un Bon Moment" | Externalisée (`reco-config/<podcast>/`) |
| **Doc** | Notes pour toi | README + tutorial + exemples |
| **Tests** | Suffisamment | CI publique, contributions externes |
| **Repo** | Privé | Public (GitHub) |
| **Effort initial** | 0 | 2-3 semaines de refonte structure |
| **Effet réseau** | Zéro | Contributions, bug reports, validation |

### Indicateurs pour décider

- [x] **Connais-je 3 personnes qui curent un podcast et qui voudraient l'outil ?** : non
- [x] **Suis-je prêt à investir 2-3 semaines en refonte (templating + doc + CI) ?** : oui
- [X] **Suis-je à l'aise avec du code public (qualité, licences) ?** : oui
- [X] **Mon but est** :
  - [x] aider 1 podcast (le mien)
  - [x] aider N podcasts indépendants
  - [x] construire une référence (effet de carrière / portfolio)
  - [ ] zéro objectif externe, juste pour moi

### Ma réponse

> **Direction choisie** : ☐ personnel · [x] open-source kit · ☐ "je verrai plus tard"

> ⚠️ Attention : **"je verrai plus tard" = personnel** dans les faits. La modularité prématurée pour open-source future = coût immédiat pour bénéfice hypothétique (anti-YAGNI). Si tu choisis "verrai plus tard", traite-le comme "personnel" et n'ajoute aucune abstraction "au cas où".

> **Date de décision** : 2026-06-10

---

## Décision 3 — Volume cible 12 mois

Pas obligatoire mais aide à cadrer l'investissement.

- [5-10] Combien de podcasts traités dans 12 mois ?
  - 1 (Un Bon Moment seul) → SQLite inutile, embeddings overkill
  - 2-3 → multi-source à introduire, dédup cross-podcast utile
  - 5-10 → orchestration pipeline + auth + observabilité incontournables
  - 10+ → SQLite + API + multi-utilisateur + i18n

- [>1000] Combien d'épisodes au total ?
  - < 200 → JSON + scripts ad-hoc OK
  - 200-1000 → SQLite cache d'index utile, search nécessaire
  - > 1000 → SQLite source de vérité, API REST

- [>20k] Combien de recos au total ?
  - < 5k → tout passe en mémoire
  - 5-20k → cache + index = obligatoire
  - > 20k → embeddings + full-text search dédié

---

## Cadre de décision long-terme

Une fois les décisions 1, 2, 3 prises, voici **comment elles cascadent** :

```
Décision 1 (privé/public)
├── privé → focus polish UX, pipeline qualité (golden set, dédup)
└── public → focus site features, SEO, multi-format, auth

Décision 2 (open-source ou pas)
├── personnel → pas d'effort de templating
└── open-source → refonte config + doc + CI (à faire UNE fois)

Décision 3 (volume)
├── < 200 ép → status quo JSON
└── > 200 ép → SQLite cache + search index
```

---

## Garde-fous pour la suite

1. **Aucune décision structurelle ne se prend sans relire ce document.** Si tu te trouves en train de discuter "API REST vs HTML server-rendered" sans avoir tranché la décision 1, **stop, retourne à la décision 1**.

2. **Re-trancher est OK.** Si dans 6 mois tu changes d'avis, met à jour ce doc et documente la migration. Ce qui n'est PAS OK : avoir 6 mois de code construits sur une ambiguïté.

3. **Test du miroir** : si demain quelqu'un te demande "ton projet, c'est quoi ?", ta réponse doit être cohérente avec ce document. Sinon, l'un des deux ment.

---

## Historique

| Date | Décision | Notes |
|---|---|---|
| _2026-06-10_ | _à remplir_ | _à remplir_ |
