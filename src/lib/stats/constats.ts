/**
 * src/lib/stats/constats.ts — les chiffres des « constats » de la page /stats.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * La page /stats empilait des tuiles chiffrées. La maquette retenue après
 * l'audit d'interface du 2026-10-07 (« un constat par écran ») les raconte :
 * un grand chiffre, une phrase, un graphique. Une phrase ne vaut que si son
 * chiffre est juste ; ils sont donc TOUS calculés ici, au build, avec les
 * mêmes règles que le reste du site :
 *  - une recommandation est une reco PUBLIÉE (`recoPubliee`) qui n'est pas
 *    une citation — le compte de l'accueil ;
 *  - une œuvre est comptée par ses mentions VISIBLES (`status !== 'discarded'`)
 *    et doit exister dans le catalogue — le compte des galeries et des stats.
 *
 * La maquette annonçait 904 recommandations, 1 075 œuvres et 31 œuvres pour
 * Albert Dupontel ; le site, 903, 1 073 et 30. Trois causes, aucune erreur :
 *  - 904 comptait les MENTIONS non citées ; il en existe une sans reco
 *    (ubm-1560, la chaîne de Christophe Pauly). Ici : les recos, comme l'accueil.
 *  - 1 075 venait d'un corpus où les corrections de données du 2026-10-07
 *    étaient déjà fusionnées (deux mentions revalidées). Ici : le corpus du build.
 *  - 30 était le classement par attribution EXACTE ; une mention signée
 *    « Navo & Albert Dupontel » lui échappait. Ici : les noms sont séparés.
 *
 * Fonctions pures, sans I/O : la page leur passe ses collections.
 */
import { recoPubliee } from '../../utils/recoPubliee';
import { computeTypeDistribution, publicMentions } from './aggregator';
import { frSortKey } from './slug';

// --- Entrées (formes minimales) ---------------------------------------------

export interface RecoC {
  id: string;
  sourceId: string;
  episodeGuid: string;
  status?: string;
  kind?: string | null;
  recommendedBy?: string | null;
}

export interface MentionC {
  itemId: string;
  status?: 'draft' | 'validated' | 'discarded';
  sourceRef: { sourceId: string; episodeGuid?: string | null };
}

export interface ItemC {
  id: string;
  title: string;
  types: readonly string[];
  creator?: string | null;
}

export interface EpisodeC {
  guid: string;
  sourceId: string;
  title: string;
  date?: Date | null;
  season?: number | null;
  number?: number | null;
}

export interface SourceC {
  id: string;
  title: string;
  hosts: readonly string[];
}

export interface CorpusC {
  recos: readonly RecoC[];
  mentions: readonly MentionC[];
  items: readonly ItemC[];
  episodes: readonly EpisodeC[];
  sources: readonly SourceC[];
}

// --- Sorties ----------------------------------------------------------------

export interface Barre {
  label: string;
  valeur: number;
  /** Précision affichée sous la barre (ex. « 12 épisodes »). */
  detail?: string;
}

export interface Constats {
  /** Premier et dernier épisode datés : la période couverte. */
  periode: { debut: Date; fin: Date } | null;
  episodes: number;
  recommandations: number;
  evoquees: number;
  oeuvres: number;
  oeuvreLaPlusCitee: {
    titre: string;
    createur: string | null;
    episodes: number;
    debut: Date | null;
    fin: Date | null;
    suivante: { titre: string; episodes: number } | null;
    classement: Barre[];
  } | null;
  uneSeuleFois: { une: number; plusieurs: number; total: number } | null;
  quiRecommande: {
    total: number;
    hotes: { nom: string; n: number }[];
    aPlusieursHotes: number;
    invites: number;
    sansAttribution: number;
  } | null;
  invitePlusProlixe: {
    nom: string;
    oeuvres: number;
    recommandees: number;
    episode: EpisodeC;
    egalite: string[];
    plusRiches: { episode: EpisodeC; n: number }[];
  } | null;
  types: { type: string; n: number }[];
  annees: { annee: number; episodes: number; recommandations: number }[];
}

// --- Outils -----------------------------------------------------------------

/** « Kyan Khojandi & Navo », « A, B et C » → les personnes, normalisées. */
export function personnes(liste: string | null | undefined): string[] {
  return (liste ?? '')
    .split(/\s*(?:&|,|;|\bet\b)\s*/)
    .map((p) => p.trim())
    .filter(Boolean);
}

const cle = (nom: string) => frSortKey(nom.trim());
const parTitre = (a: string, b: string) => (cle(a) < cle(b) ? -1 : cle(a) > cle(b) ? 1 : 0);
const estRecommandation = (r: RecoC) => recoPubliee(r.status) && r.kind !== 'citation';

// --- Calcul -----------------------------------------------------------------

/**
 * Calcule les constats d'un corpus, restreint à une source si `sourceId`.
 * Chaque constat vaut `null` quand les données ne permettent pas de l'écrire.
 */
export function calculerConstats(corpus: CorpusC, sourceId?: string): Constats {
  const dans = <T>(liste: readonly T[], src: (x: T) => string) =>
    sourceId ? liste.filter((x) => src(x) === sourceId) : [...liste];
  const recos = dans(corpus.recos, (r) => r.sourceId).filter((r) => recoPubliee(r.status));
  const mentions = publicMentions(dans(corpus.mentions, (m) => m.sourceRef.sourceId))
    .map((m) => m as MentionC);
  const episodes = dans(corpus.episodes, (e) => e.sourceId);
  const sources = dans(corpus.sources, (s) => s.id);
  const items = corpus.items;
  const itemParId = new Map(items.map((i) => [i.id, i]));
  const episodeParGuid = new Map(episodes.map((e) => [e.guid, e]));

  // Période couverte.
  const dates = episodes.map((e) => e.date).filter((d): d is Date => d instanceof Date)
    .sort((a, b) => a.getTime() - b.getTime());
  const periode = dates.length ? { debut: dates[0]!, fin: dates[dates.length - 1]! } : null;

  // Œuvres visibles, et leurs mentions.
  const mentionsParOeuvre = new Map<string, MentionC[]>();
  for (const m of mentions) {
    if (!itemParId.has(m.itemId)) continue;
    const l = mentionsParOeuvre.get(m.itemId) ?? [];
    l.push(m);
    mentionsParOeuvre.set(m.itemId, l);
  }

  // 1. L'œuvre citée dans le plus d'épisodes.
  const parEpisodes = [...mentionsParOeuvre.entries()].map(([id, ms]) => {
    const guids = new Set(ms.map((m) => m.sourceRef.episodeGuid).filter(Boolean) as string[]);
    const ds = [...guids].map((g) => episodeParGuid.get(g)?.date).filter((d): d is Date => d instanceof Date)
      .sort((a, b) => a.getTime() - b.getTime());
    return { item: itemParId.get(id)!, episodes: guids.size, debut: ds[0] ?? null, fin: ds[ds.length - 1] ?? null };
  }).filter((o) => o.episodes > 0)
    .sort((a, b) => b.episodes - a.episodes || parTitre(a.item.title, b.item.title));
  const premiere = parEpisodes[0];
  const oeuvreLaPlusCitee = premiere ? {
    titre: premiere.item.title,
    createur: premiere.item.creator ?? null,
    episodes: premiere.episodes,
    debut: premiere.debut,
    fin: premiere.fin,
    suivante: parEpisodes[1] ? { titre: parEpisodes[1].item.title, episodes: parEpisodes[1].episodes } : null,
    classement: parEpisodes.slice(0, 5).map((o) => ({ label: o.item.title, valeur: o.episodes })),
  } : null;

  // 2. Les œuvres qui ne passent qu'une fois.
  const total = mentionsParOeuvre.size;
  const une = [...mentionsParOeuvre.values()].filter((ms) => ms.length === 1).length;
  const uneSeuleFois = total ? { une, plusieurs: total - une, total } : null;

  // 3. Qui recommande.
  const recommandations = recos.filter(estRecommandation);
  const hotesDeclares = [...new Map(sources.flatMap((s) => s.hosts).map((h) => [cle(h), h])).values()];
  const hotesCles = new Set(hotesDeclares.map(cle));
  let aPlusieursHotes = 0, invites = 0, sansAttribution = 0;
  const parHote = new Map(hotesDeclares.map((h) => [cle(h), 0]));
  for (const r of recommandations) {
    const qui = personnes(r.recommendedBy);
    if (!qui.length) { sansAttribution += 1; continue; }
    const hotes = qui.filter((p) => hotesCles.has(cle(p)));
    for (const h of new Set(hotes.map(cle))) parHote.set(h, (parHote.get(h) ?? 0) + 1);
    if (new Set(hotes.map(cle)).size >= 2) aPlusieursHotes += 1;
    if (!hotes.length) invites += 1;
  }
  const quiRecommande = hotesDeclares.length && recommandations.length ? {
    total: recommandations.length,
    hotes: hotesDeclares.map((h) => ({ nom: h, n: parHote.get(cle(h)) ?? 0 })).sort((a, b) => b.n - a.n),
    aPlusieursHotes, invites, sansAttribution,
  } : null;

  // 4. L'invité qui a cité le plus d'œuvres en un seul épisode.
  const parInviteEpisode = new Map<string, { nom: string; guid: string; oeuvres: number; recommandees: number }>();
  for (const r of recos) {
    for (const p of new Set(personnes(r.recommendedBy))) {
      if (hotesCles.has(cle(p))) continue;
      const k = `${cle(p)}|${r.episodeGuid}`;
      const cur = parInviteEpisode.get(k) ?? { nom: p, guid: r.episodeGuid, oeuvres: 0, recommandees: 0 };
      cur.oeuvres += 1;
      if (r.kind !== 'citation') cur.recommandees += 1;
      parInviteEpisode.set(k, cur);
    }
  }
  const records = [...parInviteEpisode.values()].filter((x) => episodeParGuid.has(x.guid))
    .sort((a, b) => b.oeuvres - a.oeuvres || parTitre(a.nom, b.nom));
  const record = records[0];
  const recosParEpisode = new Map<string, number>();
  for (const r of recommandations) recosParEpisode.set(r.episodeGuid, (recosParEpisode.get(r.episodeGuid) ?? 0) + 1);
  const invitePlusProlixe = record ? {
    nom: record.nom,
    oeuvres: record.oeuvres,
    recommandees: record.recommandees,
    episode: episodeParGuid.get(record.guid)!,
    egalite: records.slice(1).filter((x) => x.oeuvres === record.oeuvres).map((x) => x.nom),
    plusRiches: [...recosParEpisode.entries()]
      .filter(([g]) => episodeParGuid.has(g))
      .sort((a, b) => b[1] - a[1] || parTitre(episodeParGuid.get(a[0])!.title, episodeParGuid.get(b[0])!.title))
      .slice(0, 5)
      .map(([g, n]) => ({ episode: episodeParGuid.get(g)!, n })),
  } : null;

  // 5. Types d'œuvres : la même répartition que le reste de la page.
  const repartition = computeTypeDistribution(
    items.map((i) => ({ id: i.id, title: i.title, types: i.types })),
    mentions.map((m) => ({ itemId: m.itemId, status: m.status, sourceRef: { sourceId: m.sourceRef.sourceId } })),
  );
  const types = Object.entries(repartition).map(([type, n]) => ({ type, n }));

  // 6. Recommandations par épisode, année par année (date de diffusion).
  const parAnnee = new Map<number, { episodes: number; recommandations: number }>();
  for (const e of episodes) {
    if (!(e.date instanceof Date)) continue;
    const a = e.date.getUTCFullYear();
    const cur = parAnnee.get(a) ?? { episodes: 0, recommandations: 0 };
    cur.episodes += 1;
    cur.recommandations += recosParEpisode.get(e.guid) ?? 0;
    parAnnee.set(a, cur);
  }
  const annees = [...parAnnee.entries()].sort((a, b) => a[0] - b[0])
    .map(([annee, v]) => ({ annee, ...v }));

  return {
    periode,
    episodes: episodes.length,
    recommandations: recommandations.length,
    evoquees: recos.filter((r) => r.kind === 'citation').length,
    oeuvres: total,
    oeuvreLaPlusCitee,
    uneSeuleFois,
    quiRecommande,
    invitePlusProlixe,
    types,
    annees,
  };
}
