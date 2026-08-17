/**
 * Tests RecoCard — badges, sécurité des liens, métadonnées, accessibilité.
 *
 * La résolution des icônes de plateforme vit dans
 * `test_reco_card_icons.test.ts` : c'est le seul bloc qui lit le disque, et
 * réunir les deux faisait dépasser 500 lignes à ce fichier.
 */
import { describe, it, expect } from 'vitest';
import { readFile } from 'node:fs/promises';
// Deux tests instancient le conteneur EUX-MÊMES, pour passer des props que
// les utilitaires partagés ne prévoient pas.
import { experimental_AstroContainer as AstroContainer } from 'astro/container';

import RecoCard from '../../src/components/RecoCard.astro';

import { baseReco, parse, render, renderProps } from './_reco_card';

describe('RecoCard — marqueur œuvre d\'invité (Story 4)', () => {
  it('affiche le badge ⭐ « Leur œuvre » quand guestWork=true', async () => {
    const html = await render({ ...baseReco, guestWork: true });
    // ÉTOILE SEULE depuis le 2026-08-17 : la pastille libellée doublait la
    // largeur de la ligne créateur. Le sens passe par l'info-bulle et le nom
    // accessible — jamais par la seule forme.
    expect(html).toContain('guestwork-star');
    // M3 : ⭐ (le 🎤 entrait en collision avec TYPE_EMOJIS['artiste']).
    expect(html).toContain('⭐');
    // Le libellé N'EST PLUS affiché, mais reste atteignable : c'est ce qui
    // distingue « épuré » de « information perdue ».
    expect(html).toMatch(/title="[^"]*Leur œuvre/);
    expect(html).toMatch(/aria-label="[^"]*(œuvre|oeuvre)/i);
  });

  it('n\'utilise plus 🎤 pour le badge guestWork (collision type artiste, M3)', async () => {
    const html = await render({ ...baseReco, guestWork: true });
    expect(html).not.toContain('🎤');
  });

  it('n\'affiche aucun badge guestWork quand le flag est absent', async () => {
    const html = await render(baseReco);
    expect(html).not.toContain('guestwork-star');
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
    // La pastille « 📝 Mentionné » a été retirée : elle flottait seule
    // au-dessus de « Reco de … » et disait deux fois la même chose.
    // L'information est portée par le VERBE de la ligne méta.
    const html = await render({ ...baseReco, kind: 'citation', recommendedBy: 'Navo' });
    expect(html).toContain('Mention de');
    expect(html).not.toContain('Reco de');
    expect(html).not.toContain('kind-badge');
  });

  it('combo legacy citation + guestWork → les DEUX badges (NIT-9)', async () => {
    const html = await render({
      ...baseReco, kind: 'citation', guestWork: true, recommendedBy: 'Navo',
    });
    // Les deux informations coexistent sans se disputer la place : le verbe
    // pour la mention, l'étoile pour l'œuvre de la personne.
    expect(html).toContain('Mention de');
    expect(html).toContain('⭐');
    expect(html).toContain('guestwork-star');
  });
});

// ---------------------------------------------------------------------------
// Agencement de la carte (2026-07-30)
//   1. le titre partage la rangée des icônes de type au lieu d'être dessous ;
//   2. le badge « Leur œuvre » descend sur la ligne du créateur.
// ---------------------------------------------------------------------------
describe('RecoCard — titre sur la rangée des types', () => {
  it('le titre est un enfant DIRECT de la rangée card-top', async () => {
    const doc = parse(await render({ ...baseReco, types: ['film'] }));
    const title = doc.querySelector('.card-top > h3.title');
    expect(title).not.toBeNull();
    expect(title!.textContent).toBe('Mon spectacle');
  });

  it('les icônes de type précèdent le titre dans la rangée', async () => {
    const doc = parse(await render({ ...baseReco, types: ['film'] }));
    const enfants = Array.from(doc.querySelector('.card-top')!.children);
    expect(enfants[0]!.getAttribute('role')).toBe('img');
    expect(enfants[1]!.tagName.toLowerCase()).toBe('h3');
  });

  it('le titre reste HORS du conteneur role="img" (sinon annoncé comme partie de l’image)', async () => {
    const doc = parse(await render({ ...baseReco, types: ['film', 'livre'] }));
    expect(doc.querySelector('[role="img"] h3')).toBeNull();
    expect(doc.querySelector('[role="img"] .title')).toBeNull();
    // Le conteneur d'emojis ne contient QUE des emojis décoratifs.
    const type = doc.querySelector('.type[role="img"]')!;
    expect(type.textContent!.trim()).toBe('🎬📖');
  });

  it('un seul <h3> par carte (le titre n’est pas dupliqué par le déplacement)', async () => {
    const doc = parse(await render(baseReco));
    expect(doc.querySelectorAll('h3')).toHaveLength(1);
  });

  it('le titre n’est plus un frère de la ligne créateur', async () => {
    const doc = parse(await render(baseReco));
    expect(doc.querySelector('.card > h3.title')).toBeNull();
  });
});

describe('RecoCard — badge « Leur œuvre » sur la ligne créateur', () => {
  it('le badge descend sur la ligne créateur et quitte la rangée du haut', async () => {
    const doc = parse(await render({ ...baseReco, guestWork: true }));
    expect(doc.querySelector('.creator .guestwork-star')).not.toBeNull();
    expect(doc.querySelector('.card-top .guestwork-star')).toBeNull();
  });

  it('le nom du créateur précède le badge sur la ligne', async () => {
    const doc = parse(await render({ ...baseReco, guestWork: true }));
    const ligne = doc.querySelector('.creator')!;
    const enfants = Array.from(ligne.children);
    expect(enfants[0]!.className).toContain('creator-name');
    expect(enfants[0]!.textContent).toContain('Untel');
    expect(enfants[enfants.length - 1]!.className).toContain('guestwork-star');
  });

  it('guestWork SANS créateur : le badge ne disparaît pas, la ligne est rendue pour lui seul', async () => {
    const doc = parse(await render({ ...baseReco, creator: undefined, guestWork: true }));
    const ligne = doc.querySelector('.creator');
    expect(ligne).not.toBeNull();
    expect(ligne!.querySelector('.guestwork-star')).not.toBeNull();
    // Repli honnête : pas de nom fabriqué ni d'espace réservé vide.
    expect(ligne!.querySelector('.creator-name')).toBeNull();
    // Le libellé n'est plus visible : c'est l'info-bulle qui le porte.
    expect(ligne!.querySelector('.guestwork-star')!.getAttribute('title'))
      .toContain('Leur œuvre');
    expect(ligne!.textContent).not.toContain('Untel');
  });

  it('la mention se lit dans la ligne méta, plus dans une pastille', async () => {
    // Le badge « Mentionné » occupait une ligne pour un mot, juste au-dessus
    // de « Reco de … ». Le verbe porte la même information sans rien coûter.
    const doc = parse(await render({ ...baseReco, kind: 'citation', recommendedBy: 'Navo' }));
    expect(doc.querySelector('.card-top .kind-badge')).toBeNull();
    expect(doc.querySelector('.meta')!.textContent).toContain('Mention de Navo');
  });

  it('combo citation + guestWork : chaque information à sa place', async () => {
    const doc = parse(await render({
      ...baseReco, kind: 'citation', guestWork: true, recommendedBy: 'Navo',
    }));
    // L'étoile qualifie la PERSONNE : ligne créateur.
    expect(doc.querySelector('.creator .guestwork-star')).not.toBeNull();
    // La mention qualifie la RECO : ligne méta.
    expect(doc.querySelector('.meta')!.textContent).toContain('Mention de');
  });

  it('showGuestWorkBadge=false sans créateur → aucune ligne créateur du tout', async () => {
    const container = await AstroContainer.create();
    const html = await container.renderToString(RecoCard as never, {
      props: {
        reco: { ...baseReco, creator: undefined, guestWork: true },
        showGuestWorkBadge: false,
      },
    });
    expect(parse(html).querySelector('.creator')).toBeNull();
  });
});

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

  it('est le DERNIER élément de la rangée d’icônes', async () => {
    // Il vivait dans un bloc à part, ce qui lui donnait une ligne pour lui
    // seul sous les liens. Il est maintenant un item de la MÊME rangée,
    // calé à droite (retour utilisateur 2026-08-17).
    const doc = parse(await renderProps({
      reco: { ...baseReco, types: ['film'] },
      sourceId: 'ubm',
    }));
    const rangee = doc.querySelector('.links')!;
    const items = Array.from(rangee.children);
    expect(items.length).toBeGreaterThan(1);
    expect(items[items.length - 1]!.className).toContain('report-link');
    // Et il n'existe plus de conteneur séparé.
    expect(doc.querySelector('.report-link-wrap')).toBeNull();
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
