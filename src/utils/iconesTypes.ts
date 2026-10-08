/**
 * iconesTypes.ts — une icône au trait par type d'œuvre (tracé SVG 24 × 24).
 *
 * Les cartes de l'onglet « Par type » affichaient les emojis du site. La
 * maquette retenue après l'audit d'interface du 2026-10-07 (variante 4) les
 * remplace par une icône au trait dans la couleur d'accent : un seul détail
 * de couleur par carte, et un dessin qui suit le thème de la source au lieu
 * des couleurs figées d'un emoji.
 *
 * Chaque valeur est l'attribut `d` d'un unique `<path>`, tracé sans
 * remplissage (`fill="none"`, `stroke="currentColor"`).
 */
export const ICONE_TYPE: Record<string, string> = {
  film: 'M4 9h16v10a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z M4 9l1.5-4.5 14 3.6 M8.5 5.6 7.8 9 M13 6.8 12.3 9',
  serie: 'M3 7h18v12H3z M8 3l4 4 4-4',
  video: 'M3 7h12v10H3z M15 10l6-3v10l-6-3',
  chaine: 'M3 6h18v12H3z M10 9.5v5l4.5-2.5z',
  musique: 'M9 18V6l11-2v12 M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0z M20 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z',
  album: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6z',
  podcast: 'M4 15v-3a8 8 0 0 1 16 0v3 M4 15h3v5H4z M17 15h3v5h-3z',
  livre: 'M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z M4 21V5 M19 19v2H6',
  bd: 'M4 5h16v11H9l-5 4z',
  artiste: 'M12 3a3 3 0 0 1 3 3v5a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3z M6 11a6 6 0 0 0 12 0 M12 17v4 M9 21h6',
  spectacle: 'M3 6h18v4a2 2 0 0 0 0 4v4H3v-4a2 2 0 0 0 0-4z M9 6v12',
  jeu: 'M6 8h12a4 4 0 0 1 4 4v1a4 4 0 0 1-7 2.6L14 15h-4l-1 .6A4 4 0 0 1 2 13v-1a4 4 0 0 1 4-4z M7 10.5v3 M5.5 12h3',
  lieu: 'M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z M12 7.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z',
  application: 'M7 3h10v18H7z M11 18h2',
  autre: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z',
};

/** Le tracé du type, ou celui d'« autre » pour un type sans icône. */
export function iconeDuType(type: string | undefined): string {
  return (type && ICONE_TYPE[type]) || ICONE_TYPE.autre!;
}
