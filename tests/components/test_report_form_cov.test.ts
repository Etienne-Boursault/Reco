/**
 * Tests `ReportForm.astro` — formulaire de signalement visiteur.
 *
 * Points sensibles couverts :
 *  - le challenge captcha est rendu server-side (token en champ caché +
 *    question étiquetant le champ de réponse) ;
 *  - le honeypot est déporté hors écran, PAS `display:none` (H16-1), et
 *    masqué aux lecteurs d'écran ;
 *  - le fallback `mailto:` (P0-2) n'apparaît QUE si `siteConfig.contactEmail`
 *    est renseigné, et pré-remplit sujet + corps sans perdre le contexte.
 *
 * `src/config/site.js` est mocké pour piloter `contactEmail` — c'est la
 * frontière de personnalisation des forks, et la seule façon d'atteindre
 * les deux branches du composant.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const config: { siteName: string; contactEmail?: string } = {
  siteName: 'Reco',
  contactEmail: undefined,
};
vi.mock('../../src/config/site.js', () => ({ siteConfig: config }));

const { experimental_AstroContainer: AstroContainer } = await import('astro/container');

/** Extrait un paramètre du `mailto:` rendu (les `&` sont échappés en HTML). */
function mailtoParam(html: string, key: string): string {
  const href = (html.match(/href="(mailto:[^"]+)"/)?.[1] ?? '').replace(/&#38;/g, '&');
  return new URL(href.replace('mailto:', 'mailto://')).searchParams.get(key) ?? '';
}
const ReportForm = (await import('../../src/components/ReportForm.astro')).default;

async function render(props: Record<string, unknown> = {}): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(ReportForm as any, {
    props: { sourceId: 'ubm', recoId: 'ubm-0001', ...props },
  });
}

beforeEach(() => {
  config.contactEmail = undefined;
});

describe('ReportForm — structure du formulaire', () => {
  it('POST vers /api/report, sans validation navigateur', async () => {
    const html = await render();
    expect(html).toMatch(/<form[^>]*method="POST"/);
    expect(html).toContain('action="/api/report"');
    expect(html).toContain('novalidate');
  });

  it('transporte sourceId et recoId en champs cachés', async () => {
    const html = await render();
    expect(html).toMatch(/<input type="hidden" name="sourceId" value="ubm"[^>]*>/);
    expect(html).toMatch(/<input type="hidden" name="recoId" value="ubm-0001"[^>]*>/);
  });

  it('les 4 catégories sont des radios dans un fieldset/legend', async () => {
    const html = await render();
    expect(html).toMatch(/<fieldset class="categories"/);
    expect(html).toMatch(/<legend[^>]*>/);
    for (const v of ['error', 'broken-link', 'inappropriate', 'suggestion']) {
      expect(html).toContain(`value="${v}"`);
    }
  });

  it('le champ détails est requis, borné et décrit par son indice', async () => {
    const html = await render();
    expect(html).toContain('maxlength="1000"');
    expect(html).toContain('minlength="5"');
    expect(html).toContain('aria-required="true"');
    expect(html).toContain('aria-describedby="report-details-hint"');
    expect(html).toContain('1000');
  });

  it('les limites nom/email viennent de REPORT_LIMITS', async () => {
    const html = await render();
    expect(html).toContain('maxlength="80"');
    expect(html).toContain('maxlength="254"');
  });

  it('la zone de statut est un live region polie', async () => {
    const html = await render();
    expect(html).toMatch(/<p class="status" aria-live="polite" role="status"/);
  });

  it('expose les chaînes i18n du script en data-attributes', async () => {
    const html = await render();
    expect(html).toContain('data-i18n-sending=');
    expect(html).toContain('data-i18n-success=');
    expect(html).toContain('data-i18n-endpoint-405=');
  });
});

describe('ReportForm — captcha rendu server-side', () => {
  it('embarque un token signé et la question qui étiquette le champ', async () => {
    const html = await render();
    expect(html).toMatch(/name="captchaToken" value="[A-Za-z0-9_.-]+"/);
    expect(html).toMatch(/<span data-captcha-question[^>]*>Combien font \d \+ \d \?<\/span>/);
    expect(html).toContain('id="report-captcha"');
    expect(html).toContain('inputmode="numeric"');
  });

  it('deux rendus produisent deux tokens distincts (jti à usage unique)', async () => {
    const a = (await render()).match(/name="captchaToken" value="([^"]+)"/)?.[1];
    const b = (await render()).match(/name="captchaToken" value="([^"]+)"/)?.[1];
    expect(a).toBeTruthy();
    expect(a).not.toBe(b);
  });
});

describe('ReportForm — honeypot (H16-1)', () => {
  it('champ leurre hors du parcours clavier et masqué aux AT', async () => {
    const html = await render();
    expect(html).toContain('name="url_unused"');
    expect(html).toContain('tabindex="-1"');
    expect(html).toMatch(/<div class="honeypot" aria-hidden="true"/);
  });

  it('n’utilise pas display:none (détectable par les bots)', async () => {
    const html = await render();
    expect(html).not.toMatch(/class="honeypot"[^>]*style="display:\s*none/);
  });
});

describe('ReportForm — contexte de la reco signalée', () => {
  it('sans recoTitle, aucun encart de contexte', async () => {
    const html = await render();
    expect(html).not.toContain('class="context"');
  });

  it('avec recoTitle, l’encart nomme l’œuvre concernée', async () => {
    const html = await render({ recoTitle: 'Parasite' });
    expect(html).toContain('Signalement concernant :');
    expect(html).toMatch(/<strong[^>]*>Parasite<\/strong>/);
  });
});

describe('ReportForm — fallback mailto (P0-2)', () => {
  it('sans contactEmail configuré : ni bouton ni <noscript> mailto', async () => {
    const html = await render({ recoTitle: 'Parasite' });
    expect(html).not.toContain('data-report-mailto');
    expect(html).not.toContain('mailto:');
    expect(html).not.toContain('<noscript>');
  });

  it('avec contactEmail : bouton caché + repli <noscript>', async () => {
    config.contactEmail = 'contact@reco.test';
    const html = await render({ recoTitle: 'Parasite' });
    expect(html).toContain('data-report-mailto');
    expect(html).toContain('href="mailto:contact@reco.test?subject=');
    expect(html).toMatch(/<a[^>]*class="mailto-fallback"[^>]*hidden/);
    expect(html).toContain('<noscript>');
  });

  it('le sujet reprend le titre de la reco quand il est connu', async () => {
    config.contactEmail = 'contact@reco.test';
    const html = await render({ recoTitle: 'Parasite' });
    const subject = mailtoParam(html, 'subject');
    expect(subject).toContain('Parasite');
  });

  it('sans titre de reco, le sujet retombe sur l’identifiant', async () => {
    config.contactEmail = 'contact@reco.test';
    const html = await render();
    const subject = mailtoParam(html, 'subject');
    expect(subject).toContain('ubm-0001');
  });

  it('le corps pré-rempli porte la source, la reco et son titre entre parenthèses', async () => {
    config.contactEmail = 'contact@reco.test';
    const html = await render({ recoTitle: 'Parasite' });
    const body = mailtoParam(html, 'body');
    expect(body).toContain('ubm');
    expect(body).toContain('ubm-0001 (Parasite)');
  });

  it('sans titre, le corps ne contient pas de parenthèses vides', async () => {
    config.contactEmail = 'contact@reco.test';
    const html = await render();
    const body = mailtoParam(html, 'body');
    expect(body).toContain('ubm-0001');
    expect(body).not.toContain('()');
  });
});
