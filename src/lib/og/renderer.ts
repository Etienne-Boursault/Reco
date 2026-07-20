/**
 * Renderer Open Graph build-time : Satori (JSX → SVG) + resvg (SVG → PNG).
 *
 * Conçu pour être appelé depuis un endpoint Astro statique
 * (`getStaticPaths`) — le rendu se produit au build, jamais en runtime.
 *
 * Police : Inter, chargée depuis `src/fonts/og/` (commit explicite — pas
 * de dépendance `@fontsource/inter` en runtime, cf. ADR 0029) avec fallback sur
 * `node_modules/@fontsource/inter/files/` si présent (compat dev local).
 * Le chargement est mémoïsé via une **promesse** (pas un Buffer post-await)
 * pour éviter une race condition quand `Promise.all` lance N renders en
 * parallèle (cf. CR senior H1).
 *
 * Cache disque keyé par sha256(input) : un build récurrent qui ne change
 * pas un titre n'invoque pas Satori (cf. CR senior H6 / archi P2-A).
 *
 * NOTE : Satori ne supporte pas tous les emojis natifs sans
 * `loadAdditionalAsset`. Pour rester sobre (zéro réseau au build), on
 * laisse Satori dessiner le glyph `.notdef` ("tofu") quand l'emoji est
 * inconnu — le template les met côte à côte du label texte qui suffit à
 * différencier les cartes.
 */

import satori from 'satori';
import { Resvg } from '@resvg/resvg-js';
import { readFile, mkdir, writeFile, access } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { ogTemplate, type OGTemplateInput } from './template.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

// ---- Polices : chargement paresseux + cache (mémoïsation de la PROMESSE) --

interface FontPair { regular: Buffer; bold: Buffer; }

let fontPromise: Promise<FontPair> | null = null;

async function doLoadFonts(): Promise<FontPair> {
  // 1) Police commit dans le repo (`src/fonts/og/`) — source unique
  //    contrôlée, licence OFL 1.1 (cf. NOTICE).
  // 2) Fallback `node_modules/@fontsource/inter` si encore installé en dev.
  const candidates = [
    join(__dirname, '..', '..', 'fonts', 'og'),
    join(__dirname, '..', '..', '..', 'node_modules', '@fontsource', 'inter', 'files'),
  ];
  let regular: Buffer | null = null;
  let bold: Buffer | null = null;
  for (const base of candidates) {
    try {
      regular = await readFile(join(base, 'inter-latin-400-normal.woff'));
      bold = await readFile(join(base, 'inter-latin-700-normal.woff'));
      break;
    } catch {
      // Tente le suivant.
    }
  }
  if (!regular || !bold) {
    throw new Error(
      "Police Inter introuvable. Place `inter-latin-400-normal.woff` et " +
      "`inter-latin-700-normal.woff` dans `src/fonts/og/` (ou installe " +
      "`@fontsource/inter` en dev).",
    );
  }
  return { regular, bold };
}

async function loadFonts(): Promise<FontPair> {
  // Mémoïse la PROMESSE (pas le résultat post-await) : si N renders
  // démarrent en parallèle, ils partagent un unique I/O disque.
  if (!fontPromise) fontPromise = doLoadFonts();
  return fontPromise;
}

// ---- Cache disque (sha256(input) → PNG) ----------------------------------

const CACHE_DIR = join(process.cwd(), 'dist', '.cache', 'og');

function cacheKey(input: OGTemplateInput, opts: RenderOptions): string {
  const payload = JSON.stringify({ input, opts });
  return createHash('sha256').update(payload).digest('hex');
}

async function readCache(key: string): Promise<Uint8Array | null> {
  try {
    const buf = await readFile(join(CACHE_DIR, `${key}.png`));
    return new Uint8Array(buf);
  } catch {
    return null;
  }
}

async function writeCache(key: string, png: Uint8Array): Promise<void> {
  try {
    await mkdir(CACHE_DIR, { recursive: true });
    await writeFile(join(CACHE_DIR, `${key}.png`), png);
  } catch {
    // Cache best-effort : on n'échoue jamais un build pour un cache I/O.
  }
}

// ---- Rendu --------------------------------------------------------------

export interface RenderOptions {
  width?: number;
  height?: number;
  /** Désactive le cache disque (utile en tests). */
  noCache?: boolean;
}

/** PNG de repli minimal en mémoire (1×1 transparent) — utilisé si Satori plante. */
const FALLBACK_PNG_1X1 = Buffer.from(
  '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4' +
  '890000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082',
  'hex',
);

/**
 * Génère un PNG à partir d'un template OG.
 *
 * - Cache disque keyé par sha256(input, opts) : second build = cache hit.
 * - Fallback : si Satori/resvg plantent (titre kanji-only sans police
 *   couvrante, emoji-only…), on retourne un PNG 1×1 transparent plutôt
 *   que d'échouer le build entier. Le log stderr signale le slug fautif.
 *
 * @returns un Uint8Array prêt à être servi par Astro.
 */
export async function renderOG(
  input: OGTemplateInput,
  opts: RenderOptions = {},
): Promise<Uint8Array> {
  const width = opts.width ?? 1200;
  const height = opts.height ?? 630;

  if (!opts.noCache) {
    const key = cacheKey(input, { width, height });
    const cached = await readCache(key);
    if (cached) return cached;
  }

  try {
    const { regular, bold } = await loadFonts();
    const svg = await satori(ogTemplate(input) as any, {
      width,
      height,
      fonts: [
        { name: 'Inter', data: regular, weight: 400, style: 'normal' },
        { name: 'Inter', data: bold, weight: 700, style: 'normal' },
      ],
    });
    const resvg = new Resvg(svg, { fitTo: { mode: 'width', value: width } });
    const png = resvg.render().asPng();
    if (!opts.noCache) {
      await writeCache(cacheKey(input, { width, height }), png);
    }
    return png;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error(
      `[og/renderer] rendu Satori/resvg échoué pour "${input.title}" — ` +
      `fallback PNG 1×1. Cause :`,
      err,
    );
    return new Uint8Array(FALLBACK_PNG_1X1);
  }
}

// Helpers exposés pour les tests unitaires.
export const __testing = {
  cacheKey,
  resetFontCache: () => {
    fontPromise = null;
  },
};
