/**
 * R-P2-06 — Fixtures golden cross-stack.
 *
 * Les mêmes fichiers JSON sous `tests/fixtures/registry/{valid,invalid}/`
 * sont consommés par les tests TS (ici) ET les tests Python
 * (`tests/registry/test_fixtures_cross_stack.py`). Cela garantit que les
 * deux validateurs (Zod + Python) restent en parité de comportement.
 */
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tryParseRegistry } from '../../src/lib/registry/types.js';

const FIXTURES_ROOT = resolve(
  __dirname,
  '..',
  'fixtures',
  'registry',
);

function readJson(path: string): unknown {
  return JSON.parse(readFileSync(path, 'utf-8'));
}

describe('fixtures golden cross-stack', () => {
  const validDir = join(FIXTURES_ROOT, 'valid');
  for (const name of readdirSync(validDir).filter((f) => f.endsWith('.json'))) {
    it(`valid/${name} → parse OK`, () => {
      const raw = readJson(join(validDir, name));
      const r = tryParseRegistry(raw);
      expect(r.ok).toBe(true);
    });
  }

  const invalidDir = join(FIXTURES_ROOT, 'invalid');
  for (const name of readdirSync(invalidDir).filter((f) => f.endsWith('.json'))) {
    it(`invalid/${name} → parse KO`, () => {
      const raw = readJson(join(invalidDir, name));
      // F-H-8 : `http://` n'est plus invalide hors production. Pour préserver
      // la parité cross-stack (Python rejette toujours), on force NODE_ENV
      // pendant la validation des fixtures invalides.
      const prev = process.env.NODE_ENV;
      process.env.NODE_ENV = 'production';
      try {
        const r = tryParseRegistry(raw);
        expect(r.ok).toBe(false);
      } finally {
        process.env.NODE_ENV = prev;
      }
    });
  }
});
