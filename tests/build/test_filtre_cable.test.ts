/**
 * Garde : un composant qui rend l'interface de filtrage doit EMBARQUER son
 * câblage.
 *
 * POURQUOI CE FICHIER EXISTE — incident du 2026-08-18
 * ---------------------------------------------------
 * `AllRecosView.astro` rend le champ `#search`, les puces `.chip` et la
 * grille `#reco-grid`. Le code qui les anime vivait dans `SourceCatalog.astro`.
 * Astro n'embarque que les scripts des composants RÉELLEMENT rendus : sur
 * `/[source]/recos`, qui monte le premier sans le second, le champ existait
 * donc sans le moindre écouteur. On pouvait taper, rien ne se passait.
 *
 * C'est la deuxième fois que ce mécanisme casse la page : le 2026-08-17, les
 * styles des cartes avaient disparu pour exactement la même raison. La
 * dépendance est invisible à la lecture — d'où cette garde.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const COMPOSANTS = 'src/components';

function fichiersAstro(): string[] {
  return readdirSync(COMPOSANTS).filter((f) => f.endsWith('.astro'));
}

/** Rend-il l'interface que `filtreRecos` pilote ? */
function rendLeFiltre(source: string): boolean {
  return source.includes('id="search"') && source.includes('id="reco-grid"');
}

describe('câblage du filtre de recos', () => {
  it('trouve bien des composants à vérifier', () => {
    const concernes = fichiersAstro().filter((f) =>
      rendLeFiltre(readFileSync(join(COMPOSANTS, f), 'utf8')));
    // Sans cette assertion, la garde passerait sur zéro fichier et
    // annoncerait une santé qu'elle n'a jamais constatée.
    expect(concernes.length).toBeGreaterThan(0);
  });

  it.each(fichiersAstro())('%s : rend le filtre ⇒ importe son câblage', (nom) => {
    const source = readFileSync(join(COMPOSANTS, nom), 'utf8');
    if (!rendLeFiltre(source)) return;
    expect(
      source.includes('filtreRecos'),
      `${nom} rend « #search » et « #reco-grid » sans importer ` +
        `« filtreRecos » : sur une page qui ne monte que ce composant, le ` +
        `champ n'aura aucun écouteur.`,
    ).toBe(true);
  });
});
