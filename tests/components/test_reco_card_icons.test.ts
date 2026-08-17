/**
 * Tests RecoCard — RÉSOLUTION DES ICÔNES de plateforme.
 *
 * Séparé du reste parce que c'est le seul bloc qui touche au SYSTÈME DE
 * FICHIERS : chaque icône whitelistée doit exister dans
 * `public/icons/platforms/`, et un test qui se contenterait de vérifier
 * l'attribut `src` laisserait passer une icône manquante — qui ne se voit
 * qu'à l'affichage.
 *
 * Le fichier d'origine réunissait ces tests et tous les autres, et dépassait
 * 500 lignes.
 */
import { describe, it, expect } from 'vitest';
import { readFile } from 'node:fs/promises';

import { baseReco, parse, render, renderProps } from './_reco_card';

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
// Icône Deezer — rebrand de novembre 2023 : l'égaliseur multicolore a laissé
// place à un cœur violet. L'ancien fichier montrait encore les quatre barres.
// ---------------------------------------------------------------------------
describe('RecoCard — icône Deezer (cœur violet)', () => {
  const lireIcone = () =>
    readFile(
      new URL('../../public/icons/platforms/www.deezer.com.svg', import.meta.url),
      'utf8',
    );

  it('un lien Deezer pointe bien vers la favicon self-hosted', async () => {
    const html = await renderProps({
      reco: {
        ...baseReco,
        types: ['autre'],
        links: [{ label: 'Deezer', url: 'https://www.deezer.com/fr/album/1', kind: 'streaming' }],
      },
    });
    expect(html).toContain('/icons/platforms/www.deezer.com.svg');
    expect(html).not.toContain('link-symbol');
  });

  it('suit les conventions du dossier (24×24, role=img, fond arrondi, sans <title>)', async () => {
    const svg = await lireIcone();
    expect(svg.trimEnd()).toMatch(/^<svg[^>]*>[\s\S]*<\/svg>$/);
    expect(svg).toContain('viewBox="0 0 24 24"');
    expect(svg).toContain('width="24"');
    expect(svg).toContain('height="24"');
    expect(svg).toContain('role="img"');
    expect(svg).toMatch(/<rect width="24" height="24" rx="5"/);
    expect(svg).not.toContain('<title');
    // Une seule ligne, pas de commentaire (cf. les autres icônes du dossier).
    expect(svg.trimEnd()).not.toContain('\n');
    expect(svg).not.toContain('<!--');
  });

  it('porte un cœur en <path> et plus l’égaliseur à quatre barres', async () => {
    const svg = await lireIcone();
    // Le glyphe est un tracé unique (le fond `rect` mis à part).
    expect(svg.match(/<path/g)).toHaveLength(1);
    expect(svg.match(/<rect/g)).toHaveLength(1);
    // Les couleurs de l'ancien égaliseur ont disparu.
    for (const ancienne of ['#40ab5d', '#f18021', '#e02b3a', '#4b9fd5']) {
      expect(svg).not.toContain(ancienne);
    }
    // Violet Deezer.
    expect(svg.toUpperCase()).toContain('#A238FF');
  });
});

