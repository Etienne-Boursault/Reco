/**
 * Les cartes de partage du site : quelle carte pour quelle page, avec quels
 * chiffres.
 *
 * Retenues après l'audit d'interface du 2026-10-07 (direction B, «
 * Étiquette »). Avant, seuls l'accueil et la source avaient une carte : une
 * œuvre ou un épisode partagés montraient la carte générique ou la vignette
 * YouTube, qui ne dit rien des recommandations.
 *
 * Module PUR, sans `astro:content` : l'endpoint `src/pages/og/[...slug].png.ts`
 * lui passe les collections, et les tests l'appellent directement. Les
 * nombres sortent des MÊMES fonctions que les pages (`splitEpisodeRecos`,
 * `buildWorkIndex`, `selectByType`) : une carte qui annoncerait un autre
 * chiffre que la page qu'elle illustre serait pire que pas de carte.
 */

import { siteConfig } from '../../config/site.js';
import { t } from '../../i18n/index.js';
import { splitEpisodeRecos } from '../episode/splitRecos.js';
import { selectByType, type MentionLike as MentionGalerie } from '../gallery/aggregate.js';
import { GALERIES_PAR_TYPE, PAGES_DEDIEES } from '../gallery/typesGaleries.js';
import { buildWorkIndex, type MentionLike } from '../work/aggregator.js';
import { iconeDuType } from '../../utils/iconesTypes.js';
import { plural } from '../../utils/plural.js';
import { episodeLabel, TYPE_LABELS } from '../../utils/recoTypes.js';
import { recoPubliee } from '../../utils/recoPubliee.js';
import { sortRecosByTimestamp } from '../../utils/recoOrder.js';
import { titreEpisodeAffiche } from '../../utils/titreEpisode.js';
import type { EtiquetteInput } from './etiquette.js';
import { truncate } from './template.js';

export interface SourceCarte {
  id: string;
  title: string;
  tagline?: string;
  accent?: string;
  bg?: string;
}
export interface EpisodeCarte {
  guid: string;
  sourceId: string;
  title: string;
  number?: number;
  season?: number;
}
export interface RecoCarte {
  id: string;
  sourceId: string;
  episodeGuid: string;
  status: string;
  title: string;
  kind?: string;
  guestWork?: boolean;
  timestamp?: string;
}
export interface ItemCarte {
  id: string;
  /** Source du dossier de l'item (`items/<source>/<id>.json`). */
  sourceId: string;
  title: string;
  types: string[];
  creator?: string | null;
}

export interface DonneesCartes {
  sources: SourceCarte[];
  episodes: EpisodeCarte[];
  recos: RecoCarte[];
  items: ItemCarte[];
  mentions: MentionLike[];
}

export interface CarteOG {
  /** Chemin sous `/og/`, sans l'extension `.png`. */
  slug: string;
  carte: EtiquetteInput;
}

/** Une ligne de liste ou un sous-titre ne doit pas déborder du côté sombre. */
const LONGUEUR_LIGNE = 38;

/**
 * Une fiche d'œuvre a-t-elle SA carte ? Dès sa première mention publique,
 * c'est-à-dire toutes les fiches du site.
 *
 * Le seuil a d'abord été de DEUX mentions : une carte par œuvre portait le
 * build de 51 s à 647 s (mesuré le 2026-10-07). L'éditeur a tranché le jour
 * même : « avoir un build long n'est pas un souci ». Le coût ne se paie plus
 * qu'une fois : le cache des cartes survit désormais aux builds (cf.
 * `renderer.ts`), et seules les cartes dont le dessin change sont recalculées.
 *
 * Partagée par l'endpoint et par la page œuvre, pour qu'une page ne réclame
 * jamais une image que le build n'a pas produite.
 */
export const MENTIONS_MIN_CARTE_OEUVRE = 1;
export function oeuvreAUneCarte(mentionCount: number): boolean {
  return mentionCount >= MENTIONS_MIN_CARTE_OEUVRE;
}

/** Libellé « Recommandée 5 fois · évoquée 9 fois » — celui de la fiche œuvre. */
export function libelleStatsOeuvre(recoCount: number, mentionCount: number): string {
  const evocations = mentionCount - recoCount;
  if (recoCount === 0) {
    return mentionCount > 1
      ? t('work.stats.mention.many', { count: mentionCount })
      : t('work.stats.mention.one');
  }
  return [
    recoCount > 1 ? t('work.stats.reco.many', { count: recoCount }) : t('work.stats.reco.one'),
    evocations > 0
      ? evocations > 1
        ? t('work.stats.evoked.many', { count: evocations })
        : t('work.stats.evoked.one')
      : null,
  ].filter(Boolean).join(' · ');
}

const couleurs = (s: SourceCarte) => ({ accent: s.accent, bg: s.bg });

/**
 * Segment de slug sûr : garde uniquement [A-Za-z0-9_-], par identifiant —
 * un « / » dans un guid ne doit pas devenir un dossier.
 *
 * La CASSE EST CONSERVÉE. Ce segment passait en minuscules, mais les pages
 * réclament leur carte avec le guid BRUT : l'épisode `yt-7kh5yi46Xh8`
 * demandait `…/yt-7kh5yi46Xh8.png` quand le build écrivait
 * `…/yt-7kh5yi46xh8.png`. L'écart passait inaperçu tant que ces épisodes, qui
 * ont une vignette YouTube, n'avaient pas de carte ; et Windows, insensible à
 * la casse, l'aurait masqué en local, pas l'hébergeur sous Linux. Seuls les
 * caractères hors URL (aucun identifiant actuel n'en porte) sont remplacés.
 */
export function segmentSur(s: string): string {
  return s.replace(/[^A-Za-z0-9_-]/g, '-').replace(/-+/g, '-');
}

export function cartesDuSite(d: DonneesCartes): CarteOG[] {
  const cartes: CarteOG[] = [];
  const publiees = d.recos.filter((r) => recoPubliee(r.status));
  const recosVraies = publiees.filter((r) => (r.kind ?? 'reco') !== 'citation');
  const monoSource = d.sources.length === 1;

  // 1. Carte de repli (pages sans carte propre) : tout le catalogue.
  cartes.push({
    slug: 'default',
    carte: {
      gabarit: 'etiquette',
      chiffre: recosVraies.length,
      chiffreLibelle: plural(recosVraies.length, 'recommandation'),
      chiffreContexte: monoSource ? `dans ${d.sources[0]!.title}` : undefined,
      rubrique: 'Catalogue',
      titre: siteConfig.siteName,
      // L'accroche en ligne de DÉTAIL (petite, en retrait), comme sur la
      // maquette : en sous-titre blanc de 40 px, elle tassait le titre.
      detail: truncate(siteConfig.baseline, LONGUEUR_LIGNE * 2),
      piedDomaineSeul: true,
    },
  });

  for (const src of d.sources) {
    const recosSrc = publiees.filter((r) => r.sourceId === src.id);
    const vraiesSrc = recosSrc.filter((r) => (r.kind ?? 'reco') !== 'citation');
    const episodesSrc = d.episodes.filter((e) => e.sourceId === src.id);

    // 2. La source — c'est aussi l'accueil d'un déploiement mono-source.
    cartes.push({
      slug: segmentSur(src.id),
      carte: {
        gabarit: 'etiquette',
        chiffre: vraiesSrc.length,
        chiffreLibelle: plural(vraiesSrc.length, 'recommandation'),
        chiffreContexte: `dans ${episodesSrc.length} ${plural(episodesSrc.length, 'épisode')}`,
        rubrique: `Podcast · ${src.title}`,
        titre: monoSource ? siteConfig.siteName : src.title,
        detail: truncate(monoSource ? siteConfig.baseline : src.tagline ?? '', LONGUEUR_LIGNE * 2) || undefined,
        piedDomaineSeul: true,
        ...couleurs(src),
      },
    });

    // 3. Les épisodes qui ont au moins une recommandation. Les autres gardent
    //    leur vignette YouTube : une carte « 0 recommandation » n'aurait rien
    //    à montrer.
    for (const ep of episodesSrc) {
      const recosEp = sortRecosByTimestamp(recosSrc.filter((r) => r.episodeGuid === ep.guid));
      const { spontaneous, guestWorks, citations } = splitEpisodeRecos(recosEp);
      const n = spontaneous.length + guestWorks.length;
      if (n === 0) continue;
      cartes.push({
        slug: `${segmentSur(src.id)}/episode/${segmentSur(ep.guid)}`,
        carte: {
          gabarit: 'etiquette',
          repere: episodeLabel(ep) || undefined,
          chiffre: n,
          chiffreLibelle: plural(n, 'recommandation'),
          chiffreContexte: citations.length > 0
            ? `et ${t(citations.length > 1 ? 'episode.count.citations.many' : 'episode.count.citations.one', { count: citations.length })}`
            : undefined,
          rubrique: `Podcast · ${src.title}`,
          titre: titreEpisodeAffiche(ep.title, src.title),
          liste: [...spontaneous, ...guestWorks].slice(0, 3).map((r) => truncate(r.title, LONGUEUR_LIGNE)),
          ...couleurs(src),
        },
      });
    }

    // 4. Les galeries par type, avec les nombres de leurs pages — qui
    //    retiennent les œuvres MENTIONNÉES par la source, quel que soit leur
    //    dossier (cf. `films.astro`, `[galerie].astro`).
    const mentionsSrc = d.mentions.filter((m) => m.sourceRef.sourceId === src.id);
    const mentionnees = new Set(mentionsSrc.map((m) => m.itemId));
    const itemsMentionnes = d.items.filter((it) => mentionnees.has(it.id));
    for (const g of [...PAGES_DEDIEES, ...GALERIES_PAR_TYPE]) {
      const oeuvres = selectByType(itemsMentionnes, mentionsSrc as MentionGalerie[], g.types);
      if (oeuvres.length === 0) continue;
      cartes.push({
        slug: `${segmentSur(src.id)}/galerie/${g.slug}`,
        carte: {
          gabarit: 'etiquette',
          chiffre: oeuvres.length,
          chiffreLibelle: oeuvres.length > 1 ? g.plusieurs : g.unGe,
          chiffreContexte: `dans ${src.title}`,
          rubrique: 'Galerie',
          icone: iconeDuType(g.types[0]),
          titre: g.titre,
          liste: oeuvres.slice(0, 3).map((o) => truncate(o.title, LONGUEUR_LIGNE)),
          ...couleurs(src),
        },
      });
    }

    // 5. Les fiches d'œuvre assez citées (cf. `oeuvreAUneCarte`) — sur les
    //    items du DOSSIER de la source, comme la page œuvre.
    const itemsSrc = d.items.filter((it) => it.sourceId === src.id);
    const index = buildWorkIndex({
      sourceId: src.id,
      items: itemsSrc.map((it) => ({ ...it, types: [...it.types] })),
      mentions: mentionsSrc,
      episodes: episodesSrc,
    });
    for (const [itemId, work] of index) {
      if (!oeuvreAUneCarte(work.mentionCount)) continue;
      const type = work.item.types[0];
      cartes.push({
        slug: `${segmentSur(src.id)}/oeuvre/${segmentSur(itemId)}`,
        carte: {
          gabarit: 'etiquette',
          chiffre: work.mentionCount,
          chiffreLibelle: plural(work.mentionCount, 'mention'),
          chiffreContexte: `dans ${src.title}`,
          rubrique: (type && TYPE_LABELS[type]) || 'Œuvre',
          icone: iconeDuType(type),
          titre: work.item.title,
          sousTitre: work.item.creator ? truncate(work.item.creator, LONGUEUR_LIGNE) : undefined,
          detail: libelleStatsOeuvre(work.recoCount, work.mentionCount),
          ...couleurs(src),
        },
      });
    }
  }
  return cartes;
}
