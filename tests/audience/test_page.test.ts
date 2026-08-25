/**
 * Tests de rendu de `/audience` — la page elle-même, pas ses briques.
 *
 * POURQUOI TESTER LE RENDU
 * ------------------------
 * Les trois défauts trouvés le jour de la mise en service étaient tous des
 * défauts d'AFFICHAGE, invisibles depuis les modules pris isolément : un
 * « taux » à 664 %, un périmètre qui cachait l'accueil et les 404, et la page
 * qui se comptait elle-même. Chaque brique était juste ; la page mentait.
 *
 * Le conteneur d'Astro permet de la rendre pour de vrai. Ces tests vérifient
 * ce qui ne doit jamais varier — le garde d'accès, les en-têtes de réponse,
 * l'attribution obligatoire, la présence des repères d'accessibilité — plutôt
 * que des chiffres, qui dépendent des mesures présentes sur la machine.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import Page from '../../src/routes/audience.astro';

const CLE = 'cle-de-test-de-vingt-huit-signes';
let cleInitiale: string | undefined;

beforeEach(() => {
  cleInitiale = process.env.RECO_AUDIENCE_KEY;
  process.env.RECO_AUDIENCE_KEY = CLE;
});

afterEach(() => {
  if (cleInitiale === undefined) delete process.env.RECO_AUDIENCE_KEY;
  else process.env.RECO_AUDIENCE_KEY = cleInitiale;
});

async function rendre(query = '', entetes: Record<string, string> = {}) {
  const container = await AstroContainer.create();
  return container.renderToResponse(Page, {
    request: new Request(`https://exemple.test/audience${query}`, { headers: entetes }),
  });
}

async function corps(query = '', entetes: Record<string, string> = {}) {
  return (await rendre(query, entetes)).text();
}

/**
 * Rend la page sur des mesures maîtrisées, dans un dossier jetable.
 *
 * `agreger` lit depuis `process.cwd()` : sans ce déplacement, la page rendue
 * en test n'a AUCUNE donnée et affiche « Rien à afficher ». Trois assertions
 * de ce fichier passaient pour cette seule raison — `indexOf` rendait -1 et
 * `slice(-401, -1)` piochait la fin du document, où le motif cherché ne
 * risquait pas de se trouver. Un test qui ne rend jamais le bloc qu'il
 * prétend inspecter ne prouve rien.
 */
async function corpsAvecMesures(
  lignes: { audience?: Record<string, unknown>[]; clics?: Record<string, unknown>[] },
  query = `?cle=${CLE}`,
) {
  const avant = process.cwd();
  const racine = mkdtempSync(path.join(tmpdir(), 'reco-page-'));
  try {
    for (const [genre, contenu] of [
      ['audience', lignes.audience ?? []],
      ['clicks', lignes.clics ?? []],
    ] as const) {
      if (!contenu.length) continue;
      const dossier = path.join(racine, 'tools', 'output', genre, 'un-bon-moment');
      mkdirSync(dossier, { recursive: true });
      writeFileSync(
        path.join(dossier, '2026-08-25.jsonl'),
        contenu.map((l) => `${JSON.stringify(l)}\n`).join(''),
        'utf8',
      );
    }
    process.chdir(racine);
    return await corps(query);
  } finally {
    process.chdir(avant);
    rmSync(racine, { recursive: true, force: true });
  }
}

const VISITE = {
  ts: '2026-08-25T10:00:00.000Z', chemin: '/un-bon-moment/films', statut: 200,
  robot: false, appareil: 'mobile', provenance: null, langue: 'fr', pays: 'FR',
  visiteur: 'aaaaaaaaaaaa', dureeMs: 5,
};
const CLIC = {
  ts: '2026-08-25T10:05:00.000Z', url: 'https://exemple.test/x', category: 'tmdb',
  sourceId: 'un-bon-moment', recoId: 'ubm-1', ref: '/un-bon-moment/films',
};

// ===== Le garde ============================================================
describe('accès', () => {
  it('répond 404 sans clé : un 403 confirmerait l’adresse', async () => {
    const reponse = await rendre();

    expect(reponse.status).toBe(404);
    expect(await reponse.text()).not.toContain('<html');
  });

  it('répond 404 sur une mauvaise clé', async () => {
    expect((await rendre('?cle=mauvaise-cle-de-la-bonne-taille')).status).toBe(404);
  });

  it('n’existe pas quand aucune clé n’est configurée', async () => {
    // Mieux vaut une absence qu'une porte ouverte par oubli.
    delete process.env.RECO_AUDIENCE_KEY;
    expect((await rendre(`?cle=${CLE}`)).status).toBe(404);
  });

  it('ouvre avec la bonne clé', async () => {
    expect((await rendre(`?cle=${CLE}`)).status).toBe(200);
  });
});

// ===== Ce que la réponse promet ============================================
describe('en-têtes', () => {
  it('interdit la mise en cache et l’indexation, et retient la clé', async () => {
    // La clé est dans l'URL : sans `no-referrer`, un lien sortant la ferait
    // fuir vers le site visité.
    const reponse = await rendre(`?cle=${CLE}`);

    expect(reponse.headers.get('cache-control')).toBe('no-store');
    expect(reponse.headers.get('referrer-policy')).toBe('no-referrer');
    expect(reponse.headers.get('x-robots-tag')).toBe('noindex, nofollow');
  });
});

// ===== La page rendue ======================================================
describe('structure', () => {
  it('porte les repères d’accessibilité que le scan exige', async () => {
    // La page n'importe pas `global.css` : son lien d'évitement et sa cible
    // lui sont propres, et rien ne les vérifierait ailleurs.
    const html = await corps(`?cle=${CLE}`);

    expect(html).toContain('<html lang="fr"');
    expect(html).toContain('href="#main"');
    expect(html).toContain('id="main"');
  });

  it('affiche l’attribution DB-IP, qu’impose la licence CC BY', async () => {
    // Ce n'est pas une politesse : la table embarquée en vient.
    const html = await corps(`?cle=${CLE}`);

    expect(html).toContain('db-ip.com');
    expect(html).toContain('CC BY 4.0');
  });

  it('rappelle ce que la mesure ne fait pas', async () => {
    const html = await corps(`?cle=${CLE}`);

    expect(html).toContain('sans tracker');
    expect(html).toContain('parcours ne sont pas reconstitués');
  });

  it('nomme le périmètre agrégé', async () => {
    // Un total dont on ignore l'étendue ne veut rien dire.
    expect(await corps(`?cle=${CLE}`)).toContain('tout le site');
  });

  it('isole une source sur demande', async () => {
    const html = await corps(`?cle=${CLE}&source=un-bon-moment`);

    expect(html).toContain('un-bon-moment');
    expect(html).not.toContain('tout le site ·');
  });

  it('n’affiche jamais « % » sur les clics par visiteur', async () => {
    // Le premier jet présentait ce rapport comme un taux et sortait 664 %.
    const html = await corpsAvecMesures({ audience: [VISITE], clics: [CLIC, CLIC] });
    const i = html.indexOf('clics par visiteur');

    expect(i).toBeGreaterThan(-1);
    expect(html.slice(i - 400, i)).not.toContain('%');
    expect(html).not.toContain('taux de découverte');
  });
});

// ===== Ce que la page avoue ===============================================
describe('honnêteté des chiffres', () => {
  it('avoue les clics écartés du rapport', async () => {
    // Les deux compteurs n'ont pas démarré ensemble : les clics existaient
    // depuis le 2026-08-19, les visites depuis le 2026-08-25. Écarter les
    // clics orphelins sans le dire reviendrait à masquer une lacune.
    const html = await corpsAvecMesures({ audience: [], clics: [CLIC] });

    expect(html).toContain('clic écarté');
  });

  it('ne dit rien quand les deux mesures se recouvrent', async () => {
    const html = await corpsAvecMesures({ audience: [VISITE], clics: [CLIC] });

    expect(html).not.toContain('écarté');
    expect(html).not.toContain('écartés');
  });
});

// ===== Le diagnostic des en-têtes ==========================================
describe('?entetes=1', () => {
  it('liste les noms reçus', async () => {
    // Le conteneur d'Astro fabrique une requête SANS en-tête : il faut les
    // fournir, sinon le test passerait sur une liste vide sans rien prouver.
    const html = await corps(`?cle=${CLE}&entetes=1`, {
      'x-forwarded-for': '203.0.113.7',
      'accept-language': 'fr-FR',
    });

    expect(html).toContain('En-têtes reçus par le serveur');
    expect(html).toContain('x-forwarded-for');
    expect(html).toContain('accept-language');
  });

  it('n’affiche QUE les noms, jamais les valeurs', async () => {
    // Un `authorization` ou un cookie n'ont rien à faire dans une page, même
    // protégée par une clé.
    const html = await corps(`?cle=${CLE}&entetes=1`, {
      'x-forwarded-for': '203.0.113.7',
      cookie: 'session=secret-a-ne-pas-afficher',
    });

    expect(html).toContain('x-forwarded-for');
    expect(html).not.toContain('203.0.113.7');
    expect(html).not.toContain('secret-a-ne-pas-afficher');
  });

  it('s’affiche même sans aucune mesure', async () => {
    // Le diagnostic sert surtout à la mise en service, quand rien n'a encore
    // été enregistré. Il était enfermé dans le bloc « il y a des données ».
    const html = await corps(`?cle=${CLE}&entetes=1&source=source-jamais-vue`, {
      'x-forwarded-for': '203.0.113.7',
    });

    expect(html).toContain('En-têtes reçus par le serveur');
  });

  it('reste absent sans le paramètre', async () => {
    expect(await corps(`?cle=${CLE}`)).not.toContain('En-têtes reçus par le serveur');
  });
});
