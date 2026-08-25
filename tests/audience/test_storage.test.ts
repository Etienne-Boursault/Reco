/**
 * Tests de `src/lib/audience/storage.mjs` — l'écriture des visites.
 *
 * CE QU'ILS PROTÈGENT
 * -------------------
 * Ce module est appelé sur le chemin de CHAQUE requête. La propriété qui
 * compte le plus n'est donc pas qu'il écrive bien, mais qu'il n'échoue
 * jamais bruyamment : un disque plein ne doit pas empêcher une page de
 * s'afficher. Le reste — découpage par jour, format — est vérifiable une fois.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mkdtempSync, readFileSync, rmSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

// @ts-expect-error — module `.mjs` sans déclaration de types
import { enregistrer, fichierDuJour, racineAudience } from '../../src/lib/audience/storage.mjs';

let racine: string;

const EVENEMENT = {
  ts: '2026-08-25T14:00:00.000Z',
  chemin: '/un-bon-moment/films',
  statut: 200,
  robot: false,
  appareil: 'ordinateur',
  provenance: 'www.google.com',
  langue: 'fr',
  pays: 'FR',
  visiteur: 'a1b2c3d4e5f6',
  dureeMs: 38,
};

beforeEach(() => {
  racine = mkdtempSync(path.join(tmpdir(), 'reco-audience-'));
  // Le garde anti-répétition du journal est un état de module : on le remet à
  // zéro, sinon le premier test qui échoue rendrait les suivants muets.
  (enregistrer as { _prevenu?: boolean })._prevenu = false;
});

afterEach(() => rmSync(racine, { recursive: true, force: true }));

describe('écriture', () => {
  it('écrit une ligne JSON par visite', () => {
    expect(enregistrer(EVENEMENT, 'un-bon-moment', racine)).toBe(true);

    const fichier = fichierDuJour('un-bon-moment', new Date(EVENEMENT.ts), racine);
    const lignes = readFileSync(fichier, 'utf8').trim().split('\n');
    expect(lignes).toHaveLength(1);
    expect(JSON.parse(lignes[0])).toEqual(EVENEMENT);
  });

  it('ajoute à la suite sans écraser', () => {
    enregistrer(EVENEMENT, 'un-bon-moment', racine);
    enregistrer({ ...EVENEMENT, chemin: '/autre' }, 'un-bon-moment', racine);

    const fichier = fichierDuJour('un-bon-moment', new Date(EVENEMENT.ts), racine);
    expect(readFileSync(fichier, 'utf8').trim().split('\n')).toHaveLength(2);
  });

  it('sépare les jours', () => {
    // Le découpage quotidien est ce qui rend l'agrégation lisible, et permet
    // de supprimer une période sans toucher au reste.
    enregistrer(EVENEMENT, 'un-bon-moment', racine);
    enregistrer({ ...EVENEMENT, ts: '2026-08-26T09:00:00.000Z' }, 'un-bon-moment', racine);

    expect(existsSync(fichierDuJour('un-bon-moment', new Date('2026-08-25T00:00:00Z'), racine)))
      .toBe(true);
    expect(existsSync(fichierDuJour('un-bon-moment', new Date('2026-08-26T00:00:00Z'), racine)))
      .toBe(true);
  });

  it('sépare les sources', () => {
    enregistrer(EVENEMENT, 'un-bon-moment', racine);
    enregistrer(EVENEMENT, 'autre-podcast', racine);

    expect(existsSync(path.join(racineAudience(racine), 'un-bon-moment'))).toBe(true);
    expect(existsSync(path.join(racineAudience(racine), 'autre-podcast'))).toBe(true);
  });
});

describe('robustesse — une écriture ne casse jamais une page', () => {
  it('rend false au lieu de lever quand le disque refuse', () => {
    // Un dossier inaccessible ne doit pas remonter jusqu'au visiteur.
    const journal = { warn: vi.fn() };
    const ok = enregistrer(EVENEMENT, 'un-bon-moment', '/chemin/qui/nexiste/pas\0invalide', journal);

    expect(ok).toBe(false);
    expect(journal.warn).toHaveBeenCalled();
  });

  it('ne prévient qu’une fois : sinon le journal noie la panne', () => {
    const journal = { warn: vi.fn() };
    for (let i = 0; i < 5; i += 1) {
      enregistrer(EVENEMENT, 'un-bon-moment', '/chemin\0invalide', journal);
    }

    expect(journal.warn).toHaveBeenCalledTimes(1);
  });

  it('refuse un identifiant de source douteux', () => {
    // Il compose un chemin de fichier : une traversée de répertoire passerait
    // par là.
    expect(enregistrer(EVENEMENT, '../../etc', racine)).toBe(false);
    expect(enregistrer(EVENEMENT, '', racine)).toBe(false);
  });

  it('refuse une ligne démesurée plutôt que de casser l’atomicité', () => {
    // Au-delà de PIPE_BUF, deux ajouts concurrents peuvent s'entrelacer et
    // corrompre le fichier.
    const enorme = { ...EVENEMENT, chemin: '/' + 'x'.repeat(5000) };
    expect(enregistrer(enorme, 'un-bon-moment', racine)).toBe(false);
  });
});
