/**
 * Tests OG template — structure JSX-as-object.
 *
 * On ne lance pas Satori ici (lent + binaire natif) ; on vérifie que le
 * template produit un arbre conforme aux attentes de Satori (avec `display`
 * sur les conteneurs flex, troncature des titres longs, fallback emoji…).
 */

import { describe, it, expect } from 'vitest';
import { ogTemplate, TYPE_EMOJI, __testing } from '../../src/lib/og/template.js';

const { truncate, safeHex, lighten } = __testing;

describe('ogTemplate', () => {
  it('produit un arbre racine de 1200×630', () => {
    const tree = ogTemplate({ title: 'Titre' });
    expect(tree.type).toBe('div');
    expect(tree.props.style.width).toBe('1200px');
    expect(tree.props.style.height).toBe('630px');
  });

  it('inclut le titre dans l\'arbre', () => {
    const tree = ogTemplate({ title: 'Mon épisode' });
    const serialized = JSON.stringify(tree);
    expect(serialized).toContain('Mon épisode');
  });

  it('tronque un titre trop long (>90 car) sans couper un mot', () => {
    const longTitle = 'Lorem ipsum dolor sit amet '.repeat(10);
    const tree = ogTemplate({ title: longTitle });
    const titleNode = tree.props.children.find(
      (c: any) => c?.props?.style?.fontWeight === 700,
    );
    expect(titleNode).toBeTruthy();
    const txt: string = titleNode.props.children;
    expect(txt.length).toBeLessThanOrEqual(95);
    expect(txt).toMatch(/…$/);
    // Aucun mot ne doit être coupé : le dernier mot avant `…` doit être un
    // mot complet du titre source. Le titre source est "Lorem ipsum dolor
    // sit amet" répété — donc le mot précédent `…` doit appartenir à ce
    // vocabulaire (pas une fraction type "Lor" ou "ips").
    const lastWord = txt.replace(/…$/, '').trim().split(/\s+/).pop() || '';
    expect(['Lorem', 'ipsum', 'dolor', 'sit', 'amet']).toContain(lastWord);
  });

  it('mot unique de 200 chars : tronqué brutalement (pas de space à trouver)', () => {
    const monolith = 'a'.repeat(200);
    const tree = ogTemplate({ title: monolith });
    const titleNode = tree.props.children.find(
      (c: any) => c?.props?.style?.fontWeight === 700,
    );
    const txt: string = titleNode.props.children;
    expect(txt).toMatch(/…$/);
    expect(txt.length).toBeLessThanOrEqual(95);
  });

  it('utilise emoji et typeLabel quand fournis', () => {
    const tree = ogTemplate({
      title: 'Titre',
      emoji: '🎬',
      typeLabel: 'Film',
    });
    const serialized = JSON.stringify(tree);
    expect(serialized).toContain('🎬');
    expect(serialized).toContain('Film');
  });

  it('inclut sourceLabel et le branding par défaut', () => {
    const tree = ogTemplate({ title: 'X', sourceLabel: 'Un Bon Moment' });
    const serialized = JSON.stringify(tree);
    expect(serialized).toContain('Un Bon Moment');
    expect(serialized).toContain('source-internet.fr');
  });

  it('TYPE_EMOJI couvre tous les types de la collection recos', () => {
    const expected = [
      'film', 'serie', 'livre', 'bd', 'musique', 'album',
      'podcast', 'jeu', 'spectacle', 'lieu', 'artiste', 'video', 'autre',
    ];
    for (const t of expected) {
      expect((TYPE_EMOJI as any)[t], `emoji manquant pour type "${t}"`).toBeTruthy();
    }
  });

  it('tous les conteneurs ont style.display défini (contrainte Satori)', () => {
    const tree = ogTemplate({
      title: 'Titre',
      subtitle: 'Sous-titre',
      emoji: '🎬',
      typeLabel: 'Film',
      sourceLabel: 'Source',
    });
    function walk(node: any) {
      if (!node || typeof node !== 'object') return;
      const children = node.props?.children;
      const childCount = Array.isArray(children) ? children.filter(Boolean).length : 0;
      if (childCount > 1) {
        expect(
          node.props.style?.display,
          `display manquant sur ${JSON.stringify(node).slice(0, 80)}`,
        ).toBeTruthy();
      }
      if (Array.isArray(children)) {
        for (const c of children) walk(c);
      }
    }
    walk(tree);
  });

  // --- Edge cases paramétrés (CR senior H7) ---
  it.each([
    ['', 'vide'],
    ['🎬🎬🎬', 'emoji-only'],
    ["Père Noël à l'écoute", 'accents'],
    ['日本語タイトル', 'cjk'],
  ])('rend sans planter pour input "%s" (%s)', (title) => {
    expect(() => ogTemplate({ title })).not.toThrow();
    const tree = ogTemplate({ title });
    expect(tree.type).toBe('div');
  });

  // --- Validation hex (CR senior M5 / anti-injection) ---
  it('ignore les accent/bg invalides (anti-injection CSS)', () => {
    const tree = ogTemplate({
      title: 'X',
      accent: 'red; background:url(http://evil/)',
      bg: 'expression(alert(1))',
    });
    const serialized = JSON.stringify(tree);
    expect(serialized).not.toContain('evil');
    expect(serialized).not.toContain('expression');
  });

  it('accepte un hex valide (#5eead4)', () => {
    const tree = ogTemplate({ title: 'X', accent: '#5eead4' });
    const serialized = JSON.stringify(tree);
    expect(serialized).toContain('#5eead4');
  });
});

describe('truncate (helper interne)', () => {
  it("traite l'espace insécable (nbsp) comme un séparateur", () => {
    // "abc defghijklmnop" — coupe au nbsp, pas au milieu de "defgh..."
    const s = 'abc ' + 'd'.repeat(20);
    const out = truncate(s, 10);
    expect(out).toMatch(/…$/);
    expect(out.startsWith('abc')).toBe(true);
  });

  it('compte les code points, pas les unités UTF-16', () => {
    // 5 emojis surrogates = 5 code points, mais 10 unités UTF-16.
    const s = '🎬🎬🎬🎬🎬';
    const out = truncate(s, 10);
    // Pas tronqué : 5 cp ≤ 10.
    expect(out).toBe(s);
  });

  it('ne renvoie pas un surrogate orphelin', () => {
    const s = '🎬🎬🎬🎬🎬🎬';
    const out = truncate(s, 3);
    // Chaque caractère retenu est un code point complet.
    for (const cp of out.replace(/…$/, '')) {
      expect(cp).toBeTruthy();
    }
  });
});

describe('safeHex', () => {
  it('accepte #rgb, #rrggbb, #rrggbbaa', () => {
    expect(safeHex('#abc', '#000')).toBe('#abc');
    expect(safeHex('#aabbcc', '#000')).toBe('#aabbcc');
    expect(safeHex('#aabbccdd', '#000')).toBe('#aabbccdd');
  });

  it('rejette les chaînes non hex', () => {
    expect(safeHex('red', '#000')).toBe('#000');
    expect(safeHex('#zzz', '#000')).toBe('#000');
    expect(safeHex('rgb(0,0,0)', '#000')).toBe('#000');
    expect(safeHex(undefined, '#000')).toBe('#000');
  });
});

describe('lighten (gradient fin)', () => {
  it('produit un hex valide à partir de #rrggbb', () => {
    const out = lighten('#0e0e10', 0.06);
    expect(out).toMatch(/^#[0-9a-f]{6}$/);
    expect(out).not.toBe('#0e0e10');
  });

  it('développe #rgb en #rrggbb avant calcul', () => {
    const out = lighten('#000', 0.1);
    expect(out).toMatch(/^#[0-9a-f]{6}$/);
  });

  it('laisse passer un hex 8-chars sans planter', () => {
    expect(lighten('#0e0e10ff', 0.06)).toBe('#0e0e10ff');
  });
});
