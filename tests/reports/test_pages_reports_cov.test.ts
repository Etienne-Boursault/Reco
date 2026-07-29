/**
 * tests/reports/test_pages_reports_cov.test.ts
 *
 * Les deux pages liées aux signalements :
 *  - `src/pages/[source]/reports.astro` — queue admin (noindex), lue
 *    build-time via `listReports` ;
 *  - `src/pages/[source]/report/[recoId].astro` — formulaire public par reco.
 *
 * `listReports` est mocké (pas de lecture de `tools/output/reports/`) et
 * `astro:content` aussi : les tests restent déterministes.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderPage, visibleText } from '../gallery/_render_page';

const getCollection = vi.fn();
vi.mock('astro:content', () => ({
  getCollection: (name: string) => getCollection(name),
}));

const listReports = vi.fn();
vi.mock('../../src/lib/reports/storage.js', () => ({
  listReports: (sourceId: string) => listReports(sourceId),
}));

import ReportsQueue, { getStaticPaths as queuePaths } from '../../src/pages/[source]/reports.astro';
import ReportForm, { getStaticPaths as formPaths } from '../../src/pages/[source]/report/[recoId].astro';

interface Entry {
  data: Record<string, unknown>;
}

const SOURCE = {
  id: 'ubm',
  data: {
    id: 'ubm',
    title: 'Un Bon Moment',
    theme: { colors: { bg: '#101010', surface: '#181818', text: '#fff', muted: '#999', accent: '#ff5500' } },
  },
};

function seed(map: Partial<Record<'sources' | 'recos', Entry[]>>): void {
  getCollection.mockImplementation(async (name: string) => map[name as never] ?? []);
}

function report(over: Record<string, unknown> = {}) {
  return {
    id: 'rep-0001',
    sourceId: 'ubm',
    recoId: 'ubm-0001',
    category: 'error',
    details: 'Le titre est faux.',
    submitter: { wantCredit: false },
    submittedAt: '2026-07-01T10:00:00Z',
    status: 'pending',
    resolvedAt: null,
    resolvedBy: null,
    notes: null,
    ...over,
  };
}

beforeEach(() => {
  getCollection.mockReset();
  getCollection.mockImplementation(async () => []);
  listReports.mockReset();
  listReports.mockReturnValue([]);
});

// ---------------------------------------------------------------------------
// /[source]/reports — queue admin
// ---------------------------------------------------------------------------
describe('/[source]/reports — queue admin', () => {
  const render = () =>
    renderPage(ReportsQueue, {
      params: { source: 'ubm' },
      props: { source: SOURCE },
      path: '/ubm/reports',
    });

  it('getStaticPaths émet une page par source', async () => {
    seed({ sources: [SOURCE, { id: 'autre', data: { id: 'autre', title: 'Autre' } } as never] });
    const paths = (await queuePaths()) as Array<{ params: { source: string } }>;

    expect(paths.map((p) => p.params.source)).toEqual(['ubm', 'autre']);
  });

  it('interroge `listReports` avec l’id de la source', async () => {
    await render();
    expect(listReports).toHaveBeenCalledWith('ubm');
  });

  it('est marquée noindex (page interne)', async () => {
    expect(await render()).toContain('<meta name="robots" content="noindex, nofollow">');
  });

  it('queue vide → message dédié, aucune liste', async () => {
    const text = visibleText(await render());

    expect(text).toContain('Aucun signalement en attente.');
    expect(await render()).not.toContain('class="reports"');
  });

  it('ventile les compteurs par statut', async () => {
    listReports.mockReturnValue([
      report({ id: 'a', status: 'pending' }),
      report({ id: 'b', status: 'pending' }),
      report({ id: 'c', status: 'resolved' }),
      report({ id: 'd', status: 'dismissed' }),
    ]);
    const text = visibleText(await render());

    expect(text).toContain('2 en attente');
    expect(text).toContain('1 résolus');
    expect(text).toContain('1 écartés');
  });

  it('n’affiche que les signalements `pending` dans la liste', async () => {
    listReports.mockReturnValue([
      report({ id: 'a', details: 'À traiter' }),
      report({ id: 'b', status: 'resolved', details: 'Déjà traité' }),
    ]);
    const text = visibleText(await render());

    expect(text).toContain('À traiter');
    expect(text).not.toContain('Déjà traité');
  });

  it('traduit les catégories connues et laisse la clé brute sinon', async () => {
    listReports.mockReturnValue([
      report({ id: 'a', category: 'broken-link' }),
      report({ id: 'b', category: 'inconnue' }),
    ]);
    const text = visibleText(await render());

    expect(text).toContain('Lien cassé');
    expect(text).toContain('inconnue');
  });

  it('lie chaque signalement à la page de report de sa reco', async () => {
    listReports.mockReturnValue([report({ recoId: 'ubm-0042' })]);
    const html = await render();

    expect(html).toContain('href="/ubm/report/ubm-0042"');
    expect(html).toContain('ubm-0042');
  });

  it('affiche nom, email et souhait de crédit quand ils sont fournis', async () => {
    listReports.mockReturnValue([
      report({ submitter: { name: 'Camille', email: 'c@exemple.fr', wantCredit: true } }),
    ]);
    const text = visibleText(await render());

    expect(text).toContain('Camille');
    expect(text).toContain('<c@exemple.fr>');
    expect(text).toContain('veut être crédité');
  });

  it('aucun bloc « auteur » quand le signalement est anonyme', async () => {
    listReports.mockReturnValue([report()]);
    const html = await render();

    expect(html).not.toContain('class="submitter"');
  });

  it('un nom sans email n’affiche pas de chevrons vides', async () => {
    listReports.mockReturnValue([
      report({ submitter: { name: 'Camille', wantCredit: false } }),
    ]);
    const text = visibleText(await render());

    expect(text).toContain('Camille');
    expect(text).not.toContain('<>');
    expect(text).not.toContain('veut être crédité');
  });

  it('formate la date de soumission en locale FR', async () => {
    listReports.mockReturnValue([report({ submittedAt: '2026-07-01T10:00:00Z' })]);
    const text = visibleText(await render());

    expect(text).toContain(new Date('2026-07-01T10:00:00Z').toLocaleString('fr-FR'));
  });

  it('une date illisible est affichée telle quelle plutôt que « Invalid Date »', async () => {
    listReports.mockReturnValue([report({ submittedAt: 'pas-une-date' })]);
    const text = visibleText(await render());

    expect(text).toContain('Invalid Date');
    expect(text).not.toContain('undefined');
  });

  it('rappelle la commande CLI de résolution', async () => {
    const text = visibleText(await render());
    expect(text).toContain('python tools/manage_reports.py --resolve <id>');
  });
});

// ---------------------------------------------------------------------------
// /[source]/report/[recoId] — formulaire public
// ---------------------------------------------------------------------------
describe('/[source]/report/[recoId] — formulaire', () => {
  function reco(id: string, over: Record<string, unknown> = {}): Entry {
    return {
      data: {
        id,
        title: `Reco ${id}`,
        types: ['film'],
        sourceId: { id: 'ubm' },
        episodeGuid: 'g1',
        status: 'validated',
        kind: 'reco',
        ...over,
      },
    };
  }

  async function paths(): Promise<Array<{ params: { source: string; recoId: string }; props: Record<string, unknown> }>> {
    return (await formPaths()) as never;
  }

  it('une route par reco signalable', async () => {
    seed({ sources: [SOURCE], recos: [reco('ubm-0001'), reco('ubm-0002')] });
    const p = await paths();

    expect(p.map((x) => x.params)).toEqual([
      { source: 'ubm', recoId: 'ubm-0001' },
      { source: 'ubm', recoId: 'ubm-0002' },
    ]);
  });

  it('les recos `discarded` ne sont pas signalables', async () => {
    seed({
      sources: [SOURCE],
      recos: [reco('ubm-0001'), reco('ubm-0002', { status: 'discarded' })],
    });

    expect((await paths()).map((x) => x.params.recoId)).toEqual(['ubm-0001']);
  });

  it('une reco orpheline (source inconnue) est ignorée', async () => {
    seed({
      sources: [SOURCE],
      recos: [reco('ubm-0001'), reco('x-0001', { sourceId: { id: 'inexistante' } })],
    });

    expect((await paths()).map((x) => x.params.recoId)).toEqual(['ubm-0001']);
  });

  it('rend le formulaire avec le contexte de la reco et en noindex', async () => {
    seed({ sources: [SOURCE], recos: [reco('ubm-0001', { title: 'Parasite' })] });
    const p = await paths();
    const html = await renderPage(ReportForm, {
      params: p[0].params,
      props: p[0].props,
      path: '/ubm/report/ubm-0001',
    });

    expect(html).toContain('<title>Signaler — Parasite — Reco</title>');
    expect(html).toContain('<meta name="robots" content="noindex, nofollow">');
    expect(html).toContain('href="/ubm"');
    expect(html).toContain('ubm-0001');
    expect(visibleText(html)).toContain('Signaler un problème');
    // Le thème de la source est bien transmis.
    expect(html).toContain('--accent:#ff5500');
  });
});
