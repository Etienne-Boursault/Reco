/**
 * GalleryCard — la carte des pages galerie (/<source>/films, /series…).
 *
 * Trois exigences, toutes issues d'un même constat produit : l'ANNÉE de
 * création d'une œuvre, sortie de son contexte, ne dit rien à un visiteur qui
 * parcourt un catalogue. Elle avait été retirée de `RecoCard.astro` mais était
 * restée ici, où elle produisait en plus une aberration : quand le créateur
 * manquait, l'année s'affichait *à sa place*, dans un `<p class="gcard-creator">`.
 *
 *   1. aucune année nulle part sur la carte ;
 *   2. pas de `gcard-creator` du tout quand il n'y a pas de créateur ;
 *   3. la carte cliquable (`href`) et la carte inerte rendent le MÊME corps —
 *      il n'y a plus deux copies du gabarit à maintenir en parallèle.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import GalleryCard from '../../src/components/GalleryCard.astro';

type Props = Record<string, unknown>;

async function render(props: Props): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(GalleryCard as any, { props });
}

const BASE: Props = {
  id: 'i1',
  title: 'Rick et Morty',
  types: ['serie'],
  mentionCount: 3,
};

/** Corps de la carte, débarrassé de la balise racine et de ses attributs. */
function body(html: string): string {
  return html
    .replace(/^[\s\S]*?<div class="gcard-icon"/, '<div class="gcard-icon"')
    .replace(/<\/(a|article)>\s*$/, '')
    .replace(/\s+/g, ' ')
    .trim();
}

describe('GalleryCard — l’année ne s’affiche plus', () => {
  it('n’affiche pas l’année quand un créateur est présent', async () => {
    const html = await render({ ...BASE, creator: 'Dan Harmon', year: 2013 });
    expect(html).toContain('Dan Harmon');
    expect(html).not.toContain('2013');
  });

  it('n’affiche pas l’année à la place du créateur manquant', async () => {
    const html = await render({ ...BASE, year: 2013 });
    expect(html).not.toContain('2013');
    expect(html).not.toContain('gcard-creator');
  });

  it('n’émet aucun élément créateur vide quand le créateur est absent', async () => {
    for (const creator of [undefined, null, '']) {
      const html = await render({ ...BASE, creator });
      expect(html, `creator=${String(creator)}`).not.toContain('gcard-creator');
    }
  });

  it('affiche le créateur seul, sans séparateur orphelin', async () => {
    const html = await render({ ...BASE, creator: 'Alexandre Astier' });
    expect(html).toContain('Alexandre Astier');
    expect(html).not.toMatch(/Alexandre Astier[\s\S]{0,40}·/);
  });
});

describe('GalleryCard — cliquable ou non, un seul gabarit', () => {
  it('rend un <a> quand href est fourni', async () => {
    const html = await render({ ...BASE, href: '/un-bon-moment/oeuvre/i1' });
    expect(html).toMatch(/^\s*<a /);
    expect(html).toContain('href="/un-bon-moment/oeuvre/i1"');
    expect(html).toContain('gcard--link');
  });

  it('rend un <article> sans href, et sans attribut href résiduel', async () => {
    const html = await render(BASE);
    expect(html).toMatch(/^\s*<article /);
    expect(html).not.toContain('href');
    expect(html).not.toContain('gcard--link');
  });

  it('produit un corps identique dans les deux formes', async () => {
    const lien = await render({ ...BASE, creator: 'Dan Harmon', href: '/x' });
    const inerte = await render({ ...BASE, creator: 'Dan Harmon' });
    // La forme CLIQUABLE ajoute, en fin de carte, l'intention de l'action pour
    // les lecteurs d'écran. C'est la seule différence admise : elle n'a aucun
    // sens sur une carte inerte, qui ne mène nulle part. On la retire avant de
    // comparer — le reste du gabarit doit rester strictement identique, sinon
    // les deux formes divergeraient à la première évolution.
    const sansIndice = (h: string) =>
      body(h).replace(/<span class="visually-hidden"[^>]*>[^<]*<\/span>\s*$/, '').trim();
    expect(sansIndice(lien)).toBe(sansIndice(inerte));
  });

  it('la forme cliquable annonce l’action, sans aria-label qui masque le contenu', async () => {
    // L'`aria-label` d'origine (« <titre> — Voir la page complète… ») REMPLAÇAIT
    // le contenu : type, créateur et décompte de mentions n'étaient plus
    // annoncés, et une commande vocale sur le texte visible échouait
    // (WCAG 2.5.3 ; 203 occurrences par galerie, audit du 2026-08-16).
    const lien = await render({ ...BASE, creator: 'Dan Harmon', href: '/x' });
    const racine = lien.match(/<a [^>]*class="gcard gcard--link"[^>]*>/)?.[0] ?? '';
    expect(racine).toBeTruthy();
    expect(racine).not.toContain('aria-label');
    expect(lien).toContain('visually-hidden');
    // Le contenu visible reste dans le nom accessible.
    expect(lien).toContain('Dan Harmon');
  });
});

describe('GalleryCard — le reste du contenu est préservé', () => {
  it('porte le type, le titre et le décompte de mentions', async () => {
    const html = await render({ ...BASE, mentionCount: 3 });
    expect(html).toContain('Rick et Morty');
    expect(html).toContain('Série');
    expect(html).toContain('3');
    expect(html).toContain('mentions');
  });

  it('accorde « mention » au singulier', async () => {
    const html = await render({ ...BASE, mentionCount: 1 });
    expect(html).toContain('mention');
    expect(html).not.toContain('mentions');
  });

  it('expose les types en attribut de données pour le filtrage client', async () => {
    const html = await render({ ...BASE, types: ['serie', 'video'] });
    expect(html).toContain('data-types="serie,video"');
  });

  it('retombe sur le type « autre » quand la liste est vide', async () => {
    const html = await render({ ...BASE, types: [] });
    expect(html).toContain('Autre');
  });
});
