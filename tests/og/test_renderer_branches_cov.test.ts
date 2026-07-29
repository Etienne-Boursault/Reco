/**
 * tests/og/test_renderer_branches_cov.test.ts — Branches restantes de
 * `src/lib/og/renderer.ts` : cache disque froid (miss → écriture → hit) et
 * repli PNG 1×1 quand la police est introuvable.
 *
 * Le cache est keyé sur `join(process.cwd(), 'dist', '.cache', 'og')`, évalué
 * à l'import du module. On stubbe donc `process.cwd()` AVANT un import
 * dynamique : le test travaille dans un dossier temporaire et n'écrit jamais
 * dans le `dist/` partagé du dépôt.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { mkdtempSync, rmSync, readdirSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

function isPNG(bytes: Uint8Array): boolean {
  return bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47;
}

/** Importe le renderer avec `process.cwd()` redirigé vers `root`. */
async function importRendererWithCwd(root: string) {
  vi.resetModules();
  const spy = vi.spyOn(process, 'cwd').mockReturnValue(root);
  try {
    return await import('../../src/lib/og/renderer.js');
  } finally {
    spy.mockRestore();
  }
}

describe('renderOG — cache disque froid', () => {
  let ROOT: string;

  afterEach(() => {
    if (ROOT && existsSync(ROOT)) rmSync(ROOT, { recursive: true, force: true });
    vi.resetModules();
    vi.restoreAllMocks();
  });

  it('miss → rendu + écriture du PNG ; hit → relecture identique', async () => {
    ROOT = mkdtempSync(join(tmpdir(), 'reco-og-cache-'));
    const { renderOG } = await importRendererWithCwd(ROOT);
    const cacheDir = join(ROOT, 'dist', '.cache', 'og');
    expect(existsSync(cacheDir)).toBe(false);

    const input = { title: 'Carte de test', sourceLabel: 'Un Bon Moment' };
    const first = await renderOG(input);
    expect(isPNG(first)).toBe(true);

    // Le miss a déclenché `writeCache` : un unique PNG keyé sha256.
    const files = readdirSync(cacheDir);
    expect(files).toHaveLength(1);
    expect(files[0]).toMatch(/^[0-9a-f]{64}\.png$/);

    // Deuxième appel : servi depuis le disque, octets identiques.
    const second = await renderOG(input);
    expect(Buffer.from(second).equals(Buffer.from(first))).toBe(true);
    expect(readdirSync(cacheDir)).toHaveLength(1);
  });

  it('noCache → ni lecture ni écriture de cache', async () => {
    ROOT = mkdtempSync(join(tmpdir(), 'reco-og-nocache-'));
    const { renderOG } = await importRendererWithCwd(ROOT);
    const png = await renderOG({ title: 'Sans cache' }, { noCache: true });
    expect(isPNG(png)).toBe(true);
    expect(existsSync(join(ROOT, 'dist', '.cache', 'og'))).toBe(false);
  });
});

describe('renderOG — police introuvable', () => {
  afterEach(() => {
    vi.doUnmock('node:fs/promises');
    vi.resetModules();
    vi.restoreAllMocks();
  });

  it('les deux chemins de police échouent → PNG 1×1 de repli + trace stderr', async () => {
    vi.resetModules();
    vi.doMock('node:fs/promises', async (importOriginal) => {
      const actual = await importOriginal<typeof import('node:fs/promises')>();
      return {
        ...actual,
        default: actual,
        readFile: async () => {
          throw new Error('ENOENT (simulé)');
        },
      };
    });
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const { renderOG } = await import('../../src/lib/og/renderer.js');

    const png = await renderOG({ title: 'Sans police' }, { noCache: true });

    // Repli : PNG 1×1 transparent (68 octets), pas d'exception.
    expect(png).toBeInstanceOf(Uint8Array);
    expect(isPNG(png)).toBe(true);
    expect(png.length).toBe(68);
    expect(error).toHaveBeenCalledOnce();
    expect(String(error.mock.calls[0][0])).toContain('Sans police');
    expect(String(error.mock.calls[0][1])).toMatch(/Police Inter introuvable/);
  });
});
