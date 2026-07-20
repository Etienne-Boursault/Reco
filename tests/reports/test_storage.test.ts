/**
 * tests/reports/test_storage.test.ts — Persistance atomique des reports.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { mkdtempSync, readFileSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  writeReport,
  readReport,
  listReports,
  listSourcesWithReports,
  reportPath,
} from '../../src/lib/reports/storage.ts';
import type { Report } from '../../src/lib/reports/types.ts';

let CWD: string;

beforeEach(() => {
  CWD = mkdtempSync(join(tmpdir(), 'reco-reports-'));
});

function mkReport(overrides: Partial<Report> = {}): Report {
  return {
    id: 'rep-test-1',
    sourceId: 'un-bon-moment',
    recoId: 'ubm-0001',
    category: 'error',
    details: 'Le titre est incorrect.',
    submitter: { wantCredit: false },
    submittedAt: '2026-06-11T10:00:00.000Z',
    status: 'pending',
    resolvedAt: null,
    resolvedBy: null,
    notes: null,
    ...overrides,
  };
}

describe('reports storage', () => {
  it('écrit un report au bon chemin', () => {
    const r = mkReport();
    writeReport(r, CWD);
    const p = reportPath(r.sourceId, r.id, CWD);
    expect(existsSync(p)).toBe(true);
    const text = readFileSync(p, 'utf8');
    expect(JSON.parse(text)).toMatchObject({ id: r.id, sourceId: r.sourceId });
  });

  it('readReport renvoie le report écrit', () => {
    const r = mkReport({ details: 'détail avec accent é' });
    writeReport(r, CWD);
    const back = readReport(r.sourceId, r.id, CWD);
    expect(back).not.toBeNull();
    expect(back?.details).toBe('détail avec accent é');
  });

  it('readReport renvoie null si absent', () => {
    expect(readReport('absent-source', 'rep-nope', CWD)).toBeNull();
  });

  it('listReports trie par submittedAt desc', () => {
    writeReport(mkReport({ id: 'rep-a', submittedAt: '2026-06-11T10:00:00.000Z' }), CWD);
    writeReport(mkReport({ id: 'rep-b', submittedAt: '2026-06-12T10:00:00.000Z' }), CWD);
    writeReport(mkReport({ id: 'rep-c', submittedAt: '2026-06-10T10:00:00.000Z' }), CWD);
    const list = listReports('un-bon-moment', { cwd: CWD });
    expect(list.map((r) => r.id)).toEqual(['rep-b', 'rep-a', 'rep-c']);
  });

  it('listReports filtre par status', () => {
    writeReport(mkReport({ id: 'rep-a', status: 'pending' }), CWD);
    writeReport(mkReport({ id: 'rep-b', status: 'resolved' }), CWD);
    const pending = listReports('un-bon-moment', { status: 'pending', cwd: CWD });
    expect(pending).toHaveLength(1);
    expect(pending[0].id).toBe('rep-a');
  });

  it('listSourcesWithReports énumère les sources avec reports', () => {
    writeReport(mkReport({ sourceId: 'src-a' }), CWD);
    writeReport(mkReport({ id: 'rep-2', sourceId: 'src-b' }), CWD);
    expect(listSourcesWithReports(CWD)).toEqual(['src-a', 'src-b']);
  });

  it("listReports d'une source absente renvoie []", () => {
    expect(listReports('inexistante', { cwd: CWD })).toEqual([]);
  });
});

// Cleanup au teardown (tmp dirs)
import { afterAll } from 'vitest';
afterAll(() => {
  // les CWD individuels sont sous tmp/ — on ne tente pas de tout supprimer
  // (mkdtempSync laisse des dossiers, ramassés par OS). Le CWD courant est
  // jeté par beforeEach à chaque test.
  if (CWD && existsSync(CWD)) {
    try { rmSync(CWD, { recursive: true, force: true }); } catch { /* ignore */ }
  }
});
