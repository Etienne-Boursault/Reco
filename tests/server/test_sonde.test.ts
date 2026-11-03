/**
 * Tests de `src/server/sonde.mjs` — la sonde des vérifications chez l'hébergeur.
 *
 * La base est remplacée par une fausse connexion qui imite MariaDB sur les
 * seuls points vérifiés : le verrou de ligne entre deux connexions, la
 * contrainte `CHECK` et le mode strict. La question posée ici n'est pas « la
 * base de l'hébergeur tient-elle ? » — c'est la sonde qui le dira sur place —
 * mais « la sonde rapporte-t-elle fidèlement ce que la base répond ? ».
 */
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { Readable } from 'node:stream';
import { createHash } from 'node:crypto';

vi.mock('mysql2/promise', () => ({ createConnection: vi.fn(async (options: unknown) => options) }));

import {
  autorise, connecterMariaDB, dossierDonnees, lireEnvoi, poserTemoin, processus,
  relireTemoin, sonder, TEMOIN, verifierBase,
  // @ts-expect-error — module `.mjs` sans déclaration de types
} from '../../src/server/sonde.mjs';

const CLE = 'une-cle-de-sonde-pour-les-tests';
const ENTETES = { authorization: `Bearer ${CLE}` };
const ENV_BDD = {
  RECO_SONDE_CLE: CLE,
  RECO_BDD_HOTE: 'base.test',
  RECO_BDD_NOM: 'catalogue',
  RECO_BDD_UTILISATEUR: 'site',
  RECO_BDD_MOT_DE_PASSE: 'mot-de-passe-de-test',
};

let racine: string;
beforeAll(() => { racine = mkdtempSync(path.join(tmpdir(), 'reco-sonde-')); });
afterAll(() => rmSync(racine, { recursive: true, force: true }));

/** Une requête : un flux lisible, avec l'adresse, la méthode et les en-têtes. */
function fausseRequete(url: string | undefined, methode = 'GET',
  entetes: Record<string, string> = ENTETES, corps: Buffer[] = []) {
  return Object.assign(Readable.from(corps), { url, method: methode, headers: entetes });
}

/** Une réponse qui retient ce qu'on lui écrit, et dit quand elle est finie. */
function fausseReponse() {
  let finir: () => void = () => {};
  const finie = new Promise<void>((r) => { finir = r; });
  const res = {
    statut: 0,
    entetes: {} as Record<string, unknown>,
    corps: '',
    writeHead(statut: number, entetes: Record<string, unknown>) {
      res.statut = statut;
      res.entetes = entetes;
    },
    end(corps: string) {
      res.corps = corps;
      finir();
    },
  };
  return { res, finie };
}

async function interroger(url: string, options: Record<string, unknown>, methode = 'GET',
  corps: Buffer[] = []) {
  const { res, finie } = fausseReponse();
  const pris = sonder(fausseRequete(url, methode, ENTETES, corps), res, options);
  expect(pris).toBe(true);
  await finie;
  return { statut: res.statut, entetes: res.entetes, json: JSON.parse(res.corps) };
}

type Erreur = Error & { code?: string };
function erreur(code: string | undefined, message = 'refusé'): Erreur {
  return Object.assign(new Error(message), code ? { code } : {});
}

/**
 * Une fausse base partagée par deux connexions : un verrou de ligne, une ligne
 * écrite, et des refus réglables étape par étape.
 */
function fausseBase(reglages: {
  refuserCreation?: boolean;
  lectureVide?: boolean;
  contraintesAbsentes?: boolean;
  erreurSansCode?: boolean;
  finEnEchec?: boolean;
} = {}) {
  const etat = { verrou: null as object | null, requetes: [] as string[], fermees: 0 };
  function connexion() {
    const moi = {
      async query(sql: string, valeurs: unknown[] = []) {
        etat.requetes.push(sql.split('\n')[0]);
        if (sql.startsWith('SELECT VERSION()')) return [[{ version: '10.11.19-MariaDB' }]];
        if (sql.startsWith('CREATE TABLE') && reglages.refuserCreation) throw erreur('ER_DBACCESS_DENIED_ERROR');
        if (sql.endsWith('FOR UPDATE')) {
          if (etat.verrou && etat.verrou !== moi) throw erreur('ER_LOCK_WAIT_TIMEOUT');
          etat.verrou = moi;
          return [[{ valeur: 'été' }]];
        }
        if (sql.startsWith('SELECT valeur')) return [reglages.lectureVide ? [] : [{ valeur: 'été' }]];
        if (sql.startsWith('INSERT') && !reglages.contraintesAbsentes) {
          if (valeurs[0] === 'Pas bon') throw erreur(reglages.erreurSansCode ? undefined : 'ER_CONSTRAINT_FAILED', 'contrainte');
          if (String(valeurs[1]).length > 8) throw erreur('ER_DATA_TOO_LONG');
        }
        return [[]];
      },
      async beginTransaction() {},
      async commit() { if (etat.verrou === moi) etat.verrou = null; },
      async end() {
        etat.fermees += 1;
        if (reglages.finEnEchec) throw erreur('ECONNRESET');
      },
    };
    return moi;
  }
  return { etat, connecter: async () => connexion() };
}

describe('autorise — la clé de la sonde', () => {
  it('refuse tout quand aucune clé n’est posée', () => {
    expect(autorise(fausseRequete('/__sonde/processus'), undefined)).toBe(false);
  });

  it('refuse une requête sans en-tête, ou avec une autre clé', () => {
    expect(autorise(fausseRequete('/', 'GET', {}), CLE)).toBe(false);
    expect(autorise(fausseRequete('/', 'GET', { authorization: 'Bearer autre' }), CLE)).toBe(false);
  });

  it('accepte la bonne clé', () => {
    expect(autorise(fausseRequete('/'), CLE)).toBe(true);
  });
});

describe('sonder — inerte tant qu’on ne l’ouvre pas', () => {
  const { res } = fausseReponse();

  it('laisse passer les adresses ordinaires, et une requête sans adresse', () => {
    expect(sonder(fausseRequete('/oeuvres/'), res, { env: ENV_BDD })).toBe(false);
    expect(sonder(fausseRequete(undefined), res, { env: ENV_BDD })).toBe(false);
  });

  it('rend la main sans clé posée, avec une mauvaise clé, ou sur une route inconnue', () => {
    expect(sonder(fausseRequete('/__sonde/processus'), res, { env: {} })).toBe(false);
    expect(sonder(fausseRequete('/__sonde/processus', 'GET', { authorization: 'Bearer x' }), res,
      { env: ENV_BDD })).toBe(false);
    expect(sonder(fausseRequete('/__sonde/inconnue'), res, { env: ENV_BDD })).toBe(false);
    expect(sonder(fausseRequete('/__sonde/v1', 'GET'), res, { env: ENV_BDD })).toBe(false);
    expect(res.statut).toBe(0);
  });

  it('lit la clé dans l’environnement du processus par défaut', () => {
    vi.stubEnv('RECO_SONDE_CLE', '');
    expect(sonder(fausseRequete('/__sonde/processus'), res)).toBe(false);
    vi.unstubAllEnvs();
  });
});

describe('processus — combien de processus, et depuis quand', () => {
  it('donne le pid et une heure de démarrage passée', async () => {
    const { statut, entetes, json } = await interroger('/__sonde/processus?n=1', { env: ENV_BDD });
    expect(statut).toBe(200);
    expect(entetes['Cache-Control']).toBe('no-store');
    expect(json.pid).toBe(process.pid);
    expect(Date.parse(json.demarreLe)).toBeLessThanOrEqual(Date.parse(json.maintenant));
    expect(processus().pid).toBe(process.pid);
  });
});

describe('V1 — un envoi lu en entier', () => {
  it('compte les octets et rend leur SHA-256, avec la taille annoncée', async () => {
    const morceaux = [Buffer.alloc(700_000, 1), Buffer.alloc(348_576, 2)];
    const attendu = createHash('sha256').update(Buffer.concat(morceaux)).digest('hex');
    const { res, finie } = fausseReponse();
    const req = fausseRequete('/__sonde/v1', 'POST', { ...ENTETES, 'content-length': '1048576' }, morceaux);
    expect(sonder(req, res, { env: ENV_BDD })).toBe(true);
    await finie;
    expect(JSON.parse(res.corps)).toEqual({ octets: 1_048_576, sha256: attendu, annonce: '1048576' });
  });

  it('dit quand aucune taille n’était annoncée', async () => {
    const { json } = await interroger('/__sonde/v1', { env: ENV_BDD }, 'POST', [Buffer.from('abc')]);
    expect(json.octets).toBe(3);
    expect(json.annonce).toBeNull();
    expect((await lireEnvoi(fausseRequete('/', 'POST', {}))).octets).toBe(0);
  });
});

describe('V2 — la base', () => {
  it('rapporte la version, la transaction, le verrou, les refus et la durée', async () => {
    const base = fausseBase();
    const { json } = await interroger('/__sonde/v2', { env: ENV_BDD, connecter: base.connecter }, 'POST');
    expect(json).toMatchObject({
      ok: true,
      etape: 'fin',
      version: '10.11.19-MariaDB',
      transaction: true,
      verrou: 'ER_LOCK_WAIT_TIMEOUT',
      verrouLibere: true,
      check: 'ER_CONSTRAINT_FAILED',
      strict: 'ER_DATA_TOO_LONG',
    });
    expect(json.dureeMs).toBeGreaterThanOrEqual(0);
    // Le mode strict est fixé sur les deux connexions, et la table disparaît.
    expect(base.etat.requetes.filter((r) => r.startsWith('SET SESSION sql_mode'))).toHaveLength(2);
    expect(base.etat.requetes.at(-1)).toBe('DROP TABLE IF EXISTS sonde_essai');
    expect(base.etat.fermees).toBe(2);
  });

  it('nomme les variables qui manquent, sans tenter de connexion', async () => {
    const connecter = vi.fn();
    const resultat = await verifierBase({ env: { RECO_BDD_HOTE: 'base.test' }, connecter });
    expect(resultat).toEqual({
      ok: false,
      etape: 'variables',
      manquantes: ['RECO_BDD_NOM', 'RECO_BDD_UTILISATEUR', 'RECO_BDD_MOT_DE_PASSE'],
    });
    expect(connecter).not.toHaveBeenCalled();
  });

  it('dit qu’elle n’a pas pu se connecter', async () => {
    const connecter = async () => { throw erreur('ER_ACCESS_DENIED_ERROR'); };
    expect(await verifierBase({ env: ENV_BDD, connecter }))
      .toEqual({ ok: false, etape: 'connexion', erreur: 'ER_ACCESS_DENIED_ERROR' });
  });

  it('ferme la première connexion quand la seconde échoue, même si la fermeture échoue', async () => {
    const base = fausseBase({ finEnEchec: true });
    let appels = 0;
    const connecter = async () => {
      appels += 1;
      if (appels === 2) throw new Error('trop de connexions');
      return base.connecter();
    };
    const resultat = await verifierBase({ env: ENV_BDD, connecter });
    expect(resultat).toEqual({ ok: false, etape: 'connexion', erreur: 'trop de connexions' });
    expect(base.etat.fermees).toBe(1);
  });

  it('s’arrête à l’étape qui échoue, et supprime quand même la table', async () => {
    const base = fausseBase({ refuserCreation: true });
    const resultat = await verifierBase({ env: ENV_BDD, connecter: base.connecter });
    expect(resultat).toMatchObject({ ok: false, etape: 'table', erreur: 'ER_DBACCESS_DENIED_ERROR' });
    expect(base.etat.requetes.at(-1)).toBe('DROP TABLE IF EXISTS sonde_essai');
  });

  it('rapporte une relecture vide, et une base qui accepte tout', async () => {
    const base = fausseBase({ lectureVide: true, contraintesAbsentes: true });
    const resultat = await verifierBase({ env: ENV_BDD, connecter: base.connecter });
    expect(resultat).toMatchObject({ ok: true, transaction: false, check: null, strict: null });
  });

  it('rend le message d’un refus qui n’a pas de code', async () => {
    const base = fausseBase({ erreurSansCode: true });
    const resultat = await verifierBase({ env: ENV_BDD, connecter: base.connecter });
    expect(resultat.check).toBe('contrainte');
  });

  it('se connecte avec les variables du Manager, sans instructions multiples', async () => {
    const options = await connecterMariaDB(ENV_BDD);
    expect(options).toMatchObject({
      host: 'base.test', port: 3306, database: 'catalogue', user: 'site', multipleStatements: false,
    });
    expect((await connecterMariaDB({ ...ENV_BDD, RECO_BDD_PORT: '3307' })).port).toBe(3307);
  });
});

describe('V3 — le dossier de données', () => {
  it('prend RECO_DONNEES_DIR, ou reco-donnees par défaut', () => {
    expect(dossierDonnees({ RECO_DONNEES_DIR: racine })).toBe(path.resolve(racine));
    expect(dossierDonnees({})).toBe(path.resolve('reco-donnees'));
  });

  it('pose le témoin une seule fois, puis le relit', async () => {
    const dossier = path.join(racine, 'donnees');
    const env = { ...ENV_BDD, RECO_DONNEES_DIR: dossier };
    const premier = await interroger('/__sonde/v3', { env }, 'POST');
    expect(premier.json.cree).toBe(true);
    const second = await interroger('/__sonde/v3', { env }, 'POST');
    expect(second.json).toEqual({ cree: false, temoin: premier.json.temoin });
    const relu = await interroger('/__sonde/v3', { env });
    expect(relu.json).toEqual({ temoin: premier.json.temoin, ecriture: true });
  });

  it('dit qu’il n’y a pas de témoin, ou qu’on ne peut plus écrire', () => {
    const dossier = path.join(racine, 'vide');
    const refuser = () => { throw erreur('EROFS'); };
    expect(relireTemoin(dossier, { ecrire: refuser })).toEqual({ temoin: null, ecriture: false });
  });

  it('laisse remonter une écriture refusée pour une autre raison qu’un témoin existant', () => {
    const refuser = () => { throw erreur('EACCES'); };
    expect(() => poserTemoin(path.join(racine, 'refus'), { ecrire: refuser })).toThrow('refusé');
  });

  it('répond 500 avec le code, ou le message, quand le dossier est inutilisable', async () => {
    const fichier = path.join(racine, 'un-fichier');
    writeFileSync(fichier, 'pas un dossier');
    const pose = await interroger('/__sonde/v3', { env: { ...ENV_BDD, RECO_DONNEES_DIR: fichier } }, 'POST');
    expect(pose.statut).toBe(500);
    expect(typeof pose.json.erreur).toBe('string');

    const abime = path.join(racine, 'abime');
    poserTemoin(abime);
    writeFileSync(path.join(abime, TEMOIN), '{ illisible');
    const relu = await interroger('/__sonde/v3', { env: { ...ENV_BDD, RECO_DONNEES_DIR: abime } });
    expect(relu.statut).toBe(500);
    expect(relu.json.erreur).toMatch(/JSON/);
  });
});
