/**
 * Compteurs qui codaient « 1 » en dur dans leur clé de traduction.
 *
 * BUG CONSTATÉ SUR LE SITE CONSTRUIT (revue d'architecture, 2026-07-29) :
 * l'épisode « avec MCFLY ET CARLITO » n'a aucune recommandation, et affichait
 *
 *     <p class="count"> 1 recommandation </p>      <- en-tête
 *     Aucune recommandation extraite de cet épisode.   <- corps
 *
 * sur la même page. Deux causes cumulées :
 *   1. le seuil était `count > 1`, alors que la règle du projet
 *      (`src/utils/plural.ts`) est « pluriel dès n >= 2 » — donc 0 ET 1 au
 *      singulier. À 0, `> 1` est faux et bascule sur la clé singulier ;
 *   2. la clé singulier codait le nombre EN DUR (`'1 recommandation'`), donc
 *      elle affichait « 1 » pour n'importe quelle valeur singulière.
 *
 * Le cas est atteignable par construction : `getStaticPaths` génère
 * explicitement les épisodes sans reco validée (le catalogue y renvoie).
 */
import { describe, it, expect } from 'vitest';
import { t } from '../../src/i18n';

/** Reproduit le choix de clé fait par les pages, après correction. */
const libelle = (n: number, base: string) =>
  n >= 2 ? t(`${base}.many` as never, { count: n }) : t(`${base}.one` as never, { count: n });

describe('compteurs d’épisode — le nombre vient du compte, jamais de la clé', () => {
  it.each([
    ['episode.count.recommendations', 0, '0 recommandation'],
    ['episode.count.recommendations', 1, '1 recommandation'],
    ['episode.count.recommendations', 2, '2 recommandations'],
    ['episode.count.recommendations', 12, '12 recommandations'],
    ['episode.count.citations', 0, '0 mention'],
    ['episode.count.citations', 1, '1 mention'],
    ['episode.count.citations', 3, '3 mentions'],
  ])('%s à %i → « %s »', (base, n, attendu) => {
    expect(libelle(n, base)).toBe(attendu);
  });

  it('zéro ne peut plus afficher « 1 » — le cas qui a produit le bug', () => {
    expect(libelle(0, 'episode.count.recommendations')).not.toContain('1 ');
    expect(libelle(0, 'episode.count.citations')).not.toContain('1 ');
  });
});

describe('compteur du méta-index — même défaut, même correction', () => {
  it.each([
    [0, '0 podcast indexé'],
    [1, '1 podcast indexé'],
    [2, '2 podcasts indexés'],
  ])('%i → « %s »', (n, attendu) => {
    expect(libelle(n, 'meta.podcastCount')).toBe(attendu);
  });

  it('à 0 le singulier s’applique, contrairement à `count === 1`', () => {
    // La page utilisait `count === 1 ? .one : .many`, seule des quatre
    // orthographes du seuil dans le dépôt à violer la règle : elle rendait
    // « 0 podcasts indexés » au pluriel.
    expect(libelle(0, 'meta.podcastCount')).not.toContain('podcasts');
  });
});
