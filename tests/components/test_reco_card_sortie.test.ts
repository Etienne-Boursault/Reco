/**
 * RecoCard — la mention « Sortie annoncée le … » (R4 B, 27/11/2026, tranche F).
 *
 * Les dates sont très lointaines (2099) ou très anciennes (2001) : le test ne
 * vire pas au rouge avec le temps.
 */
import { describe, expect, it } from 'vitest';

import { baseReco, parse, render } from './_reco_card';

const album = { ...baseReco, types: ['album'] };

describe('RecoCard — sortie annoncée', () => {
  it('affiche la date en toutes lettres tant qu’elle n’est pas passée', async () => {
    const doc = parse(await render({ ...album, releaseDate: '2099-03-20' }));
    const mention = doc.querySelector('.sortie');
    expect(mention?.textContent?.trim()).toBe('Sortie annoncée le 20 mars 2099');
    expect(mention?.tagName).toBe('P');
  });

  it('n’affiche rien sans date', async () => {
    const doc = parse(await render(album));
    expect(doc.querySelector('.sortie')).toBeNull();
  });

  it('n’affiche rien une fois la date passée', async () => {
    const doc = parse(await render({ ...album, releaseDate: '2001-03-20' }));
    expect(doc.querySelector('.sortie')).toBeNull();
    expect(doc.body.textContent).not.toContain('Sortie annoncée');
  });
});
