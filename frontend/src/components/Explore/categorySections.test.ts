import { describe, expect, it } from 'vitest';

import type { Article, ArticleCategory } from '../../services/searches';
import { NO_CATEGORY_COLOR } from './categoryColor';
import { UNCLASSIFIED_KEY, containsArticle, sectionsByCategory } from './categorySections';
import type { StoryGroup } from './stories';

const HUACHICOL: ArticleCategory = { id: 7, name: 'Huachicol', color: '#A3E635', symbol: null };
const HOMICIDIO: ArticleCategory = { id: 5, name: 'Homicidio', color: '#FF4D6D', symbol: null };
const ARMAS: ArticleCategory = { id: 6, name: 'Armas y explosivos', color: null, symbol: null };

function note(id: number, category: ArticleCategory | null): Article {
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
    category,
  };
}

function card(lead: Article, ...others: Article[]): StoryGroup {
  return { lead, others };
}

describe('sectionsByCategory', () => {
  it('junta las tarjetas por categoría y cuenta las notas de cada historia', () => {
    const sections = sectionsByCategory([
      card(note(1, HOMICIDIO)),
      card(note(2, HUACHICOL), note(3, HUACHICOL), note(4, HUACHICOL)),
      card(note(5, HOMICIDIO)),
    ]);

    expect(sections.map((s) => [s.name, s.count, s.groups.length])).toEqual([
      ['Huachicol', 3, 1],
      ['Homicidio', 2, 2],
    ]);
    expect(sections[1]?.groups.map((g) => g.lead.article_id)).toEqual([1, 5]);
  });

  it('una historia va en la sección de su primera nota', () => {
    const [only] = sectionsByCategory([card(note(1, HUACHICOL), note(2, HOMICIDIO))]);

    expect([only?.name, only?.count]).toEqual(['Huachicol', 2]);
  });

  it('«Sin clasificar» va al final aunque tenga más notas; empates por nombre', () => {
    const sections = sectionsByCategory([
      card(note(1, null)),
      card(note(2, null)),
      card(note(3, HOMICIDIO)),
      card(note(4, ARMAS)),
    ]);

    expect(sections.map((s) => s.key)).toEqual(['6', '5', UNCLASSIFIED_KEY]);
    expect(sections.at(-1)?.name).toBe('Sin clasificar');
  });

  it('sin color usa el gris de lo que no tiene categoría', () => {
    const colors = sectionsByCategory([card(note(1, ARMAS)), card(note(2, null))]).map(
      (s) => s.color,
    );

    expect(colors).toEqual([NO_CATEGORY_COLOR, NO_CATEGORY_COLOR]);
  });
});

describe('containsArticle', () => {
  const [section] = sectionsByCategory([card(note(1, HUACHICOL), note(2, HUACHICOL))]);

  it('encuentra la nota principal y las de su historia', () => {
    if (!section) throw new Error('falta la sección');
    expect([1, 2, 3, null].map((id) => containsArticle(section, id))).toEqual([
      true,
      true,
      false,
      false,
    ]);
  });
});
