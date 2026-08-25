/**
 * Tests de `src/lib/audience/derive.mjs` — ce qu'on retient d'une visite.
 *
 * CE QU'ILS PROTÈGENT
 * -------------------
 * Ce module est le seul endroit où l'on décide ce que le site conserve de ses
 * visiteurs. Une régression ici ne casse rien de visible : elle fait
 * simplement conserver plus que promis, en silence. D'où des tests qui
 * vérifient autant ce qui est JETÉ que ce qui est gardé.
 *
 * Trois promesses tenues par ces tests :
 *  — aucun en-tête n'est conservé tel quel, seulement des catégories ;
 *  — la chaîne de requête ne touche jamais le disque ;
 *  — l'identifiant de visiteur ne survit pas à la journée.
 */
import { describe, expect, it } from 'vitest';

// @ts-expect-error — module `.mjs` sans déclaration de types
import {
  appareil,
  cheminSeul,
  empreinteDuJour,
  estRobot,
  estUnePage,
  evenementDeVisite,
  heureRonde,
  langue,
  pays,
  provenance,
} from '../../src/lib/audience/derive.mjs';

// ===== Ce qui compte comme une page ========================================
describe('estUnePage', () => {
  it('retient une page du catalogue', () => {
    expect(estUnePage('/un-bon-moment/oeuvre/1c5928e1')).toBe(true);
    expect(estUnePage('/')).toBe(true);
  });

  it('écarte les ressources : sinon une visite compterait trente fois', () => {
    // Une page charge CSS, polices et images ; les compter noierait le signal.
    expect(estUnePage('/_astro/Layout.Br4oq2dI.css')).toBe(false);
    expect(estUnePage('/icons/platforms/www.imdb.com.svg')).toBe(false);
    expect(estUnePage('/favicon.ico')).toBe(false);
    expect(estUnePage('/version.txt')).toBe(false);
  });

  it('écarte les chemins techniques', () => {
    expect(estUnePage('/api/click')).toBe(false);
    expect(estUnePage('/og/un-bon-moment.png')).toBe(false);
    expect(estUnePage('/.well-known/reco-registry.json')).toBe(false);
  });

  it('écarte le tableau de bord : il fausserait ses propres chiffres', () => {
    // `/audience` arrivait en TÊTE des pages les plus consultées en
    // production, et ses appels sans clé — qui répondent 404 — remplissaient
    // la section « liens morts qui circulent ». Une page d'administration
    // n'est pas de l'audience : plus on consulte ses chiffres, plus on les
    // fausse.
    expect(estUnePage('/audience')).toBe(false);
    expect(estUnePage('/audience/')).toBe(false);
    expect(estUnePage('/audience?cle=x&jours=7')).toBe(false);
  });

  it('ne confond pas avec une vraie page qui commence pareil', () => {
    // Un préfixe nu écarterait aussi `/audiences-publiques`.
    expect(estUnePage('/audiences-publiques')).toBe(true);
  });

  it('ne compte que les GET', () => {
    // Un POST vers /api/report n'est pas une page vue.
    expect(estUnePage('/signaler', 'POST')).toBe(false);
  });

  it('retient une page malgré une chaîne de requête', () => {
    expect(estUnePage('/un-bon-moment/recos?type=film')).toBe(true);
  });

  it('résiste à une entrée absurde', () => {
    expect(estUnePage('')).toBe(false);
    expect(estUnePage('pas-un-chemin')).toBe(false);
    expect(estUnePage(null as never)).toBe(false);
  });
});

// ===== Le chemin ===========================================================
describe('cheminSeul', () => {
  it('coupe la chaîne de requête', () => {
    // Elle peut porter un terme de recherche ou un identifiant de session.
    expect(cheminSeul('/recherche?q=quelque+chose+de+prive')).toBe('/recherche');
  });

  it('coupe aussi le fragment', () => {
    expect(cheminSeul('/a-propos#credits')).toBe('/a-propos');
  });

  it('borne la longueur', () => {
    expect(cheminSeul('/' + 'a'.repeat(900)).length).toBeLessThanOrEqual(512);
  });
});

// ===== La provenance =======================================================
describe('provenance', () => {
  it('garde le domaine, jamais l’URL complète', () => {
    // Une URL de recherche complète contiendrait la requête de la personne.
    expect(provenance('https://www.google.com/search?q=un+bon+moment+recos', 'unebonnere.co'))
      .toBe('www.google.com');
  });

  it('ignore la navigation interne', () => {
    // Ce qui intéresse, c'est d'où l'on ARRIVE, pas comment on circule.
    expect(provenance('https://unebonnere.co/un-bon-moment', 'unebonnere.co')).toBeNull();
  });

  it('ignore aussi les sous-domaines du site', () => {
    expect(provenance('https://www.unebonnere.co/x', 'unebonnere.co')).toBeNull();
  });

  it('rend null sans référent, ou sur un référent illisible', () => {
    expect(provenance(null, 'unebonnere.co')).toBeNull();
    expect(provenance('pas une url', 'unebonnere.co')).toBeNull();
  });
});

// ===== Robot ou humain =====================================================
describe('estRobot', () => {
  it('reconnaît les robots courants', () => {
    expect(estRobot('Mozilla/5.0 (compatible; Googlebot/2.1)')).toBe(true);
    expect(estRobot('facebookexternalhit/1.1')).toBe(true);
    expect(estRobot('curl/8.4.0')).toBe(true);
  });

  it('laisse passer un vrai navigateur', () => {
    expect(estRobot('Mozilla/5.0 (Windows NT 10.0; Win64) Chrome/152.0 Safari/537.36'))
      .toBe(false);
  });

  it('compte l’absence d’agent comme un robot', () => {
    // Un client sans en-tête n'est pas un navigateur.
    expect(estRobot(null)).toBe(true);
    expect(estRobot('')).toBe(true);
  });

  it('sans ce tri, les chiffres seraient faux', () => {
    // Sur 2 600 pages, les moteurs font souvent l'essentiel du trafic : ce
    // booléen est ce qui sépare une audience d'une indexation.
    const moteurs = ['Googlebot', 'bingbot', 'Applebot', 'DuckDuckBot'];
    expect(moteurs.every((m) => estRobot(m))).toBe(true);
  });
});

// ===== L'appareil ==========================================================
describe('appareil', () => {
  it('distingue mobile et ordinateur', () => {
    expect(appareil('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)')).toBe('mobile');
    expect(appareil('Mozilla/5.0 (Windows NT 10.0; Win64; x64)')).toBe('ordinateur');
  });

  it('ne rend JAMAIS le modèle : deux catégories, pas une empreinte', () => {
    const valeurs = new Set([
      appareil('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)'),
      appareil('Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro)'),
      appareil('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'),
      appareil(null),
    ]);
    expect([...valeurs].every((v) => ['mobile', 'ordinateur', 'inconnu'].includes(v)))
      .toBe(true);
  });
});

// ===== La langue ===========================================================
describe('langue', () => {
  it('réduit l’en-tête à deux lettres', () => {
    // L'en-tête complet est un composant d'empreinte connu ; « fr » ne l'est pas.
    expect(langue('fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7')).toBe('fr');
    expect(langue('en-GB')).toBe('en');
  });

  it('rend null sur une valeur qui n’est pas une langue', () => {
    expect(langue(null)).toBeNull();
    expect(langue('*')).toBeNull();
    expect(langue('123')).toBeNull();
  });
});

// ===== Le pays =============================================================
describe('pays', () => {
  it('lit l’en-tête posé par un intermédiaire', () => {
    expect(pays({ 'cf-ipcountry': 'fr' })).toBe('FR');
    expect(pays({ 'x-vercel-ip-country': 'BE' })).toBe('BE');
  });

  it('rend null si personne n’en pose : la mesure est absente, pas fausse', () => {
    expect(pays({})).toBeNull();
    expect(pays({ 'user-agent': 'x' })).toBeNull();
  });

  it('écarte les codes « inconnu » plutôt que de les compter comme un pays', () => {
    expect(pays({ 'cf-ipcountry': 'XX' })).toBeNull();
    expect(pays({ 'cf-ipcountry': 'T1' })).toBeNull(); // réseau Tor
    expect(pays({ 'cf-ipcountry': 'FRANCE' })).toBeNull();
  });
});

// ===== L'identifiant de visiteur ==========================================
describe('empreinteDuJour', () => {
  it('donne la même valeur pour la même personne le même jour', () => {
    const a = empreinteDuJour('203.0.113.7', 'sel-secret', '2026-08-25');
    const b = empreinteDuJour('203.0.113.7', 'sel-secret', '2026-08-25');
    expect(a).toBe(b);
  });

  it('ne survit PAS à la journée', () => {
    // C'est ce qui empêche de suivre quelqu'un dans le temps.
    const lundi = empreinteDuJour('203.0.113.7', 'sel-secret', '2026-08-25');
    const mardi = empreinteDuJour('203.0.113.7', 'sel-secret', '2026-08-26');
    expect(lundi).not.toBe(mardi);
  });

  it('distingue deux visiteurs', () => {
    const a = empreinteDuJour('203.0.113.7', 'sel', '2026-08-25');
    const b = empreinteDuJour('198.51.100.2', 'sel', '2026-08-25');
    expect(a).not.toBe(b);
  });

  it('ne laisse pas remonter à l’adresse', () => {
    const e = empreinteDuJour('203.0.113.7', 'sel', '2026-08-25');
    expect(e).not.toContain('203');
    expect(e).toHaveLength(12);
  });

  it('rend null sans IP plutôt que de tout regrouper', () => {
    // Hacher une valeur par défaut donnerait un seul « visiteur » à tous les
    // anonymes — un chiffre faux vaut moins qu'un chiffre absent.
    expect(empreinteDuJour(null, 'sel', '2026-08-25')).toBeNull();
    expect(empreinteDuJour('203.0.113.7', null, '2026-08-25')).toBeNull();
  });
});

// ===== L'horodatage ========================================================
describe('heureRonde', () => {
  it('arrondit à l’heure', () => {
    // À la milliseconde, l'horodatage devient un identifiant de fait.
    expect(heureRonde('2026-08-25T14:37:52.481Z')).toBe('2026-08-25T14:00:00.000Z');
  });
});

// ===== L'événement complet ================================================
describe('evenementDeVisite', () => {
  const ENTETES = {
    'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)',
    referer: 'https://www.google.com/search?q=quelque+chose+de+prive',
    'accept-language': 'fr-FR,fr;q=0.9',
    'cf-ipcountry': 'FR',
  };

  function evenement(over = {}) {
    return evenementDeVisite({
      chemin: '/un-bon-moment/oeuvre/abc?utm_source=newsletter',
      statut: 200,
      entetes: ENTETES,
      ip: '203.0.113.7',
      sel: 'sel-secret',
      hoteDuSite: 'unebonnere.co',
      maintenant: new Date('2026-08-25T14:37:52.481Z'),
      ...over,
    });
  }

  it('catégorise tout ce qui vient des en-têtes', () => {
    expect(evenement()).toMatchObject({
      ts: '2026-08-25T14:00:00.000Z',
      chemin: '/un-bon-moment/oeuvre/abc',
      statut: 200,
      robot: false,
      appareil: 'mobile',
      provenance: 'www.google.com',
      langue: 'fr',
      pays: 'FR',
    });
  });

  it('ne conserve AUCUN en-tête tel quel', () => {
    // La garde la plus importante du fichier : on relit l'événement écrit et
    // on vérifie qu'aucune valeur brute n'y a survécu.
    const serialise = JSON.stringify(evenement());

    expect(serialise).not.toContain('Mozilla');
    expect(serialise).not.toContain('iPhone');
    expect(serialise).not.toContain('quelque+chose+de+prive');
    expect(serialise).not.toContain('203.0.113.7');
    expect(serialise).not.toContain('utm_source');
  });

  it('n’a pas de champ de parcours', () => {
    // Écarté explicitement : une séquence de pages est plus identifiante que
    // leur somme.
    const e = evenement();
    expect(Object.keys(e)).not.toContain('parcours');
    expect(Object.keys(e)).not.toContain('session');
  });

  it('garde la durée quand on la fournit', () => {
    expect(evenement({ dureeMs: 38.7 })).toMatchObject({ dureeMs: 39 });
  });

  it('ne prétend PAS mesurer le poids de la réponse', () => {
    // `server.mjs` compresse, et la compression retire `Content-Length` — il
    // annonçait la taille en clair. Le champ aurait été vide sur toutes les
    // pages HTML : mieux vaut pas de champ qu'un champ toujours nul.
    expect(Object.keys(evenement())).not.toContain('octets');
  });

  it('met null plutôt qu’une valeur inventée', () => {
    const e = evenementDeVisite({ chemin: '/', maintenant: new Date('2026-08-25T00:00:00Z') });
    expect(e.provenance).toBeNull();
    expect(e.pays).toBeNull();
    expect(e.visiteur).toBeNull();
    expect(e.dureeMs).toBeNull();
    expect(e.langue).toBeNull();
  });
});
