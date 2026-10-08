/**
 * src/lib/stats/recit.ts — les phrases des constats de la page /stats.
 *
 * `constats.ts` calcule ; ce module RÉDIGE. Une phrase écrite au build doit
 * rester vraie quand le corpus change : chaque accord suit son nombre
 * (`plural`), une égalité se dit comme telle, et un constat que les données
 * ne permettent plus d'écrire disparaît au lieu d'afficher « 0 » ou une
 * affirmation devenue fausse. Les commentaires d'interprétation de la
 * maquette (« le podcast recommande large ») ne sont gardés que sous la
 * condition qui les rend vrais.
 */
import { plural } from '../../utils/plural';
import { TYPE_LABELS_PLURAL, episodeLabel } from '../../utils/recoTypes';
import { titreEpisodeAffiche } from '../../utils/titreEpisode';
import type { Constats, EpisodeC } from './constats';

export interface BarreRecit {
  label: string;
  valeur: number;
  /** La valeur telle qu'on l'écrit (« 11,1 », « 1 075 »). */
  affiche: string;
  detail?: string;
  /** La barre dont parle le constat, mise en accent (la première par défaut). */
  enAvant?: boolean;
}

export interface ConstatRecit {
  id: string;
  chiffre: string;
  legende: string;
  phrase: string;
  graphique: {
    titre: string;
    barres: BarreRecit[];
    note?: string;
    /** Libellés longs (titres d'épisodes) : au-dessus de la barre, pas à côté. */
    libellesLongs?: boolean;
  };
}

export interface Recit {
  surtitre: string | null;
  titre: string;
  chapeau: string;
  constats: ConstatRecit[];
}

// Séparateur des milliers : espace insécable ORDINAIRE (U+00A0) plutôt que
// l'espace fine (U+202F) que produit `fr-FR`. En Inter, l'espace fine est si
// étroite qu'on lisait « 1075 œuvres » (second audit d'interface du
// 2026-10-07) ; l'insécable garde le nombre d'un seul tenant.
const milliers = (s: string) => s.replace(/\u202f/g, '\u00a0');
const fr = (n: number) => milliers(n.toLocaleString('fr-FR'));
const dec = (n: number) =>
  milliers(n.toLocaleString('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
const mois = (d: Date) =>
  new Intl.DateTimeFormat('fr-FR', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(d);
const memeMois = (a: Date, b: Date) =>
  a.getUTCFullYear() === b.getUTCFullYear() && a.getUTCMonth() === b.getUTCMonth();
const barre = (label: string, valeur: number, detail?: string): BarreRecit =>
  ({ label, valeur, affiche: fr(valeur), detail });

/** « 6 ans et demi », « 1 an », « 8 mois » : la durée entre deux dates. */
export function duree(debut: Date, fin: Date): string {
  const m = (fin.getUTCFullYear() - debut.getUTCFullYear()) * 12 + fin.getUTCMonth() - debut.getUTCMonth();
  const ans = Math.floor(m / 12);
  if (ans < 1) return `${Math.max(m, 1)} mois`;
  return `${ans} ${plural(ans, 'an')}${m % 12 >= 6 ? ' et demi' : ''}`;
}

/** « S5·E7 » s'il existe, puis le titre sans le suffixe qui le répète. */
function nomEpisode(e: EpisodeC, podcasts: ReadonlyMap<string, string>): { label: string; titre: string } {
  return {
    label: episodeLabel({ season: e.season ?? undefined, number: e.number ?? undefined }),
    titre: titreEpisodeAffiche(e.title, podcasts.get(e.sourceId)),
  };
}

/**
 * Rédige le récit d'un jeu de constats. `podcasts` donne le titre de chaque
 * source, pour retirer des titres d'épisode le suffixe « (Un Bon Moment, …) ».
 */
export function rediger(c: Constats, podcasts: ReadonlyMap<string, string>): Recit {
  const out: ConstatRecit[] = [];

  const o = c.oeuvreLaPlusCitee;
  if (o) {
    const periode = o.debut && o.fin
      ? memeMois(o.debut, o.fin) ? ` On en parle en ${mois(o.debut)}.` : ` On en parle de ${mois(o.debut)} à ${mois(o.fin)}.`
      : '';
    const suite = !o.suivante ? ''
      : o.suivante.episodes === o.episodes
        ? ` ${o.suivante.titre} fait jeu égal.`
        : ` ${o.suivante.titre} suit avec ${fr(o.suivante.episodes)} ${plural(o.suivante.episodes, 'épisode')}.`;
    out.push({
      id: 'oeuvre',
      chiffre: fr(o.episodes),
      legende: `${plural(o.episodes, 'épisode')} ${o.episodes >= 2 ? 'citent' : 'cite'} ${o.titre}`,
      phrase: `${o.createur ? `${o.titre}, de ${o.createur}, est l’œuvre qui revient le plus.` : `${o.titre} est l’œuvre qui revient le plus.`}${periode}${suite}`,
      graphique: { titre: 'Œuvres citées dans le plus d’épisodes', barres: o.classement.map((b) => barre(b.label, b.valeur)) },
    });
  }

  const u = c.uneSeuleFois;
  if (u) {
    const part = Math.round((u.une / u.total) * 100);
    out.push({
      id: 'une-fois',
      chiffre: `${part} %`,
      legende: 'des œuvres ne passent qu’une fois',
      phrase: `${fr(u.une)} des ${fr(u.total)} œuvres ${u.une >= 2 ? 'ne sont citées' : 'n’est citée'} que dans une seule mention.`
        + (part >= 50 ? ' Le podcast recommande large plutôt qu’en boucle.' : ''),
      graphique: {
        titre: `${fr(u.total)} ${plural(u.total, 'œuvre')}`,
        barres: [barre('Citées une seule fois', u.une), barre('Citées plusieurs fois', u.plusieurs)],
      },
    });
  }

  const q = c.quiRecommande;
  const tete = q?.hotes[0];
  if (q && tete && tete.n > 0) {
    const autres = q.hotes.slice(1).filter((h) => h.n > 0);
    const signatures = [`${tete.nom} en signe ${fr(tete.n)}`, ...autres.map((h) => `${h.nom} ${fr(h.n)}`)];
    const liste = signatures.length > 1
      ? `${signatures.slice(0, -1).join(', ')} et ${signatures[signatures.length - 1]}` : signatures[0]!;
    const ensemble = q.aPlusieursHotes > 0
      ? `, dont ${fr(q.aPlusieursHotes)} ${q.hotes.length === 2 ? 'à deux' : 'à plusieurs'}` : '';
    const invites = q.invites > 0
      ? ` Les invités en signent ${fr(q.invites)}.` : ' Aucune ne vient d’un invité.';
    // « Il en reste » : une phrase ne commence pas par un chiffre.
    const anonymes = q.sansAttribution > 0
      ? ` Il en reste ${fr(q.sansAttribution)} sans attribution.` : '';
    out.push({
      id: 'qui',
      chiffre: fr(tete.n),
      legende: `${plural(tete.n, 'recommandation')} ${tete.n >= 2 ? 'portent' : 'porte'} le nom de ${tete.nom}`,
      phrase: `Sur ${fr(q.total)} ${plural(q.total, 'recommandation')}, ${liste}${ensemble}.${invites}${anonymes}`,
      graphique: {
        titre: `Qui recommande · ${fr(q.total)} ${plural(q.total, 'recommandation')}`,
        barres: [
          ...q.hotes.map((h) => barre(h.nom, h.n)),
          barre('Invités', q.invites),
          ...(q.sansAttribution > 0 ? [barre('Sans attribution', q.sansAttribution)] : []),
        ],
        note: q.aPlusieursHotes > 0 ? 'Une recommandation faite à plusieurs compte pour chacun.' : undefined,
      },
    });
  }

  const p = c.invitePlusProlixe;
  if (p) {
    const ep = nomEpisode(p.episode, podcasts);
    const dont = p.recommandees === p.oeuvres ? ', toutes recommandées'
      : p.recommandees > 0 ? `, dont ${fr(p.recommandees)} ${plural(p.recommandees, 'recommandée')}` : '';
    const seul = p.egalite.length === 0
      ? ' Aucun autre invité n’en cite autant en un épisode.'
      : ` ${p.egalite[0]} en cite autant.`;
    out.push({
      id: 'invite',
      chiffre: fr(p.oeuvres),
      legende: `${plural(p.oeuvres, 'œuvre citée', 'œuvres citées')} par ${p.nom} en un épisode`,
      phrase: `Dans « ${ep.titre} »${ep.label ? ` (${ep.label})` : ''}, ${p.nom} en cite ${fr(p.oeuvres)}${dont}.${seul}`,
      graphique: {
        titre: 'Épisodes les plus riches en recommandations',
        libellesLongs: true,
        barres: p.plusRiches.map(({ episode, n }) => {
          const e = nomEpisode(episode, podcasts);
          return barre(e.label ? `${e.label} · ${e.titre}` : e.titre, n);
        }),
      },
    });
  }

  if (c.types.length) {
    const [a, b, d] = c.types;
    const total = c.types.reduce((s, t) => s + t.n, 0);
    const nom = (t: string) => (TYPE_LABELS_PLURAL[t] ?? t).toLocaleLowerCase('fr');
    const suite = [b, d].filter(Boolean).map((t) => `${nom(t!.type)} (${fr(t!.n)})`);
    out.push({
      id: 'types',
      chiffre: fr(a!.n),
      legende: b && b.n === a!.n ? `${nom(a!.type)}, à égalité avec les ${nom(b.type)}` : `${nom(a!.type)}, en tête des types`,
      phrase: `Sur ${fr(total)} ${plural(total, 'œuvre')}, chacune comptée pour son type principal`
        + (suite.length ? `, viennent ensuite les ${suite.join(' et les ')}.` : '.'),
      graphique: {
        titre: 'Œuvres par type',
        barres: c.types.slice(0, 8).map((t) => barre(TYPE_LABELS_PLURAL[t.type] ?? t.type, t.n)),
        note: 'Une œuvre compte pour son type principal.',
      },
    });
  }

  // Une année de deux épisodes ferait un « record » sans valeur.
  const annees = c.annees.filter((a) => a.episodes >= 3)
    .map((a) => ({ ...a, moyenne: a.recommandations / a.episodes }));
  const meilleure = [...annees].sort((x, y) => y.moyenne - x.moyenne || y.annee - x.annee)[0];
  if (meilleure) {
    const autres = annees.filter((a) => a.annee !== meilleure.annee).map((a) => a.moyenne);
    const fourchette = autres.length >= 2
      ? ` Les autres années tournent entre ${dec(Math.min(...autres))} et ${dec(Math.max(...autres))}.`
      : autres.length === 1 ? ` L’autre année en compte ${dec(autres[0]!)}.` : '';
    const plusLongue = [...c.annees].sort((x, y) => y.episodes - x.episodes || y.annee - x.annee)[0]!;
    const volume = plusLongue.annee !== meilleure.annee
      ? ` ${plusLongue.annee} compte le plus d’épisodes : ${fr(plusLongue.episodes)}.` : '';
    out.push({
      id: 'annees',
      chiffre: dec(meilleure.moyenne),
      legende: `recommandations par épisode en ${meilleure.annee}`,
      phrase: `${fourchette.trim()}${volume}`.trim() || `${meilleure.annee} est l’année la plus riche.`,
      graphique: {
        titre: 'Recommandations par épisode, par année',
        barres: c.annees.map((a) => ({
          label: String(a.annee),
          valeur: a.episodes ? a.recommandations / a.episodes : 0,
          affiche: a.episodes ? dec(a.recommandations / a.episodes) : '—',
          detail: `${fr(a.episodes)} ép.`,
          enAvant: a.annee === meilleure.annee,
        })),
      },
    });
  }

  const surtitre = c.periode ? `Statistiques · depuis ${mois(c.periode.debut)}` : null;
  const titre = c.periode
    ? `${duree(c.periode.debut, c.periode.fin)} de recos, en ${out.length} ${plural(out.length, 'constat')}`
    : `Les recos, en ${out.length} ${plural(out.length, 'constat')}`;
  const chapeau = `${fr(c.episodes)} ${plural(c.episodes, 'épisode')}, ${fr(c.recommandations)} `
    + `${plural(c.recommandations, 'recommandation')} et ${fr(c.evoquees)} ${plural(c.evoquees, 'œuvre évoquée', 'œuvres évoquées')} : `
    + `${fr(c.oeuvres)} ${plural(c.oeuvres, 'œuvre différente', 'œuvres différentes')} en tout.`;

  return { surtitre, titre, chapeau, constats: out };
}
