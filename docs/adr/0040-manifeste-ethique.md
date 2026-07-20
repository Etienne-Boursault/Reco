# ADR 0040 — Manifeste éthique public + page « À propos »

- Statut : Acceptée
- Date : 2026-06-11
- Décideurs : équipe Reco (item #22 de la roadmap Phase 3, vague 1)

## Contexte

Reco bascule en Phase 3 « public-facing » (cf. `docs/vision-2026.md`). Le
site par défaut (`source-internet.fr`) sera référencé, partagé, et
potentiellement forké par des éditeurs tiers. Plusieurs choix
structurants — déjà appliqués dans le code — sont implicites :

- **Refus des liens Amazon** (jamais, nulle part dans le pipeline).
- **Réserve vis-à-vis du groupe Bolloré** (cf. mémoire interne
  `reco-liens-ethiques.md` : éviter Amazon et le groupe Bolloré,
  privilégier les indépendants).
- **Pas de tracker tiers** (ADR 0029 Google Fonts retirées, ADR 0034
  hashage IP signalements, ADR 0036 youtube-nocookie).
- **Self-hostable + MIT** (ADR 0028 frontière de personnalisation).
- **Accessibilité WCAG AA stricte** (ADR 0022).

Sans page publique qui les exprime :

1. les visiteurs ne savent pas ce qui motive nos choix éditoriaux (et
   peuvent suspecter une affiliation inverse) ;
2. les podcasts indexés n'ont pas de référence à pointer pour expliquer
   pourquoi tel lien marchand est absent ;
3. les forks ne savent pas à quoi ils adhèrent en reprenant le kit ;
4. les contributeurs n'ont pas de critère pour trancher les cas limites
   (œuvre Hachette recommandée par un podcast indé : on garde ? on
   masque ? on signale ?).

## Décision

Publier deux pages statiques Astro et un document `.md` canonique :

1. **`docs/manifeste-ethique.md`** — version texte du manifeste,
   versionnée Git, source de vérité, évoluable via Pull Request publique.
2. **`/manifeste`** — version site avec ancres par section et sommaire
   navigable (cohérent avec design tokens, JSON-LD WebPage +
   BreadcrumbList).
3. **`/a-propos`** — page de présentation (qui sommes-nous, pourquoi,
   pipeline en 5 étapes, stats publiques calculées build-time, crédits,
   liens). Pointe vers le manifeste pour les détails éthiques.

Sections couvertes par le manifeste : préambule, **anti-Bolloré**
(sourcé Acrimed + Wikipédia), **librairies indépendantes** (Place des
Libraires, Lalibrairie.com, Librest), **vie privée / RGPD**, **open
source MIT**, **accessibilité WCAG AA**, **self-hostable**,
**transparence** (ADRs + roadmap publics).

Lien « À propos · Manifeste » ajouté dans `SiteFooter.astro` (présent
sur toutes les pages publiques via Layout). i18n via namespaces
`about.*` et `manifesto.*` dans `src/i18n/fr.ts` — un fork anglophone
peut traduire en copiant `fr.ts → en.ts`.

## Alternatives écartées

- **Pas de manifeste publié** : implicite suffisant. Rejeté — perte de
  positionnement vs concurrents anodins, et frein pour les podcasts qui
  veulent comprendre nos choix.
- **Manifeste tech-only (privacy / a11y / OSS)** sans la dimension
  politique (anti-Bolloré / anti-Amazon). Rejeté — la mémoire
  utilisateur `reco-liens-ethiques.md` est explicite : la posture
  anti-Bolloré est une décision projet, pas une option masquée.
- **Manifeste dans le README** sans page dédiée. Rejeté — pas indexable
  par les moteurs comme page web, pas partageable, pas sourçable
  depuis le footer.
- **Page dynamique générée depuis le `.md`** via remark/MDX. Rejeté
  pour le V1 — ajoute une dépendance et complexifie sans bénéfice
  immédiat. La duplication contrôlée `.md` ↔ `.astro` est acceptable
  pour un document court ; un test ultérieur pourra vérifier la
  synchronisation.

## Conséquences

**Positives :**

- Transparence assumée : un visiteur sait en 30 secondes ce que Reco
  refuse et ce que Reco priorise.
- Fédère la communauté autour de critères explicites — attire des
  contributeurs et des forks alignés.
- Sourçage public (Acrimed, Wikipédia, Place des Libraires) qui rend
  les choix vérifiables et discutables.
- Référence opposable pour la modération des signalements (le manifeste
  devient la grille de décision).
- Pages indexables : SEO + JSON-LD WebPage/BreadcrumbList, partage
  social fonctionnel.

**Négatives :**

- Exposition politique : un fork apolitique ou commercial peut se
  sentir contraint. Mitigation : prévoir un opt-out (`siteConfig.disableManifesto`)
  si la demande émerge — non-livré dans cette ADR par YAGNI.
- Maintenance : le manifeste vit en deux endroits (`docs/manifeste-ethique.md`
  + `src/pages/manifeste.astro`). Risque de désynchro à terme. Mitigation
  future : un linter `tests/lint/test_manifesto_sync.py` pourrait
  comparer les listes (sections, éditeurs Bolloré, librairies indés).
- Risque réputationnel : nommer Bolloré publiquement expose à des
  contestations. Mitigation : sources externes (Acrimed, Wikipédia)
  citées, pas d'affirmation non-sourcée.

**Notes :**

- Critère de bascule vers un opt-out de manifeste : ≥ 2 forks
  documentés qui demandent à désactiver la page manifeste tout en
  gardant la page À propos.
- Roadmap : blocage automatique des liens marchands vers éditeurs
  Bolloré (item #25, non couvert ici — la décision est éditoriale,
  l'implémentation viendra plus tard).
- Revisite recommandée : 2027-06 (vérifier que la liste d'éditeurs
  Bolloré est à jour, que les librairies indés référencées existent
  toujours, et que les ADR référencées sont stables).
