/**
 * Redirections permanentes des pages d'œuvre fusionnées.
 *
 * Fusionner deux fiches supprime la perdante, et son adresse `/oeuvre/<id>`,
 * déjà indexée et parfois partagée, répondait 404. Les outils de fusion
 * notent désormais chaque ancienne adresse dans
 * `src/content/redirections-oeuvres.json` (voir `tools/redirections_oeuvres.py`) ;
 * ce module y répond par un 301, qui dit aux moteurs de transférer la page.
 *
 * Le fichier est lu depuis `process.cwd()`, comme la table des pays : il
 * marche parce que l'hébergeur déploie le dépôt entier.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const FICHIER = join(process.cwd(), 'src', 'content', 'redirections-oeuvres.json');

/**
 * Charge la table, ou une table vide si elle est absente ou illisible.
 *
 * Jamais d'exception : une table cassée doit coûter des 404, pas le site.
 */
export function chargerRedirections(fichier = FICHIER, { lire = readFileSync } = {}) {
  try {
    const table = JSON.parse(lire(fichier, 'utf8'));
    return new Map(Object.entries(table).filter(
      ([de, vers]) => typeof de === 'string' && typeof vers === 'string' && vers.startsWith('/'),
    ));
  } catch {
    return new Map();
  }
}

/**
 * La cible d'une URL demandée, requête comprise, ou `null`.
 *
 * La barre finale est ignorée (`trailingSlash: 'ignore'`) ; la chaîne de
 * requête suit la redirection, pour ne perdre ni un filtre ni un marqueur.
 */
export function cibleDe(table, url) {
  if (table.size === 0) return null;
  const debutRequete = url.indexOf('?');
  const chemin = debutRequete === -1 ? url : url.slice(0, debutRequete);
  const requete = debutRequete === -1 ? '' : url.slice(debutRequete);
  const sansBarre = chemin.length > 1 ? chemin.replace(/\/+$/, '') : chemin;
  const cible = table.get(sansBarre);
  return cible ? cible + requete : null;
}

/** Répond 301 si l'URL a une cible. Rend `true` si la réponse est partie. */
export function rediriger(table, req, res) {
  if (req.method !== 'GET' && req.method !== 'HEAD') return false;
  const cible = cibleDe(table, req.url || '/');
  if (!cible) return false;
  res.writeHead(301, { Location: cible, 'Content-Length': 0 });
  res.end();
  return true;
}
