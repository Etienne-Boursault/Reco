/**
 * Tests de `src/utils/interfaceMesure.ts` et du balisage de
 * `src/components/MesureAudience.astro` (« AU-2 B », 2026-11-27 ; précision
 * d'Étienne, 11 h 19 : « transparent pour l'utilisateur, il faut qu'il puisse
 * opt-out plus facilement qu'en allant dans une page difficile d'accès »).
 *
 * Le balisage est le vrai : le composant est rendu par l'Astro Container puis
 * posé dans le document de happy-dom, avec la vraie mesure sur le vrai
 * `localStorage` de happy-dom (sauf quand il doit lever).
 *
 * Environnement `node` + une fenêtre happy-dom à la main : sous l'environnement
 * happy-dom de vitest, l'import d'un `.astro` prend sa version « navigateur » et
 * le conteneur ne sait plus le rendre.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { Window } from 'happy-dom';

import { cablerInterfaceMesure } from '../../src/utils/interfaceMesure';
import { creerMesure } from '../../src/utils/mesureNavigateur';

const MesureAudience = (await import('../../src/components/MesureAudience.astro')).default;
const HTML = await (await AstroContainer.create()).renderToString(MesureAudience as never, {});

const window = new Window();
const document = window.document;
const localStorage = window.localStorage;

const CLE = 'reco.mesure';
type Nav = { globalPrivacyControl?: boolean; doNotTrack?: string | null };

function monter(options: { navigator?: Nav; stockage?: () => Storage; html?: string } = {}) {
  document.body.innerHTML = options.html ?? HTML;
  const navigator = options.navigator ?? {};
  const mesure = creerMesure({
    stockage: options.stockage ?? (() => localStorage),
    maintenant: () => new Date('2026-11-27T12:00:00Z'),
    navigator,
  });
  const ui = cablerInterfaceMesure(document as never, window as never, mesure);
  return { mesure, ui, navigator };
}

const q = (s: string) => document.querySelector(s) as HTMLElement | null;
/** L'état du pied qui est affiché (le seul `[data-pour]` non masqué). */
const etatAffiche = () =>
  ([...document.querySelectorAll('[data-pour]')] as unknown as HTMLElement[]).filter((e) => !e.hidden).map((e) => e.dataset.pour);
const ligne = () => q('[data-mesure-ligne]')!;
const bouton = (act: string, dans: HTMLElement = document.body as never) =>
  ([...dans.querySelectorAll(`[data-mesure-act="${act}"]`)] as unknown as HTMLButtonElement[]).find(
    (b) => !b.closest('[hidden]'),
  )!;
const retour = () => q('[data-mesure-retour]')!.textContent;
const lu = () => JSON.parse(localStorage.getItem(CLE) ?? 'null');

beforeEach(() => {
  localStorage.clear();
  document.body.innerHTML = '';
});

describe('le balisage rendu côté serveur (sans script)', () => {
  it('dit sans JavaScript que seules les pages servies sont comptées, et rien d’autre', () => {
    document.body.innerHTML = HTML;
    expect(etatAffiche()).toEqual(['aucun']);
    expect(q('[data-pour="aucun"]')!.textContent).toBe(
      'sans JavaScript, seules les pages servies sont comptées.',
    );
    expect(q('[data-mesure-pied]')!.textContent).toContain('Mesure d’audience');
    expect(ligne().hidden).toBe(true);
  });

  it('la ligne est une région nommée, avec deux vrais boutons de même poids', () => {
    document.body.innerHTML = HTML;
    expect(ligne().getAttribute('role')).toBe('region');
    expect(ligne().getAttribute('aria-label')).toBe('Mesure d’audience');
    expect(ligne().textContent).toContain('Ce site compte ses visites, sans publicité ni pistage entre sites.');
    const boutons = [...ligne().querySelectorAll('button')] as unknown as HTMLButtonElement[];
    expect(boutons.map((b) => b.textContent!.trim())).toEqual(['Refuser', 'OK']);
    expect(new Set(boutons.map((b) => b.className)).size).toBe(1);
    expect(boutons.every((b) => b.type === 'button')).toBe(true);
    expect(ligne().querySelector('a')!.getAttribute('href')).toBe('/mentions-legales#donnees');
  });

  it('prévoit un retour annoncé à part, qui ne sert qu’après un clic', () => {
    document.body.innerHTML = HTML;
    const r = q('[data-mesure-retour]')!;
    expect(r.getAttribute('role')).toBe('status');
    expect(r.textContent).toBe('');
  });
});

describe('le pied : chaque état', () => {
  it('actif : « active · Désactiver »', () => {
    monter();
    expect(etatAffiche()).toEqual(['active']);
    expect(q('[data-pour="active"]')!.textContent).toMatch(/^\s*active\s*·\s*Désactiver\s*$/);
  });

  it('refusé : « désactivée · Réactiver »', () => {
    localStorage.setItem(CLE, JSON.stringify({ refus: true }));
    monter();
    expect(etatAffiche()).toEqual(['refusee']);
    expect(q('[data-pour="refusee"]')!.textContent).toMatch(/^\s*désactivée\s*·\s*Réactiver\s*$/);
  });

  it('GPC : désactivée par le réglage du navigateur, sans bouton', () => {
    monter({ navigator: { globalPrivacyControl: true } });
    expect(etatAffiche()).toEqual(['navigateur']);
    expect(q('[data-pour="navigateur"]')!.textContent).toBe('désactivée par le réglage de votre navigateur.');
    expect(q('[data-pour="navigateur"] button')).toBeNull();
  });

  it('DNT : même chose', () => {
    monter({ navigator: { doNotTrack: '1' } });
    expect(etatAffiche()).toEqual(['navigateur']);
  });

  it('stockage indisponible : le dit, sans interrupteur qui ne ferait rien', () => {
    monter({
      stockage: () => {
        throw new Error('bloqué');
      },
    });
    expect(etatAffiche()).toEqual(['indisponible']);
    expect(q('[data-pour="indisponible"]')!.textContent).toBe(
      'active, mais ce navigateur ne peut pas garder un refus.',
    );
    expect(q('[data-pour="indisponible"] button')).toBeNull();
  });
});

describe('les clics du pied', () => {
  it('« Désactiver » refuse sur place, annonce le retour et garde le focus dans le pied', () => {
    monter();
    bouton('refuser', q('[data-mesure-pied]')!).click();
    expect(etatAffiche()).toEqual(['refusee']);
    expect(lu()).toEqual({ refus: true });
    expect(retour()).toBe('Mesure désactivée');
    expect(document.activeElement).toBe(bouton('accepter'));
  });

  it('« Réactiver » repart d’un état neuf, sur place', () => {
    localStorage.setItem(CLE, JSON.stringify({ refus: true }));
    monter();
    bouton('accepter').click();
    expect(etatAffiche()).toEqual(['active']);
    expect(lu()).toMatchObject({ ne: '2026-11-27' });
    expect(retour()).toBe('Mesure réactivée');
    expect(document.activeElement).toBe(bouton('refuser', q('[data-mesure-pied]')!));
  });

  it('si le choix ne prend pas (GPC apparu entre-temps), rien n’est annoncé et le focus ne bouge pas', () => {
    const { navigator } = monter();
    navigator.globalPrivacyControl = true;
    bouton('refuser', q('[data-mesure-pied]')!).click();
    expect(etatAffiche()).toEqual(['navigateur']);
    expect(retour()).toBe('');
  });
});

describe('la ligne de première visite', () => {
  /** Ce que fait `cablerSignalVue` : `noterPage` crée l'état, puis le rappel. */
  function pageVue(m: ReturnType<typeof monter>) {
    m.mesure.noterPage('/ubm');
    m.ui.apresEnvoi();
  }

  it('n’apparaît pas avant l’envoi du signal (aucun état créé)', () => {
    monter();
    expect(ligne().hidden).toBe(true);
  });

  it('apparaît après l’envoi sur la première page, et reste sur deux pages', () => {
    pageVue(monter());
    expect(ligne().hidden).toBe(false);
    expect(lu().ligne).toBe(1);
    pageVue(monter());
    expect(ligne().hidden).toBe(false);
    expect(lu().ligne).toBe(2);
    pageVue(monter());
    expect(ligne().hidden).toBe(true);
  });

  it('« OK » la ferme sans annonce ni changement du pied, et elle ne revient pas', () => {
    pageVue(monter());
    bouton('ok').click();
    expect(ligne().hidden).toBe(true);
    expect(retour()).toBe('');
    expect(etatAffiche()).toEqual(['active']);
    pageVue(monter());
    expect(ligne().hidden).toBe(true);
  });

  it('« Refuser » dans la ligne ferme la ligne, met le pied à jour et lui passe le focus (clavier)', () => {
    pageVue(monter());
    bouton('refuser', ligne()).focus();
    bouton('refuser', ligne()).click();
    expect(ligne().hidden).toBe(true);
    expect(etatAffiche()).toEqual(['refusee']);
    expect(retour()).toBe('Mesure désactivée');
    // Sans cela, le focus tomberait sur `body` avec la ligne qui se cache (constat du tour 1, PR #224).
    expect(document.activeElement).toBe(bouton('accepter', q('[data-mesure-pied]')!));
  });

  it('« OK » dans la ligne passe le focus au bouton « Désactiver » du pied', () => {
    pageVue(monter());
    bouton('ok').focus();
    bouton('ok').click();
    expect(ligne().hidden).toBe(true);
    expect(document.activeElement).toBe(bouton('refuser', q('[data-mesure-pied]')!));
  });

  it('« Refuser » dans la ligne quand le pied n’a aucun bouton : le texte d’état prend le focus', () => {
    const m = monter();
    pageVue(m);
    m.navigator.globalPrivacyControl = true; // le choix ne prend pas : l'état devient « navigateur »
    bouton('refuser', ligne()).click();
    const texte = q('[data-pour="navigateur"]')!;
    expect(texte.getAttribute('tabindex')).toBe('-1');
    expect(document.activeElement).toBe(texte);
  });

  it('un refus déjà donné : pas de ligne, et la ligne ouverte se ferme', () => {
    const m = monter();
    m.mesure.refuser();
    m.ui.apresEnvoi();
    expect(ligne().hidden).toBe(true);
    expect(etatAffiche()).toEqual(['refusee']);
  });

  it('« Désactiver » dans le pied ferme aussi la ligne (même état, R-13)', () => {
    pageVue(monter());
    bouton('refuser', q('[data-mesure-pied]')!).click();
    expect(ligne().hidden).toBe(true);
  });

  it('ne prend pas le focus en s’affichant', () => {
    pageVue(monter());
    expect(ligne().contains(document.activeElement)).toBe(false);
  });
});

describe('un autre onglet change l’état (événement storage)', () => {
  it('le pied et la ligne suivent', () => {
    const m = monter();
    m.mesure.noterPage('/ubm');
    m.ui.apresEnvoi();
    expect(ligne().hidden).toBe(false);
    localStorage.setItem(CLE, JSON.stringify({ refus: true }));
    window.dispatchEvent(new window.Event('storage'));
    expect(etatAffiche()).toEqual(['refusee']);
    expect(ligne().hidden).toBe(true);
  });

  it('un événement qui ne change rien laisse la ligne ouverte', () => {
    const m = monter();
    m.mesure.noterPage('/ubm');
    m.ui.apresEnvoi();
    window.dispatchEvent(new window.Event('storage'));
    expect(ligne().hidden).toBe(false);
  });
});

describe('sans balisage', () => {
  it('ne fait rien et ne lève rien (page sans pied)', () => {
    const m = monter({ html: '<main>vide</main>' });
    expect(() => m.ui.apresEnvoi()).not.toThrow();
  });
});
