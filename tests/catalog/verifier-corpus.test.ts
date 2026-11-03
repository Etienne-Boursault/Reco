import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterAll, describe, expect, it } from 'vitest';

const SCRIPT = fileURLToPath(new URL('../../scripts/verifier-corpus.ts', import.meta.url));
const racines: string[] = [];
afterAll(() => {
  for (const r of racines) rmSync(r, { recursive: true, force: true });
});

/** Un épisode, une œuvre, une reco validée et sa mention ; `titre` décide d'un écart de titre. */
function corpus(titre = 'Titre', extra: Record<string, string> = {}): string {
  const racine = mkdtempSync(join(tmpdir(), 'reco-cli-'));
  racines.push(racine);
  const fichiers: Record<string, string> = {
    'content/episodes/s/e1.json': '{"guid":"e1"}',
    'content/items/s/i1.json': '{"id":"i1","title":"Titre","types":["film"]}',
    'content/recos/s/1.json': JSON.stringify({ id: 'ubm-1', status: 'validated', episodeGuid: 'e1', title: titre, types: ['film'] }),
    'content/mentions/s/ubm-1.json': '{"id":"ubm-1","status":"validated","itemId":"i1","sourceRef":{"episodeGuid":"e1"}}',
    ...extra,
  };
  for (const [chemin, contenu] of Object.entries(fichiers)) {
    mkdirSync(dirname(join(racine, chemin)), { recursive: true });
    writeFileSync(join(racine, chemin), contenu);
  }
  return racine;
}

const lancer = (racine: string, ...args: string[]) =>
  spawnSync(
    process.execPath,
    [SCRIPT, '--contenu', join(racine, 'content'), '--reference', join(racine, 'ref', 'reference.json'), ...args],
    { encoding: 'utf8' },
  );

describe('scripts/verifier-corpus.ts', () => {
  it('écrit la référence, puis répond OK tant que le corpus ne change pas', () => {
    const racine = corpus('Autre titre');
    const ecrit = lancer(racine, '--ecrire-reference', '--commit', 'abc1234');
    expect(ecrit.status).toBe(0);
    const ref = JSON.parse(readFileSync(join(racine, 'ref', 'reference.json'), 'utf8'));
    expect(ref).toMatchObject({ schemaVersion: 1, commit: 'abc1234', ecarts: [{ id: 'ubm-1', champ: 'title', classe: 'C3' }] });
    const r = lancer(racine);
    expect(r.status).toBe(0);
    expect(r.stdout).toContain('Résultat : OK');
  });

  it('échoue sur un écart nouveau, et sur un écart disparu', () => {
    const racine = corpus();
    expect(lancer(racine, '--ecrire-reference').status).toBe(0);
    writeFileSync(
      join(racine, 'content/recos/s/1.json'),
      JSON.stringify({ id: 'ubm-1', status: 'validated', episodeGuid: 'e1', title: 'Changé', types: ['film'] }),
    );
    const nouveau = lancer(racine);
    expect(nouveau.status).toBe(1);
    expect(nouveau.stdout).toContain('+ ubm-1 title C3');

    expect(lancer(racine, '--ecrire-reference').status).toBe(0);
    writeFileSync(
      join(racine, 'content/recos/s/1.json'),
      JSON.stringify({ id: 'ubm-1', status: 'validated', episodeGuid: 'e1', title: 'Titre', types: ['film'] }),
    );
    const disparu = lancer(racine);
    expect(disparu.status).toBe(1);
    expect(disparu.stdout).toContain('- ubm-1 title C3');
  });

  it('deux ids identiques et une mention orpheline : rapport explicite, code non nul', () => {
    const racine = corpus('Titre', {
      'content/recos/s/1-bis.json': '{"id":"ubm-1","status":"discarded","episodeGuid":"e1","title":"x","types":["film"]}',
      'content/mentions/s/ubm-2.json': '{"id":"ubm-2","status":"discarded","itemId":"absente","sourceRef":{"episodeGuid":"e1"}}',
    });
    const r = lancer(racine, '--sans-reference');
    expect(r.status).toBe(1);
    expect(r.stdout).toContain('doublon');
    expect(r.stdout).toContain('mention-oeuvre-absente');
    expect(r.stdout).toContain('Résultat : ÉCHEC');
  });

  it('exige une référence lisible', () => {
    const racine = corpus();
    const absente = lancer(racine);
    expect(absente.status).toBe(1);
    expect(absente.stdout).toContain('référence absente');
    mkdirSync(join(racine, 'ref'), { recursive: true });
    writeFileSync(join(racine, 'ref', 'reference.json'), '{"schemaVersion":2}');
    const invalide = lancer(racine);
    expect(invalide.status).toBe(1);
    expect(invalide.stdout).toContain('référence invalide');
  });

  it('sort le rapport en JSON', () => {
    const r = lancer(corpus(), '--sans-reference', '--json');
    expect(r.status).toBe(0);
    const rapport = JSON.parse(r.stdout);
    expect(rapport.bloquants).toEqual([]);
    expect(rapport.cliquet).toBeNull();
  });

  it('écrire la référence ne masque pas un invariant bloquant', () => {
    const racine = corpus('Titre', { 'content/mentions/s/ubm-3.json': '{"id":"ubm-3","itemId":"i1","sourceRef":{"episodeGuid":"e1"}}' });
    expect(lancer(racine, '--ecrire-reference').status).toBe(1);
    expect(existsSync(join(racine, 'ref', 'reference.json'))).toBe(true);
  });

  it('répond 2 aux erreurs d’usage', () => {
    const racine = corpus();
    expect(lancer(racine, '--inconnue').status).toBe(2);
    expect(lancer(racine, '--commit').status).toBe(2);
    const absent = spawnSync(process.execPath, [SCRIPT, '--contenu', join(racine, 'nulle-part')], { encoding: 'utf8' });
    expect(absent.status).toBe(2);
    expect(absent.stderr).toContain('dossier de contenu introuvable');
  });
});
