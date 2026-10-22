/**
 * Rendu de `src/pages/mentions-legales.astro`.
 *
 * La page fait des promesses — durées de conservation, anonymat de l'éditeur,
 * mentions de crédit obligatoires. Ces tests vérifient qu'elles restent
 * branchées sur le code qui les tient, plutôt que recopiées à la main.
 */
import { describe, expect, it } from 'vitest';
import { renderPage, visibleText } from '../gallery/_render_page';

import Mentions from '../../src/pages/mentions-legales.astro';
import { MOIS_COORDONNEES, MOIS_MESURES } from '../../src/server/retention.mjs';

const rendre = () => renderPage(Mentions, { path: '/mentions-legales' });

describe('/mentions-legales', () => {
  it('nomme l’hébergeur avec adresse et téléphone, comme la LCEN l’exige', async () => {
    const texte = visibleText(await rendre());

    expect(texte).toContain('Infomaniak Network SA');
    expect(texte).toContain('Rue Eugène Marziano 25');
    expect(texte).toContain('+41 22 820 35 41');
  });

  it('garde l’éditeur anonyme mais joignable', async () => {
    // Arbitrage du 2026-10-22 : anonymat permis aux éditeurs non professionnels.
    const html = await rendre();

    expect(visibleText(html)).not.toContain('Boursault');
    expect(html).toContain('mailto:contact@unebonnere.co');
  });

  it('annonce les durées que la purge applique réellement', async () => {
    const texte = visibleText(await rendre());

    expect(texte).toContain(`au bout de ${MOIS_MESURES} mois`);
    expect(texte).toContain(`au bout de ${MOIS_COORDONNEES} mois`);
  });

  it('porte les crédits imposés par TMDB et DB-IP', async () => {
    const texte = visibleText(await rendre());

    expect(texte).toContain('sans être approuvé ni certifié par TMDB');
    expect(texte).toContain('IP Geolocation by DB-IP');
  });

  it('a un seul h1 et un main ciblable', async () => {
    const html = await rendre();

    expect(html.match(/<h1/g)).toHaveLength(1);
    expect(html).toContain('id="main"');
  });
});
