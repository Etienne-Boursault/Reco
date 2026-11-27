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
import { evenementDeSignal, evenementDeVisite } from '../../src/lib/audience/derive.mjs';
import { CLE, MOIS_DE_VIE } from '../../src/utils/mesureNavigateur';

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

  // AU-2 B (27/11/2026) : la page décrit ce que le code fait, par des constantes
  // et des clés lues dans le code. Une clé ajoutée à une ligne de mesure sans
  // mot correspondant dans la page fait échouer le test.
  describe('mesure d’audience (AU-2 B)', () => {
    const MOTS: Record<string, string> = {
      ts: 'heure arrondie',
      chemin: 'adresse de la page',
      statut: 'code de réponse',
      robot: 'ressemble à un robot',
      prechargement: 'préchargée',
      appareil: 'mobile',
      provenance: 'domaine du site',
      langue: 'langue du navigateur',
      pays: 'le pays',
      hebergeur: 'celle d’un hébergeur',
      visiteur: 'une empreinte',
      dureeMs: 'temps de réponse',
      nature: 'signal « page vue »',
      revenant: 'déjà venu',
      aVuEpisode: 'page d’épisode',
      aVuFiche: 'fiche d’œuvre',
    };

    it('décrit chaque champ des lignes de visite et de signal écrites par le serveur', async () => {
      const texte = visibleText(await rendre());
      const cles = new Set([
        ...Object.keys(evenementDeVisite({ chemin: '/' })),
        ...Object.keys(evenementDeSignal({ chemin: '/' })),
      ]);

      for (const cle of cles) {
        expect(MOTS[cle], `champ « ${cle} » sans mot dans la page`).toBeDefined();
        expect(texte).toContain(MOTS[cle]);
      }
    });

    it('cite l’entrée du navigateur et sa durée telles que le code les fixe', async () => {
      const texte = visibleText(await rendre());

      expect(texte).toContain(CLE);
      expect(texte).toContain(`${MOIS_DE_VIE} mois`);
    });

    it('dit que l’empreinte est un pseudonyme et que le refus ne coupe pas la page servie', async () => {
      const texte = visibleText(await rendre());

      expect(texte).toContain('pseudonyme');
      expect(texte).toContain('que s’il connaît votre adresse IP');
      expect(texte).toContain('comme pour une visite sans JavaScript');
    });

    it('porte la base légale, le droit d’opposition et les crédits de la table des hébergeurs', async () => {
      const html = await rendre();
      const texte = visibleText(html);

      expect(texte).toContain('17 septembre 2020');
      expect(texte).toContain('article 21');
      expect(html).toContain('github.com/X4BNet/lists_vpn');
      expect(texte).toContain('IP to ASN Lite');
      expect(texte).toContain('CC BY 4.0');
      expect(html).toContain('https://db-ip.com');
    });

    it('n’affirme plus ce que le code ne fait plus', async () => {
      const texte = visibleText(await rendre());

      for (const ancienne of [
        'aucun traceur',
        'ne dépose rien dans votre navigateur',
        'ne permettent pas de retrouver vos visites',
        'sans aucun identifiant',
      ]) {
        expect(texte).not.toContain(ancienne);
      }
    });

    it('ne parle pas de l’exclusion de l’éditeur, qui ne concerne pas les visiteurs', async () => {
      const texte = visibleText(await rendre());

      expect(texte).not.toContain('EXCLURE');
      expect(texte).not.toContain('DNS');
    });
  });

  it('a un seul h1 et un main ciblable', async () => {
    const html = await rendre();

    expect(html.match(/<h1/g)).toHaveLength(1);
    expect(html).toContain('id="main"');
  });
});
