/**
 * Une reco `draft` ne doit jamais atteindre le site.
 *
 * La chaîne automatique de venus écrit des brouillons AVANT la relecture : le
 * seul filtre `!== 'discarded'` les aurait publiés. Le test de câblage vérifie
 * que chaque page publique qui lit la collection `recos` passe par
 * `recoPubliee`, pour qu'aucune ne revienne à l'ancien filtre.
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

import { recoPubliee } from '../../src/utils/recoPubliee';

describe('recoPubliee', () => {
  it('ne publie que les recos validées', () => {
    expect(recoPubliee('validated')).toBe(true);
    expect(recoPubliee('draft')).toBe(false);
    expect(recoPubliee('discarded')).toBe(false);
    expect(recoPubliee(undefined)).toBe(false);
  });
});

const PAGES_QUI_LISENT_LES_RECOS = [
  'src/utils/sourceCatalogData.ts',
  'src/components/SourceCatalog.astro',
  'src/pages/[source]/episode/[guid].astro',
  'src/pages/a-propos.astro',
  'src/pages/index.astro',
  'src/pages/og/[...slug].png.ts',
  'src/pages/[source]/report/[recoId].astro',
];

describe('câblage du filtre de publication', () => {
  it.each(PAGES_QUI_LISENT_LES_RECOS)('%s passe par recoPubliee', (fichier) => {
    const source = readFileSync(resolve(process.cwd(), fichier), 'utf8');
    expect(source).toContain('recoPubliee(');
    expect(source).not.toMatch(/status\s*[!=]==\s*'discarded'/);
  });
});
