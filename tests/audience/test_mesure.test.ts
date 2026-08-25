/**
 * Tests de `src/lib/audience/mesure.mjs` — le branchement sur le serveur.
 *
 * CE QU'ILS PROTÈGENT
 * -------------------
 * Ce code s'exécute sur chaque requête. Deux propriétés comptent avant toutes
 * les autres, et chacune a ses tests :
 *
 *  1. Il ne compte QUE des pages — sinon une seule visite écrirait trente
 *     lignes, une par ressource, et les chiffres ne voudraient plus rien dire.
 *  2. Il n'échoue jamais bruyamment. Un disque plein, un `res` incomplet, une
 *     erreur de dérivation : la page doit s'afficher quand même.
 */
import { describe, expect, it, vi } from 'vitest';
import { EventEmitter } from 'node:events';

// @ts-expect-error — module `.mjs` sans déclaration de types
import {
  adresseCliente,
  hoteDe,
  mesurerVisite,
  sourceDuChemin,
  sourcesDe,
} from '../../src/lib/audience/mesure.mjs';

/** Un couple requête/réponse minimal, qui sait émettre `finish`. */
function couple(url = '/un-bon-moment/films', entetes: Record<string, string> = {}) {
  const req = {
    url,
    method: 'GET',
    headers: { 'user-agent': 'Mozilla/5.0 (Windows NT 10.0) Chrome/152.0', ...entetes },
    socket: { remoteAddress: '203.0.113.7' },
  };
  const res = Object.assign(new EventEmitter(), {
    statusCode: 200,
    getHeader: (n: string) => (n === 'content-length' ? 15316 : undefined),
  });
  return { req, res };
}

describe('ce qui est compté', () => {
  it('compte une page', () => {
    const ecrire = vi.fn();
    const { req, res } = couple();
    mesurerVisite(req, res, { ecrire, sel: 'sel' });
    res.emit('finish');

    expect(ecrire).toHaveBeenCalledTimes(1);
    expect(ecrire.mock.calls[0][0]).toMatchObject({
      chemin: '/un-bon-moment/films',
      statut: 200,
      robot: false,
    });
  });

  it('ne compte PAS les ressources d’une page', () => {
    // Une visite charge la feuille de style, les polices, les icônes : les
    // compter multiplierait chaque visite par trente.
    const ecrire = vi.fn();
    for (const url of ['/_astro/x.css', '/favicon.ico', '/icons/y.svg', '/version.txt']) {
      const { req, res } = couple(url);
      mesurerVisite(req, res, { ecrire });
      res.emit('finish');
    }

    expect(ecrire).not.toHaveBeenCalled();
  });

  it('ne compte pas les appels d’API', () => {
    const ecrire = vi.fn();
    const { req, res } = couple('/api/click');
    mesurerVisite(req, res, { ecrire });
    res.emit('finish');

    expect(ecrire).not.toHaveBeenCalled();
  });

  it('compte une page absente : les 404 disent quels liens circulent', () => {
    const ecrire = vi.fn();
    const { req, res } = couple('/fiche-supprimee');
    res.statusCode = 404;
    mesurerVisite(req, res, { ecrire });
    res.emit('finish');

    expect(ecrire.mock.calls[0][0]).toMatchObject({ statut: 404 });
  });

  it('n’écrit rien avant la fin de la réponse', () => {
    // Le statut et le poids ne sont connus qu'une fois la réponse partie.
    const ecrire = vi.fn();
    const { req, res } = couple();
    mesurerVisite(req, res, { ecrire });

    expect(ecrire).not.toHaveBeenCalled();
  });

  it('ne compte pas une visite interrompue', () => {
    // `close` sans `finish` : le visiteur est parti avant la fin.
    const ecrire = vi.fn();
    const { req, res } = couple();
    mesurerVisite(req, res, { ecrire });
    res.emit('close');

    expect(ecrire).not.toHaveBeenCalled();
  });
});

describe('robustesse — mesurer ne casse jamais une requête', () => {
  it('supporte un `res` sans gestion d’événements', () => {
    // Les tests du serveur passent un double minimal ; une future couche
    // pourrait faire pareil.
    const { req } = couple();
    expect(() => mesurerVisite(req, { statusCode: 200 }, {})).not.toThrow();
  });

  it('avale une erreur d’écriture', () => {
    const ecrire = vi.fn(() => { throw new Error('disque plein'); });
    const { req, res } = couple();
    mesurerVisite(req, res, { ecrire });

    expect(() => res.emit('finish')).not.toThrow();
  });

  it('supporte une requête sans en-têtes ni adresse', () => {
    const ecrire = vi.fn();
    const res = Object.assign(new EventEmitter(), { statusCode: 200 });
    mesurerVisite({ url: '/', method: 'GET' }, res, { ecrire });

    expect(() => res.emit('finish')).not.toThrow();
    expect(ecrire).toHaveBeenCalled();
  });
});

describe('sans sel, la mesure continue', () => {
  it('compte la page mais laisse le visiteur à null', () => {
    // Un sel absent ne doit pas faire taire toute la mesure : on perd la
    // distinction pages vues / visiteurs, pas le reste.
    const ecrire = vi.fn();
    const { req, res } = couple();
    mesurerVisite(req, res, { ecrire, sel: null });
    res.emit('finish');

    expect(ecrire.mock.calls[0][0]).toMatchObject({ chemin: '/un-bon-moment/films' });
    expect(ecrire.mock.calls[0][0].visiteur).toBeNull();
  });
});

describe('adresseCliente', () => {
  it('lit le DERNIER saut, celui que pose notre proxy', () => {
    // Le premier est écrit par le client, donc forgeable.
    const req = {
      headers: { 'x-forwarded-for': '198.51.100.9, 203.0.113.7' },
      socket: { remoteAddress: '10.0.0.1' },
    };
    expect(adresseCliente(req)).toBe('203.0.113.7');
  });

  it('retombe sur l’adresse directe sans en-tête', () => {
    expect(adresseCliente({ headers: {}, socket: { remoteAddress: '203.0.113.7' } }))
      .toBe('203.0.113.7');
  });

  it('rend null quand rien n’est déterminable', () => {
    expect(adresseCliente({ headers: {}, socket: {} })).toBeNull();
  });
});

describe('sourceDuChemin', () => {
  const CONNUES = new Set(['un-bon-moment']);

  it('range la visite sous la source du chemin', () => {
    expect(sourceDuChemin('/un-bon-moment/films', CONNUES)).toBe('un-bon-moment');
  });

  it('range les pages communes sous `_site`', () => {
    expect(sourceDuChemin('/', CONNUES)).toBe('_site');
    expect(sourceDuChemin('/a-propos', CONNUES)).toBe('_site');
  });

  it('refuse de créer un dossier depuis une URL inventée', () => {
    // Sans cette garde, `/nimportequoi` suffirait à polluer l'arborescence.
    expect(sourceDuChemin('/podcast-invente', CONNUES)).toBe('_site');
  });

  it('résiste à une tentative de traversée', () => {
    expect(sourceDuChemin('/../../etc/passwd', CONNUES)).toBe('_site');
  });

  it('range TOUT sous `_site` quand aucune source n’est déclarée', () => {
    // `sourcesDe` documente exactement cela : « rend null quand rien n'est
    // déclaré — tout sera alors rangé dans `_site` ». Le code faisait
    // l'inverse : il prenait le premier segment pour un nom de source. Un
    // serveur lancé sans RECO_SOURCES créait donc un dossier par racine
    // d'URL visitée — constaté en local avec `audience/`, `route/`,
    // `nulle-part/`. Les tests d'origine passaient tous une liste non vide :
    // le trou était là.
    expect(sourceDuChemin('/un-bon-moment/films', null)).toBe('_site');
    expect(sourceDuChemin('/nimporte-quoi', null)).toBe('_site');
    expect(sourceDuChemin('/', null)).toBe('_site');
  });
});

describe('configuration', () => {
  it('tire le nom d’hôte de SITE_URL', () => {
    expect(hoteDe('https://unebonnere.co')).toBe('unebonnere.co');
    expect(hoteDe('https://unebonnere.co/chemin?x=1')).toBe('unebonnere.co');
  });

  it('rend null sans valeur ou sur une URL illisible', () => {
    // Sans hôte, toute page interne compterait comme une provenance : le site
    // se référencerait lui-même.
    expect(hoteDe(undefined)).toBeNull();
    expect(hoteDe('')).toBeNull();
    expect(hoteDe('pas une url')).toBeNull();
  });

  it('lit la liste des sources', () => {
    const s = sourcesDe('un-bon-moment, autre-podcast');
    expect(s?.has('un-bon-moment')).toBe(true);
    expect(s?.has('autre-podcast')).toBe(true);
  });

  it('rend null quand rien n’est déclaré', () => {
    // Tout ira dans `_site` : moins précis, jamais faux.
    expect(sourcesDe(undefined)).toBeNull();
    expect(sourcesDe('')).toBeNull();
    expect(sourcesDe('  ,  ')).toBeNull();
  });
});
