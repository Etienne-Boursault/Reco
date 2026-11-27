/**
 * Tests de `src/lib/audience/exclusion.mjs` : ne pas mesurer l'adresse de
 * l'éditeur (R-14, demande du 27/11/2026).
 *
 * Aucun vrai DNS : le résolveur et le minuteur sont des doublures. Noms
 * fictifs (`maison.example`), adresses de documentation (192.0.2.x, 2001:db8::).
 */
import { describe, expect, it, vi } from 'vitest';

// @ts-expect-error — module `.mjs` sans déclaration de types
import { creerExclusion, normaliser } from '../../src/lib/audience/exclusion.mjs';

const silence = { warn: vi.fn() };

/** Un résolveur dont chaque réponse se règle par nom et par famille. */
function faux(reponses: Record<string, any>) {
  const lire = (famille: '4' | '6') => async (nom: string) => {
    const r = reponses[`${nom}|${famille}`];
    if (r instanceof Error) throw r;
    if (r === undefined) throw Object.assign(new Error('ENODATA'), { code: 'ENODATA' });
    return r;
  };
  return { resolve4: vi.fn(lire('4')), resolve6: vi.fn(lire('6')) };
}

/** Un minuteur qui ne tourne pas : le test le déclenche à la main. */
function minuteur() {
  const m: { rappel?: () => void; periode?: number; unref: any; arrete: boolean } = {
    unref: vi.fn(), arrete: false,
  };
  const planifier = (rappel: () => void, periode: number) => {
    m.rappel = rappel;
    m.periode = periode;
    return m;
  };
  return { m, planifier, annuler: vi.fn(() => { m.arrete = true; }) };
}

describe('normaliser', () => {
  it.each([
    ['192.0.2.7', '192.0.2.7'],
    ['  192.0.2.7 ', '192.0.2.7'],
    ['::ffff:192.0.2.7', '192.0.2.7'],
    ['::FFFF:192.0.2.7', '192.0.2.7'],
    ['::ffff:c000:207', '192.0.2.7'],
    ['2001:DB8::1', '2001:db8::1'],
    ['2001:0db8:0000:0000:0000:0000:0000:0001', '2001:db8::1'],
  ])('%s devient %s', (entree, attendu) => {
    expect(normaliser(entree)).toBe(attendu);
  });

  it.each([[null], [undefined], [42], [''], ['maison.example'], ['999.1.1.1'], ['fe80::1%eth0']])(
    '%s n’est pas une adresse : null', (entree) => {
      expect(normaliser(entree)).toBeNull();
    });
});

describe('creerExclusion : sans liste', () => {
  it.each([[undefined], [''], ['  ,, ']])('liste %j : rien n’est exclu, rien n’est résolu', async (liste) => {
    const resolveur = faux({});
    const t = minuteur();
    const ex = creerExclusion({ liste, resolveur, planifier: t.planifier, journal: silence });
    await ex.pret;
    expect(ex.exclut('192.0.2.7')).toBe(false);
    expect(ex.exclut(null)).toBe(false);
    expect(resolveur.resolve4).not.toHaveBeenCalled();
    expect(t.m.rappel).toBeUndefined();
  });

  it('lit RECO_AUDIENCE_EXCLURE par défaut', () => {
    vi.stubEnv('RECO_AUDIENCE_EXCLURE', '192.0.2.9');
    try {
      expect(creerExclusion({ journal: silence }).exclut('192.0.2.9')).toBe(true);
    } finally {
      vi.unstubAllEnvs();
    }
  });
});

describe('creerExclusion : adresses écrites telles quelles', () => {
  it('sont prises sans résolution, sous forme normalisée', () => {
    const resolveur = faux({});
    const t = minuteur();
    const ex = creerExclusion({
      liste: ' 192.0.2.7 , 2001:DB8::1 ', resolveur, planifier: t.planifier, journal: silence,
    });
    expect(ex.exclut('192.0.2.7')).toBe(true);
    expect(ex.exclut('::ffff:192.0.2.7')).toBe(true);
    expect(ex.exclut('2001:0db8::1')).toBe(true);
    expect(ex.exclut('192.0.2.8')).toBe(false);
    expect(ex.exclut('pas une adresse')).toBe(false);
    expect(resolveur.resolve4).not.toHaveBeenCalled();
    expect(t.m.rappel).toBeUndefined(); // pas de nom : pas de minuteur
  });
});

describe('creerExclusion : noms résolus', () => {
  it('résout A et AAAA au démarrage ; la vérification ne bloque jamais', async () => {
    const resolveur = faux({
      'maison.example|4': ['192.0.2.7'],
      'maison.example|6': ['2001:DB8::7'],
    });
    const t = minuteur();
    const ex = creerExclusion({ liste: 'Maison.Example', resolveur, planifier: t.planifier, journal: silence });
    // Avant la fin de la résolution : ensemble vide, réponse immédiate.
    expect(ex.exclut('192.0.2.7')).toBe(false);
    await ex.pret;
    expect(ex.exclut('192.0.2.7')).toBe(true);
    expect(ex.exclut('2001:db8::7')).toBe(true);
    expect(ex.exclut('192.0.2.8')).toBe(false);
    expect(resolveur.resolve4).toHaveBeenCalledWith('maison.example');
  });

  it('replanifie toutes les 5 minutes, sans retenir le processus, et suit le changement d’adresse', async () => {
    const reponses: Record<string, any> = { 'maison.example|4': ['192.0.2.7'] };
    const t = minuteur();
    const ex = creerExclusion({
      liste: 'maison.example', resolveur: faux(reponses), planifier: t.planifier, journal: silence,
    });
    await ex.pret;
    expect(t.m.periode).toBe(300_000);
    expect(t.m.rappel).toBe(ex.rafraichir);
    expect(t.m.unref).toHaveBeenCalled();

    reponses['maison.example|4'] = ['192.0.2.99'];
    await ex.rafraichir();
    expect(ex.exclut('192.0.2.99')).toBe(true);
    expect(ex.exclut('192.0.2.7')).toBe(false);
  });

  it('un échec garde la dernière réponse connue, et ne le dit qu’une fois', async () => {
    const reponses: Record<string, any> = { 'maison.example|4': ['192.0.2.7'] };
    const journal = { warn: vi.fn() };
    const t = minuteur();
    const ex = creerExclusion({
      liste: 'maison.example', resolveur: faux(reponses), planifier: t.planifier, journal,
    });
    await ex.pret;

    reponses['maison.example|4'] = Object.assign(new Error('délai'), { code: 'ETIMEOUT' });
    await ex.rafraichir();
    expect(journal.warn).toHaveBeenCalledTimes(1);
    expect(ex.exclut('192.0.2.7')).toBe(true);
    expect(JSON.stringify(journal.warn.mock.calls)).not.toContain('maison.example');

    await ex.rafraichir();
    expect(ex.exclut('192.0.2.7')).toBe(true);
    expect(journal.warn).toHaveBeenCalledTimes(1);

    // Le retour du DNS remet le compteur de plaintes à zéro.
    reponses['maison.example|4'] = ['192.0.2.7'];
    await ex.rafraichir();
    reponses['maison.example|4'] = new Error('encore');
    await ex.rafraichir();
    expect(journal.warn).toHaveBeenCalledTimes(2);
  });

  it('« pas d’enregistrement » (ENODATA) vide la famille : l’adresse abandonnée ne compte plus', async () => {
    const reponses: Record<string, any> = {
      'maison.example|4': ['192.0.2.7'],
      'maison.example|6': ['2001:db8::7'],
    };
    const t = minuteur();
    const ex = creerExclusion({
      liste: 'maison.example', resolveur: faux(reponses), planifier: t.planifier, journal: silence,
    });
    await ex.pret;
    delete reponses['maison.example|6'];
    await ex.rafraichir();
    expect(ex.exclut('2001:db8::7')).toBe(false);
    expect(ex.exclut('192.0.2.7')).toBe(true);
  });

  it('un nom qui échoue ne retire pas les adresses écrites ni les autres noms', async () => {
    const t = minuteur();
    const ex = creerExclusion({
      liste: 'maison.example,bureau.example,192.0.2.1',
      resolveur: faux({
        'maison.example|4': new Error('panne'),
        'bureau.example|4': ['192.0.2.2'],
      }),
      planifier: t.planifier, journal: silence,
    });
    await ex.pret;
    expect(ex.exclut('192.0.2.1')).toBe(true);
    expect(ex.exclut('192.0.2.2')).toBe(true);
  });

  it('un résolveur qui lève sur place est traité comme un échec', async () => {
    const t = minuteur();
    const ex = creerExclusion({
      liste: 'maison.example',
      resolveur: { resolve4: () => { throw new Error('sync'); }, resolve6: () => { throw new Error('sync'); } },
      planifier: t.planifier, journal: silence,
    });
    await expect(ex.pret).resolves.toBeUndefined();
    expect(ex.exclut('192.0.2.7')).toBe(false);
  });

  it('arreter annule le minuteur', () => {
    const t = minuteur();
    const ex = creerExclusion({
      liste: 'maison.example', resolveur: faux({}), planifier: t.planifier,
      annuler: t.annuler, journal: silence,
    });
    ex.arreter();
    expect(t.annuler).toHaveBeenCalledWith(t.m);
  });

  it('arreter sans nom à résoudre ne fait rien', () => {
    const annuler = vi.fn();
    creerExclusion({ liste: '192.0.2.1', annuler, journal: silence }).arreter();
    expect(annuler).not.toHaveBeenCalled();
  });

  it('un minuteur sans unref (double de test) ne fait pas échouer', () => {
    const planifier = () => ({});
    expect(() => creerExclusion({
      liste: 'maison.example', resolveur: faux({}), planifier, journal: silence,
    })).not.toThrow();
  });

  it('un résultat de résolveur qui n’est pas une adresse est ignoré', async () => {
    const t = minuteur();
    const ex = creerExclusion({
      liste: 'maison.example', resolveur: faux({ 'maison.example|4': ['pas-une-ip', '192.0.2.7'] }),
      planifier: t.planifier, journal: silence,
    });
    await ex.pret;
    expect(ex.exclut('192.0.2.7')).toBe(true);
  });
});
