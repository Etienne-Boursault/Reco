/**
 * RecoCard — les libellés de la ligne méta (audit d'interface du 2026-10-07).
 *
 *  - #7 : le numéro d'épisode s'écrit comme le badge des vignettes
 *    (« S6·E3 »), et non plus « #3 », qui existe dans chaque saison.
 *  - #9 : une œuvre d'invité est « Présentée par » par son auteur, « Reco de »
 *    par quiconque en vante une qui n'est pas la sienne (Pulsions, Kheiron).
 *  - #8 : un lien sans logo écrit son nom, sinon deux librairies sans logo
 *    donnent deux caddies identiques.
 */
import { describe, it, expect } from 'vitest';

import { baseReco, parse, renderProps } from './_reco_card';

function meta(html: string): string {
  return parse(html).querySelector('.meta')?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

describe('RecoCard — numéro d’épisode (#7)', () => {
  it('écrit « S6·E3 » quand la saison est connue', async () => {
    const html = await renderProps({
      reco: { ...baseReco, recommendedBy: 'Babor' },
      episodeNumber: 3,
      episodeSeason: 6,
    });
    expect(meta(html)).toContain('S6·E3');
    expect(meta(html)).not.toContain('#3');
  });

  it('garde « #3 » pour un épisode sans saison', async () => {
    const html = await renderProps({
      reco: { ...baseReco, recommendedBy: 'Babor' },
      episodeNumber: 3,
    });
    expect(meta(html)).toContain('#3');
  });

  it('retombe sur le titre de l’épisode sans numéro', async () => {
    const html = await renderProps({
      reco: { ...baseReco, recommendedBy: 'Babor' },
      episodeTitle: 'Hors-série',
    });
    expect(meta(html)).toContain('Hors-série');
  });
});

describe('RecoCard — verbe de la ligne méta (#9)', () => {
  it('œuvre d’invité présentée par son auteur → « Présentée par », même badge masqué', async () => {
    for (const showGuestWorkBadge of [true, false]) {
      const html = await renderProps({
        reco: { ...baseReco, guestWork: true, recommendedBy: 'Kyan Khojandi', creator: 'Kyan Khojandi, Navo' },
        showGuestWorkBadge,
      });
      expect(meta(html)).toContain('Présentée par Kyan Khojandi');
      expect(meta(html)).not.toContain('Reco de');
    }
  });

  it('œuvre d’invité vantée par un autre → « Reco de » (Kheiron et Pulsions)', async () => {
    const html = await renderProps({
      reco: { ...baseReco, guestWork: true, recommendedBy: 'Kheiron', creator: 'Kyan Khojandi, Navo' },
    });
    expect(meta(html)).toContain('Reco de Kheiron');
    expect(meta(html)).not.toContain('Présentée par');
  });

  it('la citation prime sur l’œuvre d’invité → « Évoquée par »', async () => {
    const html = await renderProps({
      reco: { ...baseReco, kind: 'citation', guestWork: true, recommendedBy: 'Navo' },
    });
    expect(meta(html)).toContain('Évoquée par Navo');
  });
});

describe('RecoCard — liens sans logo nommés en toutes lettres (#8)', () => {
  const reco = {
    ...baseReco,
    types: ['livre'],
    links: [
      { label: 'Leslibraires.fr', url: 'https://www.leslibraires.fr/livre/1', kind: 'buy', ethics: 'indie' },
      { label: 'Librairie des femmes', url: 'https://www.librairie-des-femmes.fr/livre/2', kind: 'buy', ethics: 'indie' },
      { label: 'Instagram', url: 'https://www.instagram.com/quelquun/', kind: 'social', ethics: 'neutral' },
    ],
  };

  it('deux liens au même symbole se distinguent par leur nom visible', async () => {
    const doc = parse(await renderProps({ reco }));
    const libelles = [...doc.querySelectorAll('.link--libelle .link-label')].map((e) => e.textContent);
    expect(libelles).toEqual(['Leslibraires.fr', 'Librairie des femmes']);
  });

  it('un lien à logo reste une pastille ronde, sans libellé visible', async () => {
    const doc = parse(await renderProps({ reco }));
    const insta = doc.querySelector('a[href*="instagram.com"]')!;
    expect(insta.className).not.toContain('link--libelle');
    expect(insta.querySelector('.link-label')).toBeNull();
  });
});
