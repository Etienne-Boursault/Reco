// @vitest-environment happy-dom
/**
 * Tests du script et du style de `/bord`, le tableau de bord d'admin
 * (tableau de bord, R2 B du 27/11/2026 ; TB-1 C du 28/11/2026, vue 39 pouces
 * par défaut ; plan `pr-tableau-de-bord.md`, § 5, tranche 1d-2).
 *
 * `tools/bord_client.js` est une IIFE recopiée en ligne dans la page par
 * `bord_rendu.py` : on monte le balisage de la page, on l'évalue une fois, et
 * on le pilote par de vrais événements (clic, envoi de formulaire), `fetch`
 * remplacé. Les écouteurs sont délégués sur `document` : ils survivent au
 * remontage du balisage entre deux tests.
 */
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';

const TOOLS = path.resolve(__dirname, '../../tools');

const VUES =
  '<header class="bord-entete"><div class="bord-infos">' +
  '<div class="bord-vues" role="group" aria-label="Vue" hidden>' +
  '<button type="button" data-vue-choix="auto">auto</button>' +
  '<button type="button" data-vue-choix="39">39"</button>' +
  '<button type="button" data-vue-choix="13">13"</button>' +
  '<button type="button" data-vue-choix="telephone">téléphone</button>' +
  '<button type="button" data-vue-choix="xx">piège</button>' +
  '</div></div></header>';

function caseHtml(fait: boolean, nom = 'Instagram, S6-E07'): string {
  return '<form method="post" action="/bord/reseau" class="bord-case-form">' +
    '<input type="hidden" name="guid" value="g-1">' +
    '<input type="hidden" name="reseau" value="instagram">' +
    `<input type="hidden" name="fait" value="${fait ? 0 : 1}">` +
    `<button type="submit" class="bord-case" data-fait="${fait ? 1 : 0}"` +
    `${fait ? ' title="coché le 01/11"' : ''} ` +
    `aria-label="${nom} : ${fait ? 'décocher' : 'marquer comme fait'}" data-nom="${nom}">` +
    `${fait ? '✓' : 'À faire'}</button></form>`;
}

function monter(corps: string): void {
  document.body.innerHTML = VUES + corps;
}

function laCase(): { form: HTMLFormElement; bouton: HTMLButtonElement } {
  const form = document.querySelector('form.bord-case-form') as HTMLFormElement;
  return { form, bouton: form.querySelector('button.bord-case') as HTMLButtonElement };
}

function envoyer(form: HTMLFormElement): Event {
  const ev = new Event('submit', { bubbles: true, cancelable: true });
  form.dispatchEvent(ev);
  return ev;
}

function reponse(corps: unknown, status = 200): Response {
  return new Response(JSON.stringify(corps), {
    status, headers: { 'Content-Type': 'application/json' },
  });
}

const tick = () => new Promise((r) => setTimeout(r, 0));

let fetchMock: ReturnType<typeof vi.fn>;

beforeAll(() => {
  document.documentElement.setAttribute('data-vue', '13');
  monter(caseHtml(false));
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  const code = readFileSync(path.join(TOOLS, 'bord_client.js'), 'utf-8');
  // eslint-disable-next-line no-new-func -- évaluation volontaire de l'IIFE
  new Function(code)();
});

afterEach(() => {
  fetchMock.mockReset();
  vi.restoreAllMocks();
});

describe('le choix de la vue', () => {
  it('au chargement, le choix est révélé et la vue posée par <head> est marquée', () => {
    const groupe = document.querySelector('.bord-vues') as HTMLElement;
    expect(groupe.hidden).toBe(false);
    const presses = [...document.querySelectorAll('[data-vue-choix]')]
      .map((b) => [b.getAttribute('data-vue-choix'), b.getAttribute('aria-pressed')]);
    expect(presses).toEqual([
      ['auto', 'false'], ['39', 'false'], ['13', 'true'], ['telephone', 'false'], ['xx', 'false'],
    ]);
  });

  it('un clic pose data-vue, le garde dans localStorage et met aria-pressed à jour', () => {
    monter('');
    (document.querySelector('[data-vue-choix="telephone"]') as HTMLElement).click();
    expect(document.documentElement.getAttribute('data-vue')).toBe('telephone');
    expect(window.localStorage.getItem('bord-vue')).toBe('telephone');
    expect(document.querySelector('[data-vue-choix="telephone"]')!
      .getAttribute('aria-pressed')).toBe('true');
    expect(document.querySelector('[data-vue-choix="13"]')!
      .getAttribute('aria-pressed')).toBe('false');
  });

  it('« auto » se garde aussi : le script de <head> l\'ignore, la largeur décide', () => {
    monter('');
    (document.querySelector('[data-vue-choix="auto"]') as HTMLElement).click();
    expect(document.documentElement.getAttribute('data-vue')).toBe('auto');
    expect(window.localStorage.getItem('bord-vue')).toBe('auto');
  });

  it('un localStorage qui lève n\'empêche pas de changer de vue', () => {
    monter('');
    const avertir = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const ecrire = vi.spyOn(window.localStorage, 'setItem')
      .mockImplementation(() => { throw new Error('stockage refusé'); });
    (document.querySelector('[data-vue-choix="39"]') as HTMLElement).click();
    expect(ecrire).toHaveBeenCalled();
    expect(document.documentElement.getAttribute('data-vue')).toBe('39');
    expect(avertir).toHaveBeenCalled();
    ecrire.mockRestore();
  });

  it('une valeur hors de la liste est ignorée', () => {
    monter('');
    (document.querySelector('[data-vue-choix="13"]') as HTMLElement).click();
    (document.querySelector('[data-vue-choix="xx"]') as HTMLElement).click();
    expect(document.documentElement.getAttribute('data-vue')).toBe('13');
    expect(window.localStorage.getItem('bord-vue')).toBe('13');
  });

  it('un clic ailleurs ne change rien', () => {
    monter('<p id="ailleurs">texte</p>');
    (document.querySelector('[data-vue-choix="13"]') as HTMLElement).click();
    (document.getElementById('ailleurs') as HTMLElement).click();
    expect(document.documentElement.getAttribute('data-vue')).toBe('13');
  });
});

describe('les cases des réseaux, sans recharger la page', () => {
  it('cocher envoie le formulaire en JSON et coche la case', async () => {
    monter(caseHtml(false));
    fetchMock.mockResolvedValue(reponse({ kind: 'success', message: 'Instagram : fait.' }));
    const { form, bouton } = laCase();
    const ev = envoyer(form);
    expect(ev.defaultPrevented).toBe(true);
    await tick();
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/bord\/reseau$/);
    expect(init.method).toBe('POST');
    expect(init.headers.Accept).toBe('application/json');
    expect(Object.fromEntries(new URLSearchParams(init.body))).toEqual(
      { guid: 'g-1', reseau: 'instagram', fait: '1' });
    expect(bouton.dataset.fait).toBe('1');
    expect(bouton.textContent).toBe('✓');
    expect(bouton.getAttribute('aria-label')).toBe('Instagram, S6-E07 : décocher');
    expect(bouton.getAttribute('title')).toMatch(/^coché le \d\d\/\d\d$/);
    expect((form.elements.namedItem('fait') as HTMLInputElement).value).toBe('0');
    expect(bouton.disabled).toBe(false);
    const flash = document.querySelector('.flash') as HTMLElement;
    expect(flash.className).toBe('flash flash-success');
    expect(flash.getAttribute('role')).toBe('status');
    expect(flash.textContent).toBe('Instagram : fait.');
  });

  it('décocher remet « À faire » et retire la date', async () => {
    monter('<div class="flash flash-info" role="status">ancien</div>' + caseHtml(true));
    fetchMock.mockResolvedValue(reponse({ kind: 'bizarre', message: 'Instagram : à faire.' }));
    const { form, bouton } = laCase();
    envoyer(form);
    await tick();
    expect(Object.fromEntries(new URLSearchParams(fetchMock.mock.calls[0][1].body)).fait)
      .toBe('0');
    expect(bouton.dataset.fait).toBe('0');
    expect(bouton.textContent).toBe('À faire');
    expect(bouton.getAttribute('aria-label')).toBe('Instagram, S6-E07 : marquer comme fait');
    expect(bouton.hasAttribute('title')).toBe(false);
    expect((form.elements.namedItem('fait') as HTMLInputElement).value).toBe('1');
    // Le message réutilise le bandeau déjà là ; un genre inconnu devient « info ».
    expect(document.querySelectorAll('.flash')).toHaveLength(1);
    expect(document.querySelector('.flash')!.className).toBe('flash flash-info');
    expect(document.querySelector('.flash')!.textContent).toBe('Instagram : à faire.');
  });

  it('le libellé repris après un clic vient de data-nom, même si le nom contient « : »', async () => {
    // Tour 1, F5 : plus de regex sur l'ancien libellé.
    monter(caseHtml(false, 'Instagram, Titre : suite : fin'));
    fetchMock.mockResolvedValue(reponse({ kind: 'success' }));
    const { form, bouton } = laCase();
    bouton.setAttribute('aria-label', 'Instagram, Titre : suite : fin'); // libellé coupé
    envoyer(form);
    await tick();
    expect(bouton.getAttribute('aria-label')).toBe('Instagram, Titre : suite : fin : décocher');
    expect(bouton.getAttribute('data-nom')).toBe('Instagram, Titre : suite : fin');
  });

  it('un succès sans message ne touche pas au bandeau', async () => {
    monter(caseHtml(false));
    fetchMock.mockResolvedValue(reponse({ kind: 'success' }));
    envoyer(laCase().form);
    await tick();
    expect(laCase().bouton.dataset.fait).toBe('1');
    expect(document.querySelector('.flash')).toBeNull();
  });

  it('un refus du serveur laisse la case telle quelle et le dit', async () => {
    monter(caseHtml(false));
    fetchMock.mockResolvedValue(reponse({ kind: 'error', message: 'Fichier illisible.' }, 409));
    const { bouton } = laCase();
    envoyer(laCase().form);
    await tick();
    expect(bouton.dataset.fait).toBe('0');
    expect(bouton.textContent).toBe('À faire');
    expect(document.querySelector('.flash')!.className).toBe('flash flash-error');
    expect(document.querySelector('.flash')!.textContent).toBe('Fichier illisible.');
    expect(bouton.disabled).toBe(false);
  });

  it('un statut d\'échec sans message donne un message par défaut', async () => {
    monter(caseHtml(false));
    fetchMock.mockResolvedValue(reponse({}, 500));
    envoyer(laCase().form);
    await tick();
    expect(laCase().bouton.dataset.fait).toBe('0');
    expect(document.querySelector('.flash')!.textContent).toBe("La case n'a pas été enregistrée.");
  });

  it('si fetch est rejeté (panne réseau), le formulaire part à l\'ancienne (303)', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    monter(caseHtml(false));
    fetchMock.mockRejectedValueOnce(new TypeError('réseau'));
    const { form, bouton } = laCase();
    const soumettre = vi.spyOn(form, 'submit').mockImplementation(() => {});
    envoyer(form);
    await tick();
    expect(soumettre).toHaveBeenCalledTimes(1);
    expect(bouton.dataset.fait).toBe('0');
  });

  it('un refus qui n\'est pas du JSON (403, 413) ne relance pas de POST classique', async () => {
    // Tour 1, F4 : la page ne doit pas être remplacée par « Forbidden ».
    for (const status of [403, 413, 200]) {
      monter(caseHtml(false));
      fetchMock.mockResolvedValueOnce(new Response('Forbidden', { status }));
      const { form, bouton } = laCase();
      const soumettre = vi.spyOn(form, 'submit').mockImplementation(() => {});
      envoyer(form);
      await tick();
      expect(soumettre).not.toHaveBeenCalled();
      expect(bouton.dataset.fait).toBe('0');
      expect(bouton.disabled).toBe(false);
      expect(document.querySelector('.flash')!.className).toBe('flash flash-error');
      expect(document.querySelector('.flash')!.textContent)
        .toBe("La case n'a pas été enregistrée.");
    }
  });

  it('pendant l\'envoi, la case est désactivée (pas de double envoi)', async () => {
    monter(caseHtml(false));
    let finir: (r: Response) => void = () => {};
    fetchMock.mockReturnValue(new Promise<Response>((r) => { finir = r; }));
    envoyer(laCase().form);
    expect(laCase().bouton.disabled).toBe(true);
    finir(reponse({ kind: 'success' }));
    await tick();
    expect(laCase().bouton.disabled).toBe(false);
  });

  it('un autre formulaire de la page n\'est pas intercepté', () => {
    monter('<form id="autre" action="/x"><button>ok</button></form>');
    const ev = envoyer(document.getElementById('autre') as HTMLFormElement);
    expect(ev.defaultPrevented).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('la feuille de style', () => {
  const css = readFileSync(path.join(TOOLS, 'review_bord.css'), 'utf-8').replace(/\s+/g, '');

  it('chaque vue forcée a sa règle, et « auto » suit la largeur (§ 5)', () => {
    for (const vue of ['13', 'telephone']) {
      expect(css).toContain(`html[data-vue="${vue}"]`);
    }
    expect(css).toContain('@media(max-width:2200px){html[data-vue="auto"]');
    expect(css).toContain('@media(max-width:900px){html[data-vue="auto"]');
  });

  it('les lignes « inconnu » sont grisées sans opacité, pour garder le contraste', () => {
    expect(css).toContain('.bord-tache[data-inconnu]');
    expect(css).not.toMatch(/opacity/);
  });

  it('le focus reste visible', () => {
    expect(css).toContain(':focus-visible{outline:2pxsolid');
  });
});
