/**
 * Tests de `src/lib/audience/acces.mjs` — le garde du tableau de bord.
 *
 * CE QU'ILS PROTÈGENT
 * -------------------
 * Le dépôt a déjà livré une page interne protégée par le seul `noindex` :
 * `/[source]/reports` rendait des adresses e-mail de visiteurs, lisibles par
 * quiconque connaissait l'URL. La leçon tient en une phrase, écrite dans ce
 * fichier même : découvrabilité n'est pas accès.
 *
 * D'où deux propriétés vérifiées ici, et pas seulement « la bonne clé
 * passe » : sans clé configurée la page n'existe pas, et une clé trop courte
 * n'en est pas une.
 */
import { describe, expect, it } from 'vitest';

// @ts-expect-error — module `.mjs` sans déclaration de types
import { acces, cleAttendue, cleValide, LONGUEUR_MINIMALE } from '../../src/lib/audience/acces.mjs';

const CLE = 'une-cle-de-vingt-huit-signes';

describe('la clé attendue', () => {
  it('vient de l’environnement', () => {
    expect(cleAttendue({ RECO_AUDIENCE_KEY: CLE })).toBe(CLE);
  });

  it('est null quand rien n’est configuré', () => {
    // Le tableau de bord doit alors être ABSENT, pas ouvert.
    expect(cleAttendue({})).toBeNull();
  });

  it('refuse une clé trop courte : elle se devinerait', () => {
    expect(cleAttendue({ RECO_AUDIENCE_KEY: 'court' })).toBeNull();
    expect(CLE.length).toBeGreaterThanOrEqual(LONGUEUR_MINIMALE);
  });
});

describe('la comparaison', () => {
  it('accepte la bonne clé', () => {
    expect(cleValide(CLE, CLE)).toBe(true);
  });

  it('refuse une clé fausse de même longueur', () => {
    const fausse = 'une-cle-de-vingt-huit-signeX';
    expect(fausse).toHaveLength(CLE.length);
    expect(cleValide(fausse, CLE)).toBe(false);
  });

  it('refuse un préfixe correct', () => {
    // Le cas que `timingSafeEqual` seul, sur des tampons de tailles
    // différentes, ferait échouer par exception plutôt que par refus.
    expect(cleValide('une-cle-de', CLE)).toBe(false);
  });

  it('refuse une clé plus longue qui commence pareil', () => {
    expect(cleValide(CLE + 'suite', CLE)).toBe(false);
  });

  it('refuse une valeur absente ou d’un autre type', () => {
    expect(cleValide(undefined, CLE)).toBe(false);
    expect(cleValide(null, CLE)).toBe(false);
    expect(cleValide(123 as never, CLE)).toBe(false);
    expect(cleValide('', CLE)).toBe(false);
  });

  it('refuse toujours quand l’attendue est trop courte', () => {
    // Ceinture et bretelles : même si `cleAttendue` était contournée.
    expect(cleValide('abc', 'abc')).toBe(false);
  });
});

describe('la décision d’accès', () => {
  it('ouvre avec la bonne clé', () => {
    expect(acces(CLE, { RECO_AUDIENCE_KEY: CLE })).toEqual({ ouvert: true, raison: null });
  });

  it('ferme avec une mauvaise clé', () => {
    expect(acces('mauvaise-cle-de-la-bonne-taille', { RECO_AUDIENCE_KEY: CLE }))
      .toEqual({ ouvert: false, raison: 'cle-invalide' });
  });

  it('ferme quand rien n’est configuré, même sans clé fournie', () => {
    // Mieux vaut une absence qu'une porte ouverte par oubli.
    expect(acces(undefined, {})).toEqual({ ouvert: false, raison: 'non-configure' });
    expect(acces('nimporte-quoi-de-bonne-taille', {}))
      .toEqual({ ouvert: false, raison: 'non-configure' });
  });

  it('distingue les deux refus : l’un se corrige, l’autre se configure', () => {
    const sansConfig = acces(CLE, {});
    const mauvaiseCle = acces('x'.repeat(28), { RECO_AUDIENCE_KEY: CLE });

    expect(sansConfig.raison).toBe('non-configure');
    expect(mauvaiseCle.raison).toBe('cle-invalide');
  });
});
