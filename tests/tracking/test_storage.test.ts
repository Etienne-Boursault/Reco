/**
 * tests/tracking/test_storage.test.ts — Append JSONL, rotation daily.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { mkdtempSync, readFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import {
  appendClick,
  clicksDirFor,
  dailyFileFor,
  listDailyFiles,
  listSourcesWithClicks,
  readDailyEvents,
} from '../../src/lib/tracking/storage.ts';
// listDailyFiles, dailyFileFor are re-imported above; ensure imports exist for new tests.
import type { ClickEvent } from '../../src/lib/tracking/types.ts';

let CWD: string;
beforeEach(() => {
  CWD = mkdtempSync(join(tmpdir(), 'reco-clicks-'));
});

function ev(over: Partial<ClickEvent> = {}): ClickEvent {
  return {
    ts: '2026-06-12T10:00:00.000Z',
    url: 'https://themoviedb.org/movie/42',
    category: 'tmdb',
    sourceId: 'un-bon-moment',
    recoId: 'ubm-0001',
    ref: '/un-bon-moment/episode/abc',
    ...over,
  };
}

describe('appendClick', () => {
  it('crée le dossier et écrit une ligne JSONL', () => {
    const p = appendClick(ev(), CWD);
    expect(existsSync(p)).toBe(true);
    const content = readFileSync(p, 'utf8');
    expect(content.trim().split('\n')).toHaveLength(1);
    expect(JSON.parse(content.trim())).toMatchObject({
      url: 'https://themoviedb.org/movie/42',
      category: 'tmdb',
    });
  });

  it('append plusieurs lignes au même fichier (même jour)', () => {
    appendClick(ev({ recoId: 'a' }), CWD);
    appendClick(ev({ recoId: 'b' }), CWD);
    appendClick(ev({ recoId: 'c' }), CWD);
    const files = listDailyFiles('un-bon-moment', CWD);
    expect(files).toHaveLength(1);
    const events = readDailyEvents(files[0]);
    expect(events).toHaveLength(3);
    expect(events.map((e) => e.recoId)).toEqual(['a', 'b', 'c']);
  });

  it('rotation par jour UTC : 2 fichiers pour 2 jours', () => {
    appendClick(ev({ ts: '2026-06-12T23:00:00.000Z' }), CWD);
    appendClick(ev({ ts: '2026-06-13T00:01:00.000Z' }), CWD);
    const files = listDailyFiles('un-bon-moment', CWD);
    expect(files).toHaveLength(2);
    expect(files[0]).toMatch(/2026-06-12\.jsonl$/);
    expect(files[1]).toMatch(/2026-06-13\.jsonl$/);
  });

  it('rejette un sourceId non-slug (path traversal)', () => {
    expect(() => appendClick(ev({ sourceId: '../etc' }), CWD)).toThrow(/slug attendu/);
  });

  it('rejette un recoId non-slug', () => {
    expect(() => appendClick(ev({ recoId: '../x' }), CWD)).toThrow(/slug attendu/);
  });

  it('accepte recoId null', () => {
    const p = appendClick(ev({ recoId: null }), CWD);
    const events = readDailyEvents(p);
    expect(events[0].recoId).toBeNull();
  });
});

describe('listSourcesWithClicks', () => {
  it('liste les sources avec au moins 1 fichier', () => {
    appendClick(ev({ sourceId: 'un-bon-moment' }), CWD);
    appendClick(ev({ sourceId: 'autre-podcast' }), CWD);
    const out = listSourcesWithClicks(CWD);
    expect(out).toEqual(['autre-podcast', 'un-bon-moment']);
  });

  it('renvoie [] si root absent', () => {
    expect(listSourcesWithClicks(CWD)).toEqual([]);
  });
});

describe('readDailyEvents', () => {
  it('ignore les lignes corrompues', () => {
    const p = appendClick(ev(), CWD);
    // Ajout d'une ligne JSON corrompue
    const target = dailyFileFor('un-bon-moment', new Date('2026-06-12T10:00:00.000Z'), CWD);
    require('node:fs').appendFileSync(target, 'not-json-at-all\n');
    appendClick(ev({ recoId: 'ok' }), CWD);
    const events = readDailyEvents(p);
    expect(events).toHaveLength(2);
    expect(events[1].recoId).toBe('ok');
  });

  it('renvoie [] si fichier absent', () => {
    expect(readDailyEvents(join(CWD, 'nope.jsonl'))).toEqual([]);
  });

  it('M25-15 : skip lignes JSON valides mais qui ne passent pas le schéma Zod', () => {
    appendClick(ev(), CWD);
    const target = dailyFileFor('un-bon-moment', new Date('2026-06-12T10:00:00.000Z'), CWD);
    // JSON valide mais champ obligatoire (category) hors enum → schéma reject.
    require('node:fs').appendFileSync(
      target,
      JSON.stringify({ ts: '2026-06-12T10:00:01.000Z', url: 'https://x.example', category: 'NOPE', sourceId: 'un-bon-moment', recoId: null, ref: null }) + '\n',
    );
    appendClick(ev({ recoId: 'kept' }), CWD);
    const events = readDailyEvents(target);
    expect(events).toHaveLength(2);
    expect(events.map((e) => e.recoId)).toEqual(['ubm-0001', 'kept']);
  });
});

describe('appendClick guard', () => {
  it('throw si la ligne JSONL > 4000 bytes', () => {
    // url max = 2048, mais on peut ruser via les autres champs (ref ≤ 512).
    // Pour atteindre > 4000, on combine url + ref + payload : impossible avec
    // les limites du validator. On simule ici en bypassant Zod : on
    // construit directement un ClickEvent avec ref énorme (la storage ne
    // re-valide pas la taille — seul le validator le fait).
    const big: ClickEvent = {
      ts: '2026-06-12T10:00:00.000Z',
      url: 'https://example.com/' + 'a'.repeat(2000),
      category: 'other',
      sourceId: 'src',
      recoId: null,
      ref: '/' + 'b'.repeat(2500),
    };
    expect(() => appendClick(big, CWD)).toThrow(/ligne JSONL trop longue/);
  });
});

describe('clicksDirFor', () => {
  it('compose un path dans tools/output/clicks/<source>', () => {
    expect(clicksDirFor('un-bon-moment', CWD)).toMatch(/clicks[/\\]un-bon-moment$/);
  });

  it('B-HIGH-7 normalise le slug en minuscules (anti-divergence FS Linux/Win)', () => {
    expect(clicksDirFor('UN-BON-MOMENT', CWD)).toBe(clicksDirFor('un-bon-moment', CWD));
  });
});

describe('dailyFileFor', () => {
  it('B-MED-19 throw clair si date invalide', () => {
    expect(() => dailyFileFor('src', new Date('not-a-date'), CWD)).toThrow(/date invalide/);
  });
});

describe('listDailyFiles', () => {
  it('renvoie [] si dossier source inexistant (B-MED-20 ENOENT atomique)', () => {
    expect(listDailyFiles('jamais-vu-cette-source', CWD)).toEqual([]);
  });
});
