/**
 * Client HTTP BRUT pour les tests du serveur de production.
 *
 * POURQUOI PAS `fetch`
 * --------------------
 * `fetch` (undici) décompresse le corps tout seul et masque une partie de la
 * négociation. Or c'est précisément ce qui est testé ici : quels octets
 * partent réellement sur le fil, et sous quels en-têtes. Un test qui passe par
 * `fetch` ne verrait pas la différence entre « compressé correctement » et
 * « annoncé compressé mais envoyé en clair » — le second cas casse tous les
 * navigateurs, et c'est exactement le genre de bug qu'on cherche.
 *
 * On reste donc sur `node:http`, qui laisse le corps intact.
 */
import http from 'node:http';
import type { AddressInfo } from 'node:net';
import { gunzipSync } from 'node:zlib';

export type Reponse = {
  statut: number;
  entetes: http.IncomingHttpHeaders;
  /** Le corps TEL QU'ENVOYÉ, sans décompression. */
  brut: Buffer;
  /** Le corps après décompression si `Content-Encoding: gzip`, sinon tel quel. */
  texte: string;
};

/** Démarre un serveur sur un port libre et renvoie de quoi l'interroger. */
export async function demarrer(
  serveur: http.Server,
): Promise<{ port: number; arreter: () => Promise<void> }> {
  await new Promise<void>((resoudre) => serveur.listen(0, '127.0.0.1', resoudre));
  const port = (serveur.address() as AddressInfo).port;
  return {
    port,
    arreter: () =>
      new Promise<void>((resoudre, rejeter) =>
        serveur.close((e) => (e ? rejeter(e) : resoudre())),
      ),
  };
}

/** Une requête, avec le corps brut ET le corps décodé. */
export function demander(
  port: number,
  chemin: string,
  options: { methode?: string; entetes?: Record<string, string> } = {},
): Promise<Reponse> {
  return new Promise((resoudre, rejeter) => {
    const requete = http.request(
      {
        host: '127.0.0.1',
        port,
        path: chemin,
        method: options.methode ?? 'GET',
        headers: options.entetes ?? {},
        // Sans cela, l'agent par défaut GARDE la connexion ouverte et
        // `serveur.close()` attend son expiration : la suite passait de 2 à 88
        // secondes, uniquement en attente de sockets inutilisées.
        agent: false,
      },
      (reponse) => {
        const morceaux: Buffer[] = [];
        reponse.on('data', (m) => morceaux.push(m));
        reponse.on('end', () => {
          const brut = Buffer.concat(morceaux);
          const gzippe = reponse.headers['content-encoding'] === 'gzip';
          // `gunzipSync` sur des octets NON gzippés lève : c'est voulu, un
          // en-tête `gzip` posé sur du clair DOIT faire échouer le test.
          const texte = gzippe && brut.length
            ? gunzipSync(brut).toString('utf-8')
            : brut.toString('utf-8');
          resoudre({ statut: reponse.statusCode ?? 0, entetes: reponse.headers, brut, texte });
        });
      },
    );
    requete.on('error', rejeter);
    requete.end();
  });
}
