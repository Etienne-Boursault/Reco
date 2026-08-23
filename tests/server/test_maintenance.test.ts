/**
 * Tests de `src/server/maintenance.mjs` — le filet quand le site ne démarre pas.
 *
 * CE QU'ILS PROTÈGENT
 * -------------------
 * Le 2026-08-21, une construction a échoué et le site est resté quarante
 * minutes hors ligne. Pas ralenti : mort. `server.mjs` importait
 * `dist/server/entry.mjs` en tête de fichier ; le fichier absent, le module ne
 * se chargeait pas et le processus s'arrêtait avant d'ouvrir le port.
 *
 * Ce module répond à la place. Trois choses comptent, et chacune a son test :
 * le statut doit être 503 et non 404 — un 404 fait désindexer, un 503 fait
 * revenir ; la page ne doit dépendre d'aucune ressource externe, puisqu'elle
 * ne sert que lorsque `dist/` est absent ; et elle doit répondre à TOUTE
 * requête, sans quoi le visiteur tomberait sur un site à moitié vivant.
 */
import { describe, expect, it, afterEach } from 'vitest';

// @ts-expect-error — module `.mjs` sans déclaration de types
import {
  creerServeurMaintenance,
  echapper,
  pageMaintenance,
  repondreMaintenance,
} from '../../src/server/maintenance.mjs';
import { demander, demarrer } from './_client';

let arreterCourant: (() => Promise<void>) | null = null;

afterEach(async () => {
  if (arreterCourant) await arreterCourant();
  arreterCourant = null;
});

async function servir(options?: Record<string, unknown>) {
  const { port, arreter } = await demarrer(creerServeurMaintenance(options));
  arreterCourant = arreter;
  return port;
}

// ===== Le statut ===========================================================
describe('statut et en-têtes', () => {
  it('répond 503, pas 404', async () => {
    // Un 404 dit « cette page n'existe pas » et finit par désindexer le site.
    const port = await servir();
    const r = await demander(port, '/');

    expect(r.statut).toBe(503);
  });

  it('indique quand revenir', async () => {
    const port = await servir();
    const r = await demander(port, '/');

    expect(r.entetes['retry-after']).toBe('120');
  });

  it('interdit la mise en cache de la page d’attente', async () => {
    // Sans cela, un intermédiaire pourrait garder la page d'excuse et
    // continuer de la servir une fois le site revenu.
    const port = await servir();
    const r = await demander(port, '/');

    expect(r.entetes['cache-control']).toBe('no-store');
  });

  it('annonce une longueur exacte', async () => {
    const port = await servir();
    const r = await demander(port, '/');

    expect(Number(r.entetes['content-length'])).toBe(r.brut.length);
  });
});

// ===== La portée ===========================================================
describe('portée', () => {
  it('répond la même chose sur n’importe quelle URL', async () => {
    // Servir les quelques fichiers survivants donnerait un site où certaines
    // pages marchent et d'autres non — plus déroutant qu'une panne franche.
    const port = await servir();
    const racine = await demander(port, '/');
    const profond = await demander(port, '/un-bon-moment/oeuvre/abc123');

    expect(profond.statut).toBe(503);
    expect(profond.texte).toBe(racine.texte);
  });

  it('répond aussi aux méthodes autres que GET', async () => {
    const port = await servir();
    const r = await demander(port, '/api/report', { methode: 'POST' });

    expect(r.statut).toBe(503);
  });

  it('ne met pas de corps sur une requête HEAD', async () => {
    const port = await servir();
    const r = await demander(port, '/', { methode: 'HEAD' });

    expect(r.statut).toBe(503);
    expect(r.brut.length).toBe(0);
    // Les en-têtes, eux, restent complets.
    expect(Number(r.entetes['content-length'])).toBeGreaterThan(0);
  });
});

// ===== La page =============================================================
describe('la page', () => {
  it('n’appelle AUCUNE ressource externe', async () => {
    // Elle ne sert que lorsque `dist/` est absent : une feuille de style ou
    // une police distante ne serait pas là non plus.
    const html = pageMaintenance();
    const externes = html.match(/(?:src|href)="(?!https:\/\/www\.youtube\.com)[^"]*"/g) ?? [];

    expect(externes).toEqual([]);
  });

  it('dit que rien n’est perdu', async () => {
    // Le visiteur d'un catalogue doit comprendre que le contenu revient.
    expect(pageMaintenance()).toContain('Rien n’est perdu');
  });

  it('offre une porte de sortie vers le podcast', async () => {
    expect(pageMaintenance()).toContain('https://www.youtube.com/@KyanKhojandi');
  });

  it('demande à ne pas être indexée', async () => {
    expect(pageMaintenance()).toContain('name="robots" content="noindex"');
  });

  it('déclare la langue et l’encodage', async () => {
    const html = pageMaintenance();

    expect(html).toContain('<html lang="fr">');
    expect(html).toContain('charset="utf-8"');
  });

  it('reprend la charte de la source', async () => {
    const html = pageMaintenance({ theme: { bg: '#123456', accent: '#abcdef' } });

    expect(html).toContain('#123456');
    expect(html).toContain('#abcdef');
  });

  it('garde les couleurs par défaut pour ce qui n’est pas fourni', async () => {
    // Un thème partiel ne doit pas laisser des trous dans la feuille de style.
    const html = pageMaintenance({ theme: { bg: '#123456' } });

    expect(html).toContain('#123456');
    expect(html).toContain('#f6f4ee'); // `text` par défaut
  });

  it('accepte un autre titre et un autre lien', async () => {
    const html = pageMaintenance({
      titre: 'Autre Podcast',
      lien: 'https://exemple.fr',
      libelleLien: 'Nous écouter',
    });

    expect(html).toContain('Autre Podcast');
    expect(html).toContain('https://exemple.fr');
    expect(html).toContain('Nous écouter');
  });
});

// ===== L'échappement =======================================================
describe('échappement', () => {
  it('neutralise le HTML des valeurs injectées', async () => {
    // Les valeurs viennent d'un JSON de source, que n'importe quel fork édite.
    const html = pageMaintenance({ titre: '<script>alert(1)</script>' });

    expect(html).not.toContain('<script>alert(1)</script>');
    expect(html).toContain('&lt;script&gt;');
  });

  it('neutralise aussi les guillemets, qui sortiraient d’un attribut', async () => {
    const html = pageMaintenance({ lien: '" onerror="alert(1)' });

    expect(html).not.toContain('" onerror="');
    expect(html).toContain('&quot;');
  });

  it('échappe les cinq caractères qui comptent', async () => {
    expect(echapper('<a href="x">&</a>')).toBe(
      '&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;',
    );
  });

  it('rend une chaîne vide pour une valeur absente', async () => {
    expect(echapper(null)).toBe('');
    expect(echapper(undefined)).toBe('');
  });
});

// ===== Le délai configurable ==============================================
describe('options', () => {
  it('accepte un autre délai de retour', async () => {
    const port = await servir({ retryAfter: 30 });
    const r = await demander(port, '/');

    expect(r.entetes['retry-after']).toBe('30');
  });

  it('expose une réponse utilisable hors serveur', async () => {
    // `repondreMaintenance` est testable seul : c'est ce qui permettrait de
    // la brancher ailleurs sans dupliquer la page.
    const entetes: Record<string, unknown> = {};
    let corps = '';
    const res = {
      writeHead: (statut: number, t: Record<string, unknown>) => {
        entetes.statut = statut;
        Object.assign(entetes, t);
      },
      end: (c?: string) => { corps = c ?? ''; },
    };
    repondreMaintenance({ method: 'GET' }, res);

    expect(entetes.statut).toBe(503);
    expect(corps).toContain('Le site se remet en place');
  });
});
