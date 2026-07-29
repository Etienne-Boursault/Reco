/**
 * Résolution de l'IP cliente servant de clé de rate-limit.
 *
 * POURQUOI LE **DERNIER** ÉLÉMENT DE `X-Forwarded-For`, ET NON LE PREMIER
 * (revue de sécurité du 2026-07-29).
 *
 * L'en-tête s'écrit `<client>, <proxy1>, <proxy2>` : chaque proxy AJOUTE
 * l'adresse qu'il constate, il n'écrase pas ce que le client a envoyé.
 *
 *   - le PREMIER élément est ce que le CLIENT a bien voulu déclarer ;
 *   - le DERNIER est ce que NOTRE propre proxy a constaté.
 *
 * Les deux endpoints lisaient `xff.split(',')[0]`. Un attaquant faisait donc
 * varier l'en-tête à chaque requête (`1.2.3.4`, `1.2.3.5`…), tombait dans un
 * bucket de rate-limit neuf à chaque fois, et la limite ne se déclenchait
 * jamais — alors que chaque requête acceptée écrit un fichier sur le disque.
 * La garde `TRUSTED_PROXIES` ne servait à rien : elle vérifiait bien QUI
 * parlait, mais lisait ensuite la partie de l'en-tête que l'attaquant écrit.
 *
 * Prendre le dernier élément reste correct quand le proxy REMPLACE l'en-tête
 * plutôt que de l'étendre (nginx avec `$remote_addr`) : la liste ne contient
 * alors qu'une entrée, premier et dernier se confondent.
 *
 * LIMITE ASSUMÉE : avec PLUSIEURS proxies en cascade, la valeur juste est à la
 * position `-(N+1)`. Le projet n'expose pas la profondeur de chaîne — un seul
 * `TRUSTED_PROXIES` sans notion d'ordre — donc on traite le cas à un saut, qui
 * est celui documenté dans `docs/tutorial/04-deploy-static.md`. Le pire cas
 * d'une chaîne plus longue est de retenir l'IP d'un proxy intermédiaire :
 * un bucket trop large, jamais un bucket choisi par l'attaquant.
 *
 * Ce module existe pour que la règle vive à UN seul endroit : elle était
 * recopiée dans les deux endpoints, et c'est précisément le motif qui a déjà
 * produit deux bugs ici (une parade appliquée à un module, jamais reportée sur
 * son jumeau).
 */

export interface ResolveClientIpOptions {
  /** Pair TCP direct, tel que vu par le serveur. `null` si indisponible. */
  clientAddress: string | null;
  /** En-tête `X-Forwarded-For` brut, ou `null`. */
  forwardedFor: string | null;
  /** IPs de proxies dont on accepte l'en-tête. */
  trustedProxies: ReadonlySet<string>;
}

/**
 * IP à utiliser comme clé de rate-limit, ou `null` si indéterminable.
 *
 * `null` doit faire court-circuiter l'appelant (204 silencieux) plutôt que de
 * hasher une valeur par défaut : tous les clients sans IP tomberaient dans le
 * même bucket, ce qui est un DoS auto-infligé (CR senior C25-2).
 */
export function resolveClientIp({
  clientAddress,
  forwardedFor,
  trustedProxies,
}: ResolveClientIpOptions): string | null {
  // `''` est traité comme une absence : `tryClientAddress` le préserve
  // volontairement et laisse la décision à l'appelant — la voici.
  if (!clientAddress) return null;

  if (!trustedProxies.has(clientAddress)) {
    // Pair direct non déclaré de confiance : son en-tête ne vaut rien.
    return clientAddress;
  }

  const sauts = (forwardedFor ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

  // M25-18 : proxy de confiance sans en-tête exploitable → son adresse reste
  // préférable à `null` (health-check interne, tests).
  return sauts.at(-1) ?? clientAddress;
}
