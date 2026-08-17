// @vitest-environment happy-dom
/**
 * Tests de `src/utils/chargerFragment.ts`.
 *
 * Ce qui est réellement en jeu ici n'est pas « le HTML arrive-t-il ? » mais
 * « quelqu'un qui n'y voit rien sait-il ce qui se passe ? ». Avant ce module,
 * activer l'onglet au lecteur d'écran donnait un silence pendant la requête,
 * puis mille deux cents cartes sans un mot ; et un échec réseau ressemblait
 * exactement à un onglet vide.
 *
 * D'où la place prise par les assertions sur la zone d'annonce et sur
 * `aria-busy` — et par celle qui vérifie que cette zone SURVIT à l'injection,
 * la faute la plus facile à commettre étant de remplacer la section entière.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { chargerFragment } from '../../src/utils/chargerFragment';

const FRAGMENT = '<div id="reco-grid"><article>A</article><article>B</article></div>';

function monterSection(url: string | null = '/ubm/recos-fragment'): HTMLElement {
  document.body.innerHTML = `
    <section id="view-all" role="tabpanel" aria-busy="false"${
      url === null ? '' : ` data-fragment="${url}"`}>
      <p id="recos-statut" role="status" aria-live="polite" aria-atomic="true"></p>
      <div data-recos-cible>
        <p class="repli-recos"><a href="/ubm/recos">Voir les 2 recommandations →</a></p>
      </div>
    </section>`;
  return document.getElementById('view-all') as HTMLElement;
}

const reponse = (corps: string, ok = true, statut = 200) =>
  ({ ok, status: statut, text: () => Promise.resolve(corps) }) as Response;

const statutTexte = () => document.getElementById('recos-statut')?.textContent ?? '';

beforeEach(() => {
  document.body.innerHTML = '';
});

// ---------------------------------------------------------------------------
// Le cas nominal
// ---------------------------------------------------------------------------
describe('chargerFragment — chargement réussi', () => {
  it('injecte le fragment dans le CONTENEUR, pas dans la section', async () => {
    const section = monterSection();
    await chargerFragment(section, () => {}, () => Promise.resolve(reponse(FRAGMENT)));

    expect(section.querySelector('#reco-grid')).not.toBeNull();
    // La zone d'annonce doit avoir survécu : remplacer la section entière la
    // détruirait au moment précis où on lui demande de parler.
    expect(document.getElementById('recos-statut')).not.toBeNull();
  });

  it('remplace le lien de repli par le contenu', async () => {
    const section = monterSection();
    await chargerFragment(section, () => {}, () => Promise.resolve(reponse(FRAGMENT)));
    expect(section.querySelector('.repli-recos')).toBeNull();
  });

  it('annonce le NOMBRE de recommandations affichées', async () => {
    const section = monterSection();
    await chargerFragment(section, () => {}, () => Promise.resolve(reponse(FRAGMENT)));
    expect(statutTexte()).toBe('2 recommandations affichées.');
  });

  it('accorde au singulier', async () => {
    const section = monterSection();
    await chargerFragment(section, () => {},
      () => Promise.resolve(reponse('<div id="reco-grid"><article>A</article></div>')));
    expect(statutTexte()).toBe('1 recommandation affichée.');
  });

  it('rappelle le recâblage APRÈS l’injection, pas avant', async () => {
    // Câblé trop tôt, le filtre ne trouverait aucun de ses éléments et serait
    // mort sans que rien ne le signale.
    const section = monterSection();
    let grilleVueParLeRappel: boolean | null = null;
    await chargerFragment(
      section,
      () => { grilleVueParLeRappel = section.querySelector('#reco-grid') !== null; },
      () => Promise.resolve(reponse(FRAGMENT)),
    );
    expect(grilleVueParLeRappel).toBe(true);
  });

  it('renvoie « charge »', async () => {
    const section = monterSection();
    const issue = await chargerFragment(section, () => {},
      () => Promise.resolve(reponse(FRAGMENT)));
    expect(issue).toBe('charge');
  });

  it('appelé sans ses deux paramètres optionnels, retombe sur fetch', async () => {
    // C'est la forme employée EN PRODUCTION par `SourceCatalog` — celle qui
    // n'était couverte par aucun test, les autres passant toujours un faux
    // récupérateur. Un défaut cassé y serait donc resté invisible.
    const section = monterSection();
    const espion = vi.fn(() => Promise.resolve(reponse(FRAGMENT)));
    vi.stubGlobal('fetch', espion);

    const issue = await chargerFragment(section);

    expect(espion).toHaveBeenCalledWith('/ubm/recos-fragment');
    expect(issue).toBe('charge');
    expect(section.querySelector('#reco-grid')).not.toBeNull();
    vi.unstubAllGlobals();
  });
});

// ---------------------------------------------------------------------------
// L'attente
// ---------------------------------------------------------------------------
describe('chargerFragment — pendant la requête', () => {
  it('annonce l’attente et marque la section occupée', async () => {
    const section = monterSection();
    let pendant: { statut: string; busy: string | null } | null = null;

    await chargerFragment(section, () => {}, () => {
      pendant = {
        statut: statutTexte(),
        busy: section.getAttribute('aria-busy'),
      };
      return Promise.resolve(reponse(FRAGMENT));
    });

    expect(pendant!.statut).toBe('Chargement des recommandations…');
    expect(pendant!.busy).toBe('true');
  });

  it('relâche aria-busy à la fin, succès comme échec', async () => {
    const section = monterSection();
    await chargerFragment(section, () => {}, () => Promise.resolve(reponse(FRAGMENT)));
    expect(section.getAttribute('aria-busy')).toBe('false');

    const autre = monterSection();
    await chargerFragment(autre, () => {}, () => Promise.reject(new Error('réseau')));
    expect(autre.getAttribute('aria-busy')).toBe('false');
  });
});

// ---------------------------------------------------------------------------
// Les échecs
// ---------------------------------------------------------------------------
describe('chargerFragment — échecs', () => {
  it('réseau coupé → message explicite, repli CONSERVÉ', async () => {
    const section = monterSection();
    const issue = await chargerFragment(section, () => {},
      () => Promise.reject(new Error('hors ligne')));

    expect(issue).toBe('echec');
    expect(statutTexte()).toMatch(/échoué/);
    // Le lien vers la page complète doit rester : c'est le chemin de secours.
    expect(section.querySelector('.repli-recos')).not.toBeNull();
  });

  it('réponse HTTP en erreur → traitée comme un échec', async () => {
    // Un 404 renvoie un corps parfaitement lisible : sans le test sur `ok`, on
    // injecterait la page d'erreur à la place des recommandations.
    const section = monterSection();
    const issue = await chargerFragment(section, () => {},
      () => Promise.resolve(reponse('<h1>Introuvable</h1>', false, 404)));

    expect(issue).toBe('echec');
    expect(section.querySelector('.repli-recos')).not.toBeNull();
    expect(section.textContent).not.toContain('Introuvable');
  });

  it('ne rappelle PAS le recâblage quand rien n’a été injecté', async () => {
    const section = monterSection();
    const rappel = vi.fn();
    await chargerFragment(section, rappel, () => Promise.reject(new Error('x')));
    expect(rappel).not.toHaveBeenCalled();
  });

  it('sans data-fragment → ne tente rien du tout', async () => {
    const section = monterSection(null);
    const recuperer = vi.fn();
    const issue = await chargerFragment(section, () => {}, recuperer as never);

    expect(issue).toBe('sans-url');
    expect(recuperer).not.toHaveBeenCalled();
    // Pas d'annonce non plus : il n'y a rien à annoncer.
    expect(statutTexte()).toBe('');
  });
});

// ---------------------------------------------------------------------------
// Robustesse du DOM
// ---------------------------------------------------------------------------
describe('chargerFragment — DOM incomplet', () => {
  it('sans zone d’annonce, le chargement se fait quand même', async () => {
    // La zone d'annonce est un confort d'accessibilité, pas une dépendance :
    // son absence ne doit pas priver tout le monde du contenu.
    const section = monterSection();
    document.getElementById('recos-statut')?.remove();
    const issue = await chargerFragment(section, () => {},
      () => Promise.resolve(reponse(FRAGMENT)));

    expect(issue).toBe('charge');
    expect(section.querySelector('#reco-grid')).not.toBeNull();
  });

  it('sans conteneur cible, on annonce zéro plutôt que de mentir', async () => {
    const section = monterSection();
    section.querySelector('[data-recos-cible]')?.remove();
    const issue = await chargerFragment(section, () => {},
      () => Promise.resolve(reponse(FRAGMENT)));

    expect(issue).toBe('charge');
    expect(statutTexte()).toBe('0 recommandations affichées.');
  });
});
