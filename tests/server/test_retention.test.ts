/**
 * Tests de `src/server/retention.mjs` — les durées promises par
 * /mentions-legales. Une promesse de suppression qui ne supprime rien est pire
 * que pas de promesse : ces tests vérifient sur de vrais fichiers.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import {
  anonymiserSignalements, borne, planifierRetention, purgerMesures,
} from '../../src/server/retention.mjs';

const MAINTENANT = new Date('2026-10-22T12:00:00Z');
let racine: string;

beforeEach(() => { racine = mkdtempSync(path.join(tmpdir(), 'reco-retention-')); });
afterEach(() => rmSync(racine, { recursive: true, force: true }));

function fichier(...morceaux: string[]) {
  const chemin = path.join(racine, 'tools', 'output', ...morceaux);
  mkdirSync(path.dirname(chemin), { recursive: true });
  return chemin;
}

function signalement(id: string, submittedAt: string, submitter: Record<string, unknown>) {
  const chemin = fichier('reports', 'un-bon-moment', `${id}.json`);
  writeFileSync(chemin, JSON.stringify({ id, submittedAt, submitter, details: 'titre faux' }));
  return chemin;
}

describe('borne', () => {
  it('recule du nombre de mois demandé', () => {
    expect(borne(MAINTENANT, 13)).toBe('2025-09-22');
    expect(borne(MAINTENANT, 12)).toBe('2025-10-22');
  });
});

describe('purgerMesures', () => {
  it('supprime visites et clics de plus de 13 mois, garde le reste', () => {
    for (const genre of ['audience', 'clicks']) {
      for (const jour of ['2025-09-21', '2025-09-22', '2026-10-21']) {
        writeFileSync(fichier(genre, 'un-bon-moment', `${jour}.jsonl`), '{}\n');
      }
    }

    expect(purgerMesures(racine, MAINTENANT)).toBe(2);
    for (const genre of ['audience', 'clicks']) {
      expect(readdirSync(path.dirname(fichier(genre, 'un-bon-moment', 'x'))).sort())
        .toEqual(['2025-09-22.jsonl', '2026-10-21.jsonl']);
    }
  });

  it('ne touche pas à un fichier au nom inattendu', () => {
    const autre = fichier('audience', '_site', 'notes.txt');
    writeFileSync(autre, 'x');

    expect(purgerMesures(racine, MAINTENANT)).toBe(0);
    expect(existsSync(autre)).toBe(true);
  });

  it('ne fait rien sans dossier de mesures', () => {
    expect(purgerMesures(racine, MAINTENANT)).toBe(0);
  });
});

describe('anonymiserSignalements', () => {
  it('efface nom et e-mail au-delà de 12 mois, garde le signalement', () => {
    const vieux = signalement('rep-1', '2025-10-01T10:00:00Z', {
      name: 'Camille', email: 'camille@exemple.test', wantCredit: true,
    });
    const recent = signalement('rep-2', '2026-10-01T10:00:00Z', {
      name: 'Dominique', email: 'dominique@exemple.test', wantCredit: false,
    });

    expect(anonymiserSignalements(racine, MAINTENANT)).toBe(1);

    const lu = JSON.parse(readFileSync(vieux, 'utf8'));
    expect(lu.submitter).toEqual({ wantCredit: true });
    expect(lu.details).toBe('titre faux');
    expect(JSON.parse(readFileSync(recent, 'utf8')).submitter.email).toBe('dominique@exemple.test');
  });

  it('ne réécrit pas un signalement déjà anonyme ni un fichier illisible', () => {
    signalement('rep-3', '2024-01-01T10:00:00Z', { wantCredit: false });
    writeFileSync(fichier('reports', 'un-bon-moment', 'rep-4.json'), '{ tronqué');

    expect(anonymiserSignalements(racine, MAINTENANT)).toBe(0);
  });

  it('ignore un signalement sans auteur ou sans date lisible', () => {
    writeFileSync(fichier('reports', 'un-bon-moment', 'rep-5.json'), JSON.stringify({ submittedAt: '2020-01-01' }));
    signalement('rep-6', 20200101 as unknown as string, { email: 'x@exemple.test' });

    expect(anonymiserSignalements(racine, MAINTENANT)).toBe(0);
  });
});

describe('planifierRetention', () => {
  it('passe tout de suite, journalise, et ne retient pas le processus', () => {
    writeFileSync(fichier('audience', 'un-bon-moment', '2020-01-01.jsonl'), '{}\n');
    const journal = { log: vi.fn(), error: vi.fn() };

    const minuteur = planifierRetention(racine, { journal });
    clearInterval(minuteur);

    expect(journal.log).toHaveBeenCalledWith(expect.stringContaining('1 fichier(s) de mesure supprimé(s)'));
    expect(minuteur.hasRef()).toBe(false);
  });

  it('se tait quand il n’y a rien à faire, avec les réglages par défaut', () => {
    const log = vi.spyOn(console, 'log').mockImplementation(() => {});

    clearInterval(planifierRetention(racine));

    expect(log).not.toHaveBeenCalled();
    log.mockRestore();
  });

  it('journalise une erreur sans la propager', () => {
    // Un fichier à la place du dossier `audience` : `readdirSync` échoue.
    mkdirSync(path.join(racine, 'tools', 'output', 'audience', 'un-bon-moment'), { recursive: true });
    writeFileSync(fichier('audience', 'un-bon-moment', '2020-01-01.jsonl', 'x'), '');
    const journal = { log: vi.fn(), error: vi.fn() };

    // `rmSync` sur un dossier sans `recursive` lève : le serveur doit survivre.
    const minuteur = planifierRetention(racine, { journal });
    clearInterval(minuteur);

    expect(journal.error).toHaveBeenCalledWith('[retention] échec :', expect.anything());
  });
});
