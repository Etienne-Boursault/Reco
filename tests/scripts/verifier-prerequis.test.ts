import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
// @ts-expect-error — module ESM sans déclaration de types
import { FICHIER_PAR_DEFAUT, ancetres, bloquantes } from '../../scripts/verifier-prerequis.mjs';

const SCRIPT = fileURLToPath(new URL('../../scripts/verifier-prerequis.mjs', import.meta.url));

/** Graphe et décisions fictifs : les vraies décisions évoluent, pas ces cas. */
const FIXTURE = {
  graphe: {
    'PR-00': [],
    'PR-03': ['PR-00'],
    'PR-04': ['PR-03'],
    'PR-MC-donnees': ['PR-00'],
    'PR-05': ['PR-04', 'PR-MC-donnees'],
    'PR-08': ['PR-05'],
  },
  decisions: [
    { id: 'D-07', sujet: 'double signature', statut: 'différé', premierePR: 'PR-08' },
    { id: 'DV-01', sujet: 'liens contradictoires', statut: 'bloquant', premierePR: 'PR-MC-donnees' },
    { id: 'Q4', sujet: "liste d'exclusion", statut: 'bloquant', premierePR: 'PR-03', moment: 'sortie' },
    { id: 'DV-03', sujet: 'propriété', statut: 'tranché', premierePR: 'PR-00' },
  ],
};

const ids = (liste: Array<{ id: string }>) => liste.map((d) => d.id).sort();

describe('verifier-prerequis — règles', () => {
  it('suit les dépendances indirectes', () => {
    expect([...ancetres(FIXTURE.graphe, 'PR-08')].sort()).toEqual(
      ['PR-00', 'PR-03', 'PR-04', 'PR-05', 'PR-MC-donnees'],
    );
  });

  it('une décision différée ne bloque rien', () => {
    expect(ids(bloquantes(FIXTURE, 'PR-08'))).not.toContain('D-07');
  });

  it('une décision bloquante bloque sa PR et ses descendantes, pas les autres', () => {
    expect(ids(bloquantes(FIXTURE, 'PR-MC-donnees'))).toEqual(['DV-01']);
    expect(ids(bloquantes(FIXTURE, 'PR-05'))).toContain('DV-01');
    expect(ids(bloquantes(FIXTURE, 'PR-03'))).not.toContain('DV-01');
  });

  it("une décision « sortie » ne bloque sa PR qu'à la fusion", () => {
    expect(ids(bloquantes(FIXTURE, 'PR-03'))).toEqual([]);
    expect(ids(bloquantes(FIXTURE, 'PR-03', { sortie: true }))).toEqual(['Q4']);
    expect(ids(bloquantes(FIXTURE, 'PR-04'))).toEqual(['Q4']);
  });

  it('une décision tranchée ne bloque rien', () => {
    expect(ids(bloquantes(FIXTURE, 'PR-00'))).toEqual([]);
  });

  it('refuse une PR inconnue', () => {
    expect(() => bloquantes(FIXTURE, 'PR-99')).toThrow('PR inconnue');
  });
});

describe('verifier-prerequis — docs/v2/decisions.json', () => {
  const donnees = JSON.parse(readFileSync(FICHIER_PAR_DEFAUT, 'utf8'));

  it('chaque décision a un identifiant unique et un statut connu', () => {
    const vus = donnees.decisions.map((d: { id: string }) => d.id);
    expect(new Set(vus).size).toBe(vus.length);
    for (const d of donnees.decisions) expect(Object.keys(donnees.statuts)).toContain(d.statut);
  });

  it('chaque décision bloquante désigne une PR du graphe', () => {
    for (const d of donnees.decisions.filter((x: { statut: string }) => x.statut === 'bloquant')) {
      expect(Object.keys(donnees.graphe)).toContain(d.premierePR);
    }
  });

  it('le graphe ne référence que des PR connues', () => {
    for (const pr of Object.keys(donnees.graphe)) expect(() => ancetres(donnees.graphe, pr)).not.toThrow();
  });

  it('la phase 0 et PR-ID ne sont bloquées par aucune décision', () => {
    for (const pr of ['PR-00', 'PR-01', 'PR-02', 'PoC-S6', 'PR-ID', 'PR-01b']) {
      expect(ids(bloquantes(donnees, pr))).toEqual([]);
    }
  });

  it('PR-03 attend la règle des épisodes publics (DV-08)', () => {
    expect(ids(bloquantes(donnees, 'PR-03'))).toEqual(['DV-08']);
  });
});

describe('verifier-prerequis — ligne de commande', () => {
  const lancer = (...args: string[]) => spawnSync(process.execPath, [SCRIPT, ...args], { encoding: 'utf8' });

  it('répond 0 quand les prérequis sont remplis', () => {
    const r = lancer('PR-00');
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('prérequis remplis');
  });

  it('répond 1 et liste les décisions qui bloquent', () => {
    const r = lancer('PR-03');
    expect(r.status).toBe(1);
    expect(r.stdout).toContain('DV-08');
  });

  it('répond 2 pour une PR inconnue ou sans argument', () => {
    expect(lancer('PR-99').status).toBe(2);
    expect(lancer().status).toBe(2);
  });
});
