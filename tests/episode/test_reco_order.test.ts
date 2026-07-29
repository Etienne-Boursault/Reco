/**
 * Ordre d'affichage des recos.
 *
 * Pourquoi ce module existe : les pages appelaient `getCollection('recos')`
 * SANS tri, donc l'ordre affiché était celui d'énumération du chargeur de
 * fichiers d'Astro — un détail d'implémentation. La migration Astro 5 → 7 l'a
 * révélé en le changeant : mêmes recos, ordre différent, sans qu'aucun test ne
 * bronche. Le bug était latent depuis toujours ; la migration l'a seulement
 * rendu visible.
 *
 * Le tri retenu est CHRONOLOGIQUE : l'ordre dans lequel les recommandations
 * ont été prononcées dans l'épisode. C'est le seul ordre qui ait un sens pour
 * un auditeur, et les 1209 recos actives portent toutes un `timestamp`.
 */
import { describe, it, expect } from 'vitest';
import { compareRecosByTimestamp, sortRecosByTimestamp } from '../../src/utils/recoOrder';

const r = (id: string, timestamp?: string | null) => ({ id, timestamp });

describe('compareRecosByTimestamp', () => {
  it('classe la reco la plus tôt dans l’épisode en premier', () => {
    expect(compareRecosByTimestamp(r('a', '00:02:58'), r('b', '01:14:00'))).toBeLessThan(0);
    expect(compareRecosByTimestamp(r('b', '01:14:00'), r('a', '00:02:58'))).toBeGreaterThan(0);
  });

  it('compare en SECONDES et non en texte', () => {
    // '9:30' < '10:00' chronologiquement, mais '1' < '9' lexicographiquement :
    // un tri de chaînes inverserait ces deux-là.
    expect(compareRecosByTimestamp(r('a', '00:09:30'), r('b', '00:10:00'))).toBeLessThan(0);
    expect(compareRecosByTimestamp(r('a', '9:30'), r('b', '10:00'))).toBeLessThan(0);
  });

  it('départage deux recos au même timestamp par leur id, pour un ordre total', () => {
    expect(compareRecosByTimestamp(r('ubm-0001', '00:05:00'), r('ubm-0002', '00:05:00'))).toBeLessThan(0);
    expect(compareRecosByTimestamp(r('ubm-0002', '00:05:00'), r('ubm-0001', '00:05:00'))).toBeGreaterThan(0);
  });

  it('renvoie 0 pour une reco comparée à elle-même', () => {
    expect(compareRecosByTimestamp(r('a', '00:05:00'), r('a', '00:05:00'))).toBe(0);
  });

  it('range les recos sans timestamp exploitable à la fin, jamais au milieu', () => {
    for (const absent of [null, undefined, '', 'n/a']) {
      expect(compareRecosByTimestamp(r('a', absent), r('b', '99:59:59'))).toBeGreaterThan(0);
      expect(compareRecosByTimestamp(r('b', '99:59:59'), r('a', absent))).toBeLessThan(0);
    }
  });

  it('départage par id deux recos toutes deux sans timestamp', () => {
    expect(compareRecosByTimestamp(r('a', null), r('b', null))).toBeLessThan(0);
  });
});

describe('sortRecosByTimestamp', () => {
  it('trie sans muter le tableau reçu', () => {
    const entree = [r('c', '00:30:00'), r('a', '00:10:00'), r('b', '00:20:00')];
    const copie = [...entree];
    const sortie = sortRecosByTimestamp(entree);
    expect(sortie.map((x) => x.id)).toEqual(['a', 'b', 'c']);
    expect(entree).toEqual(copie);
    expect(sortie).not.toBe(entree);
  });

  it('produit le MÊME ordre quel que soit l’ordre d’entrée', () => {
    const recos = [r('a', '00:10:00'), r('b', '00:20:00'), r('c', '00:05:00')];
    const attendu = ['c', 'a', 'b'];
    expect(sortRecosByTimestamp(recos).map((x) => x.id)).toEqual(attendu);
    expect(sortRecosByTimestamp([...recos].reverse()).map((x) => x.id)).toEqual(attendu);
  });

  it('accepte un tableau vide', () => {
    expect(sortRecosByTimestamp([])).toEqual([]);
  });

  it('place toutes les recos sans timestamp en fin, ordonnées par id', () => {
    const out = sortRecosByTimestamp([r('z', null), r('m', '00:01:00'), r('a', null)]);
    expect(out.map((x) => x.id)).toEqual(['m', 'a', 'z']);
  });
});
