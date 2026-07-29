/**
 * Références de types ambiants du dépôt.
 *
 * `vitest/config` augmente le type `UserConfig` de Vite pour y ajouter la clé
 * `test`. Sans cette référence, `vitest.config.ts` — qui passe `{ test: … }` à
 * `getViteConfig()` d'Astro — ne compile pas : depuis Astro 7 la signature est
 * `getViteConfig(userViteConfig: ViteUserConfig, …)`, où `ViteUserConfig` est
 * le type Vite brut, sans `test`. L'appel est pourtant correct à l'exécution :
 * vitest lit bien la clé `test` de la config résolue.
 *
 * On rend donc l'augmentation visible plutôt que d'exclure `vitest.config.ts`
 * du type-check ou d'y poser une suppression : le fichier reste vérifié.
 */
/// <reference types="vitest/config" />
