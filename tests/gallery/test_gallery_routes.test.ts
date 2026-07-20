/**
 * Tests d'intégration post-build : vérifient que les routes galerie
 * sont bien rendues dans `dist/` (suppose un `astro build` préalable).
 *
 * On skip si `dist/` n'existe pas (ex. exécution isolée des tests unit).
 */
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, it, expect } from 'vitest';

const DIST = resolve(process.cwd(), 'dist');
const SOURCE = 'un-bon-moment';

function loadIfBuilt(relpath: string): string | null {
  const file = resolve(DIST, relpath);
  if (!existsSync(file)) return null;
  return readFileSync(file, 'utf8');
}

const shouldRun = existsSync(DIST);
const d = shouldRun ? describe : describe.skip;

d('Galleries — fichiers générés au build', () => {
  it('/[source]/films/index.html existe + contient h1 + ItemList JSON-LD', () => {
    const html = loadIfBuilt(`${SOURCE}/films/index.html`);
    expect(html).not.toBeNull();
    expect(html).toMatch(/<h1[^>]*>Tous les films<\/h1>/);
    expect(html).toContain('"@type":"ItemList"');
    expect(html).toContain('"@type":"BreadcrumbList"');
    // au moins quelques cartes rendues
    const count = (html!.match(/<h3 class="gcard-title"/g) ?? []).length;
    expect(count).toBeGreaterThan(10);
  });

  it('/[source]/livres existe + au moins une carte', () => {
    const html = loadIfBuilt(`${SOURCE}/livres/index.html`);
    expect(html).not.toBeNull();
    expect(html).toMatch(/<h1[^>]*>Tous les livres<\/h1>/);
    const count = (html!.match(/<h3 class="gcard-title"/g) ?? []).length;
    expect(count).toBeGreaterThan(0);
  });

  it('/[source]/musique existe + JSON-LD', () => {
    const html = loadIfBuilt(`${SOURCE}/musique/index.html`);
    expect(html).not.toBeNull();
    expect(html).toMatch(/<h1[^>]*>Toute la musique<\/h1>/);
    expect(html).toContain('"@type":"ItemList"');
  });

  it('/[source]/series existe + JSON-LD', () => {
    const html = loadIfBuilt(`${SOURCE}/series/index.html`);
    expect(html).not.toBeNull();
    expect(html).toMatch(/<h1[^>]*>Toutes les séries<\/h1>/);
  });

  it('/[source]/invite/<slug> existe au moins pour un invité connu', () => {
    // Adrien Méniel est un invité récurrent du podcast Un Bon Moment.
    // Le slug vient de slugify('Adrien Méniel') = 'adrien-meniel'.
    const html = loadIfBuilt(`${SOURCE}/invite/adrien-meniel/index.html`);
    expect(html).not.toBeNull();
    expect(html).toMatch(/<h1[^>]*>Recommandations de Adrien Méniel<\/h1>/);
    expect(html).toContain('"@type":"BreadcrumbList"');
  });

  it('skip-link a11y présent (Layout.astro)', () => {
    const html = loadIfBuilt(`${SOURCE}/films/index.html`)!;
    expect(html).toMatch(/<a href="#main" class="skip-link"/);
    expect(html).toContain('id="main"');
  });

  it("hiérarchie de titres : 1 seul <h1>", () => {
    const html = loadIfBuilt(`${SOURCE}/films/index.html`)!;
    const h1s = html.match(/<h1[\s>]/g) ?? [];
    expect(h1s.length).toBe(1);
  });
});
