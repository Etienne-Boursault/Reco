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
 * Couverture : ≥ 95 % sur les quatre métriques (lignes, instructions,
 * fonctions, branches), mesurées sur TOUT `src/` — cf. le bloc `coverage`
 * plus bas pour l'historique de ce choix.
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
      'tests/server/**/*.test.ts',
    ],
    environment: 'node',
    globals: false,
    // Satori + resvg sont natifs ; on autorise des binaires longs au démarrage.
    testTimeout: 30_000,
    coverage: {
      provider: 'v8',
      // TOUT `src/`, sans liste blanche.
      //
      // Historique : ce champ était une liste blanche curée, agrandie fichier
      // par fichier. Elle produisait un chiffre flatteur — 80 % sur le
      // périmètre choisi — pendant que le dépôt RÉEL était à 67 % de lignes et
      // 61 % de branches, avec 41 fichiers sur 97 jamais exécutés, dont 32
      // `.astro`. Un seuil qui ne s'applique qu'à ce qu'on a bien voulu y
      // mettre ne mesure rien : il enregistre une intention.
      //
      // Le glob large avait été explicitement écarté au motif qu'il « ferait
      // chuter le seuil global ». C'est exact, et c'était précisément
      // l'information à ne pas masquer.
      // `src/server/*.mjs` : le serveur de PRODUCTION. Il est arrivé dans le
      // dépôt sans un seul test parce que ce glob ne le voyait pas — un
      // fichier qui sert chaque visiteur, hors de toute mesure. Ajouté ici
      // pour que l'oubli ne puisse pas se reproduire en silence.
      include: ['src/**/*.ts', 'src/**/*.astro', 'src/server/**/*.mjs'],
      // NB : v8 n'instrumente pas les `<script>` client des `.astro` — ils ne
      // comptent ni au numérateur ni au dénominateur. La logique client qui
      // mérite d'être testée doit donc être extraite dans un module `.ts`
      // (cf. `src/utils/gridFilter.ts`, `src/utils/search.ts`), sans quoi elle
      // échappe à la mesure sans que le chiffre bronche.
      thresholds: {
        // Exigence produit : ≥ 95 % sur les QUATRE métriques. Les seuils de
        // vitest s'appliquent bien métrique par métrique (contrairement au
        // `fail_under` de coverage.py, qui porte sur un total combiné).
        lines: 95,
        functions: 95,
        statements: 95,
        branches: 95,
        // merchants.ts est couvert exhaustivement (11 résolveurs + gardes) :
        // on verrouille 100 % pour détecter toute régression de couverture.
        'src/data/merchants.ts': {
          lines: 100,
          functions: 100,
          statements: 100,
          branches: 100,
        },
        // Le serveur de production : chaque visiteur passe par ces trois
        // fichiers. Verrouillé à 100 % parce que les chemins qui comptent le
        // plus y sont les moins visibles — la garde contre la traversée de
        // répertoire, et les écouteurs d'erreur sans lesquels une lecture en
        // échec arrête le processus.
        'src/server/**/*.mjs': {
          lines: 100,
          functions: 100,
          statements: 100,
          branches: 100,
        },
      },
    },
  },
});
