/**
 * Tests post-build des pages publiques /a-propos et /manifeste (item #22).
 *
 * Vérifie sur le HTML statique produit par `astro build` que :
 *   - les pages existent (routing OK) ;
 *   - `<html lang="fr">` (WCAG 3.1.1) ;
 *   - h1 unique (WCAG 1.3.1) ;
 *   - <main id="main"> + skip-link (WCAG 2.4.1) ;
 *   - JSON-LD WebPage + BreadcrumbList présents (ADR 0027) ;
 *   - liens de navigation croisée /a-propos ↔ /manifeste présents.
 *
 * Skip silencieux en local sans build, fail explicite en CI (CR senior M1).
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const DIST = join(process.cwd(), 'dist');
const aboutPath = join(DIST, 'a-propos', 'index.html');
const manifestoPath = join(DIST, 'manifeste', 'index.html');
const hasBuild = existsSync(aboutPath) && existsSync(manifestoPath);

if (!hasBuild && process.env.CI === 'true') {
  describe('about/manifeste build output (CI guard)', () => {
    it('dist/a-propos et dist/manifeste doivent exister en CI', () => {
      expect.fail(
        'Pages /a-propos ou /manifeste introuvables dans dist/ — exécute `npm run build` avant.',
      );
    });
  });
}

function countMatches(html: string, re: RegExp): number {
  return [...html.matchAll(re)].length;
}

describe.skipIf(!hasBuild)('/a-propos — route publique (item #22)', () => {
  const html = hasBuild ? readFileSync(aboutPath, 'utf-8') : '';

  it('html lang="fr"', () => {
    expect(html).toMatch(/<html[^>]*lang="fr"/);
  });

  it('skip-link vers #main', () => {
    expect(html).toMatch(/<a[^>]*href="#main"[^>]*class="skip-link"/);
  });

  it('<main id="main">', () => {
    expect(html).toMatch(/<main[^>]*id="main"/);
  });

  it('h1 unique', () => {
    expect(countMatches(html, /<h1\b/gi)).toBe(1);
  });

  it('h1 contient le titre attendu', () => {
    expect(html).toMatch(/<h1[^>]*>[^<]*À propos[^<]*<\/h1>/);
  });

  it('JSON-LD WebPage présent', () => {
    expect(html).toContain('"@type":"WebPage"');
  });

  it('JSON-LD BreadcrumbList présent', () => {
    expect(html).toContain('"@type":"BreadcrumbList"');
  });

  it('lien vers /manifeste présent', () => {
    expect(html).toMatch(/href="\/manifeste"/);
  });

  it("pas de fuite vers Amazon (cohérence manifeste)", () => {
    expect(html).not.toMatch(/amazon\.[a-z]+/i);
  });

  it('footer global présent (lien À propos / Manifeste)', () => {
    expect(html).toMatch(/<footer[^>]*role="contentinfo"/);
    expect(html).toMatch(/href="\/manifeste"/);
  });
});

describe.skipIf(!hasBuild)('/manifeste — route publique (item #22)', () => {
  const html = hasBuild ? readFileSync(manifestoPath, 'utf-8') : '';

  it('html lang="fr"', () => {
    expect(html).toMatch(/<html[^>]*lang="fr"/);
  });

  it('<main id="main"> + skip-link', () => {
    expect(html).toMatch(/<a[^>]*href="#main"[^>]*class="skip-link"/);
    expect(html).toMatch(/<main[^>]*id="main"/);
  });

  it('h1 unique', () => {
    expect(countMatches(html, /<h1\b/gi)).toBe(1);
  });

  it('contient les 8 sections du manifeste (ancres)', () => {
    const expectedAnchors = [
      'preambule',
      'anti-bollore',
      'libraries',
      'privacy',
      'opensource',
      'a11y',
      'selfhost',
      'transparency',
    ];
    for (const a of expectedAnchors) {
      expect(html, `ancre #${a} manquante`).toMatch(new RegExp(`id="${a}"`));
    }
  });

  it('cite Acrimed et Wikipédia (sources anti-Bolloré)', () => {
    expect(html).toMatch(/acrimed\.org/);
    expect(html).toMatch(/wikipedia\.org\/wiki\/Groupe/);
  });

  it('cite Place des Libraires (librairies indés)', () => {
    expect(html).toMatch(/placedeslibraires\.fr/);
  });

  it("pas de lien Amazon (cohérence avec sa propre règle)", () => {
    expect(html).not.toMatch(/amazon\.[a-z]+/i);
  });

  it('JSON-LD WebPage + BreadcrumbList présents', () => {
    expect(html).toContain('"@type":"WebPage"');
    expect(html).toContain('"@type":"BreadcrumbList"');
  });

  it('lien retour vers /a-propos depuis le footer global', () => {
    expect(html).toMatch(/href="\/a-propos"/);
  });
});
