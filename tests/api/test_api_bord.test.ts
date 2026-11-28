/**
 * Tests de `GET /api/bord` (`src/routes/api-bord.ts`) — l'audience lue par le
 * tableau de bord de venus (tableau de bord, R2 B du 27/11/2026 ; TB-1 C du
 * 28/11/2026, l'audience au centre).
 *
 * CE QU'ILS PROTÈGENT
 * -------------------
 * - L'accès : la clé arrive dans l'en-tête `X-Reco-Cle`, jamais dans l'URL ;
 *   sans elle, ou pour une autre méthode que GET, la route n'existe pas (404).
 * - La même lecture que `/audience` : les deux pages rendent les mêmes
 *   chiffres sur les mêmes mesures (familles F2 et F10 du registre).
 * - Les signalements sortent sans nom, adresse ni texte libre (F15).
 *
 * La clé d'essai est visiblement fausse ; aucune vraie valeur n'entre ici.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { ALL } from '../../src/routes/api-bord';
import Page from '../../src/routes/audience.astro';

const CLE = 'fausse-cle-d-essai-pour-les-tests';
const HOTE = 'https://exemple.test';
let cleInitiale: string | undefined;
let avant: string;
let racine: string;

beforeEach(() => {
  cleInitiale = process.env.RECO_AUDIENCE_KEY;
  process.env.RECO_AUDIENCE_KEY = CLE;
  avant = process.cwd();
  racine = mkdtempSync(path.join(tmpdir(), 'reco-api-bord-'));
  process.chdir(racine);
});

afterEach(() => {
  process.chdir(avant);
  rmSync(racine, { recursive: true, force: true });
  if (cleInitiale === undefined) delete process.env.RECO_AUDIENCE_KEY;
  else process.env.RECO_AUDIENCE_KEY = cleInitiale;
  vi.restoreAllMocks();
});

async function appeler(
  { methode = 'GET', chemin = '/api/bord', entetes = { 'X-Reco-Cle': CLE } as Record<string, string> } = {},
) {
  const url = new URL(chemin, HOTE);
  const request = new Request(url, { method: methode, headers: entetes });
  return (await ALL({ request, url, site: undefined } as never)) as Response;
}

const jourRel = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString().slice(0, 10);

/** Écrit les lignes dans un fichier par jour, comme la mesure. */
function ecrire(genre: 'audience' | 'clicks', source: string, lignes: Record<string, unknown>[]) {
  const dossier = path.join(racine, 'tools', 'output', genre, source);
  mkdirSync(dossier, { recursive: true });
  for (const jour of new Set(lignes.map((l) => String(l.ts).slice(0, 10)))) {
    writeFileSync(
      path.join(dossier, `${jour}.jsonl`),
      lignes.filter((l) => String(l.ts).startsWith(jour)).map((l) => `${JSON.stringify(l)}\n`).join(''),
      'utf8',
    );
  }
}

function signalement(over: Record<string, unknown> = {}) {
  return {
    id: 'rep-1', sourceId: 'un-bon-moment', recoId: 'ubm-1', category: 'error',
    details: 'Le texte libre de la personne', status: 'pending',
    submitter: { name: 'Camille Témoin', email: 'camille@exemple.test', wantCredit: true },
    submittedAt: `${jourRel(1)}T08:00:00.000Z`, resolvedAt: null, resolvedBy: null, notes: null,
    ...over,
  };
}

function ecrireSignalement(rapport: Record<string, unknown>, source = 'un-bon-moment') {
  const dossier = path.join(racine, 'tools', 'output', 'reports', source);
  mkdirSync(dossier, { recursive: true });
  writeFileSync(path.join(dossier, `${rapport.id}.json`), JSON.stringify(rapport), 'utf8');
}

const id = (i: number) => `v${String(i).padStart(11, '0')}`;
const visite = (i: number, jour: string, over: Record<string, unknown> = {}) => ({
  ts: `${jour}T10:00:00.000Z`, chemin: '/un-bon-moment/films', statut: 200, robot: false,
  appareil: 'mobile', provenance: null, langue: 'fr', pays: 'FR', hebergeur: false,
  visiteur: id(i), dureeMs: 5, ...over,
});
const signal = (i: number, jour: string) => ({
  ts: `${jour}T10:00:00.000Z`, nature: 'signal', chemin: '/un-bon-moment/films',
  hebergeur: false, visiteur: id(i),
});

/**
 * Des mesures qui franchissent la bascule : un jour sans signal, le premier
 * jour de signaux (tenu pour incomplet), puis la bascule. Un jour ancien, hors
 * de la fenêtre de 7 jours, sépare les deux fenêtres ; `_site` porte l'accueil
 * et une provenance, des clics donnent le ratio.
 */
function mesuresApresBascule() {
  ecrire('audience', 'un-bon-moment', [
    visite(20, jourRel(15)), visite(21, jourRel(15)),
    visite(0, jourRel(5)),
    visite(0, jourRel(4)), signal(0, jourRel(4)),
    ...[0, 1, 2].map((i) => visite(i, jourRel(3))), ...[0, 1].map((i) => signal(i, jourRel(3))),
    visite(9, jourRel(3), { robot: true }),
  ]);
  ecrire('audience', '_site', [
    visite(5, jourRel(3), { chemin: '/', provenance: 'ailleurs.test' }),
  ]);
  ecrire('clicks', 'un-bon-moment', [
    { ts: `${jourRel(3)}T10:05:00.000Z`, url: 'https://exemple.test/x', category: 'tmdb',
      sourceId: 'un-bon-moment', recoId: 'ubm-1', ref: '/un-bon-moment/films' },
  ]);
}

// ===== L'accès ==============================================================
describe('GET /api/bord : l’accès', () => {
  it('répond 404 sans clé', async () => {
    const reponse = await appeler({ entetes: {} });

    expect(reponse.status).toBe(404);
    expect(reponse.headers.get('Cache-Control')).toBe('no-store');
  });

  it('répond 404 avec une mauvaise clé', async () => {
    expect((await appeler({ entetes: { 'X-Reco-Cle': 'une-autre-cle-tout-aussi-fausse' } })).status).toBe(404);
  });

  it('répond 404 quand la clé est passée dans l’URL au lieu de l’en-tête', async () => {
    const reponse = await appeler({ chemin: `/api/bord?cle=${CLE}`, entetes: {} });

    expect(reponse.status).toBe(404);
  });

  it('répond 404 à un POST, même avec la bonne clé', async () => {
    expect((await appeler({ methode: 'POST' })).status).toBe(404);
  });

  it('répond 404 quand aucune clé n’est configurée', async () => {
    delete process.env.RECO_AUDIENCE_KEY;

    expect((await appeler()).status).toBe(404);
  });

  it('répond 200 en JSON avec la bonne clé, sans mise en cache', async () => {
    const reponse = await appeler();

    expect(reponse.status).toBe(200);
    expect(reponse.headers.get('Content-Type')).toBe('application/json; charset=utf-8');
    expect(reponse.headers.get('Cache-Control')).toBe('no-store');
    expect(reponse.headers.get('X-Robots-Tag')).toBe('noindex, nofollow');
  });
});

// ===== Les chiffres =========================================================
describe('GET /api/bord : les mêmes chiffres que /audience', () => {
  /** Les tuiles du haut de `/audience`, lues dans le texte de la page. */
  async function tuilesDeLaPage(jours: number) {
    const container = await AstroContainer.create();
    const reponse = await container.renderToResponse(Page, {
      request: new Request(`${HOTE}/audience?cle=${CLE}&jours=${jours}`),
    });
    const texte = (await reponse.text()).replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
    const haut = texte.match(
      /(\S+) pages vues (\S+) visiteurs (\S+) clics pour 100 visiteurs (\S+) clics vers une œuvre (\S+) passages de robots/,
    );
    const colonnes = [...texte.matchAll(/(\d+) (Confirmés|Incertains|Robots) \(visiteurs-jours\) · (\d+) visites/g)]
      .map((m) => `${m[2]} ${m[1]}/${m[3]}`);
    return { haut: haut?.slice(1), colonnes };
  }

  const nf = new Intl.NumberFormat('fr-FR');

  it('sur 7 et sur 30 jours, après la bascule', async () => {
    mesuresApresBascule();
    const resume = await (await appeler()).json();

    for (const [jours, fenetre] of [[7, resume.sept], [30, resume.trente]] as const) {
      const page = await tuilesDeLaPage(jours);
      expect(page.haut).toEqual([
        nf.format(fenetre.pagesVues),
        nf.format(fenetre.visiteurs),
        fenetre.clicsPour100Visiteurs.toLocaleString('fr-FR'),
        nf.format(fenetre.clics),
        nf.format(fenetre.visitesRobots),
      ]);
      const c = fenetre.colonnes;
      expect(page.colonnes).toEqual([
        `Confirmés ${c.confirmes.visiteursJours}/${c.confirmes.visites}`,
        `Incertains ${c.incertains.visiteursJours}/${c.incertains.visites}`,
        `Robots ${c.robots.visiteursJours}/${c.robots.visites}`,
      ]);
    }
    // Les deux fenêtres diffèrent vraiment : le jour ancien n'est que dans 30 jours.
    expect(resume.trente.visiteurs).toBeGreaterThan(resume.sept.visiteurs);
    expect(resume.sept.tri).toBe('trois-colonnes');
    expect(resume.sept.bascule).toBe(jourRel(3));
    // `_site` est lu : l'accueil et sa provenance sont dans le résumé.
    expect(resume.sept.pages.map((p: { cle: string }) => p.cle)).toContain('/');
    expect(resume.sept.provenances).toEqual([{ cle: 'ailleurs.test', n: 1 }]);
    expect(resume.jours.map((j: { jour: string }) => j.jour)).toEqual([jourRel(5), jourRel(4), jourRel(3)]);
  });

  it('avant la bascule : « ancien tri », sans colonnes', async () => {
    ecrire('audience', 'un-bon-moment', [visite(0, jourRel(2)), visite(1, jourRel(1))]);
    const resume = await (await appeler()).json();

    expect(resume.sept.tri).toBe('ancien');
    expect(resume.sept.colonnes).toBeNull();
    expect(resume.trente.tri).toBe('ancien');
    expect(resume.jours).toEqual([
      { jour: jourRel(2), tri: 'ancien', visiteurs: 1, robots: 0, colonnes: null },
      { jour: jourRel(1), tri: 'ancien', visiteurs: 1, robots: 0, colonnes: null },
    ]);
  });
});

// ===== Les signalements =====================================================
describe('GET /api/bord : les signalements', () => {
  it('rend ceux en attente, de toutes les sources, sans nom, adresse ni texte (F15)', async () => {
    ecrireSignalement(signalement());
    ecrireSignalement(signalement({ id: 'rep-2', status: 'resolved' }));
    ecrireSignalement(signalement({ id: 'rep-3', sourceId: 'autre-source', recoId: 'as-4', category: 'suggestion',
      submittedAt: `${jourRel(0)}T07:00:00.000Z` }), 'autre-source');
    const brut = await (await appeler()).text();

    expect(JSON.parse(brut).signalements).toEqual({
      etat: 'lu',
      enAttente: [
        { id: 'rep-3', recoId: 'as-4', categorie: 'suggestion', date: `${jourRel(0)}T07:00:00.000Z` },
        { id: 'rep-1', recoId: 'ubm-1', categorie: 'error', date: `${jourRel(1)}T08:00:00.000Z` },
      ],
    });
    for (const interdit of ['Camille', 'camille@exemple.test', 'texte libre', 'wantCredit']) {
      expect(brut).not.toContain(interdit);
    }
  });

  it('rend une liste vide, lue, quand il n’y a aucun signalement', async () => {
    expect((await (await appeler()).json()).signalements).toEqual({ etat: 'lu', enAttente: [] });
  });

  it('dit « inconnu » et le journalise quand un fichier de signalement est tronqué (F22)', async () => {
    ecrireSignalement(signalement());
    const dossier = path.join(racine, 'tools', 'output', 'reports', 'un-bon-moment');
    writeFileSync(path.join(dossier, 'rep-casse.json'), '{"id": "rep-casse", "recoI', 'utf8');
    const journal = vi.spyOn(console, 'error').mockImplementation(() => {});

    const reponse = await appeler();

    expect(reponse.status).toBe(200);
    expect((await reponse.json()).signalements).toEqual({ etat: 'inconnu', enAttente: [] });
    expect(journal).toHaveBeenCalledWith(
      '[api/bord] signalements illisibles :', ['rep-casse.json'],
    );
  });

  it('dit « inconnu » et le journalise quand les signalements ne se lisent pas', async () => {
    // Un dossier dont le nom n'est pas un identifiant : `reportsDirFor` refuse de le lire.
    mkdirSync(path.join(racine, 'tools', 'output', 'reports', 'nom invalide'), { recursive: true });
    const journal = vi.spyOn(console, 'error').mockImplementation(() => {});

    const reponse = await appeler();

    expect(reponse.status).toBe(200);
    expect((await reponse.json()).signalements).toEqual({ etat: 'inconnu', enAttente: [] });
    expect(journal).toHaveBeenCalledWith('[api/bord] signalements illisibles :', expect.any(Error));
  });
});
