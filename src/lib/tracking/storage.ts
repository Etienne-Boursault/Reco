/**
 * src/lib/tracking/storage.ts — Persistance JSONL des clics sortants.
 *
 * Stratégie : un fichier par (sourceId, jour UTC), append-only :
 *   tools/output/clicks/<sourceId>/<YYYY-MM-DD>.jsonl
 *
 * Chaque ligne = 1 `ClickEvent` JSON minifié + `\n`. JSONL permet :
 *  - append O(1) sans relecture (vs JSON array),
 *  - parsing streaming côté Python (`tools/aggregate_clicks.py`),
 *  - corruption locale isolée à une ligne (les autres restent lisibles).
 *
 * Atomicité ligne-par-ligne : open(`a`) + writeSync + fsyncSync + closeSync.
 * Sur les FS POSIX, un write < PIPE_BUF (4 KiB) est atomique en append-mode.
 * On garde les lignes courtes (URL max 2 KiB, payload total < 3 KiB).
 *
 * Sous Windows, l'atomicité POSIX n'est PAS garantie (cf. ADR 0046 § notes
 * Windows) : on garde le garde-fou `Buffer.byteLength` pour ne jamais
 * dépasser PIPE_BUF + on s'appuie sur `fsyncSync` pour durabilité.
 */

// B-NIT-9 : ordre imports — node:* d'abord, puis local.
import {
  closeSync,
  existsSync,
  fsyncSync,
  mkdirSync,
  openSync,
  readFileSync,
  readdirSync,
  statSync,
  writeSync,
} from 'node:fs';
import { join, resolve } from 'node:path';

import type { ClickEvent, ClickStorage } from './types.js';
import { clickEventSchema } from './validator.js';

// B-HIGH-7 : pas de flag `i` — la regex tolérante diverge entre FS
// case-sensitive (Linux) et case-insensitive (Windows/macOS). On normalise
// via `.toLowerCase()` AVANT le test pour garantir un comportement uniforme.
const _SLUG_GUARD_RE = /^[a-z0-9_-]{1,128}$/;
function assertSlug(value: string, name: string): void {
  if (typeof value !== 'string' || !_SLUG_GUARD_RE.test(value.toLowerCase())) {
    throw new Error(`[tracking/storage] ${name} invalide (slug attendu) : ${JSON.stringify(value)}`);
  }
}

export function clicksRootDir(cwd: string = process.cwd()): string {
  return resolve(cwd, 'tools', 'output', 'clicks');
}

export function clicksDirFor(sourceId: string, cwd: string = process.cwd()): string {
  assertSlug(sourceId, 'sourceId');
  // M25-12 : defense in depth — resolve() + assertion startsWith pour
  // bloquer tout path-traversal qui aurait échappé à assertSlug.
  // B-HIGH-7 : on normalise via toLowerCase() pour ne pas créer des chemins
  // divergents entre FS case-sensitive (Linux) et case-insensitive (Windows).
  const root = clicksRootDir(cwd);
  const dir = resolve(root, sourceId.toLowerCase());
  if (!dir.startsWith(root)) {
    throw new Error(`[tracking/storage] path traversal détecté : ${JSON.stringify(sourceId)}`);
  }
  return dir;
}

/** Calcule le nom de fichier JSONL pour un jour donné (UTC). */
export function dailyFileFor(sourceId: string, date: Date, cwd: string = process.cwd()): string {
  const yyyy = date.getUTCFullYear();
  // B-MED-19 : garde-fou ts invalide. Sans ce check, un `Date('Invalid')`
  // produirait un nom de fichier `NaN-NaN-NaN.jsonl` et corromprait
  // l'agrégation downstream silencieusement.
  if (Number.isNaN(yyyy)) {
    throw new Error(`[tracking/storage] dailyFileFor : date invalide (${date.toString()})`);
  }
  const mm = String(date.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(date.getUTCDate()).padStart(2, '0');
  return join(clicksDirFor(sourceId, cwd), `${yyyy}-${mm}-${dd}.jsonl`);
}

/** Append atomique d'un event JSONL. Crée le dossier au besoin. */
export function appendClick(event: ClickEvent, cwd: string = process.cwd()): string {
  assertSlug(event.sourceId, 'sourceId');
  if (event.recoId !== null && event.recoId !== undefined) assertSlug(event.recoId, 'recoId');
  const dir = clicksDirFor(event.sourceId, cwd);
  mkdirSync(dir, { recursive: true });
  const path = dailyFileFor(event.sourceId, new Date(event.ts), cwd);
  const line = JSON.stringify(event) + '\n';
  // H25-5 : Buffer.byteLength('utf8') — un caractère non-ASCII compte > 1 byte.
  // La garde sur line.length sous-estime donc la taille réelle écrite sur disque
  // et pourrait laisser passer une ligne > PIPE_BUF (atomicité POSIX brisée).
  const lineBytes = Buffer.byteLength(line, 'utf8');
  if (lineBytes > 4000) {
    throw new Error(`[tracking/storage] ligne JSONL trop longue (${lineBytes} bytes > 4000)`);
  }
  const fd = openSync(path, 'a');
  try {
    writeSync(fd, line, null, 'utf8');
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  return path;
}

/**
 * Implémentation `ClickStorage` par défaut, branchée sur le FS local (JSONL).
 * Le handler reçoit cette instance par défaut ; on peut substituer en test
 * ou pour un backend alternatif (R-P1-14).
 */
export class JsonlClickStorage implements ClickStorage {
  constructor(private readonly cwd?: string) {}
  append(event: ClickEvent): void {
    appendClick(event, this.cwd);
  }
}

/** Liste les fichiers JSONL d'une source (utile pour le CLI Python via tests). */
export function listDailyFiles(sourceId: string, cwd: string = process.cwd()): string[] {
  const dir = clicksDirFor(sourceId, cwd);
  // B-MED-20 : try/catch direct sur readdirSync (ENOENT atomique). Évite
  // la race condition existsSync→readdirSync où le dir disparaît entre les
  // deux appels (rotation/cleanup concurrent).
  let names: string[];
  try {
    names = readdirSync(dir);
  } catch {
    return [];
  }
  return names
    .filter((n) => n.endsWith('.jsonl'))
    .sort()
    .map((n) => join(dir, n));
}

/**
 * Lit un fichier JSONL et renvoie les events (ignore les lignes corrompues
 * OU les lignes JSON valides mais qui ne passent pas la validation Zod —
 * cf. M25-15 : un attaquant qui écrirait directement dans le fichier ne
 * pourrait pas polluer les agrégations downstream).
 */
export function readDailyEvents(path: string): ClickEvent[] {
  if (!existsSync(path)) return [];
  const raw = readFileSync(path, 'utf8');
  const out: ClickEvent[] = [];
  for (const line of raw.split('\n')) {
    if (!line) continue;
    try {
      const parsed = JSON.parse(line);
      const validated = clickEventSchema.safeParse(parsed);
      if (!validated.success) continue;
      out.push(validated.data as ClickEvent);
    } catch {
      // ligne corrompue : on skip
    }
  }
  return out;
}

/** Énumère les `sourceId` qui ont au moins un fichier JSONL. */
export function listSourcesWithClicks(cwd: string = process.cwd()): string[] {
  const root = clicksRootDir(cwd);
  if (!existsSync(root)) return [];
  return readdirSync(root)
    .filter((name) => {
      try {
        return statSync(join(root, name)).isDirectory();
      } catch {
        return false;
      }
    })
    .sort();
}
