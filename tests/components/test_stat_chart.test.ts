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
