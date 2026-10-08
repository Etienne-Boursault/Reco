/**
 * Gabarit « Étiquette » des cartes de partage (Open Graph, 1200 × 630).
 *
 * Direction B des maquettes de l'audit d'interface du 2026-10-07, retenue :
 * un panneau couleur d'accent à gauche porte UN chiffre géant (recommandations,
 * mentions, œuvres…), le côté sombre porte la rubrique, le titre en Bebas Neue,
 * le contexte et le domaine. Elle reste lisible réduite à ~500 px de large,
 * la taille d'une vignette dans un fil social : un chiffre, un titre, peu
 * d'éléments.
 *
 * Contraintes Satori : flexbox seulement (pas de grid), toute `div` à
 * plusieurs enfants déclare `display: flex`, aucune taille de texte
 * automatique — d'où `tailleTitre`, qui choisit la taille d'après la longueur.
 */

import { siteConfig } from '../../config/site.js';

// Alias de type et NON `interface` : `GetStaticPaths` attend des props
// assignables à `Record<string, any>`, ce qu'une interface ne satisfait pas.
export type EtiquetteInput = {
  /** Discriminant pour le moteur de rendu (cf. `renderer.ts`). */
  gabarit: 'etiquette';
  /** Le chiffre géant du panneau (ex. 903, 14). */
  chiffre: number;
  /** Ce que compte le chiffre (ex. « recommandations »). */
  chiffreLibelle: string;
  /** Précision sous le libellé (ex. « dans 113 épisodes »). */
  chiffreContexte?: string;
  /** Repère au sommet du panneau (ex. « S6·E3 » pour un épisode). */
  repere?: string;
  /** Rubrique en capitales, couleur d'accent (ex. « Série », « Galerie »). */
  rubrique: string;
  /** Tracé SVG 24 × 24 de l'icône de rubrique (cf. `utils/iconesTypes`). */
  icone?: string;
  titre: string;
  /** Ligne principale sous le titre (ex. le créateur). */
  sousTitre?: string;
  /** Ligne secondaire, en retrait (ex. « Recommandée 5 fois »). */
  detail?: string;
  /** Jusqu'à trois titres d'œuvres, en liste à puces. */
  liste?: string[];
  /** Pied réduit au seul domaine (la carte d'accueil porte déjà le nom). */
  piedDomaineSeul?: boolean;
  accent?: string;
  bg?: string;
  fg?: string;
};

const HEX_COLOR_RE = /^#[0-9a-fA-F]{3,8}$/;
const couleur = (c: string | undefined, repli: string) =>
  c && HEX_COLOR_RE.test(c) ? c : repli;

/** Largeur utile du côté sombre : 1200 − 420 (panneau) − 2 × 64 (marges). */
const LARGEUR_TITRE = 652;
/** Largeur utile du panneau : 420 − 2 × 48. */
const LARGEUR_PANNEAU = 324;

/**
 * Chasse moyenne d'une capitale de Bebas Neue, en fraction de la taille.
 * Mesurée sur les cartes rendues (« UNE BONNE » à 170 px : 0,38) et arrondie
 * vers le haut : mieux vaut un titre un cran trop petit qu'un titre coupé net
 * par le bord de la carte.
 */
const CHASSE_CAPITALE = 0.4;
const CHASSE_ESPACE = 0.2;
/** Chasse d'un chiffre de Bebas Neue. */
const CHASSE_CHIFFRE = 0.42;

/** Tailles de titre essayées, de la plus grande à la plus petite. */
const TAILLES_TITRE = [220, 170, 150, 130, 112, 96, 84, 72] as const;
const INTERLIGNE_TITRE = 0.9;

/** Nombre de lignes qu'occupe `texte` en capitales à `taille` px. */
export function lignesTitre(texte: string, taille: number, largeur = LARGEUR_TITRE): number {
  const mots = texte.trim().split(/\s+/).filter(Boolean);
  if (mots.length === 0) return 0;
  const largeurMot = (m: string) => Array.from(m).length * CHASSE_CAPITALE * taille;
  const espace = CHASSE_ESPACE * taille;
  let lignes = 1;
  let courante = 0;
  for (const mot of mots) {
    const l = largeurMot(mot);
    if (courante === 0) {
      // Un mot plus large que la ligne la déborde seul : il compte pour autant
      // de lignes qu'il en remplit (Satori le coupe).
      lignes += Math.max(0, Math.ceil(l / largeur) - 1);
      courante = l % largeur || largeur;
    } else if (courante + espace + l <= largeur) {
      courante += espace + l;
    } else {
      lignes += 1 + Math.max(0, Math.ceil(l / largeur) - 1);
      courante = l % largeur || largeur;
    }
  }
  return lignes;
}

/**
 * La plus grande taille où le titre tient dans `hauteurMax`, et le titre à
 * afficher — raccourci d'un mot à la fois, avec « … », si même la plus petite
 * taille ne suffit pas.
 */
export function tailleTitre(titre: string, hauteurMax: number): { taille: number; texte: string } {
  const tient = (texte: string, taille: number) =>
    lignesTitre(texte, taille) * taille * INTERLIGNE_TITRE <= hauteurMax;
  for (const taille of TAILLES_TITRE) {
    if (tient(titre, taille)) return { taille, texte: titre };
  }
  const plusPetite = TAILLES_TITRE[TAILLES_TITRE.length - 1];
  const mots = titre.trim().split(/\s+/);
  while (mots.length > 1) {
    mots.pop();
    const texte = `${mots.join(' ').replace(/[\s,;:.·–—-]+$/u, '')}…`;
    if (tient(texte, plusPetite)) return { taille: plusPetite, texte };
  }
  return { taille: plusPetite, texte: titre };
}

/**
 * Hauteur occupée par une ligne de texte Inter de `taille` px qui peut passer
 * à la ligne : chasse moyenne ~0,5 em, interligne ~1,2. Sert à réserver la
 * place du sous-titre sous le titre — compté sur UNE ligne, celui de
 * l'accueil en prenait deux et le titre touchait la rubrique.
 */
function hauteurTexte(texte: string | undefined, taille: number): number {
  if (!texte) return 0;
  const parLigne = Math.max(1, Math.floor(LARGEUR_TITRE / (taille * 0.5)));
  return Math.ceil(Array.from(texte).length / parLigne) * taille * 1.2;
}

/**
 * Hauteur laissée au bloc central : 630 − 2 × 64 de marges, − la rubrique
 * (~30), − le pied (~32), − deux respirations de 40 entre les trois blocs.
 * Avec 24, le titre de l'accueil remplissait tout et touchait la rubrique.
 */
const HAUTEUR_CORPS = 630 - 128 - 30 - 32 - 80;

/** Taille du chiffre géant : la plus grande qui tient dans le panneau. */
export function tailleChiffre(chiffre: number, max: number): number {
  const n = String(chiffre).length;
  return Math.min(max, Math.floor(LARGEUR_PANNEAU / (n * CHASSE_CHIFFRE)));
}

const div = (style: Record<string, unknown>, children: unknown) => ({
  type: 'div',
  props: { style: { display: 'flex', ...style }, children },
});

export function etiquetteTemplate(input: EtiquetteInput) {
  const accent = couleur(input.accent, siteConfig.defaultAccent);
  const bg = couleur(input.bg, siteConfig.defaultBg);
  const fg = couleur(input.fg, siteConfig.defaultFg);
  const muted = siteConfig.defaultMuted;
  const liste = (input.liste ?? []).slice(0, 3);

  // Le titre prend ce que lui laisse ce qui l'accompagne : la liste (une
  // ligne de 30 px et 10 de marge par titre), ou le sous-titre et le détail.
  const accompagnement = liste.length > 0
    ? 28 + liste.length * (30 * 1.2 + 10)
    : (input.sousTitre ? 14 + hauteurTexte(input.sousTitre, 40) : 0)
      + (input.detail ? 10 + hauteurTexte(input.detail, 30) : 0);
  const { taille, texte } = tailleTitre(input.titre, HAUTEUR_CORPS - accompagnement);

  const panneau = div(
    {
      width: 420,
      flexShrink: 0,
      padding: '56px 48px',
      background: accent,
      color: bg,
      flexDirection: 'column',
      justifyContent: input.repere ? 'space-between' : 'flex-end',
    },
    [
      input.repere
        ? div({ fontFamily: 'Bebas Neue', fontSize: 120, lineHeight: 0.85, letterSpacing: -1 }, input.repere)
        : null,
      div({ flexDirection: 'column' }, [
        div(
          {
            fontFamily: 'Bebas Neue',
            fontSize: tailleChiffre(input.chiffre, input.repere ? 230 : 300),
            lineHeight: 0.8,
            letterSpacing: -4,
          },
          String(input.chiffre),
        ),
        div({ fontSize: 32, fontWeight: 700, marginTop: 8 }, input.chiffreLibelle),
        input.chiffreContexte ? div({ fontSize: 26, marginTop: 8 }, input.chiffreContexte) : null,
      ].filter(Boolean)),
    ].filter(Boolean),
  );

  const rubrique = div(
    { alignItems: 'center', fontSize: 24, fontWeight: 700, letterSpacing: 4, color: accent, textTransform: 'uppercase' },
    [
      input.icone
        ? {
            type: 'svg',
            props: {
              width: 28,
              height: 28,
              viewBox: '0 0 24 24',
              fill: 'none',
              stroke: accent,
              strokeWidth: 2,
              strokeLinecap: 'round',
              strokeLinejoin: 'round',
              style: { marginRight: 14 },
              children: [{ type: 'path', props: { d: input.icone } }],
            },
          }
        : null,
      { type: 'span', props: { children: input.rubrique } },
    ].filter(Boolean),
  );

  const corps = div({ flexDirection: 'column' }, [
    div(
      {
        fontFamily: 'Bebas Neue',
        fontSize: taille,
        lineHeight: INTERLIGNE_TITRE,
        letterSpacing: taille > 140 ? -2 : -1,
        textTransform: 'uppercase',
        color: fg,
      },
      texte,
    ),
    input.sousTitre ? div({ fontSize: 40, color: fg, marginTop: 14 }, input.sousTitre) : null,
    input.detail ? div({ fontSize: 30, color: muted, marginTop: 10 }, input.detail) : null,
    liste.length > 0
      ? div({ flexDirection: 'column', marginTop: 28 }, liste.map((t) =>
          div({ alignItems: 'center', fontSize: 30, color: fg, marginTop: 10 }, [
            div({ width: 10, height: 10, borderRadius: 5, background: accent, marginRight: 14, flexShrink: 0 }, []),
            { type: 'span', props: { children: t } },
          ]),
        ))
      : null,
  ].filter(Boolean));

  const pied = input.piedDomaineSeul
    ? div({ fontSize: 26, fontWeight: 700, color: fg }, siteConfig.domainLabel)
    : div({ fontSize: 26, fontWeight: 700, color: fg }, [
        // Marge et non espace : Satori supprime l'espace finale d'un `span`,
        // et le domaine se collait au point médian.
        { type: 'span', props: { style: { marginRight: 10 }, children: `${siteConfig.siteName} ·` } },
        { type: 'span', props: { style: { fontWeight: 400, color: muted }, children: siteConfig.domainLabel } },
      ]);

  return div(
    { width: 1200, height: 630, background: bg, color: fg, fontFamily: 'Inter' },
    [
      panneau,
      // Largeur EXPLICITE : avec un simple `flexGrow`, Satori ne contraint pas
      // la colonne et le texte ne passe jamais à la ligne — le titre de
      // l'accueil sortait de la carte. 780 − 2 × 64 = 652, la largeur que
      // suppose `tailleTitre`.
      div(
        { width: 1200 - 420, flexShrink: 0, padding: 64, flexDirection: 'column', justifyContent: 'space-between' },
        [rubrique, corps, pied],
      ),
    ],
  );
}
