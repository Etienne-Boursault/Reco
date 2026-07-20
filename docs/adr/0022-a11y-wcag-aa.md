# ADR 0022 — Accessibilité WCAG AA pour le site public

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco
- Lié à : vision-2026 (audience publique), roadmap Phase 2 item #14

## Contexte

Reco est un kit duplicable de catalogues de recommandations destiné à un
public large (auditeur·rices de podcasts). Une partie de ce public est
malvoyante, navigue au clavier ou utilise des lecteurs d'écran. La vision
2026 fixe l'accessibilité comme exigence non-négociable, et la
réglementation européenne (EAA, applicable depuis juin 2025) impose le
respect des Web Content Accessibility Guidelines niveau AA pour les sites
B2C.

Constat avant l'item #14 :

- Pas de skip link → un usager au clavier devait taber à travers toute
  la nav avant d'atteindre le contenu.
- `:focus-visible` n'était stylé que ponctuellement (`.search`, `.link`)
  → la majorité des éléments interactifs n'avaient pas d'anneau de focus
  visible (WCAG 2.4.7).
- Les onglets « Par épisode / Toutes les recos » utilisaient
  `aria-pressed` (sémantique « toggle button ») au lieu du pattern
  `tablist` / `tab` / `tabpanel` (WAI-ARIA Authoring Practices). Pas de
  navigation aux flèches.
- Les états « aucun résultat » n'étaient pas annoncés (`aria-live`
  manquant).
- Une partie de la palette en mode default contraste OK mais aucune
  garantie outillée → pas de filet contre les régressions.
- `prefers-reduced-motion` n'était respecté que pour l'animation
  `.reveal` (par chance, en `no-preference`), pas globalement.

Options étudiées :

1. **A11y best-effort** — corriger les pages au fil de l'eau, sans
   garantie. Rejeté : incompatible avec la vision public-facing et avec
   l'EAA.
2. **WCAG AAA strict** — viser AAA (ratio 7:1, transcripts audio…).
   Rejeté : surdimensionné pour un kit duplicable, et certains critères
   (transcripts) sont hors périmètre (le contenu vient des podcasts
   tiers).
3. **WCAG AA outillé** — choisi.

## Décision

On s'engage sur WCAG 2.1 AA pour toutes les pages publiques (pages
internes `*/verifier` exclues car `noindex`). Concrètement :

- **Skip link global** dans `src/layouts/Layout.astro` (`<a class="skip-link"
  href="#main">Aller au contenu principal</a>`), avec ancre `id="main"`
  obligatoire sur le contenu principal de chaque page.
- **Focus visible global** via `src/styles/global.css` : règle
  `:where(a, button, input, select, textarea, [tabindex]):focus-visible`
  produisant un double anneau accent + halo de fond (contraste ≥3:1 sur
  tout fond de la palette, mesuré 13.35:1 sur `--bg`).
- **Préférence motion respectée** : règle globale
  `@media (prefers-reduced-motion: reduce)` désactive animations et
  transitions.
- **Pattern tabs ARIA-conforme** sur la page source (`role="tablist"`,
  `role="tab"`, `aria-selected`, `aria-controls`, roving tabindex,
  navigation flèches/Home/End).
- **Live region** sur les compteurs et états « aucun résultat »
  (`role="status"` + `aria-live="polite"`).
- **Landmarks explicites** : `<main id="main">` partout,
  `role="contentinfo"` sur le footer racine, listes étiquetées via
  `aria-label`.
- **`<html lang="fr">`** déjà en place — vérifié par le check statique.
- **Contraste palette outillé** : `tests/a11y/check_contrast.mjs`
  vérifie sept combinaisons clés (≥4.5:1 texte / ≥3:1 focus ring).
- **Scan a11y statique** : `tests/a11y/check_a11y.mjs` scanne
  `dist/*.html` et vérifie : `lang`, skip-link, `#main`, `img[alt]`,
  noms accessibles des `<a>` et `<button>`, hiérarchie des headings,
  présence des règles CSS d'a11y.

Les deux checks sont exposés en `npm run test:a11y` et `npm run
test:contrast`, et doivent rester verts en CI.

## Conséquences

### Positives

- Audience inclusive : utilisateur·rices lecteur d'écran, clavier-only,
  vision réduite, sensibles au motion peuvent naviguer le catalogue.
- Conformité EAA et bonus SEO (Google considère la a11y comme signal
  qualité).
- Pas de framework UI lourd ajouté — l'a11y est en CSS vanilla + ARIA
  attributs, le kit reste duplicable sans dépendance.
- Filet anti-régression : tout changement de palette ou suppression de
  skip-link est rattrapé en CI.

### Négatives

- Maintenance continue : chaque nouvelle page doit ajouter `id="main"`
  et utiliser le pattern landmarks.
- Le focus ring est plus visible qu'avant — léger changement de design
  assumé (anneau accent + halo) pour respecter 2.4.7.
- Les checks statiques ne remplacent pas un audit axe-core complet ; ils
  attrapent les régressions courantes mais pas tous les cas (ex. ordre
  Tab logique). Un audit Lighthouse manuel reste recommandé à chaque
  release majeure.

### Notes

- Lighthouse cible : score a11y ≥ 95 sur homepage, page source, page
  épisode. Si descend < 90, le merge est bloqué.
- Pas de dépendance ajoutée (`axe-core` / Playwright) — l'approche
  « scan HTML statique » suffit pour un site 100 % SSG et garde le
  setup CI léger. Si on bascule vers du SSR/Edge plus tard, on
  introduira `@axe-core/playwright`.
- Page `*/verifier` exclue du scan public (interne, `noindex` +
  `Disallow` robots.txt). Elle reste utilisable au clavier mais n'a pas
  d'obligation AA.
- Critère de revisite : si on ajoute un mode clair / dark switcher,
  re-tester la palette et étendre `check_contrast.mjs`.

## Amendements

### 2026-06-10 — Durcissement post-CR (Phase 2 Vague 1)

Suite à deux revues croisées (CR senior 48 points + CR archi 22 points) on
ajoute :

- **CI dédiée** (`.github/workflows/a11y.yml`) qui exécute `test:a11y`,
  `test:contrast` et un job pa11y-ci informatif sur les pages clés. Cf.
  ADR 0024 — CI quality gates.
- **Multi-source contrast** : `check_contrast.mjs` boucle désormais sur
  toutes les sources de `src/content/sources/*.json` et valide leur
  `theme.colors` avec les mêmes seuils. Palette par défaut extraite dans
  `src/styles/tokens.ts` (SSOT). Cf. ADR 0030 — Design tokens.
- **pa11y-ci comme audit dynamique** (option B). Choisi sur lhci pour son
  intégration axe-core directe et son install plus léger. Documenté
  comme `continue-on-error` au démarrage pour calibrer le baseline.
- **i18n minimaliste** : strings d'a11y (`a11y.skipLink`,
  `a11y.externalLinkSuffix`, etc.) extraites dans `src/i18n/fr.ts`. Locale
  pilotée par `<Layout lang>`. Cf. ADR 0026.
- **WCAG 2.2 — critère 2.5.8** (Target Size Minimum, AA) : les `.chip`
  reçoivent `min-height: 28px` (≥ 24×24 CSS px). Les boutons-icône
  `.link` (36×36) sont déjà conformes.
- **Focus ring sur fond accent** (H1) : le halo `box-shadow` ajouté à la
  règle globale est dimensionné pour rester ≥ 3:1 sur n'importe quel
  fond de la palette, y compris `--accent` (mesure via `tokens.ts` + cas
  dédié dans `contrastCases`).
- **`aria-live` non clippé** (C7) : la `<p class="noresult">` reste
  toujours dans le DOM accessible ; on toggle `textContent` pour
  garantir l'annonce par les AT (l'ancienne version visually-hidden +
  toggle de classe n'était pas annoncée de manière fiable).
- **Hiérarchie de headings** : sur les pages source, ajout d'un
  `<h2 class="visually-hidden">` par section pour éviter le saut h1→h3
  (cf. C6). Les titres d'épisode dans la grille deviennent `<h3>`.
- **Skip-link cible le vrai `<main>`** (C1) : la structure des pages
  source enveloppe les tabpanels et la toolbar dans `<main id="main">`.
- **Tabs ARIA** : ajout de `aria-orientation="horizontal"`, gestion
  `Enter`/`Space` dans le handler clavier (mode « automatic activation »
  documenté).
- **Composants partagés** : `<EmptyState>` (P2-2), `<SiteFooter>` (P2-6)
  pour éviter la duplication.

### Limites assumées

- L'attribut `lang` n'est PAS auto-détecté sur les citations étrangères
  (M7). Acceptable car la majorité du contenu est francophone et le
  surcoût d'une heuristique de détection est disproportionné. À
  revisiter si on s'ouvre à plusieurs langues côté contenu.
- Le `:where()` focus-visible a une spécificité 0 — le contrat CSS
  documenté en commentaire INTERDIT d'override ce sélecteur sans
  réintroduire halo + outline-offset. À surveiller en revue.

