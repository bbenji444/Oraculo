import { describe, expect, it } from 'vitest';

import type { Article } from '../../services/searches';
import { groupByStory, moreOutletsLabel } from './stories';

function article(id: number, storyId: number | null | undefined): Article {
  return {
    article_id: id,
    title: `Nota ${String(id)}`,
    source_name: null,
    source_domain: null,
    url: 'https://x.mx',
    published_at: null,
    summary: null,
    event_type: null,
    event_date: null,
    extraction_status: 'ok',
    enrichment_status: 'ok',
    concepts: [],
    primary_location: null,
    in_region: null,
    providers: [],
    story_id: storyId,
  };
}

const ids = (articles: Article[]) => articles.map((a) => a.article_id);

describe('una tarjeta por historia', () => {
  it('junta las notas con el mismo story_id donde aparece la primera', () => {
    const groups = groupByStory([article(1, 7), article(2, null), article(3, 7), article(4, 9)]);

    expect(groups.map((g) => [g.lead.article_id, ids(g.others)])).toEqual([
      [1, [3]],
      [2, []],
      [4, []],
    ]);
  });

  it('las notas sin story_id (o de una API anterior) quedan solas', () => {
    const groups = groupByStory([article(1, null), article(2, undefined), article(3, null)]);

    expect(groups.map((g) => g.lead.article_id)).toEqual([1, 2, 3]);
    expect(groups.every((g) => g.others.length === 0)).toBe(true);
  });

  it('sin notas no hay tarjetas', () => {
    expect(groupByStory([])).toEqual([]);
  });
});

describe('texto del chevron', () => {
  it('singular y plural', () => {
    expect(moreOutletsLabel(1)).toBe('+1 medio');
    expect(moreOutletsLabel(4)).toBe('+4 medios');
  });
});
