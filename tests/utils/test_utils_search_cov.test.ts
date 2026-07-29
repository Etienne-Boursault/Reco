/**
 * Tests des helpers de recherche tolérante (`src/utils/search.ts`).
 *
 * Ce module est embarqué tel quel dans le `<script>` client de la page de
 * recherche : il doit rester pur et prévisible. On couvre ici :
 *   - `normalize()`   : diacritiques, casse, ligatures, chaînes vides,
 *   - `levenshtein()` : cas dégénérés (chaîne vide), les 3 opérations
 *     d'édition (insertion / suppression / substitution), symétrie,
 *   - `fuzzyMatch()`  : query vide, match par substring, les trois paliers
 *     de seuil (≤ 4, 5-7, ≥ 8 caractères), le court-circuit sur l'écart de
 *     longueur, la tokenisation multi-mots et les séparateurs du texte.
 */
import { describe, it, expect } from 'vitest';
import { normalize, levenshtein, fuzzyMatch } from '../../src/utils/search';

// ---------------------------------------------------------------------------
// normalize
// ---------------------------------------------------------------------------
describe('normalize', () => {
  it('retire les diacritiques', () => {
    expect(normalize('Vérino')).toBe('verino');
    expect(normalize('à ç é è ê ë î ô ù û')).toBe('a c e e e e i o u u');
  });

  it('passe en minuscules', () => {
    expect(normalize('LE MOINE ET LE PHILOSOPHE')).toBe(
      'le moine et le philosophe',
    );
  });

  it('laisse la chaîne vide inchangée', () => {
    expect(normalize('')).toBe('');
  });

  it('préserve la ponctuation et les espaces (pas de tokenisation ici)', () => {
    expect(normalize("L'Étranger, 1942")).toBe("l'etranger, 1942");
  });

  it('décompose les diacritiques déjà combinés (NFD)', () => {
    // 'e' + U+0301 (combining acute) doit donner le même résultat que 'é'.
    expect(normalize('é')).toBe(normalize('é'));
  });

  it('ne casse pas les caractères non latins sans diacritique', () => {
    expect(normalize('日本語')).toBe('日本語');
  });
});

// ---------------------------------------------------------------------------
// levenshtein
// ---------------------------------------------------------------------------
describe('levenshtein', () => {
  it('renvoie 0 pour deux chaînes identiques', () => {
    expect(levenshtein('verino', 'verino')).toBe(0);
  });

  it('renvoie la longueur de b quand a est vide', () => {
    expect(levenshtein('', 'abc')).toBe(3);
  });

  it('renvoie la longueur de a quand b est vide', () => {
    expect(levenshtein('abcd', '')).toBe(4);
  });

  it('renvoie 0 quand les deux chaînes sont vides', () => {
    expect(levenshtein('', '')).toBe(0);
  });

  it('compte une substitution', () => {
    expect(levenshtein('chat', 'chit')).toBe(1);
  });

  it('compte une insertion', () => {
    expect(levenshtein('chat', 'chats')).toBe(1);
  });

  it('compte une suppression', () => {
    expect(levenshtein('chats', 'chat')).toBe(1);
  });

  it('compte une transposition comme 2 opérations (pas de Damerau)', () => {
    expect(levenshtein('ab', 'ba')).toBe(2);
  });

  it('cumule plusieurs opérations', () => {
    // Valeurs de référence classiques de la distance d'édition.
    expect(levenshtein('kitten', 'sitting')).toBe(3);
    expect(levenshtein('sunday', 'saturday')).toBe(3);
    expect(levenshtein('flaw', 'lawn')).toBe(2);
    expect(levenshtein('samedi', 'dimanche')).toBe(7);
  });

  it('est symétrique', () => {
    expect(levenshtein('interstellar', 'intersteller')).toBe(
      levenshtein('intersteller', 'interstellar'),
    );
  });

  it('vaut la longueur max quand aucun caractère ne coïncide', () => {
    expect(levenshtein('abc', 'xyz')).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// fuzzyMatch — cas triviaux
// ---------------------------------------------------------------------------
describe('fuzzyMatch — query vide', () => {
  it('accepte tout quand la query est vide', () => {
    expect(fuzzyMatch('', 'le moine et le philosophe')).toBe(true);
  });

  it('accepte tout quand la query ne contient que des espaces', () => {
    expect(fuzzyMatch('   ', 'le moine et le philosophe')).toBe(true);
  });

  it('accepte tout même si le texte est vide', () => {
    expect(fuzzyMatch('', '')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// fuzzyMatch — substring
// ---------------------------------------------------------------------------
describe('fuzzyMatch — match par substring', () => {
  it('trouve un mot présent tel quel', () => {
    expect(fuzzyMatch('moine', 'le moine et le philosophe')).toBe(true);
  });

  it('ignore la casse et les accents de la query', () => {
    expect(fuzzyMatch('VÉRINO', 'verino focus')).toBe(true);
  });

  it('trouve un fragment au milieu d’un mot', () => {
    expect(fuzzyMatch('phil', 'le moine et le philosophe')).toBe(true);
  });

  it('exige que TOUS les tokens matchent', () => {
    expect(fuzzyMatch('moine philosophe', 'le moine et le philosophe')).toBe(
      true,
    );
    expect(fuzzyMatch('moine dragon', 'le moine et le philosophe')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// fuzzyMatch — seuils de tolérance selon la longueur du token
// ---------------------------------------------------------------------------
describe('fuzzyMatch — seuil pour les tokens courts (≤ 4 → 1)', () => {
  it('tolère une faute sur un token de 4 caractères', () => {
    // "chit" vs "chat" : 1 substitution ≤ 1.
    expect(fuzzyMatch('chit', 'le chat botte')).toBe(true);
  });

  it('refuse deux fautes sur un token de 4 caractères', () => {
    // "chit" vs "chat" corrigé en 2 opérations → au-delà du seuil.
    expect(fuzzyMatch('chio', 'le chat botte')).toBe(false);
  });
});

describe('fuzzyMatch — seuil pour les tokens moyens (5-7 → 2)', () => {
  it('tolère deux fautes sur un token de 6 caractères', () => {
    // "verimo" vs "verino" = 1 ; "verimu" vs "verino" = 2.
    expect(fuzzyMatch('verimu', 'verino spectacle')).toBe(true);
  });

  it('refuse trois fautes sur un token de 6 caractères', () => {
    expect(fuzzyMatch('vezimu', 'verino spectacle')).toBe(false);
  });

  it('la bascule se fait bien à 5 caractères, pas à 6', () => {
    // "camzz" (5) vs "camus" = 2 : accepté seulement si le palier ≤ 4 → 1
    // s'arrête bien à 4 caractères. Verrouille la borne du premier seuil.
    expect(fuzzyMatch('camzz', 'albert camus')).toBe(true);
  });
});

describe('fuzzyMatch — seuil pour les tokens longs (≥ 8 → 3)', () => {
  it('tolère trois fautes sur un token de 12 caractères', () => {
    // "intersteller" → "interstellar" = 1 substitution.
    expect(fuzzyMatch('intersteller', 'interstellar')).toBe(true);
    // 3 substitutions exactement.
    expect(fuzzyMatch('intxrstxllxr', 'interstellar')).toBe(true);
  });

  it('refuse quatre fautes sur un token long', () => {
    expect(fuzzyMatch('xntxrstxllxr', 'interstellar')).toBe(false);
  });

  it('la bascule vers 3 se fait dès 8 caractères, pas 9', () => {
    // "polanxyz" (8) vs "polanski" = 3 : accepté seulement si un token de 8
    // relève déjà du seuil 3. Verrouille la borne du second palier.
    expect(fuzzyMatch('polanxyz', 'roman polanski')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// fuzzyMatch — court-circuit sur l'écart de longueur
// ---------------------------------------------------------------------------
describe('fuzzyMatch — écart de longueur', () => {
  it('rejette un mot bien trop court pour le token (garde |Δlen| > seuil)', () => {
    // Token de 8 → seuil 3 ; le seul mot du texte fait 2 caractères.
    expect(fuzzyMatch('cathedra', 'le xy')).toBe(false);
  });

  it('rejette un mot bien trop long pour le token', () => {
    // Token de 5 → seuil 2 ; "anticonstitutionnellement" est hors de portée.
    expect(fuzzyMatch('abcde', 'anticonstitutionnellement')).toBe(false);
  });

  it('accepte un mot dont l’écart de longueur reste dans le seuil', () => {
    // "philosoph" (9) vs "philosophe" (10) : Δ = 1 ≤ 3 et distance 1.
    expect(fuzzyMatch('philosoph', 'le moine et le philosophe')).toBe(true);
  });

  it('accepte un écart de longueur ÉGAL au seuil (garde stricte, pas ≥)', () => {
    // "chat" (4, seuil 1) vs "chxat" (5) : Δ = 1 = seuil, distance 1. Le
    // token n'est pas un substring du texte, donc on passe bien par la
    // garde de longueur puis par Levenshtein.
    expect(fuzzyMatch('chat', 'le chxat')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// fuzzyMatch — tokenisation du texte indexé
// ---------------------------------------------------------------------------
describe('fuzzyMatch — séparateurs du texte indexé', () => {
  it('découpe sur l’apostrophe droite', () => {
    // "etrangar" vs le mot "etranger" isolé par l'apostrophe.
    expect(fuzzyMatch('etrangar', "l'etranger")).toBe(true);
  });

  it('découpe sur l’apostrophe typographique', () => {
    expect(fuzzyMatch('etrangar', 'l’etranger')).toBe(true);
  });

  it('découpe sur la virgule', () => {
    expect(fuzzyMatch('camuz', 'l’etranger, camus')).toBe(true);
  });

  it('découpe sur les parenthèses', () => {
    expect(fuzzyMatch('nolam', 'interstellar (nolan)')).toBe(true);
  });

  it('découpe sur la barre oblique', () => {
    expect(fuzzyMatch('musiqua', 'film/musique')).toBe(true);
  });

  it('découpe sur le tiret', () => {
    expect(fuzzyMatch('sciance', 'science-fiction')).toBe(true);
  });

  it('ignore les segments vides produits par des séparateurs consécutifs', () => {
    // Le texte commence et finit par des séparateurs : le `.filter(Boolean)`
    // doit écarter les chaînes vides sans fausser le résultat.
    expect(fuzzyMatch('camuz', ' , (camus) - ')).toBe(true);
    expect(fuzzyMatch('zzzzz', ' , () - ')).toBe(false);
  });

  it('un token d’un seul caractère ne matche pas un texte sans mot', () => {
    // Sans `.filter(Boolean)`, le segment vide passerait la garde de
    // longueur (Δ = 1 = seuil) et Levenshtein ('z' → '' = 1 ≤ 1), donnant
    // un faux positif sur une recherche à une lettre.
    expect(fuzzyMatch('z', ' , () - ')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// fuzzyMatch — combinaisons
// ---------------------------------------------------------------------------
describe('fuzzyMatch — multi-tokens', () => {
  it('mélange un token exact et un token approximatif', () => {
    expect(fuzzyMatch('moine philosoph', 'le moine et le philosophe')).toBe(
      true,
    );
  });

  it('échoue dès qu’un seul token ne matche pas', () => {
    expect(fuzzyMatch('moine philosoph dragon', 'le moine et le philosophe')).toBe(
      false,
    );
  });

  it('tolère des espaces multiples entre les tokens', () => {
    expect(fuzzyMatch('  moine   philosophe  ', 'le moine et le philosophe')).toBe(
      true,
    );
  });

  it('ne matche rien contre un texte vide', () => {
    expect(fuzzyMatch('moine', '')).toBe(false);
  });
});
