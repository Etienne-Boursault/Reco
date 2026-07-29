/**
 * Tests `MentionsTimeline.astro` — liste chronologique des mentions d'une
 * œuvre sur la page œuvre.
 *
 * Le composant croise trois sources d'incertitude : l'épisode peut manquer
 * (mention orpheline), la date peut manquer, et le timestamp n'est exploitable
 * QUE si le transcript vient de YouTube (politique transcripts : aucun offset
 * entre YouTube et Acast). On couvre chacune de ces branches.
 */
import { describe, it, expect } from 'vitest';
import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import MentionsTimeline from '../../src/components/MentionsTimeline.astro';

async function render(mentions: unknown[]): Promise<string> {
  const container = await AstroContainer.create();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return container.renderToString(MentionsTimeline as any, {
    props: { sourceId: 'ubm', mentions },
  });
}

const episode = (over: Record<string, unknown> = {}) => ({
  guid: 'ep-1',
  number: 12,
  title: 'Épisode douze',
  date: new Date('2026-03-04T00:00:00Z'),
  ...over,
});

const mention = (over: Record<string, unknown> = {}) => ({
  id: 'men-1',
  itemId: 'itm-1',
  sourceRef: { sourceId: 'ubm', episodeGuid: 'ep-1', timestamp: null, transcriptSource: null },
  ...over,
});

const jm = (m: Record<string, unknown> = {}, ep: Record<string, unknown> | null = episode()) => ({
  mention: mention(m),
  episode: ep,
});

describe('MentionsTimeline — liste', () => {
  it('aucune mention → <ol> vide', async () => {
    const html = await render([]);
    expect(html).toMatch(/<ol class="timeline"[^>]*>\s*<\/ol>/);
  });

  it('une mention par <li>', async () => {
    const html = await render([jm(), jm({ id: 'men-2' })]);
    expect(html.match(/class="tl-item/g)?.length).toBe(2);
  });
});

describe('MentionsTimeline — en-tête d’entrée', () => {
  it('épisode connu → lien vers la page épisode avec numéro et titre', async () => {
    const html = await render([jm()]);
    expect(html).toContain('href="/ubm/episode/ep-1"');
    expect(html).toContain('>#12</span>');
    expect(html).toContain('Épisode douze');
  });

  it('épisode sans numéro → pas de pastille de numéro', async () => {
    const html = await render([jm({}, episode({ number: undefined }))]);
    expect(html).not.toContain('tl-epnum');
    expect(html).toContain('Épisode douze');
  });

  it('titre YouTube prioritaire sur le titre du flux', async () => {
    const html = await render([jm({}, episode({ youtubeTitle: 'Titre YouTube' }))]);
    expect(html).toContain('Titre YouTube');
    expect(html).not.toContain('Épisode douze');
  });

  it('mention orpheline (aucun épisode) → libellé « Épisode inconnu » non cliquable', async () => {
    const html = await render([jm({}, null)]);
    expect(html).toContain('tl-eptitle-orphan');
    expect(html).toContain('Épisode inconnu');
    expect(html).not.toContain('href="/ubm/episode/');
  });

  it('date présente → <time datetime> + date longue en français', async () => {
    const html = await render([jm()]);
    expect(html).toContain('datetime="2026-03-04T00:00:00.000Z"');
    expect(html).toContain('4 mars 2026');
  });

  it('épisode sans date → aucun <time>', async () => {
    const html = await render([jm({}, episode({ date: undefined }))]);
    expect(html).not.toContain('<time');
  });

  it('date malformée (non-Date) → attribut conservé, texte de date vide', async () => {
    // Garde de `fmtDate` : une donnée qui n'est pas une vraie `Date` ne doit
    // pas produire de texte hasardeux.
    const fausseDate = { toISOString: () => '2026-03-04' } as unknown as Date;
    const html = await render([jm({}, episode({ date: fausseDate }))]);
    expect(html).toContain('datetime="2026-03-04"');
    expect(html).toMatch(/<time class="tl-date"[^>]*>\s*<\/time>/);
  });

  it('Date invalide (NaN) → texte de date vide', async () => {
    class DateBancale extends Date {
      toISOString(): string {
        return 'invalide';
      }
    }
    const html = await render([jm({}, episode({ date: new DateBancale(NaN) }))]);
    expect(html).toMatch(/<time class="tl-date"[^>]*>\s*<\/time>/);
  });
});

describe('MentionsTimeline — nature de la mention', () => {
  it('reco (défaut) → pas de classe citation, libellé « Recommandée par »', async () => {
    const html = await render([jm({ recommendedBy: 'Kyan' })]);
    expect(html).not.toContain('tl-citation');
    expect(html).toContain('Recommandée par Kyan');
  });

  it('citation → classe tl-citation et libellé « Évoquée par »', async () => {
    const html = await render([jm({ kind: 'citation', recommendedBy: 'Navo' })]);
    expect(html).toContain('tl-citation');
    expect(html).toContain('Évoquée par Navo');
  });

  it('sans recommendedBy → aucune ligne « par … »', async () => {
    const html = await render([jm()]);
    expect(html).not.toContain('tl-by');
  });

  it('œuvre d’invité → badge ⭐ « Leur œuvre »', async () => {
    const html = await render([jm({ guestWork: true })]);
    expect(html).toContain('tl-guestwork');
    expect(html).toContain('⭐');
    expect(html).toContain('Leur œuvre');
  });

  it('guestWork absent ou false → pas de badge', async () => {
    expect(await render([jm()])).not.toContain('tl-guestwork');
    expect(await render([jm({ guestWork: false })])).not.toContain('tl-guestwork');
  });

  it('citation avec quote → bloc blockquote entre guillemets français', async () => {
    const html = await render([jm({ quote: 'Un film magnifique' })]);
    expect(html).toMatch(/<blockquote class="tl-quote"[^>]*>« Un film magnifique »<\/blockquote>/);
  });

  it('sans quote → pas de blockquote', async () => {
    const html = await render([jm()]);
    expect(html).not.toContain('tl-quote');
  });
});

describe('MentionsTimeline — lien YouTube horodaté', () => {
  it('épisode sans URL YouTube → aucun lien horodaté', async () => {
    const html = await render([jm()]);
    expect(html).not.toContain('tl-ts');
  });

  it('URL YouTube + timestamp YouTube → lien profond avec offset', async () => {
    const html = await render([
      jm(
        {
          sourceRef: {
            sourceId: 'ubm',
            episodeGuid: 'ep-1',
            timestamp: '00:02:13',
            transcriptSource: 'youtube',
          },
        },
        episode({ youtubeUrl: 'https://www.youtube.com/watch?v=abc12345678' }),
      ),
    ]);
    expect(html).toContain('t=133s');
    expect(html).toContain('00:02:13');
    expect(html).toContain('data-track="click"');
  });

  it('URL YouTube sans timestamp → lien nu et libellé de repli « YouTube »', async () => {
    const html = await render([
      jm({}, episode({ youtubeUrl: 'https://www.youtube.com/watch?v=abc12345678' })),
    ]);
    expect(html).toContain('tl-ts');
    expect(html).not.toMatch(/[?&]t=\d+s/);
    expect(html).toContain('YouTube');
  });
});

describe('MentionsTimeline — extrait audio inline', () => {
  const YT = 'https://www.youtube.com/watch?v=abc12345678';

  it('transcript YouTube + timestamp > 0 → extrait embarqué', async () => {
    const html = await render([
      jm(
        {
          sourceRef: {
            sourceId: 'ubm',
            episodeGuid: 'ep-1',
            timestamp: '00:02:13',
            transcriptSource: 'youtube',
          },
        },
        episode({ youtubeUrl: YT }),
      ),
    ]);
    expect(html).toContain('tl-audio');
    expect(html).toContain('audio-trigger');
    expect(html).toContain('start=133');
  });

  it('transcript Acast → aucun offset, donc aucun extrait (politique transcripts)', async () => {
    const html = await render([
      jm(
        {
          sourceRef: {
            sourceId: 'ubm',
            episodeGuid: 'ep-1',
            timestamp: '00:02:13',
            transcriptSource: 'acast',
          },
        },
        episode({ youtubeUrl: YT }),
      ),
    ]);
    expect(html).not.toContain('tl-audio');
  });

  it('timestamp à 00:00:00 → pas d’extrait (rien à situer)', async () => {
    const html = await render([
      jm(
        {
          sourceRef: {
            sourceId: 'ubm',
            episodeGuid: 'ep-1',
            timestamp: '00:00:00',
            transcriptSource: 'youtube',
          },
        },
        episode({ youtubeUrl: YT }),
      ),
    ]);
    expect(html).not.toContain('tl-audio');
  });

  it('épisode sans URL YouTube → pas d’extrait même avec un timestamp', async () => {
    const html = await render([
      jm({
        sourceRef: {
          sourceId: 'ubm',
          episodeGuid: 'ep-1',
          timestamp: '00:02:13',
          transcriptSource: 'youtube',
        },
      }),
    ]);
    expect(html).not.toContain('tl-audio');
  });

  it('l’extrait est titré par le titre YouTube de l’épisode quand il existe', async () => {
    const html = await render([
      jm(
        {
          sourceRef: {
            sourceId: 'ubm',
            episodeGuid: 'ep-1',
            timestamp: '00:02:13',
            transcriptSource: 'youtube',
          },
        },
        episode({ youtubeUrl: YT, youtubeTitle: 'Le vrai titre YT' }),
      ),
    ]);
    expect(html).toMatch(/<iframe[^>]*title="Le vrai titre YT"/);
  });

  it('transcript YouTube sans timestamp du tout → aucun extrait', async () => {
    const html = await render([
      jm(
        {
          sourceRef: { sourceId: 'ubm', episodeGuid: 'ep-1', transcriptSource: 'youtube' },
        },
        episode({ youtubeUrl: YT }),
      ),
    ]);
    expect(html).not.toContain('tl-audio');
  });

  it('timestamp illisible → aucun extrait (parseTimecode ne rend rien)', async () => {
    const html = await render([
      jm(
        {
          sourceRef: {
            sourceId: 'ubm',
            episodeGuid: 'ep-1',
            timestamp: 'plus tard dans l’épisode',
            transcriptSource: 'youtube',
          },
        },
        episode({ youtubeUrl: YT }),
      ),
    ]);
    expect(html).not.toContain('tl-audio');
    // Le lien horodaté reste rendu, avec le texte brut du timestamp.
    expect(html).toContain('plus tard dans l’épisode');
  });

  it('mention orpheline horodatée → aucun extrait (pas d’épisode, donc pas d’URL)', async () => {
    const html = await render([
      jm(
        {
          sourceRef: {
            sourceId: 'ubm',
            episodeGuid: null,
            timestamp: '00:02:13',
            transcriptSource: 'youtube',
          },
        },
        null,
      ),
    ]);
    expect(html).not.toContain('tl-audio');
  });
});
