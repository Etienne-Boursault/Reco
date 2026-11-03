/**
 * Racine du site construit, quel que soit le MODE de build.
 *
 * Astro range sa sortie à deux endroits différents :
 *   - build statique (`npm run build`)            → `dist/`
 *   - build SSR      (`RECO_SSR=1 npm run build`) → `dist/client/` et `dist/server/`
 *
 * Les tests post-build codaient `dist/` en dur. Après un build SSR ils ne
 * trouvaient plus rien — et ne le SIGNALAIENT même pas comme une absence de
 * build, puisque `dist/` existe toujours (il contient `client` et `server`) :
 * ils échouaient donc bruyamment sur 15 assertions au lieu de se sauter.
 *
 * Le cas est devenu courant le 2026-08-16, quand la production est passée au
 * mode `middleware` : c'est désormais le build SSR qui est déployé.
 */
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

/**
 * Renvoie la racine des fichiers CLIENT, ou `null` si le site n'a pas été
 * construit. `null` plutôt qu'un chemin inexistant : l'appelant doit pouvoir
 * SAUTER ses tests, pas les voir échouer.
 */
export function distRoot(): string | null {
  const base = resolve(process.cwd(), 'dist');
  // L'ordre compte : en SSR, `dist/` existe mais ne contient que `client` et
  // `server`. On teste donc `dist/client` d'abord.
  for (const candidat of [resolve(base, 'client'), base]) {
    if (existsSync(resolve(candidat, 'index.html'))) return candidat;
  }
  return null;
}

/**
 * Délai d'un test qui lit TOUTES les pages du site construit (2 800 fichiers
 * HTML au 2026-11-03). Le délai par défaut de vitest.config.ts, 30 s, ne
 * suffit pas sous `--coverage` quand le poste est chargé : 140 s et 70 s
 * mesurés le 2026-11-03 pour les deux tests qui échouaient au hasard.
 * Un test qui dépasse ce délai-ci signale un vrai problème, pas une lenteur
 * du poste.
 */
export const DELAI_PARCOURS_DIST = 300_000;
