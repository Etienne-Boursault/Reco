/**
 * Tests `SupportLinks.astro` — boutons « Soutenir le projet » du footer.
 *
 * Le composant est le point d'entrée « dons » du kit duplicable : il ne doit
 * RIEN afficher tant que les pseudos ne sont pas renseignés (placeholders
 * `a-remplacer` du template), et marquer tous ses liens sortants.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import SupportLinks from '../../src/components/SupportLinks.astro';

async function render(props: Record<string, unknown> = {}): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(SupportLinks as any, { props });
}

describe('SupportLinks — rendu conditionnel', () => {
  it('sans prop links → rendu vide (aucun bloc .support)', async () => {
    const html = await render();
    expect(html).not.toContain('support-list');
  });

  it('tableau vide → rendu vide', async () => {
    const html = await render({ links: [] });
    expect(html).not.toContain('support-list');
  });

  it('URL vide ou blanche → lien ignoré, donc rendu vide', async () => {
    const html = await render({
      links: [
        { platform: 'kofi', url: '' },
        { platform: 'paypal', url: '   ' },
      ],
    });
    expect(html).not.toContain('support-list');
  });

  it('placeholder « a-remplacer » du template → lien ignoré', async () => {
    const html = await render({
      links: [{ platform: 'kofi', url: 'https://ko-fi.com/a-remplacer' }],
    });
    expect(html).not.toContain('support-list');
  });

  it('entrée sans champ url (donnée malformée) → ignorée sans planter', async () => {
    const html = await render({ links: [{ platform: 'kofi' }] });
    expect(html).not.toContain('support-list');
  });

  it('mélange valide + placeholder → seul le lien valide est rendu', async () => {
    const html = await render({
      links: [
        { platform: 'kofi', url: 'https://ko-fi.com/a-remplacer' },
        { platform: 'liberapay', url: 'https://liberapay.com/reco' },
      ],
    });
    expect(html).toContain('https://liberapay.com/reco');
    expect(html).not.toContain('ko-fi.com');
  });
});

describe('SupportLinks — libellés par plateforme', () => {
  it('plateforme connue → libellé + emoji du catalogue', async () => {
    const html = await render({
      links: [{ platform: 'liberapay', url: 'https://liberapay.com/reco' }],
    });
    expect(html).toContain('Liberapay');
    expect(html).toContain('💝');
  });

  it('plateforme inconnue → repli « Soutenir » / ❤️', async () => {
    const html = await render({
      links: [{ platform: 'plateforme-exotique', url: 'https://exemple.test/don' }],
    });
    expect(html).toContain('Soutenir');
    expect(html).toContain('❤️');
  });

  it('label explicite prime sur le libellé de la plateforme', async () => {
    const html = await render({
      links: [{ platform: 'kofi', url: 'https://ko-fi.com/reco', label: 'Payer un café' }],
    });
    expect(html).toContain('Payer un café');
    expect(html).not.toContain('>Ko-fi<');
  });

  it('l’emoji est décoratif (aria-hidden) — le nom reste lisible en texte', async () => {
    const html = await render({
      links: [{ platform: 'kofi', url: 'https://ko-fi.com/reco' }],
    });
    expect(html).toMatch(/<span aria-hidden="true"[^>]*>☕<\/span>/);
  });
});

describe('SupportLinks — sécurité des liens sortants', () => {
  it('target=_blank avec rel noopener noreferrer nofollow', async () => {
    const html = await render({
      links: [{ platform: 'kofi', url: 'https://ko-fi.com/reco' }],
    });
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer nofollow"');
  });

  it('le bloc porte le libellé i18n « Soutenir le projet »', async () => {
    const html = await render({
      links: [{ platform: 'kofi', url: 'https://ko-fi.com/reco' }],
    });
    expect(html).toContain('Soutenir le projet');
  });
});
