/**
 * src/pages/api/click.ts — Endpoint tracking clics sortants.
 *
 * Deux entrées :
 *  - POST JSON : `{url, category, sourceId, recoId?, ref?, bot_trap?}`,
 *    appelé via `navigator.sendBeacon` ou `fetch(keepalive:true)` depuis
 *    le script global injecté dans Layout.astro.
 *  - GET pixel : `?url=…&cat=…&src=…&reco=…&ref=…`, fallback no-JS, renvoie
 *    un GIF transparent 1×1 (43 bytes). Sert aussi pour les browsers très
 *    anciens sans `sendBeacon`.
 *
 * Privacy (ADR 0046) : `Sec-GPC: 1` → 204 silencieux, pas de cookie, IP
 * hashée+saltée pour rate-limit uniquement (jamais persistée).
 *
 * Sécurité (CR senior) :
 *  - H25-3 : POST exige Origin strict (Referer NON accepté pour CSRF).
 *  - H25-6 : GET pixel — Referer toléré ; si origin échoue → pixel renvoyé
 *    sans écriture (UX consistante, pas de tracking).
 *  - M25-16 : log `console.warn` quand une validation GET pixel échoue.
 *  - M25-17 : `TRUSTED_PROXIES` parsé module-scope (perf, lisibilité).
 *  - R-P3-21 : log si URL > 2048 chars (observabilité).
 *  - R-P3-22 : compteurs in-memory par status, exposés via getClickMetrics().
 *
 * SSR opt-in : ce fichier requiert `output: 'hybrid'` + adapter. En
 * `output: 'static'` (default kit), le tracking est désactivé (le client
 * voit le beacon échouer silencieusement — graceful degradation).
 */

import type { APIRoute } from 'astro';
import { handleClick } from '../../lib/tracking/handler.js';
import { recordClickStatus } from '../../lib/tracking/metrics.js';
import { CLICK_LIMITS } from '../../lib/tracking/types.js';

/**
 * Endpoint SSR strict. En `output: 'hybrid'` + adapter installé, le forker
 * DOIT décommenter le marqueur ci-dessous, sans quoi Astro tente de
 * pré-rendre la route et les beacons /api/click 404 silencieusement.
 *
 * Garder commenté tant que le kit reste en `output: 'static'` (default) :
 * `prerender = false` y casserait le build avec `NoAdapterInstalled`.
 *
 * Cf. ADR 0046 + fork-guide.md (section TRACKING).
 * Issue : CR senior C25-1.
 */
// export const prerender = false;

// B-LOW-15 : ces constantes sont déjà privées (module-local, pas export).
// On retire le préfixe `_` qui était un faux signal de privacy : la vraie
// portée privée vient de l'absence d'`export`.
// GIF 1×1 transparent — 43 bytes encodés base64 (header + LZW + trailer).
const PIXEL_GIF_BASE64 = 'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';
const PIXEL_GIF = Buffer.from(PIXEL_GIF_BASE64, 'base64');
// B-NIT-12 : on précalcule la taille en bytes (Buffer.byteLength sur un
// Buffer == .length, mais on documente clairement l'intention "size sur
// le wire" plutôt qu'un cast `String(.length)` ambigu).
const PIXEL_GIF_BYTE_LENGTH = Buffer.byteLength(PIXEL_GIF);

// B-HIGH-1 : cap de la taille du body POST (8 KiB) — au-delà on rejette
// 413 sans même tenter de lire le body. Évite qu'un attaquant remplisse
// la mémoire serveur via un Content-Length énorme suivi d'un stream lent.
const POST_BODY_MAX_BYTES = 8 * 1024;

// M25-17 : TRUSTED_PROXIES parsé une fois au load du module.
const TRUSTED_PROXIES: ReadonlySet<string> = new Set(
  (process.env.TRUSTED_PROXIES ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean),
);

function tryClientAddress(ctx: { clientAddress?: string }): string | null {
  // Astro 5 throws if `clientAddress` is accessed in a prerendered route.
  // Access via property read inside try/catch to dodge eager evaluation.
  try {
    const ip = ctx.clientAddress;
    return ip ?? null;
  } catch {
    return null;
  }
}

/**
 * Extrait l'IP cliente en respectant la chaîne de proxies.
 * Retourne `null` si l'IP réelle est indéterminable — le caller doit
 * alors short-circuit (204 silencieux) au lieu de hasher `0.0.0.0`,
 * qui collapserait tous les clients no-IP sur le même bucket de
 * rate-limit et créerait un DoS auto-infligé (CR senior C25-2).
 *
 * M25-18 : si `clientAddress ∈ trustedProxies` mais que `x-forwarded-for`
 * est vide → fallback `clientAddress` (au lieu de null), car le proxy est
 * trusted et c'est probablement l'IP directe utile (cas health-check
 * interne ou tests). Documenté ADR.
 */
function extractIp(request: Request, clientAddress: string | null): string | null {
  const xff = request.headers.get('x-forwarded-for');
  if (clientAddress && TRUSTED_PROXIES.has(clientAddress)) {
    if (xff) {
      const first = xff.split(',')[0].trim();
      return first || clientAddress;
    }
    return clientAddress;
  }
  return clientAddress ?? null;
}

function selfOriginOf(request: Request): string {
  const url = new URL(request.url);
  return `${url.protocol}//${url.host}`;
}

function sendResponse(status: number, body: unknown): Response {
  recordClickStatus(status);
  if (status === 204) return new Response(null, { status });
  return new Response(JSON.stringify(body ?? {}), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
  });
}

export const POST: APIRoute = async (ctx) => {
  const { request } = ctx;

  // B-HIGH-1 : cap Content-Length AVANT lecture pour ne pas allouer un body
  // énorme côté serveur. Si l'en-tête est absent on laisse passer (sendBeacon
  // ne le remplit pas toujours), mais on cap quand même le buffer effectif
  // (text()/json() seront bornés par la runtime, ici on protège le hot path).
  const contentLengthRaw = request.headers.get('content-length');
  if (contentLengthRaw !== null) {
    const contentLength = Number.parseInt(contentLengthRaw, 10);
    if (Number.isFinite(contentLength) && contentLength > POST_BODY_MAX_BYTES) {
      return sendResponse(413, { error: 'body trop volumineux' });
    }
  }

  let payload: Record<string, unknown> = {};
  try {
    const ct = request.headers.get('content-type') ?? '';
    if (ct.includes('application/json')) {
      payload = (await request.json()) as Record<string, unknown>;
    } else {
      // sendBeacon envoie text/plain par défaut. On parse en JSON quand même.
      const txt = await request.text();
      // Garde-fou défensif : même si Content-Length était absent, on rejette
      // si le body lu dépasse la borne (cas TransferEncoding: chunked).
      if (Buffer.byteLength(txt, 'utf8') > POST_BODY_MAX_BYTES) {
        return sendResponse(413, { error: 'body trop volumineux' });
      }
      if (txt) payload = JSON.parse(txt) as Record<string, unknown>;
    }
  } catch {
    return sendResponse(400, { error: 'json invalide' });
  }

  // R-P3-21 : log si URL > 2048 chars (observabilité — sera rejetée par Zod).
  if (typeof payload.url === 'string' && payload.url.length > CLICK_LIMITS.urlMax) {
    // eslint-disable-next-line no-console
    console.warn(
      `[tracking/click POST] url > ${CLICK_LIMITS.urlMax} chars (${payload.url.length}) — rejected`,
    );
  }

  const directIp = tryClientAddress(ctx);
  const ip = extractIp(request, directIp);
  if (ip === null) {
    // IP indéterminable (proxy non trusted, env serverless mal configurée) :
    // on ne hashe pas `0.0.0.0` (cf. extractIp), on retourne 204 silencieux.
    return sendResponse(204, null);
  }
  const origin = request.headers.get('origin');
  const referer = request.headers.get('referer');
  const secGpc = request.headers.get('sec-gpc');

  const result = handleClick({
    payload,
    origin,
    referer,
    selfOrigin: selfOriginOf(request),
    ip,
    secGpc,
    // H25-3 : POST NE doit PAS accepter Referer comme fallback CSRF.
    allowReferer: false,
  });

  return sendResponse(result.status, result.body);
};

export const GET: APIRoute = (ctx) => {
  const { request, url } = ctx;
  // Pixel fallback : on lit les paramètres query et on délègue au handler.
  const payload: Record<string, unknown> = {
    url: url.searchParams.get('url') ?? '',
    category: url.searchParams.get('cat') ?? '',
    sourceId: url.searchParams.get('src') ?? '',
  };
  const reco = url.searchParams.get('reco');
  if (reco) payload.recoId = reco;
  const ref = url.searchParams.get('ref');
  if (ref) payload.ref = ref;
  const trap = url.searchParams.get('bot_trap');
  if (trap) payload.bot_trap = trap;

  if (typeof payload.url === 'string' && payload.url.length > CLICK_LIMITS.urlMax) {
    // eslint-disable-next-line no-console
    console.warn(
      `[tracking/click GET] url > ${CLICK_LIMITS.urlMax} chars (${payload.url.length}) — rejected`,
    );
  }

  const directIp = tryClientAddress(ctx);
  const ip = extractIp(request, directIp);
  const origin = request.headers.get('origin');
  const referer = request.headers.get('referer');
  const secGpc = request.headers.get('sec-gpc');

  // H25-6 : sur GET pixel, on délègue au handler avec allowReferer=true.
  // Si origin/CSRF échoue → handler renvoie 403 ; on enregistre la métrique
  // mais on RETURN tout de même le GIF (UX consistante, pas de tracking).
  if (ip !== null) {
    const result = handleClick({
      payload,
      origin,
      referer,
      selfOrigin: selfOriginOf(request),
      ip,
      secGpc,
      allowReferer: true,
    });
    recordClickStatus(result.status);
    if (result.status === 400 && result.body) {
      // M25-16 : observabilité des payloads invalides côté pixel.
      // eslint-disable-next-line no-console
      console.warn(`[tracking/click GET] validation error: ${result.body.error}`);
    }
  } else {
    recordClickStatus(204);
  }

  // Pixel GET : toujours retourner le GIF même IP indéterminable, pour ne pas
  // casser l'`<img>` côté client.
  return new Response(PIXEL_GIF, {
    status: 200,
    headers: {
      'Content-Type': 'image/gif',
      'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
      // B-NIT-12 : Buffer.byteLength précalculé module-scope (intention claire,
      // pas de re-conversion à chaque requête).
      'Content-Length': String(PIXEL_GIF_BYTE_LENGTH),
    },
  });
};
