/**
 * `scripts/comparer-dist.mjs` : la parité de build d'une PR sans effet sur le site.
 *
 * Le script ne neutralise QUE les valeurs liées à l'horloge du build. Ces tests
 * vérifient qu'il voit tout le reste : un octet changé dans une page, un fichier
 * apparu ou disparu.
 */
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, describe, expect, it } from 'vitest';
// @ts-expect-error — module `.mjs` sans déclaration de types
import { comparer, normaliser } from '../../scripts/comparer-dist.mjs';

const SCRIPT = fileURLToPath(new URL('../../scripts/comparer-dist.mjs', import.meta.url));
const TEMPORAIRE = mkdtempSync(join(tmpdir(), 'comparer-dist-'));
afterAll(() => rmSync(TEMPORAIRE, { recursive: true, force: true }));

function dist(nom: string, contenus: Record<string, string>): string {
  const racine = join(TEMPORAIRE, nom);
  for (const [chemin, contenu] of Object.entries(contenus)) {
    mkdirSync(dirname(join(racine, chemin)), { recursive: true });
    writeFileSync(join(racine, chemin), contenu);
  }
  return racine;
}

const COMMUN = {
  'index.html': '<h1>Reco</h1>',
  'un-bon-moment/oeuvre/a1b2c3d4/index.html': '<h1>Bref</h1>',
};

describe('comparer-dist', () => {
  it("neutralise seulement les dates du build", () => {
    const avant = dist('dates-a', {
      ...COMMUN,
      'sitemap-0.xml': '<url><loc>/</loc><lastmod>2026-10-24T22:00:00.000Z</lastmod></url>',
      'stats.json': '{"generatedAt": "2026-10-24T22:00:00.000Z","n":3}',
      'client/version.txt': 'aaa',
    });
    const apres = dist('dates-b', {
      ...COMMUN,
      'sitemap-0.xml': '<url><loc>/</loc><lastmod>2026-10-25T08:00:00.000Z</lastmod></url>',
      'stats.json': '{"generatedAt": "2026-10-25T08:00:00.000Z","n":3}',
      'client/version.txt': 'bbb',
    });
    expect(comparer(avant, apres)).toEqual({
      identiques: 4,
      differents: [],
      seulementAvant: [],
      seulementApres: [],
    });
  });

  it('voit un octet changé, un fichier disparu et un fichier apparu', () => {
    const avant = dist('ecarts-a', { ...COMMUN, 'retiree/index.html': 'x', 'stats.json': '{"n":3}' });
    const apres = dist('ecarts-b', { ...COMMUN, 'ajoutee/index.html': 'y', 'stats.json': '{"n":4}' });
    const r = comparer(avant, apres);
    expect(r.differents).toEqual(['stats.json']);
    expect(r.seulementAvant).toEqual(['retiree/index.html']);
    expect(r.seulementApres).toEqual(['ajoutee/index.html']);
  });

  it('laisse intact un fichier sans normalisation applicable', () => {
    const contenu = Buffer.from([0x89, 0x50, 0x4e, 0x47]);
    expect(normaliser('og/carte.png', contenu)).toBe(contenu);
  });

  it('répond 0, 1 ou 2 en ligne de commande', () => {
    const lancer = (...args: string[]) => spawnSync(process.execPath, [SCRIPT, ...args], { encoding: 'utf8' });
    const a = dist('cli-a', COMMUN);
    const b = dist('cli-b', COMMUN);
    const c = dist('cli-c', { ...COMMUN, 'index.html': '<h1>Autre</h1>' });
    expect(lancer(a, b).status).toBe(0);
    const ecart = lancer(a, c);
    expect(ecart.status).toBe(1);
    expect(ecart.stdout).toContain('différent      index.html');
    expect(lancer(a).status).toBe(2);
    expect(lancer(a, join(TEMPORAIRE, 'absent')).status).toBe(2);
  });
});
