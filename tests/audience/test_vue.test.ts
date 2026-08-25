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
import { describe, expect, it } from 'vitest';

import { nbJoursDemande, perimetreDemande } from '../../src/lib/audience/vue';

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
