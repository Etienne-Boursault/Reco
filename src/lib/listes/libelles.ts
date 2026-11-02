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
import { nombreDeListesSensCritique, type Genre, type ListeSensCritique, type Listes, type Playlist } from './donnees';

export type Plateforme = 'Spotify' | 'Deezer';

/** « 298 titres », ou les deux nombres quand les plateformes divergent. */
export function libelleTitres(p: Playlist): string {
  const { spotify, deezer } = p.titres;
  if (spotify === deezer) return `${spotify} ${plural(spotify, 'titre')}`;
  return t('listes.titres.ecart', { spotify: `${spotify} ${plural(spotify, 'titre')}`, deezer });
}

/** « 122 œuvres recommandées ». */
export function libelleOeuvresRecommandees(n: number): string {
  return `${n} ${plural(n, 'œuvre recommandée', 'œuvres recommandées')}`;
}

/** « 75 films seulement évoqués », « 1 BD seulement évoquée ». */
export function libelleEvoquees(genre: Genre, n: number): string {
  return `${n} ${t(`listes.evoquees.${genre}.${n >= 2 ? 'many' : 'one'}` as I18nKey)}`;
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

/** « Voir la liste SensCritique : Films recommandés (nouvel onglet) ». */
export function ariaVoirListe(genre: Genre): string {
  return t('listes.a11y.voirListe', { nom: t(`listes.lien.reco.${genre}` as I18nKey) });
}

/** Nom accessible du lien « Aussi : 75 films seulement évoqués ↗ ». */
export function ariaEvoquees(texte: string): string {
  return t('listes.a11y.evoquees', { texte });
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
  const nSc = nombreDeListesSensCritique(listes);
  if (nSc > 0) parts.push(`${nSc} ${plural(nSc, 'liste')} SensCritique`);
  return t('listes.description', { podcast, detail: parts.join(', ') });
}

const NOMBRES: Readonly<Record<number, string>> = { 2: 'Deux', 3: 'Trois', 4: 'Quatre' };

/**
 * La phrase du bandeau d'une page par type, pour la ou les listes qu'elle
 * couvre : les recommandés d'abord, puis les seulement évoqués.
 */
export function phraseBandeau(listes: readonly ListeSensCritique[]): string {
  const livre = listes.find((l) => l.genre === 'livre');
  const bd = listes.find((l) => l.genre === 'bd');
  const reco =
    livre && bd && listes.length === 2
      ? t('listes.bandeau.reco.livresEtBd', { livres: livre.oeuvres.length, bd: bd.oeuvres.length })
      : listes.map((l) => t(`listes.bandeau.reco.${l.genre}` as I18nKey, { n: l.oeuvres.length })).join(' et ');
  const evoquees = listes.flatMap((l) => (l.evoquees ? [libelleEvoquees(l.genre, l.evoquees.oeuvres.length)] : []));
  const nombre = listes.length + evoquees.length;
  const contenu = evoquees.length > 0 ? `${reco}, et ${evoquees.join(' et ')}` : reco;
  if (nombre === 1) return t('listes.bandeau.une', { contenu });
  return t('listes.bandeau.plusieurs', { nombre: NOMBRES[nombre] ?? String(nombre), contenu });
}

export interface LienListe {
  url: string;
  libelle: string;
  aria: string;
}

/**
 * Les boutons du bandeau. Une seule liste : « Voir la liste ». Plusieurs :
 * chacune nommée (« Films recommandés », « Films évoqués »).
 */
export function liensBandeau(listes: readonly ListeSensCritique[]): LienListe[] {
  const liens = [
    ...listes.map((l) => ({ url: l.url, cle: `listes.lien.reco.${l.genre}`, genre: l.genre })),
    ...listes.flatMap((l) => (l.evoquees ? [{ url: l.evoquees.url, cle: `listes.lien.evoquees.${l.genre}`, genre: l.genre }] : [])),
  ];
  if (liens.length === 1) return [{ url: liens[0].url, libelle: t('listes.sc.voir'), aria: ariaVoirListe(liens[0].genre) }];
  return liens.map((l) => {
    const libelle = t(l.cle as I18nKey);
    return { url: l.url, libelle, aria: t('listes.a11y.liste', { nom: libelle }) };
  });
}
