/**
 * Template OG card — structure JSX-as-object pour Satori.
 *
 * Satori accepte des objets `{ type, props: { children, style, ... } }`
 * équivalents à du JSX React, ce qui évite d'introduire un loader TSX
 * dans la chaîne de build Astro.
 *
 * Format : 1200×630 (Open Graph / Twitter summary_large_image standard).
 *
 * Personnalisation :
 *  - couleurs par défaut → `src/config/site.ts` + `src/lib/theme/tokens.ts`
 *  - branding (siteName, domaine) → `src/config/site.ts`
 *  - un fork ne touche que ces deux fichiers pour rebrander la carte.
 */

import { siteConfig } from '../../config/site.js';

export interface OGTemplateInput {
  /** Titre principal (œuvre, épisode, page…). */
  title: string;
  /** Sous-titre — créateur, source, contexte. */
  subtitle?: string;
  /** Emoji représentant le type (film, livre, musique…). */
  emoji?: string;
  /** Étiquette type ("Film", "Livre"…). */
  typeLabel?: string;
  /** Branding de la source (ex. "Un Bon Moment"), affiché en footer. */
  sourceLabel?: string;
  /** Couleur d'accent (hex). Par défaut : tokens UI. */
  accent?: string;
  /** Couleur de fond (hex). Par défaut : tokens UI. */
  bg?: string;
  /** Couleur de texte principal (hex). */
  fg?: string;
}

const DEFAULTS = {
  accent: siteConfig.defaultAccent,
  bg: siteConfig.defaultBg,
  fg: siteConfig.defaultFg,
  muted: siteConfig.defaultMuted,
} as const;

/**
 * Mapping type d'œuvre → emoji par défaut (cohérent recoType collection).
 * `as const` + `Readonly<...>` empêche toute mutation accidentelle au runtime.
 */
export const TYPE_EMOJI = {
  film: '🎬',
  serie: '📺',
  livre: '📚',
  bd: '💭',
  musique: '🎵',
  album: '💿',
  podcast: '🎙️',
  jeu: '🎮',
  spectacle: '🎭',
  lieu: '📍',
  artiste: '🎨',
  video: '▶️',
  autre: '✨',
} as const satisfies Readonly<Record<string, string>>;

/** Regex hex valide (3/4/6/8 chars, optionnel alpha). Sécurité injection CSS. */
const HEX_COLOR_RE = /^#[0-9a-fA-F]{3,8}$/;

/** Valide une couleur hex, retourne `fallback` si invalide. */
function safeHex(c: string | undefined, fallback: string): string {
  if (!c) return fallback;
  return HEX_COLOR_RE.test(c) ? c : fallback;
}

/**
 * Tronque proprement un titre long (sans couper un mot).
 *
 * - Compte les **code points** (`Array.from`) et pas les unités UTF-16 :
 *   un emoji `🎬` (surrogate pair) compte pour 1 et n'est jamais coupé en
 *   son milieu. Les graphèmes composés (drapeaux ZWJ) restent une
 *   approximation acceptable — `Intl.Segmenter` serait plus exact mais
 *   surdimensionné pour notre besoin (titres < 200 chars).
 * - Détecte tout whitespace (`\s`) au point de coupe, pas uniquement
 *   l'espace ASCII (CR senior M3 : nbsp ` `, espaces fines, etc.).
 */
function truncate(s: string, max: number): string {
  const cps = Array.from(s);
  if (cps.length <= max) return s;
  const slice = cps.slice(0, max).join('');
  // Cherche le dernier whitespace dans la tranche (compatible nbsp, fines).
  const match = slice.match(/^(.*)\s\S*$/u);
  const head = match ? match[1] : slice;
  return head.trimEnd() + '…';
}

/**
 * Construit l'arbre Satori pour la carte OG.
 * Retourne l'objet attendu par `satori(node, options)`.
 */
export function ogTemplate(input: OGTemplateInput) {
  const {
    title,
    subtitle,
    emoji,
    typeLabel,
    sourceLabel = siteConfig.siteName,
  } = input;

  // Validation hex stricte (anti-injection CSS dans le SVG Satori).
  const accent = safeHex(input.accent, DEFAULTS.accent);
  const bg = safeHex(input.bg, DEFAULTS.bg);
  const fg = safeHex(input.fg, DEFAULTS.fg);

  const safeTitle = truncate(title, 90);
  const safeSubtitle = subtitle ? truncate(subtitle, 80) : undefined;
  // Choix de taille basé sur le nombre de code points, pas UTF-16.
  const titleCps = Array.from(safeTitle).length;

  return {
    type: 'div',
    props: {
      style: {
        display: 'flex',
        flexDirection: 'column',
        width: '1200px',
        height: '630px',
        // Gradient subtil : fin légèrement plus claire que `bg` (calculée
        // depuis `bg` pour rester cohérente quand la source override).
        background: `linear-gradient(135deg, ${bg} 0%, ${lighten(bg, 0.06)} 100%)`,
        color: fg,
        padding: '64px',
        fontFamily: 'Inter',
        position: 'relative',
      },
      children: [
        // Bandeau type (emoji + label)
        {
          type: 'div',
          props: {
            style: {
              display: 'flex',
              alignItems: 'center',
              fontSize: 36,
              color: accent,
              marginBottom: 24,
            },
            children: [
              emoji ? { type: 'span', props: { style: { fontSize: 56, marginRight: 16 }, children: emoji } } : null,
              typeLabel ? { type: 'span', props: { style: { textTransform: 'uppercase', letterSpacing: 4 }, children: typeLabel } } : null,
            ].filter(Boolean),
          },
        },
        // Titre principal
        {
          type: 'div',
          props: {
            style: {
              display: 'flex',
              fontSize: titleCps > 50 ? 64 : 80,
              fontWeight: 700,
              lineHeight: 1.1,
              marginTop: 8,
            },
            children: safeTitle,
          },
        },
        // Sous-titre
        safeSubtitle
          ? {
              type: 'div',
              props: {
                style: {
                  display: 'flex',
                  fontSize: 36,
                  color: DEFAULTS.muted,
                  marginTop: 24,
                  fontWeight: 400,
                },
                children: safeSubtitle,
              },
            }
          : null,
        // Footer : barre accent + branding
        {
          type: 'div',
          props: {
            style: {
              display: 'flex',
              position: 'absolute',
              bottom: 64,
              left: 64,
              right: 64,
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: 28,
            },
            children: [
              {
                type: 'div',
                props: {
                  style: { display: 'flex', alignItems: 'center', color: accent, fontWeight: 600 },
                  children: [
                    {
                      type: 'div',
                      props: {
                        style: {
                          display: 'flex',
                          width: 16,
                          height: 16,
                          borderRadius: 8,
                          background: accent,
                          marginRight: 16,
                        },
                      },
                    },
                    { type: 'span', props: { children: sourceLabel } },
                  ],
                },
              },
              {
                type: 'div',
                props: {
                  style: { color: DEFAULTS.muted, fontSize: 24 },
                  children: `${siteConfig.siteName} · ${siteConfig.domainLabel}`,
                },
              },
            ],
          },
        },
      ].filter(Boolean),
    },
  };
}

/**
 * Éclaircit une couleur hex (#rrggbb) d'un facteur 0..1 (mix vers blanc).
 * Tolère les hex 3-chars (#rgb) en les développant. Utilisé pour calculer
 * la fin du gradient à partir de la couleur `bg` de la source (CR senior
 * L10 : éviter le hardcode `#1a1a1f` qui clash avec un theme clair).
 */
function lighten(hex: string, amount: number): string {
  let h = hex.replace('#', '');
  if (h.length === 3) {
    h = h.split('').map((c) => c + c).join('');
  }
  if (h.length !== 6) return hex; // hex 8-chars (#rrggbbaa) : on laisse tel quel
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  const mix = (c: number) => Math.round(c + (255 - c) * amount);
  const toHex = (n: number) => n.toString(16).padStart(2, '0');
  return `#${toHex(mix(r))}${toHex(mix(g))}${toHex(mix(b))}`;
}

// Pour les tests unitaires (helpers internes).
export const __testing = { truncate, safeHex, lighten };
