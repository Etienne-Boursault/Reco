/**
 * src/lib/registry/meta-loader.ts — Charge `tools/output/meta/meta_index.json`
 * (override via `RECO_OUTPUT_DIR`) au build pour alimenter les pages `/meta/`.
 *
 * Le fichier est OPTIONNEL : si `META_MODE !== '1'` ou si le fichier n'existe
 * pas, on retourne `null` et les pages méta `getStaticPaths` ne yieldent rien
 * (route 404 normale pour un fork standard).
 *
 * F-H-5 : `RECO_OUTPUT_DIR` permet à un fork (ou à la CI) de redéfinir le
 * dossier racine `tools/output/` — pratique pour les builds out-of-tree
 * ou les workflows monorepo.
 *
 * F-M-14 : `RECO_META_LOADER_STRICT=1` fait throw au lieu de retourner
 * `null` quand le parse échoue — utile en CI méta-site pour catch les
 * régressions silencieuses.
 */
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { buildEntries, type RegistryEntry } from './consumer.js';
import type { MetaIndexLoader } from './types.js';

/** Résout le chemin par défaut du meta_index, en honorant `RECO_OUTPUT_DIR`. */
function defaultMetaIndexPath(env: Record<string, string | undefined> = process.env): string {
  const outDir = env.RECO_OUTPUT_DIR
    ? env.RECO_OUTPUT_DIR
    : join(process.cwd(), 'tools', 'output');
  return join(outDir, 'meta', 'meta_index.json');
}

/** Conservé pour rétro-compat des imports tests historiques. */
const META_INDEX_PATH = defaultMetaIndexPath();

export interface MetaIndex {
  entries: RegistryEntry[];
  totals: {
    podcasts: number;
    items: number;
    mentions: number;
    episodes: number;
    guests: number;
  };
  generatedAt?: string;
}

/** Active si `META_MODE === '1'`. */
export function isMetaModeEnabled(env: Record<string, string | undefined> = process.env): boolean {
  return env.META_MODE === '1';
}

/**
 * Charge et valide le meta_index. Retourne `null` si désactivé ou indisponible.
 * Le parsing utilise `buildEntries` (best-effort : entrées invalides ignorées).
 */
export function loadMetaIndex(
  path?: string,
  env: Record<string, string | undefined> = process.env,
): MetaIndex | null {
  if (!isMetaModeEnabled(env)) return null;
  const resolvedPath = path ?? defaultMetaIndexPath(env);
  if (!existsSync(resolvedPath)) return null;
  const strict = env.RECO_META_LOADER_STRICT === '1';
  try {
    const raw = JSON.parse(readFileSync(resolvedPath, 'utf-8')) as {
      entries?: Array<{ sourceUrl: string; registry: unknown }>;
      totals?: MetaIndex['totals'];
      generatedAt?: string;
    };
    const entries = buildEntries(raw.entries ?? [], (url, err) => {
      // M24-13 : cohérent avec le consumer (`buildEntries` log via callback).
      console.warn(`[meta-loader] registry invalide ignoré (${url}) : ${err}`);
    });
    return {
      entries,
      totals: raw.totals ?? {
        podcasts: entries.length,
        items: 0,
        mentions: 0,
        episodes: 0,
        guests: 0,
      },
      generatedAt: raw.generatedAt,
    };
  } catch (err) {
    // F-M-14 : en mode strict, on remonte l'erreur (CI méta-site).
    if (strict) {
      throw new Error(
        `[meta-loader] parse meta_index échoué (${resolvedPath}) : ${
          err instanceof Error ? err.message : String(err)
        }`,
      );
    }
    // M24-13 : sinon, on ne avale pas silencieusement — best-effort + trace.
    console.warn(
      `[meta-loader] parse meta_index échoué (${resolvedPath}) : ${
        err instanceof Error ? err.message : String(err)
      }`,
    );
    return null;
  }
}

/**
 * Implémentation par défaut de `MetaIndexLoader` (R-P1-02) — utile aux forks
 * qui veulent passer le loader via DI plutôt que via import direct.
 */
export class FileMetaIndexLoader implements MetaIndexLoader {
  constructor(
    private readonly path: string = META_INDEX_PATH,
    private readonly env: Record<string, string | undefined> = process.env,
  ) {}

  load(): MetaIndex | null {
    return loadMetaIndex(this.path, this.env);
  }
}
