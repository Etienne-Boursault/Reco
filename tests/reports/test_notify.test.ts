import { describe, it, expect, vi } from 'vitest';
import { notifyReportMatrix } from '../../src/lib/reports/notify.ts';
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

const ENV = {
  RECO_MATRIX_HOMESERVER: 'https://matrix.exemple.fr/',
  RECO_MATRIX_TOKEN: 's3cr3t',
  RECO_MATRIX_ROOM: '!abc:exemple.fr',
};

describe('notifyReportMatrix', () => {
  it('no-op quand la config Matrix est absente', async () => {
    const fetchImpl = vi.fn();
    await notifyReportMatrix(makeReport(), { env: {}, fetchImpl });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it('PUT sur l endpoint room-send avec Bearer + contenu m.notice', async () => {
    const fetchImpl = vi.fn(async () => new Response('{}', { status: 200 }));
    await notifyReportMatrix(makeReport(), { env: ENV, fetchImpl, txnId: () => 'TXN1' });

    expect(fetchImpl).toHaveBeenCalledOnce();
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe(
      'https://matrix.exemple.fr/_matrix/client/v3/rooms/!abc%3Aexemple.fr/send/m.room.message/TXN1',
    );
    expect(init.method).toBe('PUT');
    expect(init.headers.Authorization).toBe('Bearer s3cr3t');
    const content = JSON.parse(init.body);
    expect(content.msgtype).toBe('m.notice');
    expect(content.body).toContain('ubm-0042');
    expect(content.body).toContain('Lien mort');
    expect(content.formatted_body).toContain('<strong>');
  });

  it('ne throw jamais si le fetch échoue', async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error('network down');
    });
    await expect(
      notifyReportMatrix(makeReport(), { env: ENV, fetchImpl }),
    ).resolves.toBeUndefined();
  });

  it('échappe le HTML des champs (anti-injection)', async () => {
    const fetchImpl = vi.fn(async () => new Response('{}', { status: 200 }));
    await notifyReportMatrix(
      makeReport({ details: 'casse <script>alert(1)</script>' }),
      { env: ENV, fetchImpl, txnId: () => 'T' },
    );
    const content = JSON.parse(fetchImpl.mock.calls[0][1].body);
    expect(content.formatted_body).toContain('&lt;script&gt;');
    expect(content.formatted_body).not.toContain('<script>');
  });
});
