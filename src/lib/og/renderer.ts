/**
 * Renderer Open Graph build-time : Satori (JSX → SVG) + resvg (SVG → PNG).
 *
 * Conçu pour être appelé depuis un endpoint Astro statique
 * (`getStaticPaths`) — le rendu se produit au build, jamais en runtime.
 *
 * Polices : Inter et Bebas Neue, chargées depuis `src/fonts/og/` (commit
 * explicite — pas de dépendance aux paquets `@fontsource` en runtime, cf. ADR
 * 0029) avec fallback sur leurs dossiers `files/` dans `node_modules` si
 * présents (compat dev local).
 * Le chargement est mémoïsé via une **promesse** (pas un Buffer post-await)
 * pour éviter une race condition quand `Promise.all` lance N renders en
 * parallèle (cf. CR senior H1).
 *
 * Cache disque keyé par sha256(DESSIN) : un build récurrent qui ne change
 * pas une carte n'invoque ni Satori ni resvg (cf. CR senior H6 / archi P2-A).
 * Voir « Cache disque » plus bas pour l'emplacement et la clé.
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
import { etiquetteTemplate, type EtiquetteInput } from './etiquette.js';

/** Une carte : l'ancien gabarit, ou l'« Étiquette » (audit du 2026-10-07). */
export type OGCarte = OGTemplateInput | EtiquetteInput;

function estEtiquette(input: OGCarte): input is EtiquetteInput {
  return (input as EtiquetteInput).gabarit === 'etiquette';
}

const __dirname = dirname(fileURLToPath(import.meta.url));

// ---- Polices : chargement paresseux + cache (mémoïsation de la PROMESSE) --

interface FontPair {
  regular: Buffer;
  bold: Buffer;
  display: Buffer;
  /** sha256 des trois fichiers : entre dans la clé de cache des cartes. */
  empreinte: string;
}

let fontPromise: Promise<FontPair> | null = null;

async function doLoadFonts(): Promise<FontPair> {
  // POURQUOI `process.cwd()` D'ABORD, ET PAS `__dirname`
  //
  // Les deux chemins d'origine partaient tous deux de `__dirname`. En build
  // STATIQUE, Vite exécute ce module depuis les sources : `__dirname` vaut
  // `<racine>/src/lib/og`, les deux chemins tombent juste, et les cartes se
  // rendaient normalement. En build SSR (`RECO_SSR=1`), Astro bundle le code
  // dans `dist/server/chunks/` : `__dirname` change, les deux chemins pointent
  // dans le vide, et le rendu tombait sur le PNG 1×1 de repli.
  //
  // Personne ne s'en apercevait : le repli est silencieux côté site, l'erreur
  // ne vit que dans les logs du build, et aucun test ne regardait la taille du
  // PNG produit. La production a donc servi des vignettes de partage vides —
  // un carré transparent d'un pixel — depuis le passage en SSR.
  //
  // `process.cwd()` est la racine du projet pendant `astro build`, et la
  // racine du site chez l'hébergeur, qui déploie le dépôt entier. Il ne dépend
  // ni du bundling ni du mode.
  const candidates = [
    // 1) Polices commitées (`src/fonts/og/`) — source unique contrôlée,
    //    licence OFL 1.1 (cf. NOTICE et src/fonts/og/LICENSE).
    join(process.cwd(), 'src', 'fonts', 'og'),
    // 2) Relatif au module : vaut tant que le code n'est pas bundlé.
    join(__dirname, '..', '..', 'fonts', 'og'),
    // 3) Replis des paquets `@fontsource`, aux deux emplacements possibles.
    join(process.cwd(), 'node_modules', '@fontsource', 'inter', 'files'),
    join(__dirname, '..', '..', '..', 'node_modules', '@fontsource', 'inter', 'files'),
  ];
  // Bebas Neue, titres et chiffres de l'« Étiquette » : même ordre de
  // recherche, avec le paquet `@fontsource/bebas-neue` comme repli.
  const candidatsDisplay = [
    candidates[0],
    candidates[1],
    join(process.cwd(), 'node_modules', '@fontsource', 'bebas-neue', 'files'),
    join(__dirname, '..', '..', '..', 'node_modules', '@fontsource', 'bebas-neue', 'files'),
  ];
  let regular: Buffer | null = null;
  let bold: Buffer | null = null;
  let display: Buffer | null = null;
  for (const base of candidates) {
    try {
      regular = await readFile(join(base, 'inter-latin-400-normal.woff'));
      bold = await readFile(join(base, 'inter-latin-700-normal.woff'));
      break;
    } catch {
      // Tente le suivant.
    }
  }
  for (const base of candidatsDisplay) {
    try {
      display = await readFile(join(base, 'bebas-neue-latin-400-normal.woff'));
      break;
    } catch {
      // Tente le suivant.
    }
  }
  if (!regular || !bold || !display) {
    throw new Error(
      "Police Inter ou Bebas Neue introuvable — les cartes OG seraient des PNG 1x1. " +
      "Place `inter-latin-400-normal.woff`, `inter-latin-700-normal.woff` et " +
      "`bebas-neue-latin-400-normal.woff` dans `src/fonts/og/` (ils y sont " +
      "commités ; les paquets `@fontsource` servent de repli). Cherché dans : " +
      candidates.join(', '),
    );
  }
  const empreinte = createHash('sha256').update(regular).update(bold).update(display).digest('hex');
  return { regular, bold, display, empreinte };
}

async function loadFonts(): Promise<FontPair> {
  // Mémoïse la PROMESSE (pas le résultat post-await) : si N renders
  // démarrent en parallèle, ils partagent un unique I/O disque.
  if (!fontPromise) fontPromise = doLoadFonts();
  return fontPromise;
}

// ---- Cache disque (sha256(dessin) → PNG) ----------------------------------
//
// OÙ. Le cache vivait dans `dist/.cache/og` — que `astro build` VIDE au début
// de chaque build : il ne servait donc jamais d'un build à l'autre, et chaque
// déploiement recalculait toutes les cartes (vérifié le 2026-10-07 avec un
// fichier témoin). À la racine du dépôt, dans `.cache/` (ignoré par git), il
// survit : chez l'hébergeur, le déploiement fait `git reset --hard` puis
// `npm run build`, et un reset ne supprime pas les fichiers ignorés.
//
// QUELLE CLÉ. Elle portait sur les DONNÉES de la carte. Tant que le cache
// disparaissait à chaque build, c'était sans conséquence ; persistant, il
// aurait resservi les anciennes images après une retouche du gabarit, sans
// que rien ne le signale. La clé porte désormais sur l'ARBRE que le gabarit
// produit — styles et textes compris — et sur l'empreinte des polices :
// toute modification visible de la carte change la clé, toute carte
// inchangée est relue telle quelle.

const CACHE_DIR = join(process.cwd(), '.cache', 'og');

function cacheKey(arbre: unknown, opts: RenderOptions, empreintePolices: string): string {
  const payload = JSON.stringify({ arbre, opts, empreintePolices });
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
 * - Cache disque keyé par sha256(dessin, dimensions, polices) dans
 *   `.cache/og` : une carte inchangée est relue d'un build à l'autre.
 * - Fallback : si Satori/resvg plantent (titre kanji-only sans police
 *   couvrante, emoji-only…), on retourne un PNG 1×1 transparent plutôt
 *   que d'échouer le build entier. Le log stderr signale le slug fautif.
 *
 * @returns un Uint8Array prêt à être servi par Astro.
 */
export async function renderOG(
  input: OGCarte,
  opts: RenderOptions = {},
): Promise<Uint8Array> {
  const width = opts.width ?? 1200;
  const height = opts.height ?? 630;

  try {
    const { regular, bold, display, empreinte } = await loadFonts();
    const arbre = estEtiquette(input) ? etiquetteTemplate(input) : ogTemplate(input);
    const key = opts.noCache ? null : cacheKey(arbre, { width, height }, empreinte);
    if (key) {
      const cached = await readCache(key);
      if (cached) return cached;
    }
    const svg = await satori(arbre as any, {
      width,
      height,
      fonts: [
        { name: 'Inter', data: regular, weight: 400, style: 'normal' },
        { name: 'Inter', data: bold, weight: 700, style: 'normal' },
        { name: 'Bebas Neue', data: display, weight: 400, style: 'normal' },
      ],
    });
    const resvg = new Resvg(svg, { fitTo: { mode: 'width', value: width } });
    const png = resvg.render().asPng();
    if (key) await writeCache(key, png);
    return png;
  } catch (err) {
    // eslint-disable-next-line no-console
    console.error(
      `[og/renderer] rendu Satori/resvg échoué pour "${estEtiquette(input) ? input.titre : input.title}" — ` +
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
