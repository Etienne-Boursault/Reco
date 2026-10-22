/**
 * Tests de `src/utils/vignettes.ts`.
 *
 * Les noms doivent rester ceux de `tools/vignettes_episodes.py`, qui écrit les
 * fichiers : `tests/test_vignettes_episodes.py` fixe les mêmes valeurs côté
 * Python. Si l'un change sans l'autre, le site cherche des fichiers absents.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { nomVignette, vignette, youtubeId } from '../../src/utils/vignettes';

const ACAST = 'https://open-images.acast.com/shows/x/y.png?width=640&height=360';

describe('nomVignette', () => {
  it('nomme les deux tailles d’une vidéo YouTube', () => {
    const e = { youtubeUrl: 'https://www.youtube.com/watch?v=dpM43BlLhZI' };
    expect(nomVignette(e, 'mq')).toBe('yt-dpM43BlLhZI-mq.jpg');
    expect(nomVignette(e, 'hq')).toBe('yt-dpM43BlLhZI-hq.jpg');
  });

  it('nomme l’image du flux par l’empreinte de son adresse, extension gardée', () => {
    // Valeur fixée aussi dans le test Python.
    expect(nomVignette({ imageUrl: ACAST }, 'mq')).toBe('ep-f7b805aabc0c.png');
  });

  it('retombe sur .jpg pour une extension inconnue, et rend null sans image', () => {
    expect(nomVignette({ imageUrl: 'https://exemple.test/image' }, 'hq')).toMatch(/^ep-[0-9a-f]{12}\.jpg$/);
    expect(nomVignette({}, 'mq')).toBeNull();
    expect(youtubeId('https://youtu.be/abc')).toBeNull();
  });
});

describe('vignette', () => {
  let racine: string;
  beforeEach(() => { racine = mkdtempSync(path.join(tmpdir(), 'reco-vignettes-')); });
  afterEach(() => rmSync(racine, { recursive: true, force: true }));

  it('rend le chemin public d’un fichier présent', () => {
    mkdirSync(path.join(racine, 'public', 'vignettes'), { recursive: true });
    writeFileSync(path.join(racine, 'public', 'vignettes', 'yt-abc-mq.jpg'), 'x');

    expect(vignette({ youtubeUrl: 'https://www.youtube.com/watch?v=abc' }, 'mq', racine))
      .toBe('/vignettes/yt-abc-mq.jpg');
  });

  it('rend null plutôt que l’adresse d’origine quand le fichier manque', () => {
    expect(vignette({ youtubeUrl: 'https://www.youtube.com/watch?v=abc' }, 'hq', racine)).toBeNull();
    expect(vignette({}, 'hq', racine)).toBeNull();
  });

  it('trouve les vrais fichiers du dépôt par défaut', () => {
    expect(vignette({ youtubeUrl: 'https://www.youtube.com/watch?v=dpM43BlLhZI' }, 'hq'))
      .toBe('/vignettes/yt-dpM43BlLhZI-hq.jpg');
  });
});
