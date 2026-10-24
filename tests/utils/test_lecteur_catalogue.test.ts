/**
 * Le port de lecture du catalogue (`src/lib/catalog/reader.ts`).
 *
 * Deux choses à garantir :
 *   1. le lecteur rend exactement ce que rend `getCollection` — c'est ce qui
 *      garde le site identique octet pour octet ;
 *   2. plus aucun fichier de `src/` n'importe `getCollection` (ni ses
 *      cousines) depuis `astro:content` en dehors du port : sinon la future
 *      lecture par instantané (ADR 0058) contournerait une partie du site sans
 *      que rien ne le signale.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (nom: string) => getCollection(nom),
}));

const { collectionsReader, lecteur } = await import('../../src/lib/catalog/reader');

describe('lecteur du catalogue', () => {
  beforeEach(() => getCollection.mockReset());

  it("rend les entrées de getCollection, sans les transformer", async () => {
    const entrees = [{ id: 'a1b2c3d4', data: { title: 'Bref' } }];
    getCollection.mockResolvedValue(entrees);
    const lues = await lecteur().collection('items');
    expect(lues).toBe(entrees);
    expect(getCollection).toHaveBeenCalledWith('items');
  });

  it("rend l'adaptateur des collections, avec ou sans contexte de requête", () => {
    expect(lecteur()).toBe(collectionsReader);
    expect(lecteur({ locals: {} })).toBe(collectionsReader);
  });
});

/** Fichiers de `src/` qui pourraient lire une collection. */
function fichiersSource(racine: string): string[] {
  const trouves: string[] = [];
  const parcourir = (dossier: string) => {
    for (const entree of readdirSync(dossier)) {
      const chemin = join(dossier, entree);
      if (statSync(chemin).isDirectory()) {
        if (entree !== 'content') parcourir(chemin);
      } else if (/\.(astro|ts|mts|mjs|js)$/.test(entree)) {
        trouves.push(chemin);
      }
    }
  };
  parcourir(racine);
  return trouves;
}

describe('une seule porte d’entrée vers les données', () => {
  const SRC = resolve(process.cwd(), 'src');
  // Le port lui-même, et la définition des collections.
  const AUTORISES = new Set(['lib/catalog/reader.ts', 'content.config.ts']);
  // Importer `getCollection`, `getEntry`, `getEntries` ou `getLiveCollection`,
  // seuls ou avec d'autres noms. Les imports de TYPES restent permis.
  const IMPORT_INTERDIT =
    /import\s*\{[^}]*\b(getCollection|getEntry|getEntries|getLiveCollection)\b[^}]*\}\s*from\s*['"]astro:content['"]/;

  it('aucun fichier de src/ ne lit les collections en contournant le lecteur', () => {
    const fautifs = fichiersSource(SRC)
      .map((f) => relative(SRC, f).split('\\').join('/'))
      .filter((f) => !AUTORISES.has(f))
      .filter((f) => IMPORT_INTERDIT.test(readFileSync(join(SRC, f), 'utf8')));
    expect(fautifs).toEqual([]);
  });

  it('le motif reconnaît bien un import interdit', () => {
    expect(IMPORT_INTERDIT.test("import { getCollection } from 'astro:content';")).toBe(true);
    expect(IMPORT_INTERDIT.test("import { getCollection, type CollectionEntry } from 'astro:content';")).toBe(true);
    expect(IMPORT_INTERDIT.test("import type { CollectionEntry } from 'astro:content';")).toBe(false);
  });
});
