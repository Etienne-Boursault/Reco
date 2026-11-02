/**
 * src/lib/listes/libelles.ts — les phrases des listes, accordées et vraies.
 *
 * Les textes vivent dans `src/i18n/fr.ts` ; ce module les assemble avec les
 * nombres lus dans `tools/data/` (cf. `donnees.ts`), pour que la page, la
 * carte de l'accueil, les bandeaux et la ligne d'épisode disent la même chose.
 */
import { t } from '../../i18n';
import type { I18nKey } from '../../i18n/fr';
import { plural } from '../../utils/plural';
import { type Genre, type ListeSensCritique, type Listes, type Playlist } from './donnees';

export type Plateforme = 'Spotify' | 'Deezer';

/** « 298 titres », ou les deux nombres quand les plateformes divergent. */
export function libelleTitres(p: Playlist): string {
  const { spotify, deezer } = p.titres;
  if (spotify === deezer) return `${spotify} ${plural(spotify, 'titre')}`;
  return t('listes.titres.ecart', { spotify: `${spotify} ${plural(spotify, 'titre')}`, deezer });
}

/** « 122 œuvres ». */
export function libelleOeuvres(n: number): string {
  return `${n} ${plural(n, 'œuvre')}`;
}

/** « Films », « Bandes dessinées ». */
export function nomGenre(genre: Genre): string {
  return t(`listes.genre.${genre}` as I18nKey);
}

/** « films », « BD ». */
export function nomGenreCourt(genre: Genre): string {
  return t(`listes.genreCourt.${genre}` as I18nKey);
}

/** Saison abrégée comme le badge d'épisode du site : « S6 ». */
export function saisonCourte(p: Playlist): string {
  return `S${p.saison}`;
}

/** Nom accessible d'un bouton « Spotify ↗ » : il contient le texte visible (WCAG 2.5.3). */
export function ariaEcouter(p: Playlist, plateforme: Plateforme): string {
  return t('listes.a11y.ecouter', { nom: p.nom, plateforme });
}

export function ariaVoirListe(genre: Genre): string {
  return t('listes.a11y.voirListe', { genre: nomGenreCourt(genre) });
}

/** « Films, séries, livres et BD sur SensCritique ». */
export function apercuSensCritique(listes: readonly ListeSensCritique[]): string {
  const genres = new Intl.ListFormat('fr', { type: 'conjunction' }).format(listes.map((l) => nomGenreCourt(l.genre)));
  return t('listes.carte.sc', { genres: genres.charAt(0).toLocaleUpperCase('fr') + genres.slice(1) });
}

/** Méta-description de la page. */
export function descriptionListes(podcast: string, listes: Listes): string {
  const parts: string[] = [];
  if (listes.toutes) parts.push(`${libelleTitres(listes.toutes)} dans « ${listes.toutes.nom} »`);
  if (listes.saisons.length > 0) parts.push(`${listes.saisons.length} ${plural(listes.saisons.length, 'playlist')} de saison`);
  if (listes.senscritique.length > 0) {
    parts.push(`${listes.senscritique.length} ${plural(listes.senscritique.length, 'liste')} SensCritique`);
  }
  return t('listes.description', { podcast, detail: parts.join(', ') });
}

/** La phrase du bandeau d'une page par type, pour la ou les listes qu'elle couvre. */
export function phraseBandeau(listes: readonly ListeSensCritique[]): string {
  const livre = listes.find((l) => l.genre === 'livre');
  const bd = listes.find((l) => l.genre === 'bd');
  if (livre && bd && listes.length === 2) {
    return t('listes.bandeau.livresEtBd', { livres: livre.oeuvres.length, bd: bd.oeuvres.length });
  }
  const [l] = listes;
  return t(`listes.bandeau.${l.genre}` as I18nKey, { n: l.oeuvres.length });
}
