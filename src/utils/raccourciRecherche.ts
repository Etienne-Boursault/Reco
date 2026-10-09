/**
 * raccourciRecherche.ts — le libellé du raccourci clavier de la recherche.
 *
 * POURQUOI CE MODULE EXISTE
 * -------------------------
 * Le bouton de recherche affichait « ⌘ K » à tout le monde. Sous Windows ou
 * Linux, la touche ⌘ n'existe pas : le raccourci annoncé n'était pas celui
 * qui marche — c'est Ctrl+K, que la palette écoute déjà (audit d'interface du
 * 2026-10-07).
 *
 * Le rendu serveur ne connaît pas la plateforme du visiteur : il écrit
 * « Ctrl K », la valeur juste pour la majorité des visiteurs, et le client
 * corrige en « ⌘ K » sur un appareil Apple.
 *
 * Il vit dans `utils/` et non dans le `<script>` du composant pour être
 * testable — un script d'`.astro` ne l'est pas.
 */

/** Ce que l'on lit de `navigator` : le strict nécessaire, pour les tests. */
export interface NavigateurMinimal {
  platform?: string;
  userAgentData?: { platform?: string };
}

/** Libellé rendu par le serveur, avant toute détection. */
export const RACCOURCI_PAR_DEFAUT = 'Ctrl K';

/**
 * Vrai sur macOS et iOS/iPadOS.
 *
 * `userAgentData.platform` est la source moderne (Chromium) ; `platform`,
 * dépréciée mais seule disponible sous Safari et Firefox, sert de repli.
 */
export function estPlateformeApple(nav: NavigateurMinimal | undefined): boolean {
  if (!nav) return false;
  const moderne = nav.userAgentData?.platform;
  if (moderne) return /^(macOS|iOS)$/i.test(moderne);
  return /Mac|iPhone|iPad|iPod/i.test(nav.platform ?? '');
}

/** « ⌘ K » sur Apple, « Ctrl K » partout ailleurs. */
export function libelleRaccourci(nav: NavigateurMinimal | undefined): string {
  return estPlateformeApple(nav) ? '⌘ K' : RACCOURCI_PAR_DEFAUT;
}
