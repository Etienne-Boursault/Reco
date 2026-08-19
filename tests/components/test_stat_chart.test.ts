/**
 * Tests StatChart — F-H-10/11/12, F-M-5.
 *
 *  - F-H-10 : `<title>` enfant DIRECT du `<svg>` (a11y graphique).
 *  - F-H-11 : labels — > 12 barres ⇒ 1 label / N ; sinon tronquer à 8 chars + …
 *  - F-H-12 : pas d'attribut `height` sur le `<svg>` ; aspect-ratio CSS.
 *  - F-M-5  : prop `emptyKey` permet de surcharger `emptyMessage` via i18n.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import StatChart from '../../src/components/StatChart.astro';

async function render(props: Record<string, unknown>): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(StatChart as any, { props });
}

describe('StatChart — A11y / labels / dimensions', () => {
  it('F-H-10 : <title> enfant direct du <svg> avec le titre', async () => {
    const html = await render({
      title: 'Répartition par type',
      bars: [{ label: 'film', value: 10 }],
    });
    // <svg ...><title>Répartition par type</title>... — premier enfant.
    expect(html).toMatch(/<svg[^>]*>\s*<title>Répartition par type<\/title>/);
  });

  it('F-H-12 : pas d\'attribut height sur le <svg>', async () => {
    const html = await render({
      title: 'x',
      bars: [{ label: 'a', value: 1 }],
    });
    const svgTag = html.match(/<svg[^>]*>/)?.[0] ?? '';
    expect(svgTag).not.toMatch(/\sheight=/);
  });

  it('F-H-12 : aspect-ratio CSS posé sur le <svg>', async () => {
    const html = await render({
      title: 'x',
      bars: [{ label: 'a', value: 1 }],
    });
    const svgTag = html.match(/<svg[^>]*>/)?.[0] ?? '';
    expect(svgTag).toMatch(/aspect-ratio:\s*\d+\s*\/\s*\d+/);
  });

  // F-H-11 REVISE le 2026-08-19. Ces deux tests exigeaient l'inverse : un
  // libelle tronque a huit caracteres, et un sur N masque au-dela de douze
  // barres. L'intention — eviter le chevauchement — reste la bonne ; la
  // solution a change, parce que masquer et tronquer rendait le graphique
  // illisible : « affiche tous les noms de toutes les colonnes ».
  //
  // On INCLINE desormais plutot que de couper. Les tests suivent.
  it('F-H-11 : un libellé long n’est plus tronqué', async () => {
    const bars = Array.from({ length: 5 }, (_, i) => ({
      label: `LibelléTrèsLong${i}`,
      value: i + 1,
    }));
    const html = await render({ title: 'x', bars });
    expect(html).toContain('LibelléTrèsLong0');
    expect(html).not.toMatch(/>LibelléT…</);
  });

  it('F-H-11 : au-delà de douze barres, tous les libellés restent rendus', async () => {
    const bars = Array.from({ length: 24 }, (_, i) => ({
      label: `m${i.toString().padStart(2, '0')}`,
      value: i,
    }));
    const html = await render({ title: 'monthly', bars });
    const labels = [...html.matchAll(/<text[^>]*class="bar-label"[^>]*>([^<]*)<\/text>/g)];
    const nonVides = labels.filter((m) => m[1].trim().length > 0);
    expect(labels.length).toBe(24);
    expect(nonVides.length).toBe(24);
  });

  it('F-M-5 : emptyKey override le message via i18n', async () => {
    const html = await render({
      title: 'Répartition',
      bars: [],
      emptyKey: 'stats.empty.typeDistribution',
    });
    expect(html).toContain('Pas encore assez de données.');
  });

  it('fallback emptyMessage si emptyKey absent', async () => {
    const html = await render({
      title: 'x',
      bars: [],
      emptyMessage: 'custom vide',
    });
    expect(html).toContain('custom vide');
  });
});

describe('StatChart — tous les libellés, et les groupes (2026-08-19)', () => {
  const barres = (n: number) =>
    Array.from({ length: n }, (_, i) => ({ label: `L${i}`, value: i + 1 }));

  it('affiche TOUS les libellés, même au-delà de douze barres', async () => {
    // Le graphique « répartition par type » en compte quatorze : un sur deux
    // etait masque, et la relecture du 2026-08-19 a demande a les voir tous.
    const html = await render({ title: 'T', bars: barres(14) });
    for (let i = 0; i < 14; i++) expect(html).toContain(`>L${i}<`);
  });

  it('ne tronque plus les libellés courts', async () => {
    const html = await render({
      title: 'T',
      bars: [{ label: 'Applications', value: 1 }, { label: 'Spectacles', value: 2 }],
    });
    expect(html).toContain('Applications');
    expect(html).not.toContain('Applicat…');
  });

  it('incline les libellés quand les colonnes sont étroites', async () => {
    // Quatorze libellés horizontaux se chevaucheraient. L'inclinaison est ce
    // qui permet de tous les montrer sans les tronquer.
    const html = await render({ title: 'T', bars: barres(20) });
    expect(html).toContain('rotate(-45');
  });

  it('laisse les libellés droits quand il y a de la place', async () => {
    const html = await render({ title: 'T', bars: barres(4) });
    expect(html).not.toContain('rotate(-45');
  });

  it('trace un séparateur à chaque changement de groupe', async () => {
    // Les mois s'etalent sur six ans : sans repere, on cherche l'annee a
    // l'oeil. Signale a la relecture.
    const html = await render({
      title: 'Épisodes par mois',
      bars: [
        { label: 'jan', value: 1, groupe: '2020' },
        { label: 'fév', value: 2, groupe: '2020' },
        { label: 'jan', value: 3, groupe: '2021' },
      ],
    });
    expect(html).toContain('class="separateur-groupe"');
  });

  it('affiche le nom du groupe une seule fois par bloc', async () => {
    const html = await render({
      title: 'T',
      bars: [
        { label: 'jan', value: 1, groupe: '2020' },
        { label: 'fév', value: 2, groupe: '2020' },
        { label: 'jan', value: 3, groupe: '2021' },
      ],
    });
    expect((html.match(/>2020</g) ?? []).length).toBe(1);
    expect((html.match(/>2021</g) ?? []).length).toBe(1);
  });

  it('ne trace aucun séparateur avant la première barre', async () => {
    // Une ligne collee au bord gauche ne separe rien.
    const html = await render({
      title: 'T', bars: [{ label: 'jan', value: 1, groupe: '2020' }],
    });
    expect(html).not.toContain('class="separateur-groupe"');
  });

  it('reste inchangé quand aucune barre ne porte de groupe', async () => {
    const html = await render({ title: 'T', bars: barres(5) });
    expect(html).not.toContain('separateur-groupe');
  });
});

describe('StatChart — cadre et libellés (2026-08-19, seconde passe)', () => {
  const barres = (n: number, long = false) =>
    Array.from({ length: n }, (_, i) => ({
      label: long ? `LibelléAssezLong${i}` : `L${i}`,
      value: i + 1,
    }));

  it('agrandit la marge basse quand les libellés sont inclinés', async () => {
    // Inclines a -45°, ils descendaient sous le cadre et s'y trouvaient
    // coupes. Signale a la relecture : « les titres sont caches par le cadre ».
    const droit = await render({ title: 'T', bars: barres(4) });
    const incline = await render({ title: 'T', bars: barres(20, true) });
    const hauteur = (html: string) =>
      Number(/viewBox="0 0 600 (\d+)"/.exec(html)?.[1] ?? 0);
    expect(hauteur(incline)).toBeGreaterThan(hauteur(droit));
  });

  it('n’écrit aucun libellé sous les barres quand on les désactive', async () => {
    // Les mois s'entassaient au point d'etre illisibles : « mon idee pour les
    // annees etait bonne pour les mois, tu peux les enlever ».
    const html = await render({
      title: 'Épisodes par mois',
      libelles: 'aucun',
      bars: [
        { label: 'jan', value: 1, groupe: '2020' },
        { label: 'fév', value: 2, groupe: '2020' },
      ],
    });
    expect(html).not.toContain('class="bar-label"');
  });

  it('garde les libellés dans le tableau accessible, même désactivés', async () => {
    // Le graphique reste lisible au lecteur d'ecran : ce qu'on retire, c'est
    // l'encombrement visuel, jamais l'information.
    const html = await render({
      title: 'T', libelles: 'aucun',
      bars: [{ label: 'jan', value: 1, groupe: '2020' }],
    });
    // Astro pose un attribut de portee sur chaque balise : on cherche le
    // contenu de la cellule, pas la balise nue.
    expect(html).toMatch(/<td[^>]*>jan<\/td>/);
  });

  it('garde les groupes quand les libellés sont désactivés', async () => {
    const html = await render({
      title: 'T', libelles: 'aucun',
      bars: [
        { label: 'jan', value: 1, groupe: '2020' },
        { label: 'jan', value: 2, groupe: '2021' },
      ],
    });
    expect(html).toContain('>2020<');
    expect(html).toContain('separateur-groupe');
  });

  it('affiche les libellés par défaut', async () => {
    const html = await render({ title: 'T', bars: barres(3) });
    expect(html).toContain('class="bar-label"');
  });

  // ===== Le cadre loge les libelles ======================================
  //
  // « Les titres sont cachés par le cadre, tu peux ajuster ? Les titres et/ou
  // le cadre ? » (relecture du 2026-08-19). Ces trois tests vérifient la
  // géométrie plutôt que l'apparence : un libellé incliné à -45° descend de
  // `longueur × 6 × sin(45°)` sous son ancre, et ce point doit rester dans le
  // viewBox.
  /** Le point le plus bas atteint par un libellé, en unités du viewBox. */
  const basDesLibelles = (html: string): number => {
    const ancre = /class="bar-label"[^>]*/.test(html)
      ? Number(/<text[^>]*?y="([\d.]+)"[^>]*?class="bar-label"/.exec(html)?.[1] ?? NaN)
      : NaN;
    const textes = [...html.matchAll(/class="bar-label"[^>]*>([^<]+)</g)].map((m) => m[1]);
    const plusLong = Math.max(0, ...textes.map((t) => t.length));
    const incline = html.includes('rotate(-45');
    return ancre + (incline ? plusLong * 6 * Math.SQRT1_2 : 0) + 3;
  };

  /** La hauteur du viewBox — le cadre visible. */
  const hauteurCadre = (html: string): number =>
    Number(/viewBox="0 0 600 (\d+)"/.exec(html)?.[1] ?? NaN);

  it('loge les libellés courts sans agrandir le cadre', async () => {
    const html = await render({
      title: 'T',
      bars: [{ label: 'Jeux', value: 3 }, { label: 'BD', value: 1 }],
    });
    expect(basDesLibelles(html)).toBeLessThanOrEqual(hauteurCadre(html));
  });

  it('agrandit le cadre pour loger quatorze libellés inclinés', async () => {
    // Le cas signalé : la répartition par type, quatorze colonnes étroites.
    const types = ['Films', 'Artistes', 'Musique', 'Séries', 'Livres',
      'Spectacles', 'Chaînes', 'Vidéos', 'Autres', 'Podcasts', 'Albums',
      'Jeux', 'BD', 'Lieux'];
    const html = await render({
      title: 'T', bars: types.map((label, i) => ({ label, value: 20 - i })),
    });
    expect(html).toContain('rotate(-45');
    expect(basDesLibelles(html)).toBeLessThanOrEqual(hauteurCadre(html));
  });

  it('loge un libellé très long — le plafond fixe le coupait', async () => {
    // La version précédente plafonnait la marge à 96 px, ce qui coupait tout
    // libellé de plus de dix-sept caractères. Un nom d'invité y arrive.
    const html = await render({
      title: 'T',
      bars: Array.from({ length: 14 }, (_, i) => ({
        label: `Jean-Baptiste Machin ${i}`, value: 14 - i,
      })),
    });
    expect(basDesLibelles(html)).toBeLessThanOrEqual(hauteurCadre(html));
  });

  // ===== Le bord GAUCHE aussi ============================================
  //
  // « [Image] Albums est tronqué » (relecture du 2026-08-19, seconde salve).
  // Un libellé ancré par sa fin et tourné de -45° se projette vers le bas ET
  // vers la gauche, de la même longueur. Seule la marge basse était réservée :
  // le premier libellé sortait du cadre et perdait sa première lettre.
  /** L'abscisse la plus à gauche atteinte par le premier libellé. */
  const gaucheDuPremierLabel = (html: string): number => {
    const x = Number(/<text[^>]*?x="([\d.]+)"[^>]*?class="bar-label"/.exec(html)?.[1] ?? NaN);
    const texte = /class="bar-label"[^>]*>([^<]+)</.exec(html)?.[1] ?? '';
    const incline = html.includes('rotate(-45');
    // 7,2 px par glyphe à 12 px, projetés par cos(45°).
    return x - (incline ? texte.length * 7.2 * Math.SQRT1_2 : 0);
  };

  it('garde le premier libellé incliné dans le cadre', async () => {
    // Le cas exact : « Albums » ouvre la répartition par type, en ordre
    // alphabétique, sur quatorze colonnes.
    const html = await render({
      title: 'T',
      bars: ['Albums', 'Artistes', 'Autres', 'BD', 'Chaînes', 'Films', 'Jeux',
        'Livres', 'Musique', 'Podcasts', 'Séries', 'Spectacles', 'Vidéos',
        'Lieux'].map((label, i) => ({ label, value: 20 - i })),
    });
    expect(html).toContain('rotate(-45');
    expect(gaucheDuPremierLabel(html)).toBeGreaterThanOrEqual(0);
  });

  it('réserve la marge gauche à la mesure du premier libellé, pas plus', async () => {
    // Un libellé court ne doit pas rétrécir les barres pour rien.
    const court = await render({
      title: 'T', bars: Array.from({ length: 14 }, (_, i) => ({ label: 'BD', value: 14 - i })),
    });
    const long = await render({
      title: 'T',
      bars: Array.from({ length: 14 }, (_, i) => ({
        label: i === 0 ? 'Documentaires animaliers' : 'BD', value: 14 - i,
      })),
    });
    const premiereBarre = (html: string) =>
      Number(/<rect x="([\d.]+)"/.exec(html)?.[1] ?? NaN);
    expect(premiereBarre(long)).toBeGreaterThan(premiereBarre(court));
    expect(gaucheDuPremierLabel(long)).toBeGreaterThanOrEqual(0);
  });

  it('ne réserve aucune marge gauche quand les libellés sont droits', async () => {
    // Un libellé horizontal est centré sous sa barre : il ne sort pas à
    // gauche, et rien ne justifie de rétrécir le graphique.
    const premiereBarre = (html: string) =>
      Number(/<rect x="([\d.]+)"/.exec(html)?.[1] ?? NaN);
    const court = await render({ title: 'T', bars: barres(3) });
    const long = await render({
      title: 'T',
      bars: [{ label: 'Documentaires animaliers', value: 1 },
             { label: 'L1', value: 2 }, { label: 'L2', value: 3 }],
    });
    expect(court).not.toContain('rotate(-45');
    expect(premiereBarre(long)).toBe(premiereBarre(court));
  });
});
