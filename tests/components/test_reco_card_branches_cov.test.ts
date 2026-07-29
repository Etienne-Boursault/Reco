/**
 * Branches restantes de `RecoCard.astro` — les cas NON nominaux du travail
 * récent (symbole par type de lien, normalisation des hosts, lien
 * « Signaler », année volontairement masquée).
 *
 * Complément de `test_reco_card.test.ts`, qui couvre le nominal. Ici : type
 * inconnu, champs absents, `linkOverrides`, `logoUrl` invalide, extrait
 * Acast, et la clé de recherche SSR construite avec des champs manquants.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import RecoCard from '../../src/components/RecoCard.astro';

async function render(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(RecoCard as any, { props });
}

const baseReco = {
  id: 'ubm-0001',
  title: 'Mon spectacle',
  creator: 'Untel',
  types: ['spectacle'],
};

/** Valeur de `data-search` (clé de recherche normalisée SSR). */
function searchKey(html: string): string {
  return html.match(/data-search="([^"]*)"/)?.[1] ?? '';
}

describe('RecoCard — types inconnus', () => {
  it('type hors catalogue → emoji ✨ et libellé = clé brute', async () => {
    const html = await render({ reco: { ...baseReco, types: ['zarbi'] } });
    expect(html).toContain('✨');
    expect(html).toContain('aria-label="zarbi"');
    expect(html).toContain('data-types="zarbi"');
  });

  it('mélange type connu / inconnu → les deux libellés dans le nom accessible', async () => {
    const html = await render({ reco: { ...baseReco, types: ['film', 'zarbi'] } });
    expect(html).toContain('aria-label="Film, zarbi"');
  });

  it('liste de types absente → aucun emoji, data-types vide', async () => {
    const html = await render({ reco: { ...baseReco, types: undefined } });
    expect(html).toContain('Mon spectacle');
    expect(html).not.toContain('type-emoji');
  });
});

describe('RecoCard — clé de recherche SSR', () => {
  it('concatène titre, créateur, libellés de type et titre d’épisode, sans accents', async () => {
    const html = await render({
      reco: { ...baseReco, title: 'Été brûlant', creator: 'Éric', types: ['film'] },
      episodeTitle: 'Épisode Ça',
    });
    expect(searchKey(html)).toBe('ete brulant eric film episode ca');
  });

  it('créateur et titre d’épisode absents → pas de « undefined » dans la clé', async () => {
    const html = await render({ reco: { ...baseReco, creator: undefined, types: ['film'] } });
    const key = searchKey(html);
    expect(key).not.toContain('undefined');
    expect(key).toContain('mon spectacle');
    expect(key).toContain('film');
  });
});

describe('RecoCard — métadonnées absentes', () => {
  it('sans créateur → aucune ligne créateur ni pastille de signalement', async () => {
    const html = await render({ reco: { ...baseReco, creator: undefined } });
    expect(html).not.toContain('class="creator"');
    expect(html).not.toContain('creator-flag');
  });

  it('créateur signalé → pastille interactive (la carte n’est pas un lien)', async () => {
    const html = await render({ reco: { ...baseReco, creator: 'Roman Polanski' } });
    expect(html).toContain('creator-flag');
    expect(html).toContain('<details');
  });

  it('ni recommendedBy ni épisode → bloc meta vide', async () => {
    const html = await render({ reco: baseReco });
    expect(html).not.toContain('class="by"');
    expect(html).not.toContain('class="ep"');
  });

  it('episodeNumber prime sur episodeTitle', async () => {
    const html = await render({
      reco: baseReco,
      episodeNumber: 7,
      episodeTitle: 'Titre ignoré',
    });
    expect(html).toContain('#7');
    expect(html).not.toMatch(/class="ep"[^>]*>Titre ignoré/);
  });

  it('l’année reste masquée sur la carte même quand elle est connue', async () => {
    const html = await render({ reco: { ...baseReco, year: 1999 } });
    expect(html).not.toContain('1999');
  });
});

describe('RecoCard — extrait audio', () => {
  it('audio avec acastUrl seul → bloc audio en repli Acast', async () => {
    const html = await render({
      reco: baseReco,
      audio: { acastUrl: 'https://shows.acast.com/ubm/episodes/x' },
    });
    expect(html).toContain('card-audio');
    expect(html).toContain('audio-external');
  });

  it('audio fourni mais vide → aucun bloc audio', async () => {
    const html = await render({
      reco: baseReco,
      audio: { youtubeId: null, acastUrl: null },
    });
    expect(html).not.toContain('card-audio');
  });

  it('youtubeId + startSeconds → extrait horodaté', async () => {
    const html = await render({
      reco: baseReco,
      audio: { youtubeId: 'dQw4w9WgXcQ', startSeconds: 90 },
    });
    expect(html).toContain('card-audio');
    expect(html).toContain('start=90');
  });
});

describe('RecoCard — liens : overrides et cas limites', () => {
  it('linkOverrides remplace l’URL d’un lien auto-généré ciblé par son label', async () => {
    const html = await render({
      reco: {
        ...baseReco,
        types: ['livre'],
        linkOverrides: { 'Place des Libraires': 'https://www.placedeslibraires.fr/livre/123' },
      },
    });
    expect(html).toContain('https://www.placedeslibraires.fr/livre/123');
    expect(html).not.toContain('placedeslibraires.fr/listeliv.php');
  });

  it('un linkOverrides qui ne matche aucun label ne change rien', async () => {
    const sansOverride = await render({ reco: { ...baseReco, types: ['livre'] } });
    const avecOverride = await render({
      reco: { ...baseReco, types: ['livre'], linkOverrides: { 'Label inconnu': 'https://x.test/' } },
    });
    expect(avecOverride).toBe(sansOverride);
  });

  it('URL syntaxiquement invalide → lien filtré (aucune icône ni href cassé)', async () => {
    const html = await render({
      reco: {
        ...baseReco,
        types: ['autre'],
        links: [{ label: 'Cassé', url: 'http://[invalide', kind: 'info' }],
      },
    });
    expect(html).not.toContain('[invalide');
  });

  it('logoUrl non http(s) → ignoré, repli sur le symbole du type de lien', async () => {
    const html = await render({
      reco: {
        ...baseReco,
        types: ['autre'],
        customLinks: [
          { label: 'MonLien', url: 'https://example.com/x', logoUrl: 'javascript:alert(1)' },
        ],
      },
    });
    expect(html).not.toContain('javascript:');
    expect(html).toContain('link-symbol');
  });

  it('logoUrl syntaxiquement invalide → ignoré sans planter', async () => {
    const html = await render({
      reco: {
        ...baseReco,
        types: ['autre'],
        customLinks: [
          { label: 'MonLien', url: 'https://example.com/x', logoUrl: 'https://[cassé' },
        ],
      },
    });
    expect(html).toContain('link-symbol');
    expect(html).not.toContain('[cassé');
  });

  it('reco.links vide → on retombe sur les liens générés par le résolveur', async () => {
    const html = await render({ reco: { ...baseReco, types: ['film'], links: [] } });
    expect(html).toContain('justwatch.com');
  });

  it('aucun lien exploitable → pas de rangée d’icônes', async () => {
    const html = await render({
      reco: {
        ...baseReco,
        types: ['autre'],
        links: [{ label: 'Evil', url: 'javascript:alert(1)' }],
      },
    });
    expect(html).not.toContain('class="links"');
  });

  it('le symbole de repli d’un lien sans kind est le maillon générique', async () => {
    const html = await render({
      reco: {
        ...baseReco,
        types: ['autre'],
        links: [{ label: 'X', url: 'https://exemple-non-whiteliste.test/x' }],
      },
    });
    expect(html).toContain('🔗');
  });

  it('lien indépendant → classe .indie et title sans avertissement', async () => {
    const html = await render({
      reco: {
        ...baseReco,
        types: ['autre'],
        links: [{ label: 'Bandcamp', url: 'https://bandcamp.com/x', ethics: 'indie' }],
      },
    });
    expect(html).toContain('link indie');
    expect(html).toContain('title="Bandcamp"');
  });
});

describe('RecoCard — badge guestWork et lien Signaler', () => {
  it('showGuestWorkBadge=true explicite garde le badge', async () => {
    const html = await render({
      reco: { ...baseReco, guestWork: true },
      showGuestWorkBadge: true,
    });
    expect(html).toContain('guestwork-badge');
  });

  it('le lien Signaler pointe vers la source ET l’identifiant de la reco', async () => {
    const html = await render({ reco: baseReco, sourceId: 'autre-source' });
    expect(html).toContain('href="/autre-source/report/ubm-0001"');
  });

  it('sans sourceId, les liens sortants sont tracés avec sourceId=unknown', async () => {
    const html = await render({ reco: { ...baseReco, types: ['film'] } });
    expect(html).toContain('data-source-id="unknown"');
  });
});
