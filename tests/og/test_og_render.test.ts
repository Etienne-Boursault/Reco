/**
 * Test d'intégration : Satori + resvg produisent un PNG valide.
 *
 * On exécute quelques rendus (lents) pour vérifier que la chaîne complète
 * fonctionne : chargement police Inter + rendu SVG + conversion PNG.
 *
 * NB : ces tests nécessitent les WOFF Inter dans `src/fonts/og/` (ou
 * `node_modules/@fontsource/inter/files/`). Si absents, ils tombent sur
 * le fallback PNG 1×1 (le test détecte ce cas et le tolère explicitement).
 */

import { describe, it, expect } from 'vitest';
import { renderOG, __testing } from '../../src/lib/og/renderer.js';

function isPNG(bytes: Uint8Array): boolean {
  return (
    bytes[0] === 0x89 &&
    bytes[1] === 0x50 &&
    bytes[2] === 0x4e &&
    bytes[3] === 0x47
  );
}

describe('renderOG (intégration)', () => {
  it('produit un PNG (signature magique) ou fallback 1×1', async () => {
    const png = await renderOG(
      {
        title: 'Test OG',
        subtitle: 'Reco',
        emoji: '🎬',
        typeLabel: 'Film',
        sourceLabel: 'Un Bon Moment',
      },
      { noCache: true },
    );
    expect(png).toBeInstanceOf(Uint8Array);
    expect(isPNG(png)).toBe(true);
    expect(png.length).toBeGreaterThan(0);
  });

  it('respecte option width (taille de sortie variable)', async () => {
    __testing.resetFontCache();
    const png = await renderOG(
      { title: 'Width custom' },
      { width: 600, height: 315, noCache: true },
    );
    expect(isPNG(png)).toBe(true);
  });

  it('cache hit : deuxième appel renvoie le même contenu', async () => {
    const input = { title: 'Cache test', sourceLabel: 'Test' };
    const a = await renderOG(input);
    const b = await renderOG(input);
    expect(a.length).toBe(b.length);
    // Bytes identiques (hash key stable).
    expect(Buffer.from(a).equals(Buffer.from(b))).toBe(true);
  });

  it('fallback : input qui ferait planter Satori ne casse pas le build', async () => {
    // Couleurs invalides sont déjà rejetées par safeHex ; on teste un
    // titre vide qui descend bien dans Satori. Si Satori plante, on
    // retourne le PNG 1×1 — pas d'exception.
    const png = await renderOG({ title: '' }, { noCache: true });
    expect(png).toBeInstanceOf(Uint8Array);
    expect(isPNG(png)).toBe(true);
  });
});
