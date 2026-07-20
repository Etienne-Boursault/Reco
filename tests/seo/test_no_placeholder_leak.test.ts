/**
 * Test post-build (H10 — Fixer coordination Vague 1) :
 *  - `astro.config.mjs` `throw` déjà si `SITE_URL` est absent en prod.
 *  - Ce test ajoute une ceinture de sécurité côté tests : si un `dist/`
 *    existe (build effectué juste avant via le script CI), on vérifie
 *    qu'aucun token `reco.example` n'a fuité dans les pages HTML produites.
 *
 * Skip propre si `dist/` est absent (ex. dev local sans build préalable) —
 * on évite un faux négatif et on ne force pas un `astro build` ici (lent,
 * dépendances natives Satori). En CI le job exécute `npm run build` AVANT
 * `npm run test:seo`, donc le `describe.skipIf` ne masque que le mode dev.
 *
 * Cf. ADR 0021 §5 — SITE_URL fail-fast.
 */
import { describe, expect, test } from 'vitest';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const DIST = 'dist';
const distExists = existsSync(DIST) && existsSync(join(DIST, 'index.html'));

// Collecte récursive des fichiers HTML du dist (épisodes, sources, home,
// /verifier, etc.). Permet de couvrir TOUS les types de pages — un leak
// ne pourrait pas se cacher dans une route particulière.
function collectHtml(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) collectHtml(full, acc);
    else if (entry.isFile() && entry.name.endsWith('.html')) acc.push(full);
  }
  return acc;
}

describe.skipIf(!distExists)('no placeholder leak (post-build)', () => {
  test('dist/index.html ne contient pas reco.example', () => {
    const html = readFileSync(join(DIST, 'index.html'), 'utf-8');
    expect(html).not.toContain('reco.example');
  });

  test('aucune page HTML du dist ne contient reco.example', () => {
    const files = collectHtml(DIST);
    const leaks: string[] = [];
    for (const file of files) {
      const html = readFileSync(file, 'utf-8');
      if (html.includes('reco.example')) leaks.push(file);
    }
    expect(leaks).toEqual([]);
  });

  test('robots.txt ne contient pas reco.example', () => {
    const robotsPath = join(DIST, 'robots.txt');
    if (!existsSync(robotsPath)) return; // tolère absence si endpoint pas compilé
    const txt = readFileSync(robotsPath, 'utf-8');
    expect(txt).not.toContain('reco.example');
  });
});
