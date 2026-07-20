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
    // Slug : minuscules + chiffres + tirets internes (cohérent avec
    // `tools/config/schema.py::_RE_ID`).
    id: z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/),
    title: z.string(),
    tagline: z.string().optional(),
    hosts: z.array(z.string()).default([]),
    description: z.string().optional(),
    rssUrl: z.string().url().optional(),
    youtubeChannel: z.string().url().optional(),
    website: z.string().url().optional(),
    theme,
    // --- Champs lus par le pipeline Python (tools/config) ---
    // Définis ici pour rester compatibles avec la validation Zod d'Astro
    // (SSOT unique : `src/content/sources/<id>.json`).
    // Préfixe reco : alphanumérique minuscule, 2 à 8 chars (cohérent avec
    // `tools/config/schema.py::_RE_PREFIX`).
    recoPrefix: z.string().regex(/^[a-z0-9]{2,8}$/).optional(),
    extractionAnchorPatterns: z.array(z.string()).optional(),
    // Fragments de suffixe entre parenthèses à retirer avant matching YT.
    youtubeTitleSuffixPatterns: z.array(z.string()).optional(),
    // Code hex 6 chars préfixé # (cohérent avec `_RE_HEX_COLOR`).
    siteColorAccent: z.string().regex(/^#[0-9a-fA-F]{6}$/).optional(),
    spotifyShowId: z.string().optional(),
    transcriptDefaultSource: z.enum(['youtube', 'acast']).optional(),
    avoidBrands: z.array(z.string()).optional(),
    enabled: z.boolean().optional(),
    schemaVersion: z.number().int().optional(),
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
    // Snapshot du parsing heuristique du titre (`_parse_guests`) — mémoire
    // pour distinguer « jamais vu » vs « validé silencieusement ». Sert au
    // review_server à proposer un bouton ✕ sur les faux positifs (ex. titres
    // à wordplay français qui produisent « Seb de bon matin »).
    guestsParsed: z.array(z.string()).default([]),
    // Retraits explicites (autorité ultime sur `guests` et `guestsParsed`).
    // Casefold pour la comparaison. Vide par défaut.
    guestsExcluded: z.array(z.string()).default([]),
    // Suivi du pipeline : none = pas de transcription, auto = brute IA,
    // validated = relue par un humain.
    transcriptStatus: z.enum(['none', 'auto', 'validated']).default('none'),
    // Modèle Whisper utilisé : tiny | base | small | medium | large-v3
    // ou suffixe « (assumed) » pour les transcripts antérieurs au champ.
    transcriptModel: z.string().optional(),
    // Flag posé par `tools/audit_yt_acast.py` : le match YT↔Acast a échoué
    // à au moins un check (durée, intro). À investiguer manuellement.
    // Cf. ADR 0013 et ADR 0015 (sidecar pattern).
    matchSuspect: z.boolean().optional(),
    // Détail facultatif (forward-compat — CR senior M8). Le détail
    // canonique vit dans `tools/output/match_audit/<source>/<guid>.json`
    // (sidecar) ; ces champs ne sont QU'un miroir réduit pour les
    // consommateurs Astro qui voudraient l'exposer côté UI sans devoir
    // lire le sidecar. Le pipeline P1.6 NE les peuple PAS par défaut —
    // ils sont définis ici pour ne pas avoir à bump le schema_version
    // le jour où un job d'agrégation les peuplera.
    matchSuspectReasons: z.array(z.object({
      kind: z.string(),
      detail: z.string(),
      // ADR 0019 (option B) : Severity unifié 4 niveaux (info, warning,
      // error, critical). match_audit n'émet que warning/error en
      // pratique, mais le schema accepte les 4 pour forward-compat avec
      // les sidecars enrich_audit/lint qui partagent désormais le même enum.
      severity: z.enum(['info', 'warning', 'error', 'critical']),
    })).optional(),
    matchSuspectAuditedAt: z.string().optional(),
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
    // Relie à episodes[].guid. On garde un `z.string()` plutôt que
    // `reference('episodes')` parce que :
    //  - les recos sont stockées par `id` (ex. `ubm-0001`) alors qu'Astro
    //    indexe les épisodes par leur chemin de fichier (slug). Un
    //    `reference('episodes')` exigerait que les fichiers d'épisodes
    //    soient nommés d'après leur `guid`, ce qui n'est pas le cas
    //    aujourd'hui (les épisodes sont nommés `ep-NNN.json`).
    //  - le pipeline d'extraction peut produire une reco avant que le
    //    fichier d'épisode correspondant ne soit présent (matching YT
    //    asynchrone). Un `reference()` casserait le build dans ce cas.
    //  - les pages joignent les deux collections via un `Map<guid, ep>`,
    //    ce qui reste lisible et performant.
    episodeGuid: z.string(),
    title: z.string(),
    creator: z.string().optional(), // auteur·rice / réalisateur·rice / artiste
    types: z.array(recoType).min(1),
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
    // Override d'URL par plateforme auto-générée. Clé = label exact tel que
    // produit par merchants.ts (ex. "Place des Libraires", "JustWatch"…).
    // Permet de remplacer un lien de recherche par un lien direct sans
    // toucher au reste. Valeur vide = pas d'override (lien auto conservé).
    linkOverrides: z.record(z.string(), z.string().url()).optional(),
    // Liens manuels ajoutés via le review_server (libellé + URL + logo
    // optionnel ; si logoUrl est vide, Astro retombe sur le favicon Google
    // du domaine de l'URL).
    customLinks: z
      .array(
        z.object({
          label: z.string(),
          url: z.string().url(),
          logoUrl: z.string().url().optional(),
        }),
      )
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
    // Audit trail par champ enrichi : { "externalIds.tmdb": "2026-04-15T10:00:00Z",
    // "watchProviders": "2026-04-15T10:00:00Z", ... }. Posé par
    // `tools/refresh_enrichment.py`. Forward-compat — pas de bump schemaVersion.
    // Cf. ADR 0023.
    enrichedAt: z.record(z.string(), z.string()).optional(),
    // draft = extrait par IA ; validated = relu/confirmé ; discarded = écarté
    // (faux positif, pas une vraie reco). Le site public masque les discarded.
    status: z.enum(['draft', 'validated', 'discarded']).default('draft'),
    // Nature de la mention, orthogonale au workflow `status` :
    //   - `reco`     : œuvre RECOMMANDÉE par un·e intervenant·e.
    //   - `citation` : œuvre simplement ÉVOQUÉE / mentionnée (ex. « ils
    //     parlent de Titanic » sans le recommander).
    // Une citation est toujours un `validated` (humain a tranché) avec
    // `kind=citation`. Absent → `reco` (backward-compat).
    kind: z.enum(['reco', 'citation']).default('reco'),
    // Marqueur « œuvre d'invité » : l'œuvre est présentée par un·e invité·e
    // (auto-promo : spectacle, album, livre). Reste `kind=reco` mais on la
    // distingue pour ne pas polluer les vraies recommandations. Orthogonal
    // au workflow `status`. Absent → œuvre normale (backward-compat).
    //
    // L3 — Asymétrie VOULUE avec `mentions.guestWork` (défini plus bas comme
    // `z.boolean().nullable().optional()`). Ici, côté RECO, le champ est
    // `optional()` SANS `nullable()` : le writer de recos ne doit JAMAIS
    // émettre `guestWork: null` (absent = pas une œuvre d'invité, un tri-état
    // n'apporterait rien et casserait la strictness `=== true` en aval, cf.
    // splitRecos/RecoCard N6). Côté MENTION, `nullable()` est toléré parce que
    // les mentions historiques peuvent avoir sérialisé un `null` explicite
    // (miroir du flag reco, forward-compat) — cf. `mentions.guestWork`.
    guestWork: z.boolean().optional(),
    // Liste des LLMs qui ont identifié cette reco. Une reco confirmée par
    // plusieurs LLMs (ex. ["openai", "anthropic"]) est un signal de qualité.
    // Champ DÉRIVÉ depuis `extractionHistory` (sorted unique providers).
    extractors: z.array(z.string()).optional(),
    // Titres alternatifs (orthographes phonétiques absorbées par dédup).
    // Peuplé par `reco_dedup.merge_cluster` lors de la fusion d'un cluster
    // de doublons : chaque membre supprimé voit son titre rejoindre cette
    // liste pour rester traçable et améliorer les futures recherches.
    aliases: z.array(z.string()).optional(),
    // Source du timestamp top-level : "acast" → offset YT au clic ; "youtube"
    // → pas d'offset (le timestamp est déjà calé sur la vidéo). Drapeau
    // calculé via `pick_display_state(extractionHistory)`.
    transcriptSource: z.enum(['acast', 'youtube']).optional(),
    // Historique complet des extractions (1 entrée par tuple
    // transcriptModel × transcriptSource × llmProvider × llmModel).
    // Permet de tracer qui/quand/comment a trouvé cette reco et de
    // comparer la qualité des extracteurs au fil du temps.
    extractionHistory: z
      .array(
        z.object({
          at: z.string(),
          transcriptModel: z.string(),
          transcriptSource: z.enum(['acast', 'youtube']),
          llmProvider: z.enum(['anthropic', 'openai']),
          llmModel: z.string(),
          worker: z.string(),
          timestamp_at_extraction: z.string(),
        }),
      )
      .optional(),
  }),
});

// --- ITEMS (œuvres référencées, nouvelle couche cf. ADR 0001) -------------
// Persistés par `tools/repository/item_repo.py::ItemRepoJson`.
// Convention : clés camelCase, snake_case côté Python (cf. codecs).
// Voir DATA_SCHEMA.md + ADRs 0001-0004 pour le rationale.
const itemExternalIds = z.object({
  tmdb: z.number().int().nullable().optional(),
  tmdbType: z.enum(['movie', 'tv']).nullable().optional(),
  spotify: z.string().nullable().optional(),
  musicbrainz: z.string().nullable().optional(),
  openlibrary: z.string().nullable().optional(),
  isbn: z.string().nullable().optional(),
  justwatch: z.string().nullable().optional(),
});

const itemType = z.enum([
  'livre', 'film', 'serie', 'musique', 'album',
  'artiste', 'podcast', 'jeu', 'bd', 'article',
  'spectacle', 'lieu', 'video',
  'autre',
]);

const items = defineCollection({
  loader: glob({
    pattern: ['**/*.json', '!**/__cross_stack_fixture__/**'],
    base: './src/content/items',
  }),
  schema: z.object({
    id: z.string().regex(/^[a-z0-9-]{1,64}$/),
    types: z.array(itemType).min(1),
    title: z.string().min(1),
    creator: z.string().nullable().optional(),
    year: z.number().int().min(1800).max(2100).nullable().optional(),
    aliases: z.array(z.string()).optional(),
    externalIds: itemExternalIds.optional(),
    customLinks: z.array(z.object({
      label: z.string(),
      url: z.string().url(),
    })).optional(),
    watchProviders: z.array(z.object({
      name: z.string(),
      url: z.string().url(),
      region: z.string().nullable().optional(),
      ethics: z.enum(['indie', 'neutral', 'avoid']).nullable().optional(),
    })).optional(),
    linkOverrides: z.record(z.string(), z.string()).optional(),
    recommendedBy: z.string().nullable().optional(),
    schemaVersion: z.number().int().min(1).default(1),
    // Flag posé par `tools/audit_tmdb.py` (sidecar agrégé). Optionnel,
    // forward-compat — pas de bump schema_version Item. Cf. ADR 0014.
    enrichmentSuspect: z.boolean().optional(),
    // Audit trail par champ enrichi (cf. ADR 0023). Forward-compat,
    // pas de bump schemaVersion. Clé = nom de champ ; valeur = ISO8601.
    enrichedAt: z.record(z.string(), z.string()).optional(),
  }),
});

// --- MENTIONS (occurrences d'items dans des épisodes) ----------------------
const mentions = defineCollection({
  loader: glob({
    pattern: ['**/*.json', '!**/__cross_stack_fixture__/**'],
    base: './src/content/mentions',
  }),
  schema: z.object({
    id: z.string().regex(/^[a-z0-9-]{1,64}$/),
    itemId: z.string().regex(/^[a-z0-9-]{1,64}$/),
    sourceRef: z.object({
      sourceId: z.string(),
      episodeGuid: z.string().nullable().optional(),
      timestamp: z.string().regex(/^\d{2}:\d{2}:\d{2}$/).nullable().optional(),
      transcriptSource: z.enum(['youtube', 'acast']).nullable().optional(),
    }),
    recommendedBy: z.string().nullable().optional(),
    quote: z.string().nullable().optional(),
    kind: z.enum(['reco', 'citation']).default('reco'),
    // Miroir du flag reco `guestWork` (œuvre présentée par un·e invité·e).
    // Optionnel/forward-compat : les mentions historiques n'en ont pas.
    guestWork: z.boolean().nullable().optional(),
    status: z.enum(['draft', 'validated', 'discarded']).default('draft'),
    extractionHistory: z.array(z.object({
      transcriptModel: z.string().nullable(),
      transcriptSource: z.enum(['youtube', 'acast']).nullable(),
      llmProvider: z.string(),
      llmModel: z.string(),
      worker: z.string().nullable(),
      at: z.string(),
      extra: z.record(
        z.string(),
        z.union([z.string(), z.number(), z.boolean()]),
      ).optional(),
    })).optional(),
    extractors: z.array(z.string()).optional(),
    schemaVersion: z.number().int().min(1).default(1),
  }),
});

export const collections = { sources, episodes, recos, items, mentions };
