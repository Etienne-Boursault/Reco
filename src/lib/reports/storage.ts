/**
 * src/lib/reports/storage.ts — Persistance JSON des reports.
 *
 * Stratégie identique à `tools/common.py::atomic_write_text` :
 *  - écrit `<dir>/<id>.json.tmp`,
 *  - flush + fsync,
 *  - rename atomique (`fs.renameSync`).
 *
 * Pas de DB ⇒ kit duplicable, inspection trivial via `cat`. Le CLI Python
 * partage le même format (cf. `tools/manage_reports.py`).
 */

import { closeSync, existsSync, fsyncSync, mkdirSync, openSync, readFileSync, readdirSync, renameSync, statSync, writeSync } from 'node:fs';
import { join, resolve } from 'node:path';
import type { Report, ReportStatus } from './types.js';

/**
 * H16-4 — Guard contre path traversal. `sourceId` et `reportId` doivent être
 * des slugs stricts : `[a-z0-9_-]{1,128}`. Pas de `..`, pas de `/`, pas de `\`.
 * On lève si non-conforme — appelé en début de chaque fonction publique qui
 * compose un path. Préfère échouer fort plutôt que de désinfecter (l'appelant
 * doit toujours fournir des slugs propres ; un slug invalide signale un bug).
 */
const _SLUG_GUARD_RE = /^[a-z0-9_-]{1,128}$/i;
function assertSlug(value: string, name: string): void {
  if (typeof value !== 'string' || !_SLUG_GUARD_RE.test(value)) {
    throw new Error(`[reports/storage] ${name} invalide (slug attendu) : ${JSON.stringify(value)}`);
  }
}

/**
 * Racine du dossier des reports.
 * `process.cwd()` est la racine du repo quand Astro tourne (dev, build, vitest).
 */
export function reportsRootDir(cwd: string = process.cwd()): string {
  return resolve(cwd, 'tools', 'output', 'reports');
}

export function reportsDirFor(sourceId: string, cwd: string = process.cwd()): string {
  assertSlug(sourceId, 'sourceId');
  return join(reportsRootDir(cwd), sourceId);
}

export function reportPath(sourceId: string, reportId: string, cwd: string = process.cwd()): string {
  assertSlug(sourceId, 'sourceId');
  assertSlug(reportId, 'reportId');
  return join(reportsDirFor(sourceId, cwd), `${reportId}.json`);
}

/** Écrit `report` de façon atomique. Crée le dossier au besoin. */
export function writeReport(report: Report, cwd: string = process.cwd()): string {
  assertSlug(report.sourceId, 'sourceId');
  assertSlug(report.id, 'reportId');
  const dir = reportsDirFor(report.sourceId, cwd);
  mkdirSync(dir, { recursive: true });
  const target = join(dir, `${report.id}.json`);
  const tmp = `${target}.tmp`;
  const body = JSON.stringify(report, null, 2) + '\n';
  const fd = openSync(tmp, 'w');
  try {
    writeSync(fd, body, 0, 'utf8');
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  renameSync(tmp, target);
  return target;
}

/** Lit un report par id (path explicite ou (sourceId, id)). Renvoie `null` si absent. */
export function readReport(sourceId: string, reportId: string, cwd: string = process.cwd()): Report | null {
  const p = reportPath(sourceId, reportId, cwd);
  if (!existsSync(p)) return null;
  try {
    return JSON.parse(readFileSync(p, 'utf8')) as Report;
  } catch {
    return null;
  }
}

/**
 * Liste les reports d'une source (lecture build-time pour la queue admin).
 *
 * - Ignore les fichiers `.tmp` (écritures en cours).
 * - Trie par `submittedAt` desc (le plus récent en tête).
 * - Filtrage par `status` optionnel.
 */
export function listReports(
  sourceId: string,
  opts: { status?: ReportStatus; cwd?: string } = {},
): Report[] {
  const dir = reportsDirFor(sourceId, opts.cwd);
  if (!existsSync(dir)) return [];
  const out: Report[] = [];
  for (const name of readdirSync(dir)) {
    if (!name.endsWith('.json') || name.endsWith('.tmp')) continue;
    const p = join(dir, name);
    try {
      const r = JSON.parse(readFileSync(p, 'utf8')) as Report;
      if (opts.status && r.status !== opts.status) continue;
      out.push(r);
    } catch {
      // Fichier corrompu : on skip silencieusement (la lecture admin doit
      // rester robuste à un report mal-formé isolé).
    }
  }
  out.sort((a, b) => (a.submittedAt < b.submittedAt ? 1 : -1));
  return out;
}

/** Énumère les `sourceId` qui ont au moins un report (utile pour la queue globale). */
export function listSourcesWithReports(cwd: string = process.cwd()): string[] {
  const root = reportsRootDir(cwd);
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
