/**
 * `tryClientAddress` — lecture défensive de `APIContext.clientAddress`.
 *
 * Pourquoi un module partagé plutôt qu'une garde recopiée dans chaque route :
 * les deux endpoints POST du site (`/api/click`, `/api/report`) doivent lire
 * l'IP cliente, et Astro **lève** à la lecture de `clientAddress` sur une route
 * pré-rendue. La parade — lire la propriété DANS un `try` plutôt que de la
 * déstructurer dans la signature — était documentée dans `click.ts` mais
 * n'avait jamais été appliquée à `report.ts`, qui plantait donc en 500.
 *
 * Le piège est subtil (une déstructuration ressemble à un accès inoffensif),
 * donc il est capturé ici une fois pour toutes, avec ses tests.
 */
import { describe, it, expect } from 'vitest';
import { tryClientAddress } from '../../src/lib/http/clientAddress';

describe('tryClientAddress', () => {
  it('renvoie l’adresse quand elle est disponible', () => {
    expect(tryClientAddress({ clientAddress: '203.0.113.7' })).toBe('203.0.113.7');
  });

  it('renvoie null quand la propriété est absente', () => {
    expect(tryClientAddress({})).toBeNull();
  });

  it('renvoie null quand la propriété vaut undefined', () => {
    expect(tryClientAddress({ clientAddress: undefined })).toBeNull();
  });

  it('renvoie null — sans propager — quand la lecture LÈVE', () => {
    // Reproduit le comportement d'Astro sur une route pré-rendue.
    const ctx = {
      get clientAddress(): string {
        throw new Error('ClientAddressNotAvailable');
      },
    };
    expect(() => tryClientAddress(ctx)).not.toThrow();
    expect(tryClientAddress(ctx)).toBeNull();
  });

  it('ne lit la propriété qu’UNE fois par appel', () => {
    // Garde-fou : une implémentation naïve qui testerait la présence avant de
    // lire la valeur déclencherait le getter deux fois — donc deux fois
    // l'exception potentielle, et deux fois le coût côté Astro.
    let lectures = 0;
    const ctx = {
      get clientAddress(): string {
        lectures += 1;
        return '198.51.100.1';
      },
    };
    expect(tryClientAddress(ctx)).toBe('198.51.100.1');
    expect(lectures).toBe(1);
  });

  it('préserve une chaîne vide telle quelle plutôt que de la muer en null', () => {
    // `''` est une valeur que le caller doit pouvoir distinguer : c'est une
    // adresse fournie mais vide, pas une adresse indisponible.
    expect(tryClientAddress({ clientAddress: '' })).toBe('');
  });
});
