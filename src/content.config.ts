import { defineCollection, reference, z } from 'astro:content';
import { glob } from 'astro/loaders';

/**
 * SCHÉMA DE DONNÉES — le « contrat » du projet.
 *
 * Trois collections, conçues pour être MULTI-SOURCE (plusieurs podcasts) :
 *   - sources  : un podcast (branding, thème, flux RSS…)
 *   - episodes : un épisode rattaché à une source
 *   - recos    : une recommandation rattachée à un épisode
 *
 * Le pipeline de collecte (tools/) DOIT produire des fichiers JSON conformes
 * à ces schémas. Toute évolution se fait ici en priorité (source de vérité).
 * Voir DATA_SCHEMA.md pour la version lisible/humaine.
 */

// --- Types d'œuvres recommandées -------------------------------------------
const recoType = z.enum([
  'film',
  'serie',
  'livre',
  'bd',
  'musique',
  'album',
  'podcast',
  'jeu',
  'spectacle',
  'lieu',
  'artiste',  // personne (humoriste, musicien, journaliste, etc.) → Insta + site
  'video',    // vidéo YT spécifique (chaîne, vidéo virale) → lien YT direct
  'autre',
]);

// --- Identité visuelle d'une source ----------------------------------------
const theme = z.object({
  // Noms de familles de polices (déclarées en CSS via @font-face ou import).
  fontDisplay: z.string().default('Reco Display'),
  fontBody: z.string().default('Reco Body'),
  colors: z.object({
    bg: z.string(),
    surface: z.string(),
    text: z.string(),
    muted: z.string(),
    accent: z.string(),
    accentText: z.string().default('#ffffff'),
  }),
});

// --- SOURCES (podcasts) -----------------------------------------------------
const sources = defineCollection({
  loader: glob({ pattern: '**/*.json', base: './src/content/sources' }),
  schema: z.object({
    id: z.string(), // slug, ex: "un-bon-moment"
    title: z.string(),
    tagline: z.string().optional(),
    hosts: z.array(z.string()).default([]),
    description: z.string().optional(),
    rssUrl: z.string().url().optional(),
    youtubeChannel: z.string().url().optional(),
    website: z.string().url().optional(),
    theme,
  }),
});

// --- EPISODES ---------------------------------------------------------------
const episodes = defineCollection({
  loader: glob({ pattern: '**/*.json', base: './src/content/episodes' }),
  schema: z.object({
    sourceId: reference('sources'),
    guid: z.string(), // identifiant stable issu du RSS
    number: z.number().int().optional(), // numéro d'épisode (saison si dispo)
    season: z.number().int().optional(),
    title: z.string(),
    youtubeTitle: z.string().optional(), // titre de la vidéo YouTube associée
    date: z.coerce.date().optional(),
    audioUrl: z.string().url().optional(),
    youtubeUrl: z.string().url().optional(),
    audioDuration: z.number().int().optional(), // durée de l'audio (secondes)
    youtubeDuration: z.number().int().optional(), // durée de la vidéo YT (secondes)
    description: z.string().optional(),
    guests: z.array(z.string()).default([]),
    // Suivi du pipeline : none = pas de transcription, auto = brute IA,
    // validated = relue par un humain.
    transcriptStatus: z.enum(['none', 'auto', 'validated']).default('none'),
  }),
});

// --- Liens marchands / « éthiques » ----------------------------------------
const link = z.object({
  label: z.string(), // ex: "Place des Libraires"
  url: z.string().url(),
  // streaming = écouter/voir ; buy = acheter ; borrow = emprunter ; info = fiche.
  kind: z.enum(['buy', 'borrow', 'streaming', 'info', 'official', 'social']).default('info'),
  // Marqueur de provenance pour la politique éditoriale.
  ethics: z.enum(['indie', 'neutral', 'avoid']).default('neutral'),
});

// --- RECOS (recommandations) ------------------------------------------------
const recos = defineCollection({
  loader: glob({ pattern: '**/*.json', base: './src/content/recos' }),
  schema: z.object({
    id: z.string(),
    sourceId: reference('sources'),
    episodeGuid: z.string(), // relie à episodes[].guid
    title: z.string(),
    creator: z.string().optional(), // auteur·rice / réalisateur·rice / artiste
    type: recoType,
    year: z.number().int().optional(),
    recommendedBy: z.string().optional(), // Kyan / Navo / invité…
    quote: z.string().optional(), // citation ou contexte dans l'épisode
    timestamp: z.string().optional(), // ex: "01:12:30"
    note: z.string().optional(),
    links: z.array(link).default([]),
    // Identifiants externes utiles au résolveur de liens éthiques.
    externalIds: z
      .object({
        tmdb: z.string().optional(),
        tmdbType: z.enum(['movie', 'tv']).optional(),
        imdb: z.string().optional(),
        isbn: z.string().optional(),
        musicbrainz: z.string().optional(),
        youtube: z.string().optional(),     // vidéo YT précise (id ou URL)
        instagram: z.string().optional(),   // handle Instagram (sans @)
        website: z.string().url().optional(),
        justwatch: z.string().url().optional(), // URL JustWatch EXACTE (via TMDB)
        deezer: z.string().url().optional(),    // URL Deezer EXACTE (track/album/artist)
        spotify: z.string().url().optional(),   // URL Spotify EXACTE (track/album/artist)
      })
      .partial()
      .optional(),
    // Plateformes de streaming pour film/serie (peuplé par enrich_tmdb.py).
    watchProviders: z
      .array(
        z.object({
          label: z.string(),
          url: z.string().url(),
          ethics: z.enum(['indie', 'neutral', 'avoid']).optional(),
        }),
      )
      .optional(),
    // draft = extrait par IA ; validated = relu/confirmé ; discarded = écarté
    // (faux positif, pas une vraie reco). Le site public masque les discarded.
    status: z.enum(['draft', 'validated', 'discarded']).default('draft'),
    // Liste des LLMs qui ont identifié cette reco. Une reco confirmée par
    // plusieurs LLMs (ex. ["openai", "anthropic"]) est un signal de qualité.
    extractors: z.array(z.string()).optional(),
  }),
});

export const collections = { sources, episodes, recos };
