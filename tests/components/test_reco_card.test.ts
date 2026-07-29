/**
 * Tests RecoCard — Story 4 (marqueur « œuvre d'invité ») + badges de nature.
 *
 * On vérifie le badge distinct affiché quand `reco.guestWork === true`, et
 * l'absence de badge sinon. Le combo legacy citation + guestWork verrouille
 * l'affichage des DEUX badges (NIT-9).
 */
import { describe, it, expect } from 'vitest';
import { readFile } from 'node:fs/promises';
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

  it('C2 — un lien explicite vers un domaine banni (Amazon) est CONSERVÉ mais marqué avoid', async () => {
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
    // Arbitrage produit 2026-07-19 : ne PAS supprimer — une œuvre disponible
    // uniquement sur une plateforme proscrite se retrouverait sans aucun lien
    // utile. On la garde en l'affichant avec le badge d'avertissement.
    expect(html).toContain('amazon.fr');
    expect(html).toContain('link avoid');
    expect(html).toContain('moins recommandée');
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

  it('host non whitelisté → symbole selon le type (plus de globe link.svg)', async () => {
    const html = await renderProps({
      reco: {
        ...baseReco,
        types: ['autre'],
        links: [{ label: 'Example', url: 'https://example.com/x', kind: 'streaming' }],
      },
    });
    // On ne rend plus le globe « link.svg » (lu comme une image cassée)…
    expect(html).not.toContain('link.svg');
    expect(html).not.toContain('example.com.svg');
    // …mais un symbole selon la nature du lien (streaming → ▶️).
    expect(html).toContain('link-symbol');
    expect(html).toContain('▶️');
  });

  it('symbole de repli varie selon le kind (buy → 🛒, borrow → 📚, info → ℹ️)', async () => {
    const mk = (kind: string) =>
      renderProps({
        reco: {
          ...baseReco,
          types: ['autre'],
          links: [{ label: 'X', url: 'https://example.com/x', kind }],
        },
      });
    expect(await mk('buy')).toContain('🛒');
    expect(await mk('borrow')).toContain('📚');
    expect(await mk('info')).toContain('ℹ️');
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

  it('logoUrl custom sur host NON whitelisté : ignoré (no-tracker), repli symbole', async () => {
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
    expect(html).not.toContain('link.svg');
    // customLink sans `kind` → symbole générique (maillon 🔗).
    expect(html).toContain('link-symbol');
    expect(html).toContain('🔗');
  });
});

// ---------------------------------------------------------------------------
// Normalisation des hosts (variantes → favicon whitelistée partagée)
// ---------------------------------------------------------------------------
describe('RecoCard — normalisation des hosts', () => {
  const iconFor = (url: string, kind = 'info') =>
    renderProps({
      reco: { ...baseReco, types: ['autre'], links: [{ label: 'X', url, kind }] },
    });

  it('sous-domaine d’artiste Bandcamp → favicon bandcamp.com', async () => {
    expect(await iconFor('https://gorillaz.bandcamp.com/album/x')).toContain(
      '/icons/platforms/bandcamp.com.svg',
    );
  });

  it('sous-domaine itch.io → favicon itch.io', async () => {
    expect(await iconFor('https://polytron.itch.io/fez')).toContain(
      '/icons/platforms/itch.io.svg',
    );
  });

  it('YouTube mobile (m.youtube.com) → favicon www.youtube.com', async () => {
    expect(await iconFor('https://m.youtube.com/watch?v=x')).toContain(
      '/icons/platforms/www.youtube.com.svg',
    );
  });

  it('en.wikipedia.org → favicon fr.wikipedia.org (même logo)', async () => {
    expect(await iconFor('https://en.wikipedia.org/wiki/Fez')).toContain(
      '/icons/platforms/fr.wikipedia.org.svg',
    );
  });

  it('www.rakuten.tv → favicon rakuten.tv', async () => {
    expect(await iconFor('https://www.rakuten.tv/fr/movie/x')).toContain(
      '/icons/platforms/rakuten.tv.svg',
    );
  });

  it('un host sans alias ni marque-racine reste sans favicon (symbole)', async () => {
    const html = await iconFor('https://not-a-bandcamp.example.com/x');
    expect(html).not.toContain('.svg');
    expect(html).toContain('link-symbol');
  });

  it('www.paramountplus.com → favicon www.intl.paramountplus.com (même service)', async () => {
    expect(await iconFor('https://www.paramountplus.com/fr/shows/x/')).toContain(
      '/icons/platforms/www.intl.paramountplus.com.svg',
    );
  });

  it('www.gallimard-bd.fr → favicon www.gallimard.fr (label du même éditeur)', async () => {
    expect(await iconFor('https://www.gallimard-bd.fr/livre/x')).toContain(
      '/icons/platforms/www.gallimard.fr.svg',
    );
  });

  it('www.librairie-gallimard.com n’est PAS aliasé (librairie ≠ maison d’édition)', async () => {
    const html = await iconFor('https://www.librairie-gallimard.com/livre/x');
    expect(html).not.toContain('/icons/platforms/www.gallimard.fr.svg');
    expect(html).toContain('link-symbol');
  });
});

// ---------------------------------------------------------------------------
// Vague 4 (2026-07-29) — lot borné d'icônes de marques identifiables.
// Chaque host whitelisté DOIT avoir son SVG sur disque : whitelister sans
// déployer le fichier afficherait une image cassée (cf. commentaire du Set
// dans RecoCard.astro). On verrouille les deux bouts.
// ---------------------------------------------------------------------------
describe('RecoCard — icônes vague 4', () => {
  const iconFor = (url: string, kind = 'streaming') =>
    renderProps({
      reco: { ...baseReco, types: ['autre'], links: [{ label: 'X', url, kind }] },
    });

  const CASES: Array<[host: string, url: string]> = [
    ['www.twitch.tv', 'https://www.twitch.tv/someone'],
    ['watch.plex.tv', 'https://watch.plex.tv/movie/x'],
    ['www.tf1.fr', 'https://www.tf1.fr/tf1/emission/x'],
  ];

  for (const [host, url] of CASES) {
    it(`${host} → /icons/platforms/${host}.svg (et pas un symbole)`, async () => {
      const html = await iconFor(url);
      expect(html).toContain(`/icons/platforms/${host}.svg`);
      expect(html).not.toContain('link-symbol');
    });

    it(`${host} : le SVG existe et est un XML <svg> 24×24`, async () => {
      const svg = await readFile(
        new URL(`../../public/icons/platforms/${host}.svg`, import.meta.url),
        'utf8',
      );
      expect(svg.trimEnd()).toMatch(/^<svg[^>]*>[\s\S]*<\/svg>$/);
      expect(svg).toContain('viewBox="0 0 24 24"');
      expect(svg).toContain('width="24"');
      expect(svg).toContain('height="24"');
      expect(svg).toContain('role="img"');
      // Icônes décoratives : le nom accessible vient de l'aria-label du lien.
      expect(svg).not.toContain('<title');
    });
  }
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
  it('n’affiche PAS l’année sur la carte (retirée), mais rend « Reco de … » et le label épisode', async () => {
    const html = await renderProps({
      reco: { ...baseReco, year: 2021, recommendedBy: 'Kyan' },
      episodeNumber: 42,
    });
    // L'année (date de création de l'œuvre) n'est plus rendue sur la carte
    // (hors contexte → parasite). Cf. RecoCard.astro + retour 2026-07-29.
    expect(html).not.toContain('2021');
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

  it('est rendu APRÈS la rangée d’icônes (placement sous les liens)', async () => {
    const html = await renderProps({
      reco: { ...baseReco, types: ['film'] },
      sourceId: 'ubm',
    });
    const linksIdx = html.indexOf('class="links"');
    const reportIdx = html.indexOf('report-link-wrap');
    expect(linksIdx).toBeGreaterThan(-1);
    expect(reportIdx).toBeGreaterThan(linksIdx);
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
