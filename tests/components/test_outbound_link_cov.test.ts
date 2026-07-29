/**
 * Tests `OutboundLink.astro` — ancre avec tracking de clic sortant.
 *
 * Deux comportements sensibles :
 *  - R-P1-16 : `category` optionnelle, dérivée de l'URL par `categorizeUrl` ;
 *  - M25-22 : `rel` MERGÉ avec `noopener noreferrer` (jamais écrasé), pour
 *    ne pas perdre la protection anti-tabnabbing quand l'appelant fournit
 *    son propre `rel`.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import OutboundLink from '../../src/components/OutboundLink.astro';

async function render(
  props: Record<string, unknown>,
  slot = 'Voir',
): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(OutboundLink as any, {
    props: { sourceId: 'ubm', ...props },
    slots: { default: slot },
  });
}

/** Jeton `rel` rendus, dans l'ordre. */
function rel(html: string): string[] {
  return (html.match(/ rel="([^"]*)"/)?.[1] ?? '').split(' ').filter(Boolean);
}

describe('OutboundLink — attributs de tracking', () => {
  it('pose data-track/-category/-source-id', async () => {
    const html = await render({ href: 'https://open.spotify.com/album/x' });
    expect(html).toContain('data-track="click"');
    expect(html).toContain('data-source-id="ubm"');
    expect(html).toContain('data-category="spotify"');
  });

  it('sans recoId, l’attribut data-reco-id est absent (M25-23)', async () => {
    const html = await render({ href: 'https://example.com/x' });
    expect(html).not.toContain('data-reco-id="');
  });

  it('avec recoId, l’attribut est posé', async () => {
    const html = await render({ href: 'https://example.com/x', recoId: 'ubm-0001' });
    expect(html).toContain('data-reco-id="ubm-0001"');
  });

  it('category explicite court-circuite la dérivation automatique', async () => {
    const html = await render({
      href: 'https://open.spotify.com/album/x',
      category: 'other',
    });
    expect(html).toContain('data-category="other"');
  });

  it('URL non parsable → catégorie « other » plutôt qu’une erreur', async () => {
    const html = await render({ href: 'pas-une-url' });
    expect(html).toContain('data-category="other"');
  });
});

describe('OutboundLink — fusion du rel (M25-22)', () => {
  it('target=_blank par défaut → noopener + noreferrer', async () => {
    const html = await render({ href: 'https://example.com/x' });
    expect(html).toContain('target="_blank"');
    expect(rel(html)).toEqual(['noopener', 'noreferrer']);
  });

  it('un rel custom est PRÉSERVÉ et complété, pas remplacé', async () => {
    const html = await render({ href: 'https://example.com/x', rel: 'nofollow sponsored' });
    expect(rel(html)).toEqual(['nofollow', 'sponsored', 'noopener', 'noreferrer']);
  });

  it('un rel qui contient déjà noopener n’est pas dupliqué', async () => {
    const html = await render({ href: 'https://example.com/x', rel: 'noopener nofollow' });
    expect(rel(html)).toEqual(['noopener', 'nofollow', 'noreferrer']);
  });

  it('rel avec espaces superflus → jetons nettoyés', async () => {
    const html = await render({ href: 'https://example.com/x', rel: '  nofollow   ugc ' });
    expect(rel(html)).toEqual(['nofollow', 'ugc', 'noopener', 'noreferrer']);
  });

  it('target interne (_self) sans rel → marqueur sémantique « external » seul', async () => {
    const html = await render({ href: '/ubm/oeuvre/x', target: '_self' });
    expect(html).toContain('target="_self"');
    expect(rel(html)).toEqual(['external']);
  });

  it('target interne AVEC rel custom → le rel de l’appelant est respecté tel quel', async () => {
    const html = await render({ href: '/ubm/oeuvre/x', target: '_self', rel: 'nofollow' });
    expect(rel(html)).toEqual(['nofollow']);
  });

  it('rel vide sur target interne → repli « external »', async () => {
    const html = await render({ href: '/x', target: '_self', rel: '   ' });
    expect(rel(html)).toEqual(['external']);
  });
});

describe('OutboundLink — passe-plat a11y et contenu', () => {
  it('rend le slot et propage class/title/aria-label', async () => {
    const html = await render({
      href: 'https://example.com/x',
      class: 'link indie',
      title: 'Bandcamp',
      ariaLabel: 'Bandcamp (nouvel onglet)',
    });
    expect(html).toContain('Voir');
    expect(html).toContain('class="link indie"');
    expect(html).toContain('title="Bandcamp"');
    expect(html).toContain('aria-label="Bandcamp (nouvel onglet)"');
  });

  it('sans title ni aria-label, aucun attribut vide n’est émis', async () => {
    const html = await render({ href: 'https://example.com/x' });
    expect(html).not.toContain('title=""');
    expect(html).not.toContain('aria-label=""');
  });
});
