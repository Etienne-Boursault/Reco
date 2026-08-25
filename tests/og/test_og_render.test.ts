/**
 * Test d'intégration : Satori + resvg produisent un PNG valide.
 *
 * On exécute quelques rendus (lents) pour vérifier que la chaîne complète
 * fonctionne : chargement police Inter + rendu SVG + conversion PNG.
 *
 * CE QUE CE FICHIER TOLÉRAIT, ET NE TOLÈRE PLUS
 * ---------------------------------------------
 * L'en-tête disait : « Si [les polices sont] absentes, ils tombent sur le
 * fallback PNG 1×1 (le test détecte ce cas et le tolère explicitement). »
 * Un test écrit pour ne jamais échouer ne peut rien détecter — et c'est
 * exactement ce qui est arrivé : la production a servi des vignettes de
 * partage vides, un carré transparent d'un pixel, sans qu'aucun test ne
 * bronche. Les polices sont désormais COMMITÉES dans `src/fonts/og/` ; le
 * repli n'est plus un cas normal, c'est une panne.
 */

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { renderOG, __testing } from '../../src/lib/og/renderer.js';

/** Le repli silencieux : 68 octets, 1×1 transparent. Une vraie carte ~46 Ko. */
const TAILLE_MINIMALE = 1024;

/** Largeur et hauteur lues dans le chunk IHDR d'un PNG. */
function dimensions(bytes: Uint8Array): { largeur: number; hauteur: number } {
  const vue = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  return { largeur: vue.getUint32(16), hauteur: vue.getUint32(20) };
}

function isPNG(bytes: Uint8Array): boolean {
  return (
    bytes[0] === 0x89 &&
    bytes[1] === 0x50 &&
    bytes[2] === 0x4e &&
    bytes[3] === 0x47
  );
}

describe('renderOG (intégration)', () => {
  it('produit une VRAIE carte, pas le repli 1×1', async () => {
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
    // `length > 0` était vrai du repli aussi : c'est la taille qui distingue.
    expect(png.length).toBeGreaterThan(TAILLE_MINIMALE);
    expect(dimensions(png)).toEqual({ largeur: 1200, hauteur: 630 });
  });

  it('respecte option width (taille de sortie variable)', async () => {
    __testing.resetFontCache();
    const png = await renderOG(
      { title: 'Width custom' },
      { width: 600, height: 315, noCache: true },
    );
    expect(isPNG(png)).toBe(true);
    expect(dimensions(png)).toEqual({ largeur: 600, hauteur: 315 });
  });

  it('les polices sont dans le dépôt, pas seulement dans node_modules', async () => {
    // La vraie cause de la panne : `src/fonts/og/` ne contenait qu'un README,
    // alors que le code, le NOTICE et l'ADR 0029 affirmaient les fichiers
    // commités. Le rendu reposait donc entièrement sur `node_modules`, et le
    // moindre changement de chemin le faisait basculer sur le repli.
    for (const nom of ['inter-latin-400-normal.woff', 'inter-latin-700-normal.woff']) {
      const octets = readFileSync(join(process.cwd(), 'src', 'fonts', 'og', nom));
      expect(octets.length).toBeGreaterThan(10_000);
      // Signature WOFF : `wOFF`.
      expect(octets.subarray(0, 4).toString('ascii')).toBe('wOFF');
    }
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
