/**
 * Tests de `src/server/redirections.mjs` — les 301 des fiches fusionnées.
 *
 * Trois niveaux : le module seul (table, cible, réponse), le serveur complet
 * avec un faux gestionnaire (le 301 part AVANT Astro), et la vraie table du
 * dépôt (aucune chaîne, aucune adresse mal formée).
 */
import { afterEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

// @ts-expect-error — module `.mjs` sans déclaration de types
import { chargerRedirections, cibleDe, rediriger } from '../../src/server/redirections.mjs';
// @ts-expect-error — module `.mjs` sans déclaration de types
import { creerServeur } from '../../src/server/serveur.mjs';
import { demander, demarrer } from './_client';

const TABLE = new Map([
  ['/un-bon-moment/oeuvre/perdant', '/un-bon-moment/oeuvre/survivant'],
]);

describe('chargerRedirections', () => {
  it('lit la table et écarte les cibles qui ne sont pas des chemins', () => {
    const lire = () => JSON.stringify({ '/a': '/b', '/c': 'https://ailleurs.fr/', '/d': 3 });
    const table = chargerRedirections('table.json', { lire });
    expect([...table]).toEqual([['/a', '/b']]);
  });

  it('rend une table vide si le fichier manque ou est illisible', () => {
    const manquant = () => { throw new Error('ENOENT'); };
    expect(chargerRedirections('absent.json', { lire: manquant }).size).toBe(0);
    expect(chargerRedirections('casse.json', { lire: () => '{pas du json' }).size).toBe(0);
  });

  it('lit par défaut la table du dépôt', () => {
    expect(chargerRedirections().size).toBeGreaterThan(0);
  });
});

describe('cibleDe', () => {
  it('trouve la cible, avec ou sans barre finale', () => {
    expect(cibleDe(TABLE, '/un-bon-moment/oeuvre/perdant')).toBe('/un-bon-moment/oeuvre/survivant');
    expect(cibleDe(TABLE, '/un-bon-moment/oeuvre/perdant/')).toBe('/un-bon-moment/oeuvre/survivant');
  });

  it('garde la chaîne de requête', () => {
    expect(cibleDe(TABLE, '/un-bon-moment/oeuvre/perdant/?ref=x'))
      .toBe('/un-bon-moment/oeuvre/survivant?ref=x');
  });

  it('ne redirige ni une adresse inconnue, ni la racine, ni avec une table vide', () => {
    expect(cibleDe(TABLE, '/un-bon-moment/oeuvre/autre')).toBeNull();
    expect(cibleDe(TABLE, '/')).toBeNull();
    expect(cibleDe(new Map(), '/un-bon-moment/oeuvre/perdant')).toBeNull();
  });
});

describe('rediriger', () => {
  function fausseReponse() {
    const r: { statut?: number; entetes?: Record<string, unknown>; fini: boolean } = { fini: false };
    return {
      r,
      res: {
        writeHead: (s: number, e: Record<string, unknown>) => { r.statut = s; r.entetes = e; },
        end: () => { r.fini = true; },
      },
    };
  }

  it('répond 301 vers le survivant', () => {
    const { r, res } = fausseReponse();
    expect(rediriger(TABLE, { method: 'GET', url: '/un-bon-moment/oeuvre/perdant' }, res)).toBe(true);
    expect(r).toEqual({ statut: 301, entetes: { Location: '/un-bon-moment/oeuvre/survivant', 'Content-Length': 0 }, fini: true });
  });

  it('laisse passer un POST et une URL absente', () => {
    const { r, res } = fausseReponse();
    expect(rediriger(TABLE, { method: 'POST', url: '/un-bon-moment/oeuvre/perdant' }, res)).toBe(false);
    expect(rediriger(TABLE, { method: 'HEAD' }, res)).toBe(false);
    expect(r.fini).toBe(false);
  });
});

describe('le serveur redirige avant de chercher la page', () => {
  let arreter: (() => Promise<void>) | null = null;
  afterEach(async () => { await arreter?.(); arreter = null; });

  it('301 sans appeler Astro, puis aiguillage normal pour le reste', async () => {
    const recu: string[] = [];
    const handler = (req: any, res: any) => {
      recu.push(req.url);
      res.writeHead(200, { 'Content-Type': 'text/plain', 'Content-Length': 2 });
      res.end('ok');
    };
    const serveur = creerServeur(handler, '/nulle-part', null, TABLE);
    const lance = await demarrer(serveur);
    arreter = lance.arreter;

    const redirige = await demander(lance.port, '/un-bon-moment/oeuvre/perdant/');
    expect(redirige.statut).toBe(301);
    expect(redirige.entetes.location).toBe('/un-bon-moment/oeuvre/survivant');

    const normal = await demander(lance.port, '/un-bon-moment/oeuvre/survivant');
    expect(normal.statut).toBe(200);
    expect(recu).toEqual(['/un-bon-moment/oeuvre/survivant']);
  });
});

describe('la table du dépôt', () => {
  const table: Record<string, string> = JSON.parse(readFileSync(
    join(process.cwd(), 'src', 'content', 'redirections-oeuvres.json'), 'utf8'));
  const FORME = /^\/[a-z0-9-]+\/oeuvre\/[a-z0-9-]+$/;

  it('ne contient que des adresses de fiche bien formées', () => {
    for (const [de, vers] of Object.entries(table)) {
      expect(de).toMatch(FORME);
      expect(vers).toMatch(FORME);
    }
  });

  it('ne fait jamais traverser deux 301', () => {
    for (const vers of Object.values(table)) expect(table[vers]).toBeUndefined();
  });
});
