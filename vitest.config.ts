import { getViteConfig } from 'astro/config';

/**
 * Configuration vitest pour les tests SEO/OG du site Astro.
 *
 * Champ d'application : `tests/seo/` + `tests/og/` (côté frontend uniquement).
 * Les tests Python du pipeline (tests/test_*.py) restent gérés par pytest.
 *
 * On délègue à `getViteConfig` (`astro/config`) qui injecte le plugin
 * Vite Astro — indispensable pour tester `MetaTags.astro` via l'Astro
 * Container API (cf. `test_meta_tags_unit.test.ts`).
 *
 * Couverture : seuil lines ≥ 80 % sur `src/lib/og/`, `src/lib/seo/`,
 * `src/components/MetaTags.astro` et `src/pages/robots.txt.ts`.
 */
export default getViteConfig({
  test: {
    include: [
      'tests/seo/**/*.test.ts',
      'tests/og/**/*.test.ts',
      'tests/gallery/**/*.test.ts',
      'tests/work/**/*.test.ts',
      'tests/reports/**/*.test.ts',
      'tests/audio/**/*.test.ts',
      'tests/search-frontend/**/*.test.ts',
      'tests/about/**/*.test.ts',
      'tests/registry/**/*.test.ts',
      'tests/meta/**/*.test.ts',
      'tests/tracking/**/*.test.ts',
      'tests/api/**/*.test.ts',
      'tests/stats/**/*.test.ts',
      'tests/components/**/*.test.ts',
      'tests/merchants/**/*.test.ts',
      'tests/i18n/**/*.test.ts',
      'tests/episode/**/*.test.ts',
      'tests/utils/**/*.test.ts',
      'tests/js/**/*.test.ts',
    ],
    environment: 'node',
    globals: false,
    // Satori + resvg sont natifs ; on autorise des binaires longs au démarrage.
    testTimeout: 30_000,
    coverage: {
      provider: 'v8',
      include: [
        'src/lib/og/**/*.ts',
        'src/lib/seo/**/*.ts',
        'src/lib/registry/**/*.ts',
        // L5 : helpers purs de la page épisode et de la page œuvre, désormais
        // couverts par tests/episode/** et tests/work/**.
        'src/lib/episode/**/*.ts',
        'src/lib/work/**/*.ts',
        'src/pages/robots.txt.ts',
        'src/config/site.ts',
        // CG1/CG2 (2026-07-19) : résolveur de liens éthiques et carte reco.
        // NB : on N'ajoute PAS le glob large `src/components/**/*.astro` — il
        // ferait chuter le seuil global (13+ composants non testés → 0 %). On
        // cible RecoCard.astro et merchants.ts, qui ont désormais leurs tests.
        'src/data/**/*.ts',
        'src/components/RecoCard.astro',
      ],
      thresholds: {
        lines: 80,
        functions: 80,
        statements: 80,
        // merchants.ts est couvert exhaustivement (11 résolveurs + gardes) :
        // on verrouille 100 % pour détecter toute régression de couverture.
        'src/data/merchants.ts': {
          lines: 100,
          functions: 100,
          statements: 100,
          branches: 100,
        },
      },
    },
  },
});
