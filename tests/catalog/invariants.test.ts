import { describe, expect, it } from 'vitest';
import { analyser, classer } from '../../src/lib/catalog/invariants.ts';
import { canoniserUrl, classerLiens } from '../../src/lib/catalog/liens.ts';
import { comparerReference, formaterReference, lireReference } from '../../src/lib/catalog/reference.ts';
import type { Corpus, Ecart, Entree, Json } from '../../src/lib/catalog/invariants.ts';

const e = (chemin: string, donnees: Json): Entree => ({ chemin, donnees });

/** Un épisode, une œuvre, une reco validée et sa mention, sans aucun écart. */
function sain(): Corpus {
  return {
    sources: [e('sources/s.json', { id: 's' })],
    episodes: [e('episodes/s/e1.json', { guid: 'e1' })],
    items: [e('items/s/i1.json', { id: 'i1', title: 'Titre', creator: 'Auteur', types: ['film'] })],
    recos: [
      e('recos/s/1.json', {
        id: 'ubm-1', status: 'validated', episodeGuid: 'e1', title: 'Titre', creator: 'Auteur', types: ['film'],
      }),
    ],
    mentions: [
      e('mentions/s/ubm-1.json', { id: 'ubm-1', status: 'validated', itemId: 'i1', sourceRef: { episodeGuid: 'e1' } }),
    ],
    redirections: {},
  };
}

const regles = (r: ReturnType<typeof analyser>, cle: 'bloquants' | 'avertissements'): string[] =>
  r[cle].map((v) => v.regle).sort();
const ecartsDe = (r: ReturnType<typeof analyser>): string[] => r.ecarts.map((x) => `${x.id} ${x.champ} ${x.classe}`);

describe('classer', () => {
  it('ne signale rien quand les deux copies sont vides ou égales', () => {
    expect(classer(undefined, null)).toBeNull();
    expect(classer('', undefined)).toBeNull();
    expect(classer('a', 'a')).toBeNull();
  });
  it('classe C2 une valeur présente d’un seul côté, C3 deux valeurs', () => {
    expect(classer('a', undefined)).toBe('C2');
    expect(classer(null, 3)).toBe('C2');
    expect(classer('a', 'b')).toBe('C3');
  });
  it('accepte une égalité sur mesure', () => {
    expect(classer('12', 12, (x, y) => String(x) === String(y))).toBeNull();
  });
});

describe('canoniserUrl — liste fermée de règles', () => {
  it('Steam : même numéro de jeu, avec ou sans nom', () => {
    expect(canoniserUrl('https://store.steampowered.com/app/753640/Outer_Wilds/')).toBe(
      canoniserUrl('https://store.steampowered.com/app/753640/'),
    );
  });
  it('TMDB : même type et numéro, avec ou sans nom, suite gardée', () => {
    expect(canoniserUrl('https://www.themoviedb.org/tv/60715-bref/watch?locale=FR&hl=fr')).toBe(
      'https://www.themoviedb.org/tv/60715/watch?locale=FR',
    );
    expect(canoniserUrl('https://www.themoviedb.org/movie/12')).toBe('https://www.themoviedb.org/movie/12');
  });
  it('Deezer : avec ou sans langue', () => {
    expect(canoniserUrl('https://www.deezer.com/fr/album/302127')).toBe('https://www.deezer.com/album/302127');
  });
  it('Spotify : avec ou sans intl', () => {
    expect(canoniserUrl('https://open.spotify.com/intl-fr/artist/4Z8W4fKeB5YxbusRsdQVPb')).toBe(
      'https://open.spotify.com/artist/4Z8W4fKeB5YxbusRsdQVPb',
    );
  });
  it('Instagram : poignée sans requête, sans tenir compte de la casse', () => {
    expect(canoniserUrl('https://www.instagram.com/PaulDechavanne/?hl=fr')).toBe(
      canoniserUrl('https://www.instagram.com/pauldechavanne'),
    );
  });
  it('YouTube : poignée et chaîne gardent chacune leur forme', () => {
    expect(canoniserUrl('https://www.youtube.com/@Nardwuar')).toBe('youtube:@nardwuar');
    expect(canoniserUrl('https://www.youtube.com/channel/UC8h8NJG9gacZ5lAJJvhD0fQ')).toBe(
      'youtube:channel:UC8h8NJG9gacZ5lAJJvhD0fQ',
    );
    expect(canoniserUrl('https://www.youtube.com/watch?v=abc&si=xyz')).toBe('https://www.youtube.com/watch?v=abc');
  });
  it('ailleurs, ne retire que hl, si et utm_*', () => {
    expect(canoniserUrl('https://exemple.fr/a?utm_source=x&b=1#ancre')).toBe('https://exemple.fr/a?b=1#ancre');
    expect(canoniserUrl('https://exemple.fr/a?hl=fr')).toBe('https://exemple.fr/a');
    expect(canoniserUrl('https://exemple.fr')).toBe('https://exemple.fr');
    expect(canoniserUrl('https://exemple.fr/a?%E0%A4%A=1&&si=2')).toBe('https://exemple.fr/a?%E0%A4%A=1');
  });
  it('rend telle quelle une adresse invalide', () => {
    expect(canoniserUrl('pas une url')).toBe('pas une url');
  });
});

describe('classerLiens', () => {
  const reco = (...liens: [string, string][]): Json => ({ links: liens.map(([label, url]) => ({ label, url })) });
  const steam = 'https://store.steampowered.com/app/1/';
  const site = 'https://exemple.fr/';

  it('jeux identiques : aucun écart', () => {
    expect(classerLiens([reco(['Steam', steam]), reco(['Steam', steam])], new Set())).toEqual({
      brut: 'identiques',
      classe: null,
    });
  });
  it('un jeu contient l’autre : complétion C2', () => {
    expect(classerLiens([reco(['Steam', steam], ['Site', site]), reco(['Steam', steam])], new Set())).toEqual({
      brut: 'inclus',
      classe: 'C2',
    });
  });
  it('jeux complémentaires : C2', () => {
    expect(classerLiens([reco(['Steam', steam]), reco(['Site', site])], new Set())).toEqual({
      brut: 'complementaires',
      classe: 'C2',
    });
  });
  it('deux écritures d’une même URL : C1', () => {
    expect(
      classerLiens([reco(['Steam', steam]), reco(['Steam', 'https://store.steampowered.com/app/1/Jeu/'])], new Set()),
    ).toEqual({ brut: 'memeLibelleUrlDifferentes', classe: 'C1' });
  });
  it('YouTube : la chaîne enregistrée vaut la poignée de l’œuvre', () => {
    const recos = [
      reco(['Chaîne YouTube', 'https://www.youtube.com/@nardwuar']),
      reco(['Chaîne YouTube', 'https://www.youtube.com/channel/UC1']),
    ];
    expect(classerLiens(recos, new Set(['UC1'])).classe).toBe('C1');
    expect(classerLiens(recos, new Set()).classe).toBe('C3');
  });
  it('YouTube : deux poignées ne se fusionnent pas', () => {
    const recos = [
      reco(['Chaîne YouTube', 'https://www.youtube.com/@a']),
      reco(['Chaîne YouTube', 'https://www.youtube.com/@b'], ['Chaîne YouTube', 'https://www.youtube.com/channel/UC1']),
    ];
    expect(classerLiens(recos, new Set(['UC1'])).classe).toBe('C3');
  });
  it('deux objets différents sous un même libellé : C3', () => {
    expect(
      classerLiens(
        [reco(['Spotify', 'https://open.spotify.com/album/A']), reco(['Spotify', 'https://open.spotify.com/album/B'])],
        new Set(),
      ),
    ).toEqual({ brut: 'memeLibelleUrlDifferentes', classe: 'C3' });
  });
  it('ignore les liens sans URL et range les liens sans libellé ensemble', () => {
    const recos: Json[] = [{ links: [null, 'texte', { label: 'x' }, { url: site }] }, { links: [{ url: site }] }, {}];
    expect(classerLiens(recos, new Set()).brut).toBe('inclus');
    expect(classerLiens([], new Set())).toEqual({ brut: 'identiques', classe: null });
  });
});

describe('analyser — comptes et invariants', () => {
  it('ne signale rien sur un corpus sain', () => {
    const r = analyser(sain());
    expect(r.bloquants).toEqual([]);
    expect(r.avertissements).toEqual([]);
    expect(r.ecarts).toEqual([]);
    expect(r.recosValideesSansEcart).toBe(1);
    expect(r.comptes.recos).toEqual({ fichiers: 1, idsDistincts: 1, doublons: {}, erreurs: [], sansId: [] });
    expect(r.statuts).toEqual({ recos: { validated: 1 }, mentions: { validated: 1 } });
  });

  it('deux ids identiques et une mention orpheline : rapport explicite', () => {
    const c = sain();
    c.recos.push(e('recos/s/1-bis.json', { id: 'ubm-1', status: 'discarded', episodeGuid: 'e1' }));
    c.mentions.push(e('mentions/s/ubm-2.json', { id: 'ubm-2', status: 'discarded', itemId: 'absente', sourceRef: { episodeGuid: 'e1' } }));
    const r = analyser(c);
    expect(regles(r, 'bloquants')).toEqual(['doublon', 'mention-oeuvre-absente']);
    expect(r.comptes.recos.doublons).toEqual({ 'ubm-1': ['recos/s/1-bis.json', 'recos/s/1.json'] });
    expect(r.orphelins.mentionSansOeuvre).toEqual(['ubm-2']);
    expect(r.orphelins.mentionSansReco).toEqual({ discarded: 1 });
  });

  it('signale les fichiers illisibles, sans identifiant, et les redirections illisibles', () => {
    const c = sain();
    c.items.push({ chemin: 'items/s/casse.json', erreur: 'Unexpected token' }, { chemin: 'items/s/x.json' });
    c.episodes.push(e('episodes/s/sans.json', { title: 'sans guid' }));
    c.erreurRedirections = 'Unexpected end of JSON input';
    const r = analyser(c);
    expect(regles(r, 'bloquants')).toEqual(['lecture', 'lecture', 'sans-id']);
    expect(r.comptes.items.erreurs).toEqual([
      { chemin: 'items/s/casse.json', erreur: 'Unexpected token' },
      { chemin: 'items/s/x.json', erreur: 'illisible' },
    ]);
  });

  it('signale les épisodes absents', () => {
    const c = sain();
    c.mentions.push(e('mentions/s/ubm-3.json', { id: 'ubm-3', status: 'discarded', itemId: 'i1' }));
    c.recos.push(e('recos/s/3.json', { id: 'ubm-3', status: 'discarded', episodeGuid: 'inconnu' }));
    const r = analyser(c);
    expect(regles(r, 'bloquants')).toEqual(['mention-episode-absent', 'reco-episode-absent']);
  });

  it('avertit pour une reco validée sans mention, une œuvre sans mention et un écart de statut', () => {
    const c = sain();
    c.recos.push(e('recos/s/4.json', { id: 'ubm-4', status: 'validated', episodeGuid: 'e1' }));
    c.items.push(e('items/s/i2.json', { id: 'i2', title: 'Seule', types: ['livre'] }));
    c.recos.push(e('recos/s/5.json', { id: 'ubm-5', status: 'discarded', episodeGuid: 'e1' }));
    c.mentions.push(e('mentions/s/ubm-5.json', { id: 'ubm-5', status: 'validated', itemId: 'i1', sourceRef: { episodeGuid: 'e1' } }));
    const r = analyser(c);
    expect(regles(r, 'avertissements')).toEqual(['ecart-statut', 'oeuvre-sans-mention', 'reco-validee-sans-mention']);
    expect(r.orphelins.recoSansMention).toEqual({ validated: 1 });
  });

  it('bloque une mention en brouillon, statut absent compris', () => {
    const c = sain();
    c.recos.push(e('recos/s/6.json', { id: 'ubm-6', status: 'draft', episodeGuid: 'e1' }));
    c.mentions.push(e('mentions/s/ubm-6.json', { id: 'ubm-6', itemId: 'i1', sourceRef: { episodeGuid: 'e1' } }));
    const r = analyser(c);
    expect(r.bloquants.find((v) => v.regle === 'brouillon-public')?.ids).toEqual(['ubm-6']);
    expect(r.statuts.recos).toEqual({ validated: 1, draft: 1 });
  });

  it('bloque un recommendedBy sur une œuvre, sauf vide', () => {
    const c = sain();
    c.items.push(
      e('items/s/i3.json', { id: 'i3', title: 'A', types: ['film'], recommendedBy: 'Navo' }),
      e('items/s/i4.json', { id: 'i4', title: 'B', types: ['film'], recommendedBy: null }),
    );
    expect(analyser(c).bloquants.find((v) => v.regle === 'recommendedBy-sur-oeuvre')?.ids).toEqual(['i3']);
  });

  it('vérifie les redirections', () => {
    const c = sain();
    c.items.push(
      e('items/s/vivante.json', { id: 'vivante', title: 'V', types: ['film'] }),
      e('items/s/vide.json', { id: 'vide', title: 'S', types: ['film'] }),
    );
    c.mentions.push(e('mentions/s/ubm-7.json', { id: 'ubm-7', status: 'discarded', itemId: 'vivante', sourceRef: { episodeGuid: 'e1' } }));
    c.redirections = {
      '/s/oeuvre/i1': '/s/oeuvre/vide',
      '/s/oeuvre/vivante': '/s/oeuvre/absente',
      '/s/oeuvre/vieux': '/s/oeuvre/i1',
      '/s/autre/x': '/s/oeuvre/i1',
      '/s/oeuvre/y': 42,
    };
    const r = analyser(c);
    expect(regles(r, 'bloquants')).toEqual(['redirection-chaine', 'redirection-format', 'redirection-source-vivante-avec-page']);
    expect(r.bloquants.find((v) => v.regle === 'redirection-source-vivante-avec-page')?.ids).toEqual(['i1']);
    expect(r.bloquants.find((v) => v.regle === 'redirection-chaine')?.ids).toEqual(['vieux']);
    expect(regles(r, 'avertissements')).toEqual([
      'oeuvre-sans-mention',
      'redirection-cible-absente',
      'redirection-cible-sans-page',
      'redirection-source-vivante-sans-page',
    ]);
  });
});

describe('analyser — écarts', () => {
  function avec(reco: Json, mention: Json = {}, item: Json = {}): ReturnType<typeof analyser> {
    const c = sain();
    const r0 = c.recos[0]?.donnees as Json;
    const m0 = c.mentions[0]?.donnees as Json;
    const i0 = c.items[0]?.donnees as Json;
    c.recos = [e('recos/s/1.json', { ...r0, ...reco })];
    c.mentions = [e('mentions/s/ubm-1.json', { ...m0, ...mention })];
    c.items = [e('items/s/i1.json', { ...i0, ...item })];
    return analyser(c);
  }

  it('classe les champs de l’œuvre', () => {
    expect(ecartsDe(avec({ title: 'titre' }))).toEqual(['ubm-1 title C3']);
    expect(ecartsDe(avec({ creator: '' }))).toEqual(['ubm-1 creator C2']);
    expect(ecartsDe(avec({ year: 2001 }))).toEqual(['ubm-1 year C2']);
    expect(ecartsDe(avec({ types: ['serie', 'film'] }, {}, { types: ['film', 'serie'] }))).toEqual([]);
    expect(ecartsDe(avec({ types: ['serie'] }))).toEqual(['ubm-1 types C3']);
  });

  it('classe les champs de la mention', () => {
    expect(ecartsDe(avec({ recommendedBy: 'Navo' }))).toEqual(['ubm-1 recommendedBy C2']);
    expect(ecartsDe(avec({ quote: 'a' }, { quote: 'b' }))).toEqual(['ubm-1 quote C3']);
    expect(ecartsDe(avec({ timestamp: '00:01:00' }, { sourceRef: { episodeGuid: 'e1', timestamp: '00:01:00' } }))).toEqual([]);
    expect(ecartsDe(avec({}, { kind: 'reco' }))).toEqual([]);
    expect(ecartsDe(avec({ kind: 'citation' }))).toEqual(['ubm-1 kind C3']);
  });

  it('guestWork : absent vaut faux', () => {
    expect(ecartsDe(avec({ guestWork: true }))).toEqual(['ubm-1 guestWork C3']);
    expect(ecartsDe(avec({ guestWork: false }))).toEqual([]);
    expect(avec({ guestWork: true }).recosValideesSansEcart).toBe(0);
  });

  it('alias de la reco absents de l’œuvre : C2', () => {
    expect(ecartsDe(avec({ aliases: ['A'] }, {}, { aliases: ['B'] }))).toEqual(['ubm-1 aliases C2']);
    expect(ecartsDe(avec({ aliases: ['A'] }, {}, { aliases: ['A'] }))).toEqual([]);
  });

  it('externalIds : par clé, tmdb en texte ou en nombre, watchPage équivalente', () => {
    const tmdb = 'https://www.themoviedb.org/tv/1-nom/watch';
    const r = avec(
      { externalIds: { tmdb: '12', watchPage: tmdb, isbn: '978', instagram: 'a' } },
      {},
      { externalIds: { tmdb: 12, watchPage: 'https://www.themoviedb.org/tv/1/watch', instagram: 'b', tiktok: 't' } },
    );
    expect(ecartsDe(r)).toEqual([
      'ubm-1 externalIds.instagram C3',
      'ubm-1 externalIds.isbn C2',
      'ubm-1 externalIds.tiktok C2',
      'ubm-1 externalIds.watchPage C1',
    ]);
    expect(ecartsDe(avec({ externalIds: { watchPage: tmdb } }, {}, { externalIds: { watchPage: 'https://x.fr/' } }))).toEqual([
      'ubm-1 externalIds.watchPage C3',
    ]);
  });

  it('ignore les recos non validées et celles sans mention', () => {
    const c = sain();
    c.recos.push(
      e('recos/s/8.json', { id: 'ubm-8', status: 'discarded', episodeGuid: 'e1', title: 'autre' }),
      e('recos/s/9.json', { id: 'ubm-9', status: 'validated', episodeGuid: 'e1', title: 'autre' }),
    );
    c.mentions.push(e('mentions/s/ubm-8.json', { id: 'ubm-8', status: 'discarded', itemId: 'i1', sourceRef: { episodeGuid: 'e1' } }));
    expect(analyser(c).ecarts).toEqual([]);
  });

  it('sans œuvre, ne compare que les champs de la mention', () => {
    const c = sain();
    c.mentions = [e('mentions/s/ubm-1.json', { id: 'ubm-1', status: 'validated', itemId: 'absente', sourceRef: { episodeGuid: 'e1' }, quote: 'q' })];
    const r = analyser(c);
    expect(ecartsDe(r)).toEqual(['ubm-1 quote C2']);
    c.mentions = [e('mentions/s/ubm-1.json', { id: 'ubm-1', status: 'validated', sourceRef: { episodeGuid: 'e1' } })];
    const sansItemId = analyser(c);
    expect(sansItemId.ecarts).toEqual([]);
    expect(sansItemId.bloquants.find((v) => v.regle === 'mention-oeuvre-absente')?.ids).toEqual(['ubm-1']);
  });

  it('liens identiques entre plusieurs recos : aucun écart, œuvres triées', () => {
    const lien = [{ label: 'Site', url: 'https://exemple.fr/' }];
    const c = sain();
    c.items.push(e('items/s/i0.json', { id: 'i0', title: 'Titre', creator: 'Auteur', types: ['film'] }));
    c.recos = ['ubm-1', 'ubm-2', 'ubm-3', 'ubm-4'].map((id) =>
      e(`recos/s/${id}.json`, { id, status: 'validated', episodeGuid: 'e1', title: 'Titre', creator: 'Auteur', types: ['film'], links: lien }),
    );
    c.mentions = ['ubm-1', 'ubm-2', 'ubm-3', 'ubm-4'].map((id, k) =>
      e(`mentions/s/${id}.json`, { id, status: 'validated', itemId: k < 2 ? 'i1' : 'i0', sourceRef: { episodeGuid: 'e1' } }),
    );
    const r = analyser(c);
    expect(r.liens).toEqual({ oeuvresMultiRecos: 2, identiques: 2, inclus: 0, complementaires: 0, memeLibelleUrlDifferentes: 0 });
    expect(r.ecarts).toEqual([]);
  });

  it('liens des œuvres citées par plusieurs recos', () => {
    const c = sain();
    c.recos = [
      e('recos/s/1.json', { ...(c.recos[0]?.donnees as Json), links: [{ label: 'Steam', url: 'https://store.steampowered.com/app/1/' }] }),
      e('recos/s/2.json', {
        id: 'ubm-2', status: 'validated', episodeGuid: 'e1', title: 'Titre', creator: 'Auteur', types: ['film'],
        links: [{ label: 'Steam', url: 'https://store.steampowered.com/app/1/' }, { label: 'Site', url: 'https://exemple.fr/' }],
        externalIds: { youtubeChannelId: 'UC1' },
      }),
    ];
    c.mentions.push(e('mentions/s/ubm-2.json', { id: 'ubm-2', status: 'validated', itemId: 'i1', sourceRef: { episodeGuid: 'e1' } }));
    const r = analyser(c);
    expect(r.liens).toEqual({ oeuvresMultiRecos: 1, identiques: 0, inclus: 1, complementaires: 0, memeLibelleUrlDifferentes: 0 });
    expect(ecartsDe(r)).toEqual(['i1 liens C2', 'ubm-2 externalIds.youtubeChannelId C2']);
    expect(r.resumeEcarts).toEqual({
      'externalIds.youtubeChannelId': { total: 1, C1: 0, C2: 1, C3: 0 },
      liens: { total: 1, C1: 0, C2: 1, C3: 0 },
    });
  });
});

describe('référence datée', () => {
  const a: Ecart = { id: 'ubm-1', champ: 'title', classe: 'C3' };
  const b: Ecart = { id: 'ubm-2', champ: 'year', classe: 'C2' };

  it('cliquet dans les deux sens', () => {
    expect(comparerReference([a], [a])).toEqual({ nouveaux: [], disparus: [] });
    expect(comparerReference([a, b], [a])).toEqual({ nouveaux: [b], disparus: [] });
    expect(comparerReference([a], [a, b])).toEqual({ nouveaux: [], disparus: [b] });
  });

  it('un changement de classe compte comme un nouvel écart et un écart disparu', () => {
    const c2 = { ...a, classe: 'C2' as const };
    expect(comparerReference([c2], [a])).toEqual({ nouveaux: [c2], disparus: [a] });
  });

  it('se relit telle qu’elle s’écrit', () => {
    const avecCommit = { schemaVersion: 1 as const, date: '2026-10-24', commit: '7c2bf3f3', ecarts: [a, b] };
    expect(lireReference(formaterReference(avecCommit))).toEqual(avecCommit);
    const sans = { schemaVersion: 1 as const, date: '2026-10-24', ecarts: [] };
    expect(lireReference(formaterReference(sans))).toEqual(sans);
  });

  it('refuse une référence mal formée', () => {
    expect(() => lireReference('{"schemaVersion":2,"date":"x","ecarts":[]}')).toThrow('référence invalide');
    expect(() => lireReference('[]')).toThrow('référence invalide');
    expect(() => lireReference('{"schemaVersion":1,"date":"x","ecarts":[{"id":"a","champ":"b","classe":"C9"}]}')).toThrow(
      'écart mal formé',
    );
  });
});
