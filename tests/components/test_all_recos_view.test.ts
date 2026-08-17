/**
 * Tests de `src/components/AllRecosView.astro`.
 *
 * Ce composant a été EXTRAIT de `SourceCatalog` le 2026-08-16 : la vue
 * « toutes les recos » y pesait 96 % du document alors qu'elle est masquée au
 * chargement. Les assertions qui portaient sur la grille, les chips de filtres
 * et la zone « aucun résultat » ont donc migré ici — elles testent la même
 * chose, au bon endroit.
 *
 * Le composant reçoit ses données déjà préparées (c'est `loadCatalogData` qui
 * lit les collections) : aucun mock d'`astro:content` n'est nécessaire, ce qui
 * rend ces tests plus directs que ceux qu'ils remplacent.
 */
import { describe, it, expect } from 'vitest';

const { renderWithSite } = await import('./_container');
const AllRecosView = (await import('../../src/components/AllRecosView.astro')).default;

const reco = (over: Record<string, unknown> = {}) => ({
  id: 'ubm-0001',
  episodeGuid: 'ep-1',
  title: 'Parasite',
  creator: 'Bong Joon-ho',
  types: ['film'],
  status: 'validated',
  ...over,
});

const EPISODE = { guid: 'ep-1', number: 12, title: 'Épisode douze' };

async function render(over: Record<string, unknown> = {}): Promise<string> {
  return renderWithSite(AllRecosView, {
    props: {
      sourceId: 'ubm',
      recos: [reco()],
      epByGuid: new Map([['ep-1', EPISODE]]),
      types: [['film', 1]],
      ...over,
    },
  });
}

// ---------------------------------------------------------------------------
// La grille
// ---------------------------------------------------------------------------
describe('AllRecosView — grille des recos', () => {
  it('rend une carte par reco', async () => {
    const html = await render({
      recos: [reco(), reco({ id: 'ubm-0002', title: 'Drive' })],
      types: [['film', 2]],
    });
    expect(html).toContain('Parasite');
    expect(html).toContain('Drive');
    expect(html).toContain('id="reco-grid"');
  });

  it('aucune reco → état vide au lieu de la grille', async () => {
    const html = await render({ recos: [], types: [] });
    expect(html).not.toContain('id="reco-grid"');
    expect(html).toContain('Pas encore de recommandation');
  });

  it('les cartes reçoivent le numéro d’épisode résolu par guid', async () => {
    expect(await render()).toContain('12');
  });

  it('une reco orpheline (guid inconnu) ne casse pas le rendu', async () => {
    const html = await render({
      recos: [reco({ episodeGuid: 'fantome' })],
      epByGuid: new Map(),
    });
    expect(html).toContain('Parasite');
  });
});

// ---------------------------------------------------------------------------
// Les chips de filtres
// ---------------------------------------------------------------------------
describe('AllRecosView — chips de filtres par type', () => {
  it('respecte l’ordre reçu et affiche le compte', async () => {
    // L'ordre est décidé en amont par `loadCatalogData` (fréquence
    // décroissante) : le composant ne le recalcule pas, il l'honore.
    const html = await render({ types: [['film', 3], ['livre', 1]] });
    expect(html.indexOf('Films')).toBeLessThan(html.indexOf('Livres'));
    expect(html).toContain('>3<');
    expect(html).toContain('data-filter="film"');
  });

  it('un type inconnu retombe sur sa clé brute comme libellé', async () => {
    const html = await render({ types: [['nawak', 2]] });
    expect(html).toContain('nawak');
    expect(html).toContain('data-filter="nawak"');
  });

  it('la chip « Tout » est active par défaut', async () => {
    const html = await render();
    expect(html).toMatch(/class="chip is-active"[^>]*data-filter="all"[^>]*aria-pressed="true"/);
  });
});

// ---------------------------------------------------------------------------
// Accessibilité
// ---------------------------------------------------------------------------
describe('AllRecosView — accessibilité', () => {
  it('la zone « aucun résultat » porte le trio ARIA complet', async () => {
    // C7 : l'élément reste TOUJOURS dans le DOM, seul son `textContent` change
    // — sinon `aria-live="polite"` n'annoncerait rien.
    const html = await render();
    const zone = html.match(/<p[^>]*id="noresult"[^>]*>/)?.[0] ?? '';
    expect(zone).toContain('role="status"');
    expect(zone).toContain('aria-live="polite"');
    expect(zone).toContain('aria-atomic="true"');
  });

  it('la zone est rendue VIDE : le message est posé côté client', async () => {
    expect(await render()).toMatch(/id="noresult"[^>]*><\/p>/);
  });

  it('le champ de recherche porte un nom accessible', async () => {
    const html = await render();
    expect(html).toMatch(/<input[^>]*id="search"[^>]*aria-label="[^"]+"/);
  });

  it('titre masqué par défaut, VISIBLE sur la page autonome', async () => {
    // Sur la page `/[source]/recos`, cette vue est le contenu principal : son
    // titre doit être un `<h1>` réel, pas un titre réservé aux lecteurs
    // d'écran comme dans l'onglet du catalogue.
    expect(await render()).toMatch(/<h2 class="visually-hidden">/);
    const autonome = await render({ titreVisible: true });
    expect(autonome).toMatch(/<h1[^>]*>Toutes les recommandations<\/h1>/);
  });
});

// ---------------------------------------------------------------------------
// Échappement — le fragment est injecté par `innerHTML` côté client
// ---------------------------------------------------------------------------
describe('AllRecosView — échappement', () => {
  /**
   * Retire le CONTENU des valeurs d'attributs, en gardant leur nom.
   *
   * Sans cette étape, toute assertion se trompe de cible : une regex voit
   * `data-search="<script>…"` et croit à une balise, alors que le navigateur
   * n'y lit qu'une chaîne. C'est exactement le faux positif sur lequel la
   * première version de ces tests a buté. Ce qui reste après nettoyage est le
   * SQUELETTE du document — les seules balises et les seuls attributs que le
   * navigateur créera réellement.
   *
   * (L'API Container d'Astro impose l'environnement Node : pas de DOM ici,
   * d'où ce nettoyage textuel plutôt qu'un vrai parseur.)
   */
  const squelette = (html: string): string => html.replace(/="[^"]*"/g, '=""');

  it('un titre contenant du balisage ne crée AUCUNE balise', async () => {
    // Ce composant sert aussi de FRAGMENT injecté via `innerHTML` : tout ce
    // qu'il émet doit être sûr à la SOURCE.
    const html = await render({
      recos: [reco({ title: '<script>alert(1)</script><img src=x onerror=boom>' })],
    });
    expect(squelette(html)).not.toMatch(/<script/i);
    // `onerror` DOIT être cherché À L'INTÉRIEUR d'une balise : `<` puis aucun
    // `>` avant l'attribut. Sans cette contrainte, l'assertion se déclenche sur
    // le texte échappé `&lt;img src=x onerror=boom&gt;`, qui est inoffensif —
    // c'est un piège dans lequel ce test est déjà tombé.
    expect(squelette(html)).not.toMatch(/<[a-z][^>]*\son[a-z]+=/i);
    // Le titre reste LISIBLE — échapper ne doit pas escamoter le texte.
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
  });

  it('un guillemet dans un titre ne crée AUCUN attribut', async () => {
    // C'est ici que se jouerait une vraie faille : un guillemet non échappé
    // fermerait l'attribut et permettrait d'en injecter un autre.
    const html = await render({
      recos: [reco({ title: 'A" onmouseover="alert(1)" x="' })],
    });
    expect(squelette(html)).not.toMatch(/<[a-z][^>]*\son[a-z]+=/i);
    // Le guillemet survit, mais sous sa forme échappée.
    expect(html).toContain('&quot;');
  });
});
