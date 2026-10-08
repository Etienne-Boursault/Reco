/**
 * Cas limites de la page invité (`src/lib/gallery/invite.ts`) et des libellés
 * de fiche (`libelleStatsOeuvre`, `src/lib/og/cartes.ts`) : épisode sans date,
 * mention sans épisode, œuvre sans type, nom de groupe, singuliers et pluriels.
 */
import { describe, expect, it } from 'vitest';

import {
  bibliothequeDeLInvite,
  initiales,
  passagesDeLInvite,
  prenom,
  type MentionInvite,
} from '../../src/lib/gallery/invite';
import { libelleStatsOeuvre } from '../../src/lib/og/cartes';

const mention = (itemId: string, guid: string | null, over: Partial<MentionInvite> = {}): MentionInvite => ({
  itemId,
  recommendedBy: 'Paul Mirabel',
  status: 'validated',
  sourceRef: { episodeGuid: guid },
  ...over,
});

describe('passagesDeLInvite — cas limites', () => {
  it('un épisode sans date passe en tête, une mention sans épisode ne compte pas', () => {
    const passages = passagesDeLInvite(
      'Paul Mirabel',
      [
        { guid: 'e2', title: 'e2', date: new Date('2024-01-01') },
        { guid: 'e1', title: 'e1' },
        { guid: 'e3', title: 'e3', date: new Date('2025-01-01') },
      ],
      [mention('A', 'e2'), mention('B', 'e1'), mention('C', null), mention('D', 'e3', { recommendedBy: null })],
    );
    expect(passages.map((e) => e.guid)).toEqual(['e1', 'e2']);
  });
});

describe('bibliothequeDeLInvite — cas limites', () => {
  it('une œuvre sans type est rangée dans « autre », une mention sans épisode n’en ajoute pas', () => {
    const bib = bibliothequeDeLInvite(
      'Paul Mirabel',
      [{ id: 'Sans type', title: 'Sans type', types: [] }],
      [mention('Sans type', null), mention('Inconnue', 'e1')],
      [{ guid: 'e1', title: 'e1' }],
    );
    expect(bib.recommandations).toEqual([
      { type: 'autre', lignes: [{ oeuvre: { id: 'Sans type', title: 'Sans type', types: [] }, episodes: [] }] },
    ]);
    expect(bib.nbRecommandations).toBe(1);
  });
});

describe('initiales et prénom', () => {
  it('deux lettres au plus, tirets compris', () => {
    expect(initiales('Jean-Pierre Jeunet')).toBe('JP');
    expect(initiales('Orelsan')).toBe('O');
  });

  it('le nom entier pour un groupe ou un nom seul', () => {
    expect(prenom('Kyan Khojandi & Florent Bernard')).toBe('Kyan Khojandi & Florent Bernard');
    expect(prenom('Laurie et Pablo')).toBe('Laurie et Pablo');
    expect(prenom('Orelsan')).toBe('Orelsan');
    expect(prenom('  Paul Mirabel ')).toBe('Paul');
  });
});

describe('libelleStatsOeuvre — singuliers et pluriels', () => {
  it('seulement évoquée, une ou plusieurs fois', () => {
    expect(libelleStatsOeuvre(0, 1)).toBe('Évoquée 1 fois');
    expect(libelleStatsOeuvre(0, 3)).toBe('Évoquée 3 fois');
  });

  it('recommandée une fois, sans évocation ou avec une seule', () => {
    expect(libelleStatsOeuvre(1, 1)).toBe('Recommandée 1 fois');
    expect(libelleStatsOeuvre(1, 2)).toBe('Recommandée 1 fois · évoquée 1 fois');
  });
});
