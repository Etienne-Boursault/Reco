/**
 * `/[source]/reports` ne doit PAS être construite sans `RECO_ADMIN=1`.
 *
 * Cette page rend le nom, l'ADRESSE E-MAIL et le texte libre des personnes qui
 * signalent une erreur. Elle était pré-rendue sans condition : `getStaticPaths`
 * émettait une route par source, la page atterrissait dans `dist/` et partait
 * **avec le site public**. Au premier signalement reçu, l'adresse d'un
 * visiteur devenait lisible par quiconque, sans authentification.
 *
 * Les trois protections en place n'étaient que de la DÉCOUVRABILITÉ, jamais de
 * l'ACCÈS : `noindex`, `Disallow: /*​/reports` dans robots.txt, et le filtre
 * sitemap. Pire, `robots.txt` publie le motif d'URL et les `sourceId` sont sur
 * la page d'accueil.
 *
 * Ce fichier est SÉPARÉ de `test_pages_reports_cov.test.ts` : vérifier
 * l'absence du flag exige de recharger le module avec un environnement
 * différent, ce qui pollue le registre de modules des autres tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));
vi.mock('../../src/lib/reports/storage.js', () => ({
  listReports: () => [],
}));

const SOURCES = [
  { id: 'ubm', data: { id: 'ubm', title: 'Un Bon Moment' } },
  { id: 'autre', data: { id: 'autre', title: 'Autre' } },
];

beforeEach(() => {
  getCollection.mockReset();
  getCollection.mockImplementation(async () => SOURCES);
});

async function pathsAvecEnv(valeur: string | undefined): Promise<unknown[]> {
  vi.resetModules();
  if (valeur === undefined) vi.stubEnv('RECO_ADMIN', '');
  else vi.stubEnv('RECO_ADMIN', valeur);
  const mod = await import('../../src/pages/[source]/reports.astro');
  const paths = await mod.getStaticPaths();
  vi.unstubAllEnvs();
  return paths as unknown[];
}

describe('/[source]/reports — garde de build', () => {
  it('n’émet AUCUNE route quand RECO_ADMIN est absent', async () => {
    expect(await pathsAvecEnv(undefined)).toEqual([]);
  });

  it('n’émet AUCUNE route pour une valeur autre que « 1 »', async () => {
    for (const valeur of ['0', 'true', 'yes', 'admin']) {
      expect(await pathsAvecEnv(valeur), `RECO_ADMIN=${valeur}`).toEqual([]);
    }
  });

  it('émet une route par source quand RECO_ADMIN=1', async () => {
    const paths = (await pathsAvecEnv('1')) as Array<{ params: { source: string } }>;
    expect(paths.map((p) => p.params.source)).toEqual(['ubm', 'autre']);
  });
});
