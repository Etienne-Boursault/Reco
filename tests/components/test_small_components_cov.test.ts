/**
 * Tests des composants d'affichage simples jamais couverts :
 * `MetaPodcastCard`, `WorkCard`, `AudioPlayer`, `TrendingBadge` et
 * `SearchPalette`.
 *
 * Chacun est petit mais porte des branches de repli réelles (champ absent,
 * type inconnu, timecode nul) que seul un rendu permet de vérifier.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import MetaPodcastCard from '../../src/components/MetaPodcastCard.astro';
import WorkCard from '../../src/components/WorkCard.astro';
import AudioPlayer from '../../src/components/AudioPlayer.astro';
import TrendingBadge from '../../src/components/TrendingBadge.astro';
import SearchPalette from '../../src/components/SearchPalette.astro';

async function render(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  Component: any,
  props: Record<string, unknown> = {},
): Promise<string> {
  const container = await AstroContainer.create();
  return container.renderToString(Component, { props });
}

// ---------------------------------------------------------------------------
// MetaPodcastCard (annuaire /meta)
// ---------------------------------------------------------------------------
const ENTRY = {
  slug: 'un-bon-moment',
  registry: {
    siteUrl: 'https://unbonmoment.example',
    podcast: {
      title: 'Un Bon Moment',
      tagline: 'Des invités, des recos',
      hosts: ['Kyan Khojandi', 'Navo'],
    },
    stats: { itemsCount: 412, mentionsCount: 890, episodesCount: 42 },
  },
};

describe('MetaPodcastCard — carte de l’annuaire', () => {
  it('titre lié au détail interne /meta/podcast/<slug>', async () => {
    const html = await render(MetaPodcastCard, { entry: ENTRY });
    expect(html).toContain('href="/meta/podcast/un-bon-moment"');
    expect(html).toContain('Un Bon Moment');
    expect(html).toContain('data-slug="un-bon-moment"');
  });

  it('affiche les 3 compteurs du registre', async () => {
    const html = await render(MetaPodcastCard, { entry: ENTRY });
    expect(html).toContain('412');
    expect(html).toContain('890');
    expect(html).toContain('42');
  });

  it('joint les animateurs par une puce médiane', async () => {
    const html = await render(MetaPodcastCard, { entry: ENTRY });
    expect(html).toContain('Kyan Khojandi · Navo');
  });

  it('sans animateurs déclarés → pas de ligne hosts', async () => {
    const html = await render(MetaPodcastCard, {
      entry: { ...ENTRY, registry: { ...ENTRY.registry, podcast: { title: 'X' } } },
    });
    expect(html).not.toContain('meta-card__hosts');
  });

  it('liste d’animateurs vide → pas de ligne hosts', async () => {
    const html = await render(MetaPodcastCard, {
      entry: {
        ...ENTRY,
        registry: { ...ENTRY.registry, podcast: { title: 'X', hosts: [] } },
      },
    });
    expect(html).not.toContain('meta-card__hosts');
  });

  it('sans tagline → pas de paragraphe tagline', async () => {
    const html = await render(MetaPodcastCard, {
      entry: {
        ...ENTRY,
        registry: { ...ENTRY.registry, podcast: { title: 'X', hosts: ['A'] } },
      },
    });
    expect(html).not.toContain('meta-card__tagline');
  });

  it('le CTA externe est marqué noopener/noreferrer et nommé explicitement', async () => {
    const html = await render(MetaPodcastCard, { entry: ENTRY });
    expect(html).toContain('href="https://unbonmoment.example"');
    expect(html).toContain('rel="noopener noreferrer external"');
    expect(html).toContain('target="_blank"');
    expect(html).toContain(
      'aria-label="Ouvrir https://unbonmoment.example dans un nouvel onglet"',
    );
    expect(html).toMatch(/<span class="meta-card__cta-icon" aria-hidden="true"[^>]*>↗<\/span>/);
  });
});

// ---------------------------------------------------------------------------
// WorkCard (œuvres du même créateur)
// ---------------------------------------------------------------------------
describe('WorkCard — vignette « du même créateur »', () => {
  const item = (over: Record<string, unknown> = {}) => ({
    id: 'itm-1',
    title: 'Memories of Murder',
    types: ['film'],
    ...over,
  });

  it('pointe vers la page œuvre canonique de la source', async () => {
    const html = await render(WorkCard, { sourceId: 'ubm', item: item() });
    expect(html).toContain('href="/ubm/oeuvre/itm-1"');
    expect(html).toContain('Memories of Murder');
  });

  it('un emoji par type, avec libellé accessible dupliqué en visually-hidden', async () => {
    const html = await render(WorkCard, { sourceId: 'ubm', item: item({ types: ['film', 'livre'] }) });
    expect(html).toContain('🎬');
    expect(html).toContain('📖');
    expect(html).toContain('aria-label="Film, Livre"');
    expect(html).toContain('<span class="visually-hidden"');
  });

  it('type inconnu → emoji ✨ et libellé = clé brute', async () => {
    const html = await render(WorkCard, { sourceId: 'ubm', item: item({ types: ['zarbi'] }) });
    expect(html).toContain('✨');
    expect(html).toContain('aria-label="zarbi"');
  });

  it('types absents → aucun emoji de type', async () => {
    const html = await render(WorkCard, { sourceId: 'ubm', item: item({ types: undefined }) });
    expect(html).not.toContain('wcard-emoji');
    // Nom accessible vide : Astro rend l'attribut sans valeur.
    expect(html).toMatch(/class="wcard-type" aria-label(?!=)/);
  });

  it('créateur affiché avec sa pastille de signalement non-interactive', async () => {
    const html = await render(WorkCard, {
      sourceId: 'ubm',
      item: item({ creator: 'Roman Polanski' }),
    });
    expect(html).toContain('wcard-creator');
    expect(html).toContain('creator-flag-dot');
    expect(html).not.toContain('<details');
  });

  it('sans créateur → pas de ligne créateur', async () => {
    const html = await render(WorkCard, { sourceId: 'ubm', item: item() });
    expect(html).not.toContain('wcard-creator');
  });

  it('année affichée quand elle existe (contexte page œuvre)', async () => {
    const html = await render(WorkCard, { sourceId: 'ubm', item: item({ year: 2003 }) });
    expect(html).toContain('2003');
  });

  it('sans année → pas de span année', async () => {
    const html = await render(WorkCard, { sourceId: 'ubm', item: item() });
    expect(html).not.toContain('wcard-year');
  });
});

// ---------------------------------------------------------------------------
// AudioPlayer (flux audio direct)
// ---------------------------------------------------------------------------
describe('AudioPlayer — lecteur natif', () => {
  it('rend un <audio controls preload=none> avec la source', async () => {
    const html = await render(AudioPlayer, { audioUrl: 'https://cdn.example/ep.mp3' });
    expect(html).toContain('<audio');
    expect(html).toContain('controls');
    expect(html).toContain('preload="none"');
    expect(html).toContain('src="https://cdn.example/ep.mp3"');
  });

  it('sans titre, nom accessible de repli « Lecteur audio »', async () => {
    const html = await render(AudioPlayer, { audioUrl: 'https://cdn.example/ep.mp3' });
    expect(html).toContain('aria-label="Lecteur audio"');
  });

  it('titre fourni → utilisé comme nom accessible', async () => {
    const html = await render(AudioPlayer, {
      audioUrl: 'https://cdn.example/ep.mp3',
      title: 'Extrait : Apocalypse Now',
    });
    expect(html).toContain('aria-label="Extrait : Apocalypse Now"');
  });

  it('startSeconds positif → data-start entier', async () => {
    const html = await render(AudioPlayer, {
      audioUrl: 'https://cdn.example/ep.mp3',
      startSeconds: 133.7,
    });
    expect(html).toContain('data-start="133"');
  });

  it('startSeconds absent → data-start vide (pas de seek)', async () => {
    const html = await render(AudioPlayer, { audioUrl: 'https://cdn.example/ep.mp3' });
    expect(html).not.toMatch(/data-start="\d/);
  });

  it('startSeconds à 0 → data-start vide', async () => {
    const html = await render(AudioPlayer, {
      audioUrl: 'https://cdn.example/ep.mp3',
      startSeconds: 0,
    });
    expect(html).not.toMatch(/data-start="\d/);
  });

  it('startSeconds négatif → data-start vide', async () => {
    const html = await render(AudioPlayer, {
      audioUrl: 'https://cdn.example/ep.mp3',
      startSeconds: -5,
    });
    expect(html).not.toMatch(/data-start="-?\d/);
  });

  it('message de repli pour les navigateurs sans <audio>', async () => {
    const html = await render(AudioPlayer, { audioUrl: 'https://cdn.example/ep.mp3' });
    expect(html).toContain('ne supporte pas');
  });
});

// ---------------------------------------------------------------------------
// TrendingBadge
// ---------------------------------------------------------------------------
describe('TrendingBadge — pastille « tendance »', () => {
  it('fenêtre par défaut de 12 mois dans le libellé', async () => {
    const html = await render(TrendingBadge, { count: 3 });
    expect(html).toContain('Mentionnée 3 fois au cours des 12 derniers mois');
    expect(html).toContain('3×');
  });

  it('fenêtre personnalisée reprise dans le libellé', async () => {
    const html = await render(TrendingBadge, { count: 2, windowMonths: 6 });
    expect(html).toContain('Mentionnée 2 fois au cours des 6 derniers mois');
  });

  it('le 🔥 est décoratif, le badge porte role=img + aria-label', async () => {
    const html = await render(TrendingBadge, { count: 2 });
    expect(html).toMatch(/<span class="trending" role="img" aria-label="[^"]+"/);
    expect(html).toMatch(/<span aria-hidden="true"[^>]*>🔥<\/span>/);
  });
});

// ---------------------------------------------------------------------------
// SearchPalette
// ---------------------------------------------------------------------------
describe('SearchPalette — palette Cmd+K', () => {
  it('rend un déclencheur relié au dialogue par aria-controls', async () => {
    const html = await render(SearchPalette);
    expect(html).toContain('data-search-palette-trigger');
    expect(html).toContain('aria-haspopup="dialog"');
    expect(html).toContain('aria-controls="search-palette-dialog"');
  });

  it('le dialogue est masqué au chargement et modal', async () => {
    const html = await render(SearchPalette);
    expect(html).toMatch(/id="search-palette-dialog"[^>]*role="dialog"/);
    expect(html).toMatch(/id="search-palette-dialog"[\s\S]*?aria-modal="true"/);
    expect(html).toMatch(/id="search-palette-dialog"[^>]*hidden/);
  });

  it('le champ de recherche est étiqueté et décrit par l’indice clavier', async () => {
    const html = await render(SearchPalette);
    expect(html).toContain('for="search-palette-input"');
    expect(html).toContain('aria-describedby="search-palette-hint"');
    expect(html).toContain('Échap pour fermer');
  });

  it('la zone de résultats est un <output> aria-live', async () => {
    const html = await render(SearchPalette);
    expect(html).toMatch(/<output[^>]*id="search-palette-results"[^>]*aria-live="polite"/);
  });
});
