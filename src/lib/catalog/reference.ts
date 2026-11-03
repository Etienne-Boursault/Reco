/**
 * Référence datée des écarts connus, et cliquet dans les deux sens (ADR 0061).
 */
import type { Classe, Ecart } from './invariants.ts';

const objet = (v: unknown): Record<string, unknown> =>
  v !== null && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : {};

// --- Référence datée et cliquet -------------------------------------------------------

export interface Reference {
  schemaVersion: 1;
  date: string;
  commit?: string;
  ecarts: Ecart[];
}

const cleEcart = (e: Ecart): string => `${e.id}|${e.champ}|${e.classe}`;

/**
 * Cliquet dans les deux sens : un écart absent de la référence est nouveau, un
 * écart de la référence absent du corpus a disparu. Les deux font échouer la
 * vérification, pour que la référence suive le corpus, relue, dans la même PR.
 */
export function comparerReference(ecarts: Ecart[], reference: Ecart[]): { nouveaux: Ecart[]; disparus: Ecart[] } {
  const actuels = new Set(ecarts.map(cleEcart));
  const connus = new Set(reference.map(cleEcart));
  return {
    nouveaux: ecarts.filter((e) => !connus.has(cleEcart(e))),
    disparus: reference.filter((e) => !actuels.has(cleEcart(e))),
  };
}

/** Sérialise une référence : une ligne par écart, pour des diffs lisibles. */
export function formaterReference(ref: Reference): string {
  const lignes = ref.ecarts.map((e) => `    ${JSON.stringify({ id: e.id, champ: e.champ, classe: e.classe })}`);
  const entete = [`  "schemaVersion": 1`, `  "date": ${JSON.stringify(ref.date)}`];
  if (ref.commit !== undefined) entete.push(`  "commit": ${JSON.stringify(ref.commit)}`);
  return `{\n${entete.join(',\n')},\n  "ecarts": [\n${lignes.join(',\n')}\n  ]\n}\n`;
}

/** Lit une référence ; lève une erreur explicite si sa forme est inattendue. */
export function lireReference(texteJson: string): Reference {
  const d = objet(JSON.parse(texteJson));
  if (d.schemaVersion !== 1 || typeof d.date !== 'string' || !Array.isArray(d.ecarts)) {
    throw new Error('référence invalide : schemaVersion 1, date et ecarts attendus');
  }
  const ecarts = d.ecarts.map(objet).map((e) => {
    if (typeof e.id !== 'string' || typeof e.champ !== 'string' || !['C1', 'C2', 'C3'].includes(e.classe as string)) {
      throw new Error(`référence invalide : écart mal formé (${JSON.stringify(e)})`);
    }
    return { id: e.id, champ: e.champ, classe: e.classe as Classe };
  });
  return { schemaVersion: 1, date: d.date, ...(typeof d.commit === 'string' ? { commit: d.commit } : {}), ecarts };
}
