import { describe, expect, it } from 'vitest';
import { titreEpisodeAffiche } from '../../src/utils/titreEpisode';

describe('titreEpisodeAffiche', () => {
  it('retire le suffixe qui répète le badge saison/épisode', () => {
    expect(
      titreEpisodeAffiche(
        'Babor et Jenny Letellier irremplaçables (Un Bon Moment, S6-E03)',
        'Un Bon Moment',
      ),
    ).toBe('Babor et Jenny Letellier irremplaçables');
  });

  it('accepte un numéro sans zéro et une casse différente', () => {
    expect(
      titreEpisodeAffiche('Manon Bril et Florent Bernard (un bon moment, S5-E1)', 'Un Bon Moment'),
    ).toBe('Manon Bril et Florent Bernard');
  });

  it('garde « hors-série », qui n’est écrit nulle part ailleurs', () => {
    const titre = 'Qui est Greg Romano ? Épisode 1 (Un Bon Moment, hors-série)';
    expect(titreEpisodeAffiche(titre, 'Un Bon Moment')).toBe(titre);
  });

  it('ne touche pas une parenthèse qui ne nomme pas le podcast', () => {
    const titre = 'Un invité (et son frère)';
    expect(titreEpisodeAffiche(titre, 'Un Bon Moment')).toBe(titre);
  });

  it('ne touche pas un suffixe placé ailleurs qu’en fin de titre', () => {
    const titre = '(Un Bon Moment, S5-E2) suite';
    expect(titreEpisodeAffiche(titre, 'Un Bon Moment')).toBe(titre);
  });

  it('échappe les caractères spéciaux du nom du podcast', () => {
    expect(titreEpisodeAffiche('Titre (C++ & Co., S1-E2)', 'C++ & Co.')).toBe('Titre');
  });

  it('rend le titre complet si le retirer le viderait', () => {
    expect(titreEpisodeAffiche('(Un Bon Moment, S5-E2)', 'Un Bon Moment')).toBe(
      '(Un Bon Moment, S5-E2)',
    );
  });

  it('ne retire rien sans nom de podcast, et tolère les valeurs absentes', () => {
    const titre = 'Titre (Un Bon Moment, S5-E2)';
    expect(titreEpisodeAffiche(titre, undefined)).toBe(titre);
    expect(titreEpisodeAffiche(titre, '  ')).toBe(titre);
    expect(titreEpisodeAffiche(undefined, 'Un Bon Moment')).toBe('');
    expect(titreEpisodeAffiche(null, null)).toBe('');
  });
});
