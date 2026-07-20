/**
 * Tests post-build de la route `/<source>/oeuvre/<itemId>` — vérifie qu'au
 * moins une page d'œuvre a été émise et contient les blocs attendus
 * (h1, timeline, JSON-LD, canonical, OG).
 *
 * Comportement CI vs local : skip silencieux si pas de build local, fail
 * explicite si CI=true (cf. test_meta_tags_build pour le pattern).
 */
import { describe, it, expect } from 'vitest';
import { readFileSync, existsSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const DIST = join(process.cwd(), 'dist');
const oeuvreDir = join(DIST, 'un-bon-moment', 'oeuvre');
const hasBuild = existsSync(oeuvreDir);

if (!hasBuild && process.env.CI === 'true') {
  describe('work canonical page (CI guard)', () => {
    it('dist/un-bon-moment/oeuvre/ doit exister en CI', () => {
      expect.fail(
        `dist/un-bon-moment/oeuvre/ introuvable — exécute \`SITE_URL=https://source-internet.fr npm run build\` avant les tests work en CI.`,
      );
    });
  });
}

describe.skipIf(!hasBuild)('work canonical page — post-build', () => {
  const subdirs = hasBuild
    ? readdirSync(oeuvreDir).filter((d) =>
        statSync(join(oeuvreDir, d)).isDirectory(),
      )
    : [];
  const firstId = subdirs[0];
  const html = firstId
    ? readFileSync(join(oeuvreDir, firstId, 'index.html'), 'utf-8')
    : '';

  it('génère au moins une page d’œuvre', () => {
    expect(subdirs.length).toBeGreaterThan(0);
  });

  it('contient un <h1> unique pour le titre œuvre', () => {
    const h1s = html.match(/<h1[^>]*>/g) ?? [];
    expect(h1s.length).toBe(1);
  });

  it('contient <main id="main"> + skip-link', () => {
    expect(html).toContain('id="main"');
    expect(html).toContain('class="skip-link"');
  });

  it('contient une balise canonical vers /<source>/oeuvre/<id>', () => {
    expect(html).toMatch(
      /<link rel="canonical" href="https?:\/\/[^"]+\/un-bon-moment\/oeuvre\/[^"]+"/,
    );
  });

  it('contient un JSON-LD schema.org typé', () => {
    expect(html).toMatch(/<script type="application\/ld\+json"/);
    expect(html).toContain('https://schema.org');
  });

  it('contient une <time datetime=...> pour au moins une mention datée', () => {
    // Beaucoup d'épisodes ont une date — on s'attend à au moins une page
    // dont la timeline contient un <time>. On ne fail pas si la première
    // page sondée tombe sur un item orphelin de date (rare mais possible).
    const sampled = subdirs.slice(0, 20).map((id) =>
      readFileSync(join(oeuvreDir, id, 'index.html'), 'utf-8'),
    );
    expect(sampled.some((h) => /<time[^>]*\sdatetime="/.test(h))).toBe(true);
  });
});
