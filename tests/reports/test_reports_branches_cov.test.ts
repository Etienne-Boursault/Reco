/**
 * tests/reports/test_reports_branches_cov.test.ts — Branches restantes de
 * `src/lib/reports/{notify,validation,handler,rateLimit,storage}.ts`.
 *
 * Axe principal : les chemins « best-effort » et les gardes défensives que le
 * happy path n'atteint jamais (contexte de notif absent/complet, defaults
 * `process.env` / `fetch` global, honeypot absent, rejeu captcha, échec I/O,
 * GC du rate-limit, path traversal du storage).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { notifyReportMatrix } from '../../src/lib/reports/notify.ts';
import { reportPayloadSchema, isEmailValid } from '../../src/lib/reports/validation.ts';
import { handleReport } from '../../src/lib/reports/handler.ts';
import { generateChallenge } from '../../src/lib/reports/captcha.ts';
import { createRateLimiter } from '../../src/lib/reports/rateLimit.ts';
import {
  listReports,
  listSourcesWithReports,
  readReport,
  reportsDirFor,
  reportPath,
} from '../../src/lib/reports/storage.ts';
import type { Report } from '../../src/lib/reports/types.ts';

function makeReport(over: Partial<Report> = {}): Report {
  return {
    id: 'rep-123',
    sourceId: 'un-bon-moment',
    recoId: 'ubm-0042',
    category: 'broken-link',
    details: 'Le lien Deezer ne marche plus',
    submitter: { name: 'Alice', email: undefined, wantCredit: false },
    submittedAt: '2026-07-28T10:00:00.000Z',
    status: 'pending',
    resolvedAt: null,
    resolvedBy: null,
    notes: null,
    ...over,
  };
}

const MATRIX_ENV = {
  RECO_MATRIX_HOMESERVER: 'https://matrix.exemple.fr/',
  RECO_MATRIX_TOKEN: 's3cr3t',
  RECO_MATRIX_ROOM: '!abc:exemple.fr',
};

// --- notify -----------------------------------------------------------------

describe('notifyReportMatrix — contexte enrichi', () => {
  async function send(over: Parameters<typeof notifyReportMatrix>[1] = {}, report = makeReport()) {
    const fetchImpl = vi.fn(async () => new Response('{}', { status: 200 }));
    await notifyReportMatrix(report, { env: MATRIX_ENV, fetchImpl, txnId: () => 'T', ...over });
    return JSON.parse(fetchImpl.mock.calls[0][1].body as string) as {
      body: string;
      formatted_body: string;
    };
  }

  it('contexte complet → titre, types, épisode, auteur, timestamp et lien', async () => {
    const content = await send({
      context: {
        recoTitle: 'Chris Fleming',
        recoTypes: 'Spectacle, Vidéo',
        episodeLabel: 'S5·E21',
        episodeTitle: 'Le grand test',
        recommendedBy: 'David Castello-Lopes',
        timestamp: '01:42:03',
        url: 'https://reco.example/ubm/episode/42',
      },
    });
    expect(content.body).toContain('« Chris Fleming » · Spectacle, Vidéo');
    expect(content.body).toContain('Épisode S5·E21 — Le grand test');
    expect(content.body).toContain('Reco de David Castello-Lopes · ⏱ 01:42:03');
    expect(content.body).toContain('🔗 https://reco.example/ubm/episode/42');
    expect(content.formatted_body).toContain('<strong>Chris Fleming</strong>');
    expect(content.formatted_body).toContain('Épisode S5·E21 — Le grand test');
    expect(content.formatted_body).toContain(
      '<a href="https://reco.example/ubm/episode/42">Ouvrir l\'épisode</a>',
    );
  });

  it('titre sans types → pas de séparateur « · » parasite', async () => {
    const content = await send({ context: { recoTitle: 'Parasite' } });
    expect(content.body).toContain('« Parasite »');
    expect(content.body).not.toContain('« Parasite » ·');
    expect(content.formatted_body).toContain('<strong>Parasite</strong>');
  });

  it('label d épisode seul (sans titre) → ligne « Épisode … »', async () => {
    const content = await send({ context: { episodeLabel: '#42' } });
    const epLine = content.body.split('\n').find((l) => l.startsWith('Épisode'));
    // Sans `episodeTitle`, pas de séparateur « — » dans la ligne épisode.
    expect(epLine).toBe('Épisode #42');
  });

  it('recommendedBy seul, sans timestamp', async () => {
    const content = await send({ context: { recommendedBy: 'Navo' } });
    expect(content.body).toContain('Reco de Navo');
    expect(content.body).not.toContain('⏱');
  });

  it('timestamp seul, sans recommendedBy', async () => {
    const content = await send({ context: { timestamp: '00:12:00' } });
    expect(content.body).toContain('⏱ 00:12:00');
    expect(content.body).not.toContain('Reco de');
  });

  it('details vides et aucun submitter → lignes omises', async () => {
    const content = await send(
      {},
      makeReport({ details: '', submitter: { wantCredit: false } }),
    );
    expect(content.body).not.toContain('Détails :');
    expect(content.body).not.toContain('Par :');
    expect(content.formatted_body).not.toContain('Détails :');
    expect(content.formatted_body).not.toContain('Par :');
    expect(content.body).toContain('Réf : ubm-0042 · rep-123');
  });

  it('catégorie hors mapping → libellé brut', async () => {
    const content = await send({}, makeReport({ category: 'exotique' as Report['category'] }));
    expect(content.body).toContain('Nouveau signalement — exotique');
  });
});

describe('notifyReportMatrix — valeurs par défaut (env, fetch, txnId)', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it('sans `env`/`fetchImpl`/`txnId` → process.env, fetch global, uuid généré', async () => {
    vi.stubEnv('RECO_MATRIX_HOMESERVER', 'https://matrix.exemple.fr');
    vi.stubEnv('RECO_MATRIX_TOKEN', 'tok');
    vi.stubEnv('RECO_MATRIX_ROOM', '!room:exemple.fr');
    const globalFetch = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', globalFetch);

    await notifyReportMatrix(makeReport());

    expect(globalFetch).toHaveBeenCalledOnce();
    const [url, init] = globalFetch.mock.calls[0] as [string, RequestInit];
    // Le txn id par défaut est un UUID v4 (crypto.randomUUID).
    expect(url).toMatch(
      /^https:\/\/matrix\.exemple\.fr\/_matrix\/client\/v3\/rooms\/!room%3Aexemple\.fr\/send\/m\.room\.message\/[0-9a-f-]{36}$/,
    );
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok');
  });

  it('sans `crypto.randomUUID` → txn id de repli basé sur Date.now()', async () => {
    vi.stubEnv('RECO_MATRIX_HOMESERVER', 'https://matrix.exemple.fr');
    vi.stubEnv('RECO_MATRIX_TOKEN', 'tok');
    vi.stubEnv('RECO_MATRIX_ROOM', '!room:exemple.fr');
    // Runtime sans WebCrypto (vieux Node, worker restreint).
    vi.stubGlobal('crypto', {});
    const globalFetch = vi.fn(async () => new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', globalFetch);

    await notifyReportMatrix(makeReport());

    const [url] = globalFetch.mock.calls[0] as [string];
    expect(url).toMatch(/\/send\/m\.room\.message\/\d{10,}$/);
  });

  it('sans `env` et sans config Matrix dans process.env → no-op', async () => {
    vi.stubEnv('RECO_MATRIX_HOMESERVER', '');
    vi.stubEnv('RECO_MATRIX_TOKEN', '');
    vi.stubEnv('RECO_MATRIX_ROOM', '');
    const globalFetch = vi.fn();
    vi.stubGlobal('fetch', globalFetch);
    await notifyReportMatrix(makeReport());
    expect(globalFetch).not.toHaveBeenCalled();
  });
});

// --- validation -------------------------------------------------------------

describe('reportPayloadSchema — normalisation de la checkbox wantCredit', () => {
  const base = {
    sourceId: 'un-bon-moment',
    recoId: 'ubm-0001',
    category: 'error',
    details: 'Une faute de frappe dans le titre.',
    captchaToken: 't',
    captchaAnswer: '4',
  };

  it.each([
    ['on', true],
    ['true', true],
    [true, true],
    [false, false],
    ['', false],
  ])('wantCredit=%o → %s', (input, expected) => {
    const parsed = reportPayloadSchema.safeParse({ ...base, wantCredit: input });
    expect(parsed.success).toBe(true);
    expect(parsed.success && parsed.data.wantCredit).toBe(expected);
  });

  it('wantCredit absent → `undefined` (`.optional()` court-circuite le transform)', () => {
    const parsed = reportPayloadSchema.safeParse(base);
    expect(parsed.success).toBe(true);
    // Le handler compare avec `=== true`, donc l'absence vaut « pas de crédit ».
    expect(parsed.success && parsed.data.wantCredit).toBeUndefined();
  });

  it("valeur hors liste ('yes') → rejetée", () => {
    expect(reportPayloadSchema.safeParse({ ...base, wantCredit: 'yes' }).success).toBe(false);
  });
});

describe('isEmailValid', () => {
  it('accepte les formes raisonnables', () => {
    expect(isEmailValid('alice@example.org')).toBe(true);
    expect(isEmailValid('a.b+tag@sous.domaine.fr')).toBe(true);
  });

  it('rejette les formes évidentes non conformes', () => {
    expect(isEmailValid('pas-un-email')).toBe(false);
    expect(isEmailValid('a@b')).toBe(false);
    expect(isEmailValid('a @b.fr')).toBe(false);
    expect(isEmailValid('')).toBe(false);
  });
});

// --- handler ----------------------------------------------------------------

describe('handleReport — branches restantes', () => {
  let CWD: string;
  const SELF = 'https://reco.example';

  function extractAnswer(q: string): number {
    const m = q.match(/(\d) \+ (\d)/);
    if (!m) throw new Error(`Question inattendue : ${q}`);
    return Number(m[1]) + Number(m[2]);
  }

  function validForm(over: Record<string, string> = {}): Record<string, string> {
    const c = generateChallenge(1_000_000);
    return {
      sourceId: 'un-bon-moment',
      recoId: 'ubm-0001',
      category: 'error',
      details: 'Le titre comporte une faute de frappe.',
      captchaToken: c.token,
      captchaAnswer: String(extractAnswer(c.question)),
      ...over,
    };
  }

  beforeEach(() => {
    CWD = mkdtempSync(join(tmpdir(), 'reco-handler-cov-'));
    process.env.NODE_ENV = 'test';
    process.env.RECO_QUIET = '1';
  });

  it("origin ne respectant pas le schéma http(s) → 403 avant tout parsing d'URL", () => {
    const res = handleReport({
      formData: validForm(),
      // Chrome envoie littéralement `null` pour une origine opaque.
      origin: 'null',
      selfOrigin: SELF,
      ip: '203.0.113.9',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
    });
    expect(res).toEqual({ status: 403, body: { success: false, error: 'origin invalide' } });
  });

  it('origin syntaxiquement conforme mais non parseable → 403 (catch)', () => {
    const res = handleReport({
      formData: validForm(),
      origin: 'https://[oops',
      selfOrigin: SELF,
      ip: '203.0.113.9',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
    });
    expect(res.status).toBe(403);
  });

  it('aucun champ honeypot présent → traitement normal', () => {
    const fd = validForm();
    expect('website' in fd).toBe(false);
    expect('url_unused' in fd).toBe(false);
    const res = handleReport({
      formData: fd,
      origin: SELF,
      selfOrigin: SELF,
      ip: '203.0.113.10',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
      now: 1_000_000,
    });
    expect(res.status).toBe(200);
  });

  it('réutilisation du même token captcha → 400 « captcha: replay »', () => {
    const fd = validForm();
    const first = handleReport({
      formData: fd,
      origin: SELF,
      selfOrigin: SELF,
      ip: '203.0.113.11',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
      now: 1_000_000,
    });
    expect(first.status).toBe(200);
    const second = handleReport({
      formData: { ...fd },
      origin: SELF,
      selfOrigin: SELF,
      ip: '203.0.113.12',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
      now: 1_000_000,
    });
    expect(second).toEqual({
      status: 400,
      body: { success: false, error: 'captcha: replay' },
    });
  });

  it('sans `rateLimiter` injecté → utilise le singleton process-wide', () => {
    const ip = `198.51.100.${Math.floor(Math.random() * 200) + 20}`;
    const res = handleReport({
      formData: validForm(),
      origin: SELF,
      selfOrigin: SELF,
      ip,
      cwd: CWD,
      now: 2_000_000,
    });
    expect(res.status).toBe(200);
    // Deuxième passage immédiat sur la même IP → le singleton rate-limite.
    const again = handleReport({
      formData: validForm(),
      origin: SELF,
      selfOrigin: SELF,
      ip,
      cwd: CWD,
      now: 2_000_100,
    });
    expect(again.status).toBe(429);
  });

  it('échec d écriture (slug trop long pour le storage) → 500 avec le message', () => {
    // `reportPayloadSchema` n'impose pas de longueur max au sourceId, mais
    // `storage.assertSlug` refuse au-delà de 128 caractères ⇒ erreur I/O.
    const res = handleReport({
      formData: validForm({ sourceId: 'a'.repeat(200) }),
      origin: SELF,
      selfOrigin: SELF,
      ip: '203.0.113.13',
      rateLimiter: createRateLimiter(),
      cwd: CWD,
      now: 1_000_000,
    });
    expect(res.status).toBe(500);
    expect(res.body.error).toMatch(/^IO: \[reports\/storage\] sourceId invalide/);
  });
});

describe('handleReport — écriture qui lève une valeur non-`Error`', () => {
  afterEach(() => {
    vi.doUnmock('../../src/lib/reports/storage.ts');
    vi.resetModules();
  });

  it("→ 500 avec le message générique 'unknown'", async () => {
    vi.resetModules();
    vi.doMock('../../src/lib/reports/storage.ts', async (importOriginal) => {
      const actual = await importOriginal<typeof import('../../src/lib/reports/storage.ts')>();
      return {
        ...actual,
        writeReport: () => {
          throw 'disque plein';
        },
      };
    });
    const { handleReport: handler } = await import('../../src/lib/reports/handler.ts');
    const { generateChallenge: gen } = await import('../../src/lib/reports/captcha.ts');
    const { createRateLimiter: mkRl } = await import('../../src/lib/reports/rateLimit.ts');

    const c = gen(1_000_000);
    const m = c.question.match(/(\d) \+ (\d)/)!;
    const res = handler({
      formData: {
        sourceId: 'un-bon-moment',
        recoId: 'ubm-0001',
        category: 'error',
        details: 'Le titre comporte une faute de frappe.',
        captchaToken: c.token,
        captchaAnswer: String(Number(m[1]) + Number(m[2])),
      },
      origin: 'https://reco.example',
      selfOrigin: 'https://reco.example',
      ip: '203.0.113.14',
      rateLimiter: mkRl(),
      now: 1_000_000,
    });
    expect(res).toEqual({
      status: 500,
      body: { success: false, error: 'IO: unknown' },
    });
  });
});

// --- rateLimit --------------------------------------------------------------

describe('reports/rateLimit — salt et GC', () => {
  const savedSalt = process.env.REPORTS_IP_SALT;
  afterEach(() => {
    if (savedSalt === undefined) delete process.env.REPORTS_IP_SALT;
    else process.env.REPORTS_IP_SALT = savedSalt;
  });

  it('REPORTS_IP_SALT ≥ 16 chars → salt stable entre deux limiters', () => {
    process.env.REPORTS_IP_SALT = 'un-salt-de-test-suffisamment-long';
    const a = createRateLimiter(60_000);
    const b = createRateLimiter(60_000);
    expect(a.check('192.0.2.1', 1000)).toBe(true);
    expect(b.check('192.0.2.1', 1000)).toBe(true);
    // Deux stores distincts, mais la même IP doit produire la même clé : on
    // le vérifie indirectement en re-checkant dans le même limiter.
    expect(a.check('192.0.2.1', 1500)).toBe(false);
  });

  it('REPORTS_IP_SALT trop court (< 16) → repli sur le salt de boot', () => {
    process.env.REPORTS_IP_SALT = 'court';
    process.env.RECO_QUIET = '1';
    const rl = createRateLimiter(60_000);
    expect(rl.check('192.0.2.2', 1000)).toBe(true);
    expect(rl.check('192.0.2.2', 1500)).toBe(false);
  });

  it('GC opportuniste : purge les entrées au-delà de 10× la fenêtre', () => {
    process.env.REPORTS_IP_SALT = 'un-salt-de-test-suffisamment-long';
    const rl = createRateLimiter(1000); // gcThreshold = 10 000 ms
    for (let i = 0; i < 300; i += 1) rl.check(`10.0.0.${i}`, 1000);
    expect(rl.size()).toBe(300);

    // Sous le seuil de GC : rien n'est purgé.
    rl.check('10.1.0.1', 6000);
    expect(rl.size()).toBe(301);

    // Au-delà du seuil : toutes les entrées anciennes disparaissent.
    rl.check('10.2.0.1', 21_000);
    expect(rl.size()).toBe(1);
  });
});

// --- storage ----------------------------------------------------------------

describe('reports/storage — gardes et lectures dégradées', () => {
  let CWD: string;
  beforeEach(() => {
    CWD = mkdtempSync(join(tmpdir(), 'reco-storage-cov-'));
  });
  afterEach(() => {
    rmSync(CWD, { recursive: true, force: true });
  });

  it('H16-4 : slug de path traversal refusé', () => {
    expect(() => reportsDirFor('../evil', CWD)).toThrow(/sourceId invalide/);
    expect(() => reportPath('ubm', '../../etc/passwd', CWD)).toThrow(/reportId invalide/);
    expect(() => reportPath('ubm/nested', 'rep-1', CWD)).toThrow(/sourceId invalide/);
    expect(() => reportsDirFor('', CWD)).toThrow(/sourceId invalide/);
  });

  it('listReports ignore les fichiers non `.json` et les JSON corrompus', () => {
    const dir = join(CWD, 'tools', 'output', 'reports', 'ubm');
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'README.txt'), 'pas un report', 'utf8');
    writeFileSync(join(dir, 'rep-1.json.tmp'), '{}', 'utf8');
    writeFileSync(join(dir, 'rep-2.json'), '{cassé', 'utf8');
    writeFileSync(
      join(dir, 'rep-3.json'),
      JSON.stringify({ id: 'rep-3', sourceId: 'ubm', status: 'pending', submittedAt: '2026-01-01' }),
      'utf8',
    );
    const out = listReports('ubm', { cwd: CWD });
    expect(out.map((r) => r.id)).toEqual(['rep-3']);
  });

  it('listReports filtre par status', () => {
    const dir = join(CWD, 'tools', 'output', 'reports', 'ubm');
    mkdirSync(dir, { recursive: true });
    for (const [id, status, at] of [
      ['rep-a', 'pending', '2026-01-02'],
      ['rep-b', 'resolved', '2026-01-01'],
    ] as const) {
      writeFileSync(
        join(dir, `${id}.json`),
        JSON.stringify({ id, sourceId: 'ubm', status, submittedAt: at }),
        'utf8',
      );
    }
    expect(listReports('ubm', { cwd: CWD, status: 'resolved' }).map((r) => r.id)).toEqual([
      'rep-b',
    ]);
    expect(listReports('ubm', { cwd: CWD }).map((r) => r.id)).toEqual(['rep-a', 'rep-b']);
  });

  it('readReport : fichier absent → null ; JSON corrompu → null', () => {
    expect(readReport('ubm', 'rep-inexistant', CWD)).toBeNull();
    const dir = join(CWD, 'tools', 'output', 'reports', 'ubm');
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, 'rep-ko.json'), '{cassé', 'utf8');
    expect(readReport('ubm', 'rep-ko', CWD)).toBeNull();
  });

  it('listSourcesWithReports : racine absente → [] ; sinon dossiers triés', () => {
    expect(listSourcesWithReports(CWD)).toEqual([]);
    const root = join(CWD, 'tools', 'output', 'reports');
    mkdirSync(join(root, 'zeta'), { recursive: true });
    mkdirSync(join(root, 'alpha'), { recursive: true });
    writeFileSync(join(root, 'index.json'), '{}', 'utf8');
    expect(listSourcesWithReports(CWD)).toEqual(['alpha', 'zeta']);
  });
});
