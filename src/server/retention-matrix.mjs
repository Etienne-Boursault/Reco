/**
 * Efface, au bout de 12 mois, les notifications Matrix de signalement.
 *
 * Chaque signalement envoie une notification au salon de l'éditeur
 * (`src/lib/reports/notify.ts`), avec le nom et l'e-mail laissés par le
 * visiteur. `anonymiserSignalements` les efface du fichier au bout de 12 mois ;
 * sans cette purge, ils restaient indéfiniment dans l'historique du salon, en
 * contradiction avec /mentions-legales.
 *
 * Le bot parcourt l'historique du salon depuis le DÉBUT (le plus ancien
 * d'abord) et « rédige » (efface le contenu de) ses propres notifications de
 * signalement plus anciennes que la borne. Il s'arrête au premier message plus
 * récent. Un message déjà rédigé n'a plus de contenu : il n'est pas repris.
 * Un bot peut toujours rédiger ses propres messages, sans droit particulier.
 *
 * Sans `RECO_MATRIX_*` (déploiement sans notifications) : rien à faire.
 */
import { MOIS_COORDONNEES, borne } from './retention.mjs';

export const ENTETE_SIGNALEMENT = '🚩 Nouveau signalement';
const PAGES_MAX = 100;

/** Une notification de signalement qui porte encore des coordonnées. */
export function estNotificationAEffacer(contenu) {
  const corps = contenu?.body;
  return typeof corps === 'string' && corps.startsWith(ENTETE_SIGNALEMENT) && corps.includes('\nPar : ');
}

async function lire(fetchImpl, url, init) {
  const reponse = await fetchImpl(url, init);
  if (!reponse.ok) throw new Error(`Matrix : HTTP ${reponse.status} sur ${new URL(url).pathname}`);
  return reponse.json();
}

export async function purgerNotificationsMatrix({
  env = process.env, fetchImpl = fetch, maintenant = new Date(), mois = MOIS_COORDONNEES,
} = {}) {
  const { RECO_MATRIX_HOMESERVER: hs, RECO_MATRIX_TOKEN: jeton, RECO_MATRIX_ROOM: salon } = env;
  if (!hs || !jeton || !salon) return 0;
  const base = `${hs.replace(/\/+$/, '')}/_matrix/client/v3`;
  const entetes = { Authorization: `Bearer ${jeton}` };
  const limite = new Date(`${borne(maintenant, mois)}T00:00:00Z`).getTime();
  const { user_id: bot } = await lire(fetchImpl, `${base}/account/whoami`, { headers: entetes });
  const filtre = JSON.stringify({ types: ['m.room.message'], senders: [bot] });
  const racineSalon = `${base}/rooms/${encodeURIComponent(salon)}`;

  let effaces = 0;
  let depuis;
  for (let page = 0; page < PAGES_MAX; page += 1) {
    const params = new URLSearchParams({ dir: 'f', limit: '100', filter: filtre });
    if (depuis) params.set('from', depuis);
    const corps = await lire(fetchImpl, `${racineSalon}/messages?${params}`, { headers: entetes });
    const evenements = corps.chunk ?? [];
    for (const evt of evenements) {
      if (evt.origin_server_ts >= limite) return effaces; // le reste est plus récent
      if (!estNotificationAEffacer(evt.content)) continue;
      const txn = `reco-retention-${encodeURIComponent(evt.event_id)}`;
      await lire(fetchImpl, `${racineSalon}/redact/${encodeURIComponent(evt.event_id)}/${txn}`, {
        method: 'PUT',
        headers: { ...entetes, 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: `Conservation : ${mois} mois (mentions légales)` }),
      });
      effaces += 1;
    }
    if (!evenements.length || !corps.end) break;
    depuis = corps.end;
  }
  return effaces;
}
