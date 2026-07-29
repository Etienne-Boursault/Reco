/**
 * Garde-fou : `happy-dom` doit rester installable.
 *
 * POURQUOI CE FICHIER EXISTE — incident du 2026-07-29.
 *
 * Les tests de ce dossier s'exécutent dans un DOM (`// @vitest-environment
 * happy-dom` en tête de fichier). Or `happy-dom` n'était déclaré nulle part :
 * il arrivait dans `node_modules` par transitivité. Une simple mise à jour de
 * `vitest` et `satori` l'a élagué — et vitest a alors **silencieusement omis**
 * les deux fichiers qui en dépendaient. La suite est restée VERTE en perdant
 * 45 tests d'un coup : 1815 → 1770, sans un seul échec, sans un avertissement.
 *
 * C'est le pire mode de défaillance possible pour une suite de tests : elle ne
 * ment pas sur ce qu'elle vérifie, elle ment sur ce qu'elle vérifie ENCORE.
 *
 * Deux protections ont été posées :
 *   1. `happy-dom` est désormais une `devDependency` EXPLICITE ;
 *   2. ce fichier, qui tourne en environnement `node` (donc toujours collecté,
 *      même si `happy-dom` disparaît) et échoue BRUYAMMENT dans ce cas.
 *
 * Ne lui ajoute pas de directive `@vitest-environment` : il perdrait
 * exactement la propriété qui fait son intérêt.
 */
import { describe, it, expect } from 'vitest';

describe('environnement de test', () => {
  it('happy-dom est résolvable — sinon les tests DOM seraient omis en silence', async () => {
    const mod = await import('happy-dom');
    expect(typeof mod.Window).toBe('function');
  });

  it('happy-dom est une dépendance déclarée, pas une transitive de passage', async () => {
    const pkg = await import('../../package.json', { with: { type: 'json' } });
    const deps = {
      ...(pkg.default.dependencies ?? {}),
      ...(pkg.default.devDependencies ?? {}),
    } as Record<string, string>;
    expect(
      deps['happy-dom'],
      'happy-dom doit rester déclaré dans package.json : sans ça, une simple ' +
        'mise à jour peut l’élaguer et faire disparaître les tests DOM sans bruit.',
    ).toBeDefined();
  });
});
