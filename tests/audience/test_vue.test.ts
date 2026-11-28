/**
 * Tests de `src/lib/audience/vue.ts` — ce que la page décide avant d'afficher.
 *
 * CE QU'ILS PROTÈGENT
 * -------------------
 * Le périmètre par défaut, surtout. Le premier jet lisait la seule source
 * `un-bon-moment` et cachait donc l'accueil et toutes les 404, qui vivent sous
 * `_site` — 2 pages vues affichées sur 11 réelles, et « aucune page demandée
 * en vain » alors que trois liens morts étaient enregistrés.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { agreger } from '../../src/lib/audience/agregat';
import { lireAudience, nbJoursDemande, perimetreDemande } from '../../src/lib/audience/vue';

// `agreger` passe par ce relais : un test peut lui faire lever une valeur qui
// n'est pas une `Error`, ce qu'aucun fichier sur le disque ne provoque.
const panne = vi.hoisted(() => ({ valeur: undefined as unknown }));
vi.mock('../../src/lib/audience/agregat', async (original) => {
  const vrai = await original<typeof import('../../src/lib/audience/agregat')>();
  return {
    ...vrai,
    agreger: (o: Parameters<typeof vrai.agreger>[0]) => {
      if (panne.valeur !== undefined) throw panne.valeur;
      return vrai.agreger(o);
    },
  };
});

describe('perimetreDemande', () => {
  it('lit TOUTES les sources trouvées quand rien n’est filtré', () => {
    // `_site` n'est jamais déclarée dans `RECO_SOURCES` : elle n'existe que
    // sur le disque. S'en tenir à la configuration masquait la page d'entrée.
    const p = perimetreDemande(null, ['_site', 'un-bon-moment']);

    expect(p.sources).toEqual(['_site', 'un-bon-moment']);
  });

  it('nomme les sources agrégées : un total sans périmètre ne dit rien', () => {
    expect(perimetreDemande(null, ['_site', 'un-bon-moment']).libelle)
      .toBe('tout le site · _site, un-bon-moment');
  });

  it('isole la source demandée', () => {
    const p = perimetreDemande('un-bon-moment', ['_site', 'un-bon-moment']);

    expect(p.sources).toEqual(['un-bon-moment']);
    expect(p.libelle).toBe('un-bon-moment');
  });

  it('accepte une source absente du disque plutôt que de la remplacer', () => {
    // Le tableau sera vide, et c'est la réponse juste : inventer un repli
    // afficherait les chiffres d'une AUTRE source sous le nom demandé.
    expect(perimetreDemande('jamais-vue', ['_site']).sources).toEqual(['jamais-vue']);
  });

  it('tient debout avant la première mesure', () => {
    const p = perimetreDemande(null, []);

    expect(p.sources).toEqual([]);
    expect(p.libelle).toBe('tout le site');
  });

  it('traite une chaîne vide comme une absence de filtre', () => {
    // `?source=` sans valeur ne doit pas chercher une source nommée « ».
    expect(perimetreDemande('', ['_site']).sources).toEqual(['_site']);
  });
});

describe('nbJoursDemande', () => {
  it('retient une valeur ordinaire', () => {
    expect(nbJoursDemande('7')).toBe(7);
    expect(nbJoursDemande('365')).toBe(365);
  });

  it('revient au défaut sur ce qui n’est pas un nombre', () => {
    expect(nbJoursDemande(null)).toBe(30);
    expect(nbJoursDemande('')).toBe(30);
    expect(nbJoursDemande('abc')).toBe(30);
    expect(nbJoursDemande('NaN')).toBe(30);
  });

  it('borne les valeurs venues du dehors', () => {
    // Sans borne haute, `?jours=100000` ferait parcourir des milliers de
    // dossiers à chaque affichage.
    expect(nbJoursDemande('0')).toBe(30);
    expect(nbJoursDemande('-5')).toBe(30);
    expect(nbJoursDemande('100000')).toBe(365);
    expect(nbJoursDemande('1e9')).toBe(365);
  });

  it('refuse l’infini, que Number() accepte pourtant', () => {
    expect(nbJoursDemande('Infinity')).toBe(30);
    expect(nbJoursDemande('-Infinity')).toBe(30);
  });

  it('rend un entier même sur une valeur décimale', () => {
    expect(nbJoursDemande('7.9')).toBe(7);
  });
});

// ===== lireAudience : la seule lecture de /audience et de /api/bord =========
// Tableau de bord, R9 du 28/11/2026 : les deux pages lisent par cette fonction,
// pour qu'elles ne puissent pas annoncer des chiffres différents (F2, F10).
describe('lireAudience', () => {
  // Hier : la fenêtre compte en jours avant aujourd'hui, une date en dur en sortirait.
  const JOUR = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const URL_REQUETE = new URL('https://derriere-le-proxy.test/audience');
  const SITE = new URL('https://site-public.test');
  let racine: string;

  const visite = (over: Record<string, unknown> = {}) => ({
    ts: `${JOUR}T10:00:00.000Z`, chemin: '/un-bon-moment/films', statut: 200,
    robot: false, appareil: 'mobile', provenance: null, langue: 'fr', pays: 'FR',
    visiteur: 'aaaaaaaaaaaa', dureeMs: 5, ...over,
  });
  const ecrire = (source: string, lignes: unknown[]) => {
    const dossier = path.join(racine, 'tools', 'output', 'audience', source);
    mkdirSync(dossier, { recursive: true });
    writeFileSync(
      path.join(dossier, `${JOUR}.jsonl`),
      lignes.map((l) => `${JSON.stringify(l)}\n`).join(''),
      'utf8',
    );
  };
  const lire = (o: Partial<Parameters<typeof lireAudience>[0]> = {}) =>
    lireAudience({ racine, filtre: null, nbJours: 30, site: SITE, url: URL_REQUETE, ...o });

  beforeEach(() => {
    racine = mkdtempSync(path.join(tmpdir(), 'reco-vue-'));
    // Le cas de la page : l'accueil et une 404 sous `_site`, les fiches sous la source.
    ecrire('un-bon-moment', [visite(), visite({ visiteur: 'bbbbbbbbbbbb' }), visite({ robot: true })]);
    ecrire('_site', [visite({ chemin: '/', visiteur: 'cccccccccccc' }), visite({ chemin: '/x', statut: 404 })]);
  });
  afterEach(() => {
    panne.valeur = undefined;
    rmSync(racine, { recursive: true, force: true });
  });

  it('lit toutes les sources du disque, `_site` comprise, sans filtre', () => {
    const l = lire();

    expect(l.sources).toEqual(['_site', 'un-bon-moment']);
    expect(l.libelle).toBe('tout le site · _site, un-bon-moment');
    expect(l.erreur).toBeNull();
    // L'accueil compte : sans `_site`, la page affichait 2 pages vues sur 3.
    expect(l.donnees?.pagesVues).toBe(3);
    expect(l.donnees?.visiteurs).toBe(3);
    expect(l.donnees?.erreurs404).toEqual([{ cle: '/x', n: 1 }]);
  });

  it('rend exactement ce que rend agreger() sur le même périmètre', () => {
    // La fonction ne recompte rien : elle choisit seulement ce qu'il faut lire.
    expect(lire({ nbJours: 7 }).donnees).toEqual(
      agreger({ racine, sourceId: ['_site', 'un-bon-moment'], nbJours: 7, hoteDuSite: SITE.hostname }),
    );
  });

  it('isole la source demandée', () => {
    const l = lire({ filtre: 'un-bon-moment' });

    expect(l.sources).toEqual(['un-bon-moment']);
    expect(l.libelle).toBe('un-bon-moment');
    expect(l.donnees?.pagesVues).toBe(2);
    expect(l.donnees?.erreurs404).toEqual([]);
  });

  it('écarte des provenances les pages du site public, pas celles de l’hôte du proxy', () => {
    // Derrière le proxy, l'URL de la requête n'a pas le domaine public (constaté le 2026-10-22).
    ecrire('un-bon-moment', [
      visite({ provenance: 'site-public.test' }),
      visite({ provenance: 'derriere-le-proxy.test' }),
    ]);

    expect(lire().donnees?.provenances).toEqual([{ cle: 'derriere-le-proxy.test', n: 1 }]);
  });

  it('se rabat sur l’hôte de la requête quand le site n’est pas configuré', () => {
    ecrire('un-bon-moment', [
      visite({ provenance: 'site-public.test' }),
      visite({ provenance: 'derriere-le-proxy.test' }),
    ]);

    expect(lire({ site: undefined }).donnees?.provenances).toEqual([{ cle: 'site-public.test', n: 1 }]);
  });

  it('tient debout avant la première mesure', () => {
    rmSync(path.join(racine, 'tools'), { recursive: true, force: true });
    const l = lire();

    expect(l.sources).toEqual([]);
    expect(l.libelle).toBe('tout le site');
    expect(l.donnees?.jours).toEqual([]);
    expect(l.erreur).toBeNull();
  });

  it('rend le message d’une lecture en échec, et garde le périmètre pour le titre', () => {
    // Une « source » qui est un fichier : la lecture de ses jours échoue.
    writeFileSync(path.join(racine, 'tools', 'output', 'audience', 'casse'), '');
    const l = lire({ filtre: 'casse' });

    expect(l.donnees).toBeNull();
    expect(l.erreur).toMatch(/ENOTDIR/);
    expect(l.libelle).toBe('casse');
  });

  it('rend aussi une panne qui n’est pas une Error', () => {
    panne.valeur = 'disque absent';

    expect(lire()).toMatchObject({ donnees: null, erreur: 'disque absent' });
  });
});
