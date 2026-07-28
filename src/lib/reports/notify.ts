/**
 * src/lib/reports/notify.ts — Ping Matrix sur nouveau signalement.
 *
 * Best-effort : lit la config depuis l'env (RECO_MATRIX_HOMESERVER /
 * RECO_MATRIX_TOKEN / RECO_MATRIX_ROOM). No-op si non configuré. Ne LÈVE
 * JAMAIS : le signalement est déjà écrit sur disque, une notif ratée ne doit
 * pas faire échouer la soumission.
 *
 * `env` et `fetchImpl` sont injectables (tests). En prod (SSR Node), on lit
 * `process.env` et le `fetch` global.
 */
import type { Report } from './types.js';

const CATEGORY_LABELS: Record<string, string> = {
  error: 'Erreur',
  inappropriate: 'Contenu inapproprié',
  suggestion: 'Suggestion',
  'broken-link': 'Lien mort',
};

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export interface NotifyOptions {
  env?: Record<string, string | undefined>;
  fetchImpl?: typeof fetch;
  /** Générateur de transaction id (tests). */
  txnId?: () => string;
}

export async function notifyReportMatrix(report: Report, opts: NotifyOptions = {}): Promise<void> {
  const env = opts.env ?? process.env;
  const hs = env.RECO_MATRIX_HOMESERVER;
  const token = env.RECO_MATRIX_TOKEN;
  const room = env.RECO_MATRIX_ROOM;
  if (!hs || !token || !room) return; // non configuré → silencieux

  const cat = CATEGORY_LABELS[report.category] ?? report.category;
  const who = [report.submitter?.name, report.submitter?.email].filter(Boolean).join(' · ');

  const bodyLines = [
    `🚩 Nouveau signalement — ${cat}`,
    `Œuvre : ${report.recoId} (source ${report.sourceId})`,
    report.details ? `Détails : ${report.details}` : '',
    who ? `Par : ${who}` : '',
    `id : ${report.id}`,
  ].filter(Boolean);

  const htmlLines = [
    `🚩 <strong>Nouveau signalement — ${esc(cat)}</strong>`,
    `Œuvre : <code>${esc(report.recoId)}</code> (source ${esc(report.sourceId)})`,
    report.details ? `Détails : ${esc(report.details)}` : '',
    who ? `Par : ${esc(who)}` : '',
  ].filter(Boolean);

  const content = {
    msgtype: 'm.notice',
    body: bodyLines.join('\n'),
    format: 'org.matrix.custom.html',
    formatted_body: htmlLines.join('<br>'),
  };

  const txn = (opts.txnId ?? (() => globalThis.crypto?.randomUUID?.() ?? String(Date.now())))();
  const base = hs.replace(/\/+$/, '');
  const url = `${base}/_matrix/client/v3/rooms/${encodeURIComponent(room)}/send/m.room.message/${txn}`;
  const doFetch = opts.fetchImpl ?? fetch;

  try {
    await doFetch(url, {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(content),
    });
  } catch {
    // Best-effort : on avale l'erreur (le report est déjà persisté).
  }
}
