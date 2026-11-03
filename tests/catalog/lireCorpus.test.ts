import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { lireCorpus } from '../../src/lib/catalog/lireCorpus.ts';

const racines: string[] = [];
afterAll(() => {
  for (const r of racines) rmSync(r, { recursive: true, force: true });
});

function corpus(fichiers: Record<string, string>): string {
  const racine = mkdtempSync(join(tmpdir(), 'reco-corpus-'));
  racines.push(racine);
  for (const [chemin, contenu] of Object.entries(fichiers)) {
    mkdirSync(dirname(join(racine, chemin)), { recursive: true });
    writeFileSync(join(racine, chemin), contenu);
  }
  return racine;
}

describe('lireCorpus', () => {
  it('lit chaque fichier séparément, exclut les fixtures du schéma', () => {
    const racine = corpus({
      'sources/s.json': '{"id":"s"}',
      'episodes/s/e1.json': '{"guid":"e1"}',
      'items/s/i1.json': '{"id":"i1"}',
      'items/__cross_stack_fixture__/f.json': '{"id":"f"}',
      'items/s/LISEZMOI.md': 'pas du JSON',
      'mentions/s/b/m2.json': '{"id":"m2"}',
      'mentions/s/a.json': '{"id":"m1"}',
      'mentions/s/casse.json': '{"id":',
      'mentions/s/tableau.json': '[]',
      'redirections-oeuvres.json': '{"/s/oeuvre/x":"/s/oeuvre/i1"}',
    });
    const c = lireCorpus(racine);
    expect(c.items.map((x) => x.chemin)).toEqual(['items/s/i1.json']);
    expect(c.mentions.map((x) => x.chemin)).toEqual([
      'mentions/s/a.json',
      'mentions/s/b/m2.json',
      'mentions/s/casse.json',
      'mentions/s/tableau.json',
    ]);
    expect(c.mentions[2]?.erreur).toBeTruthy();
    expect(c.mentions[3]?.erreur).toBe('le fichier ne contient pas un objet JSON');
    expect(c.recos).toEqual([]);
    expect(c.redirections).toEqual({ '/s/oeuvre/x': '/s/oeuvre/i1' });
    expect(c.erreurRedirections).toBeUndefined();
  });

  it('rapporte une table de redirections illisible, et tolère son absence', () => {
    expect(lireCorpus(corpus({ 'redirections-oeuvres.json': '{' })).erreurRedirections).toBeTruthy();
    expect(lireCorpus(corpus({ 'sources/s.json': '{"id":"s"}' })).redirections).toEqual({});
  });

  it('refuse un dossier de contenu absent ou qui n’est pas un dossier', () => {
    const racine = corpus({ 'fichier.json': '{}' });
    expect(() => lireCorpus(join(racine, 'absent'))).toThrow('dossier de contenu introuvable');
    expect(() => lireCorpus(join(racine, 'fichier.json'))).toThrow('dossier de contenu introuvable');
  });
});
