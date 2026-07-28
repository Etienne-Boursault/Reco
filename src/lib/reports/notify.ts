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

/**
 * Contexte enrichi (résolu côté endpoint depuis les collections) pour rendre
 * le ping lisible : titre de l'œuvre, épisode, lien direct… Tous optionnels —
 * si absents, le message retombe sur l'identifiant brut de la reco.
 */
export interface ReportNotifyContext {
  /** Titre de l'œuvre recommandée (ex. « Chris Fleming »). */
  recoTitle?: string;
  /** Types formatés (ex. « Film, Série »). */
  recoTypes?: string;
  /** Libellé d'épisode (ex. « S5·E21 » / « #42 »). */
  episodeLabel?: string;
  /** Titre de l'épisode. */
  episodeTitle?: string;
  /** Qui a recommandé (ex. « David Castello-Lopes »). */
  recommendedBy?: string;
  /** Position dans l'épisode (ex. « 01:42:03 »). */
  timestamp?: string;
  /** Lien direct vers l'épisode qui contient la reco. */
  url?: string;
}

export interface NotifyOptions {
  env?: Record<string, string | undefined>;
  fetchImpl?: typeof fetch;
  /** Générateur de transaction id (tests). */
  txnId?: () => string;
  /** Contexte enrichi (titre, épisode, lien) résolu par l'appelant. */
  context?: ReportNotifyContext;
}

export async function notifyReportMatrix(report: Report, opts: NotifyOptions = {}): Promise<void> {
  const env = opts.env ?? process.env;
  const hs = env.RECO_MATRIX_HOMESERVER;
  const token = env.RECO_MATRIX_TOKEN;
  const room = env.RECO_MATRIX_ROOM;
  if (!hs || !token || !room) return; // non configuré → silencieux

  const cat = CATEGORY_LABELS[report.category] ?? report.category;
  const who = [report.submitter?.name, report.submitter?.email].filter(Boolean).join(' · ');
  const ctx = opts.context ?? {};

  // Ligne « œuvre » : titre + types si résolus, sinon rien (l'id reste en réf).
  const titleLine = ctx.recoTitle
    ? `« ${ctx.recoTitle} »${ctx.recoTypes ? ` · ${ctx.recoTypes}` : ''}`
    : '';
  // Ligne « épisode » : « Épisode S5·E21 — Titre » (selon ce qui est connu).
  const epParts = [ctx.episodeLabel, ctx.episodeTitle].filter(Boolean).join(' — ');
  const epLine = epParts ? `Épisode ${epParts}` : '';
  // Ligne « contexte reco » : « Reco de X · ⏱ 01:42:03 ».
  const metaLine = [
    ctx.recommendedBy ? `Reco de ${ctx.recommendedBy}` : '',
    ctx.timestamp ? `⏱ ${ctx.timestamp}` : '',
  ]
    .filter(Boolean)
    .join(' · ');

  const bodyLines = [
    `🚩 Nouveau signalement — ${cat}`,
    titleLine,
    epLine,
    metaLine,
    report.details ? `Détails : ${report.details}` : '',
    who ? `Par : ${who}` : '',
    ctx.url ? `🔗 ${ctx.url}` : '',
    // Réf technique conservée (id œuvre + id signalement) pour la traçabilité.
    `Réf : ${report.recoId} · ${report.id}`,
  ].filter(Boolean);

  const htmlLines = [
    `🚩 <strong>Nouveau signalement — ${esc(cat)}</strong>`,
    titleLine
      ? `<strong>${esc(ctx.recoTitle ?? '')}</strong>${ctx.recoTypes ? ` · ${esc(ctx.recoTypes)}` : ''}`
      : '',
    epLine ? `Épisode ${esc(epParts)}` : '',
    metaLine ? esc(metaLine) : '',
    report.details ? `Détails : ${esc(report.details)}` : '',
    who ? `Par : ${esc(who)}` : '',
    ctx.url ? `🔗 <a href="${esc(ctx.url)}">Ouvrir l'épisode</a>` : '',
    `Réf : <code>${esc(report.recoId)}</code> · ${esc(report.id)}`,
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
