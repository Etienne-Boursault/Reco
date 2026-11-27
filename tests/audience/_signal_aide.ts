/**
 * Doublures et montage partagés par `test_signal.test.ts` et
 * `test_signal_limites.test.ts` (le fichier de tests dépassait 500 lignes :
 * coupé par thème, tour 1 de revue, PR #224).
 */
import { EventEmitter } from 'node:events';
import { vi } from 'vitest';

// @ts-expect-error — module `.mjs` sans déclaration de types
import { creerSignal } from '../../src/lib/audience/signal.mjs';

export const ENTETES_OK = { host: 'unebonnere.co', origin: 'https://unebonnere.co' };

type Fausse = {
  req: any;
  res: any;
  /** La réponse est partie (ou ne partira jamais, pour un client coupé). */
  statut: () => number | undefined;
};

export function fabriquer(
  { corps = '{"chemin":"/a-propos"}', entetes = ENTETES_OK, methode = 'POST', flux = true } = {} as any,
): Fausse {
  const req: any = new EventEmitter();
  req.method = methode;
  req.url = '/api/vue';
  req.headers = { ...entetes };
  req.socket = { remoteAddress: '203.0.113.9' };
  const res: any = {
    code: undefined as number | undefined,
    entetes: {} as Record<string, string>,
    headersSent: false,
    writeHead(c: number, e: Record<string, string> = {}) {
      this.code = c;
      this.entetes = e;
      this.headersSent = true;
    },
    end: vi.fn(),
  };
  if (flux) {
    // Le corps arrive après que le gestionnaire s'est abonné au flux.
    queueMicrotask(() => {
      if (corps) req.emit('data', Buffer.from(corps));
      req.emit('end');
    });
  }
  return { req, res, statut: () => res.code };
}

export const AUCUN_JOURNAL = () => ({ warn: vi.fn(), error: vi.fn() });

export function monter(extra: Record<string, unknown> = {}) {
  const ecrit: any[] = [];
  const ecrire = vi.fn((ligne: any, source: string) => {
    ecrit.push({ ligne, source });
    return true;
  });
  const journal = AUCUN_JOURNAL();
  const signaler = creerSignal({
    ecrire,
    journal,
    sel: 'sel-de-test',
    horloge: () => Date.parse('2026-11-27T10:20:30Z'),
    ...extra,
  });
  return { signaler, ecrit, ecrire, journal };
}

export async function envoyer(signaler: any, options: any = {}) {
  const f = fabriquer(options);
  await signaler(f.req, f.res);
  return f;
}
