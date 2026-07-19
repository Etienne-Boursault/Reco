/**
 * Tests RecoCard — Story 4 (marqueur « œuvre d'invité ») + badges de nature.
 *
 * On vérifie le badge distinct affiché quand `reco.guestWork === true`, et
 * l'absence de badge sinon. Le combo legacy citation + guestWork verrouille
 * l'affichage des DEUX badges (NIT-9).
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import RecoCard from '../../src/components/RecoCard.astro';

async function render(reco: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(RecoCard as any, { props: { reco } });
}

const baseReco = {
  id: 'ubm-0001',
  title: 'Mon spectacle',
  creator: 'Untel',
  types: ['spectacle'],
};

describe('RecoCard — marqueur œuvre d\'invité (Story 4)', () => {
  it('affiche le badge ⭐ « Leur œuvre » quand guestWork=true', async () => {
    const html = await render({ ...baseReco, guestWork: true });
    expect(html).toContain('guestwork-badge');
    // M3 : ⭐ (le 🎤 entrait en collision avec TYPE_EMOJIS['artiste']).
    expect(html).toContain('⭐');
    // Libellé 2026-07-07 : guestWork couvre invité·es ET hosts.
    expect(html).toContain('Leur œuvre');
  });

  it('n\'utilise plus 🎤 pour le badge guestWork (collision type artiste, M3)', async () => {
    const html = await render({ ...baseReco, guestWork: true });
    expect(html).not.toContain('🎤');
  });

  it('n\'affiche aucun badge guestWork quand le flag est absent', async () => {
    const html = await render(baseReco);
    expect(html).not.toContain('guestwork-badge');
    expect(html).not.toContain('⭐');
  });

  it('masque le badge guestWork quand showGuestWorkBadge=false (N5)', async () => {
    const container = await AstroContainer.create();
    const html = await container.renderToString(RecoCard as any, {
      props: { reco: { ...baseReco, guestWork: true }, showGuestWorkBadge: false },
    });
    expect(html).not.toContain('guestwork-badge');
    expect(html).not.toContain('⭐');
    // La carte s'affiche toujours (titre présent).
    expect(html).toContain('Mon spectacle');
  });

  it('n\'affiche pas le badge citation pour une œuvre d\'invité (reste kind=reco)', async () => {
    const html = await render({ ...baseReco, guestWork: true });
    // Le badge « Mentionné » (citation) ne doit pas apparaître.
    expect(html).not.toContain('Mentionné');
  });

  it('badge citation passe par i18n (NIT-8)', async () => {
    const html = await render({ ...baseReco, kind: 'citation' });
    expect(html).toContain('📝');
    expect(html).toContain('Mentionné');
  });

  it('combo legacy citation + guestWork → les DEUX badges (NIT-9)', async () => {
    const html = await render({ ...baseReco, kind: 'citation', guestWork: true });
    expect(html).toContain('Mentionné'); // badge citation
    expect(html).toContain('⭐'); // badge œuvre d'invité (M3)
    expect(html).toContain('guestwork-badge');
  });
});

/** Rendu avec props complètes (sourceId, audio, etc.). */
async function renderProps(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(RecoCard as any, { props });
}

// ---------------------------------------------------------------------------
// Sécurité des href (S2 — validateur unifié `isSafeUrl` de merchants)
// ---------------------------------------------------------------------------
describe('RecoCard — sécurité des liens (S2)', () => {
  it('filtre un lien javascript: (aucun href hostile rendu)', async () => {
    const html = await renderProps({
      reco: {
        ...baseReco,
        types: ['film'],
        links: [
          { label: 'Evil', url: 'javascript:alert(1)' },
          { label: 'JustWatch', url: 'https://www.justwatch.com/fr/film/x' },
        ],
      },
    });
    expect(html).not.toContain('javascript:');
    expect(html).toContain('justwatch.com');
  });

  it('C2 — un lien explicite vers un domaine banni (Amazon) est retiré', async () => {
    const html = await renderProps({
      reco: {
        ...baseReco,
        types: ['film'],
        links: [
          { label: 'Amazon', url: 'https://www.amazon.fr/dp/x' },
          { label: 'JustWatch', url: 'https://www.justwatch.com/fr/film/x' },
        ],
      },
    });
    expect(html).not.toContain('amazon.fr');
    expect(html).toContain('justwatch.com');
  });
});

// ---------------------------------------------------------------------------
// Résolution d'icône (favicon self-hosted, whitelist host)
// ---------------------------------------------------------------------------
describe('RecoCard — icônes de plateforme', () => {
  it('host whitelisté → /icons/platforms/<host>.svg', async () => {
    const html = await render({ ...baseReco, types: ['film'] });
    // film → JustWatch (www.justwatch.com est whitelisté).
    expect(html).toContain('/icons/platforms/www.justwatch.com.svg');
  });

  it('host non whitelisté → placeholder link.svg', async () => {
    const html = await renderProps({
      reco: {
        ...baseReco,
        types: ['autre'],
        links: [{ label: 'Example', url: 'https://example.com/x' }],
      },
    });
    expect(html).toContain('/icons/platforms/link.svg');
    expect(html).not.toContain('example.com.svg');
  });

  it('logoUrl custom sur host whitelisté : utilisé comme <img src>', async () => {
    const html = await renderProps({
      reco: {
        ...baseReco,
        types: ['autre'],
        customLinks: [
          {
            label: 'MonLien',
            url: 'https://example.com/x',
            logoUrl: 'https://bandcamp.com/logo.png',
          },
        ],
      },
    });
    expect(html).toContain('https://bandcamp.com/logo.png');
  });

  it('logoUrl custom sur host NON whitelisté : ignoré (no-tracker), fallback link.svg', async () => {
    const html = await renderProps({
      reco: {
        ...baseReco,
        types: ['autre'],
        customLinks: [
          {
            label: 'MonLien',
            url: 'https://example.com/x',
            logoUrl: 'https://tracker.evil/logo.png',
          },
        ],
      },
    });
    expect(html).not.toContain('tracker.evil');
    expect(html).toContain('/icons/platforms/link.svg');
  });
});

// ---------------------------------------------------------------------------
// Dédup par label + cap à 6
// ---------------------------------------------------------------------------
describe('RecoCard — dédup & cap des liens', () => {
  it('cap à 6 liens (le 7e — Tidal — est coupé)', async () => {
    const html = await render({ ...baseReco, types: ['musique'] });
    // musique génère 7 liens ; slice(0,6) coupe Tidal (7e).
    expect(html).toContain('YT Music'); // 6e, présent
    expect(html).not.toContain('Tidal'); // 7e, coupé
  });

  it('dédup par label : un customLink prime sur le lien auto homonyme', async () => {
    const html = await renderProps({
      reco: {
        ...baseReco,
        types: ['musique'],
        customLinks: [
          { label: 'Bandcamp', url: 'https://custom.example/bc' },
        ],
      },
    });
    // Le customLink « Bandcamp » gagne ; le lien auto (bandcamp.com/search) saute.
    expect(html).toContain('custom.example/bc');
    expect(html).not.toContain('bandcamp.com/search');
  });
});

// ---------------------------------------------------------------------------
// Classes éthiques (indie / avoid)
// ---------------------------------------------------------------------------
describe('RecoCard — marqueurs éthiques', () => {
  it('ethics indie → classe .indie (Place des Libraires)', async () => {
    const html = await render({ ...baseReco, types: ['livre'] });
    expect(html).toContain('link indie');
  });

  it('ethics avoid → classe .avoid + titre « moins recommandée »', async () => {
    const html = await renderProps({
      reco: {
        ...baseReco,
        types: ['film'],
        // primevideo.com n'est PAS banni (≠ amazon.fr) mais marqué avoid.
        links: [
          { label: 'Prime Video', url: 'https://primevideo.com/detail/x', ethics: 'avoid' },
        ],
      },
    });
    expect(html).toContain('link avoid');
    expect(html).toContain('moins recommandée');
  });
});

// ---------------------------------------------------------------------------
// Multi-types (emoji par type + data-types)
// ---------------------------------------------------------------------------
describe('RecoCard — multi-types', () => {
  it('affiche un emoji par type et expose data-types', async () => {
    const html = await render({ ...baseReco, types: ['film', 'livre'] });
    expect(html).toContain('data-types="film,livre"');
    expect(html).toContain('🎬'); // film
    expect(html).toContain('📖'); // livre
  });
});

// ---------------------------------------------------------------------------
// Métadonnées (année, « Reco de … », label épisode)
// ---------------------------------------------------------------------------
describe('RecoCard — métadonnées', () => {
  it('rend l’année, « Reco de … » et le label épisode', async () => {
    const html = await renderProps({
      reco: { ...baseReco, year: 2021, recommendedBy: 'Kyan' },
      episodeNumber: 42,
    });
    expect(html).toContain('2021');
    expect(html).toContain('Reco de Kyan');
    expect(html).toContain('#42');
  });

  it('replie sur episodeTitle quand episodeNumber est absent', async () => {
    const html = await renderProps({
      reco: baseReco,
      episodeTitle: 'Un bon épisode',
    });
    expect(html).toContain('Un bon épisode');
  });
});

// ---------------------------------------------------------------------------
// Lien « Signaler » (X3) — présent ssi sourceId, rel=nofollow
// ---------------------------------------------------------------------------
describe('RecoCard — lien Signaler', () => {
  it('présent avec sourceId (href /<source>/report/<id>, rel=nofollow)', async () => {
    const html = await renderProps({ reco: baseReco, sourceId: 'ubm' });
    expect(html).toContain('report-link');
    expect(html).toContain('href="/ubm/report/ubm-0001"');
    expect(html).toContain('rel="nofollow"');
  });

  it('absent sans sourceId', async () => {
    const html = await render(baseReco);
    expect(html).not.toContain('report-link');
  });
});

// ---------------------------------------------------------------------------
// Slot audio (item #12)
// ---------------------------------------------------------------------------
describe('RecoCard — extrait audio', () => {
  it('rend le bloc audio quand un youtubeId est fourni', async () => {
    const html = await renderProps({
      reco: baseReco,
      audio: { youtubeId: 'dQw4w9WgXcQ' },
    });
    expect(html).toContain('card-audio');
  });

  it('pas de bloc audio quand audio est absent', async () => {
    const html = await render(baseReco);
    expect(html).not.toContain('card-audio');
  });
});

// ---------------------------------------------------------------------------
// Accessibilité des emojis de type (A1)
// ---------------------------------------------------------------------------
describe('RecoCard — a11y des emojis de type (A1)', () => {
  it('le conteneur porte role="img" + aria-label (nom accessible unique)', async () => {
    const html = await render({ ...baseReco, types: ['film'] });
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="Film"');
  });

  it('les emojis enfants sont aria-hidden (pas de double annonce)', async () => {
    const html = await render({ ...baseReco, types: ['film'] });
    expect(html).toMatch(/class="type-emoji"[^>]*aria-hidden="true"/);
  });

  it('aria-label du conteneur liste tous les types en multi-type', async () => {
    const html = await render({ ...baseReco, types: ['film', 'livre'] });
    expect(html).toContain('aria-label="Film, Livre"');
  });
});
