// @vitest-environment jsdom
/** La lista de noticias junta en una tarjeta las notas del mismo hecho (F12.1c, ADR-0026). */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { Article } from '../../services/searches';
import { ResultsList } from './ResultsList';

function article(id: number, title: string, storyId: number | null, source: string): Article {
  return {
    article_id: id,
    title,
    source_name: source,
    source_domain: null,
    url: 'https://x.mx',
    published_at: '2026-10-23T22:25:00Z',
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

afterEach(() => {
  cleanup();
});

const ARTICLES = [
  article(1, 'Dos muertos por ataque armado en Ermita Iztapalapa', 1, 'Milenio'),
  article(2, 'Cierran panteón de Janitzio a turistas', null, 'Quadratín'),
  article(3, 'Balacera en Iztapalapa deja dos muertos y un herido', 1, 'Infobae'),
  article(4, 'Detienen a dos por la balacera en Iztapalapa', 1, 'El Universal'),
];

describe('la lista junta las notas del mismo hecho', () => {
  it('muestra una tarjeta por historia y la despliega con el chevron', () => {
    render(<ResultsList articles={ARTICLES} total={4} colors={new Map()} />);

    expect(screen.getByText('4 notas en 2 tarjetas: las del mismo hecho van juntas.')).toBeTruthy();
    expect(screen.queryByText('Balacera en Iztapalapa deja dos muertos y un herido')).toBeNull();
    const chevron = screen.getByRole('button', { name: /\+2 medios/ });
    expect(chevron.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(chevron);

    expect(chevron.getAttribute('aria-expanded')).toBe('true');
    expect(chevron.textContent).toContain('▼');
    expect(screen.getByText('Balacera en Iztapalapa deja dos muertos y un herido')).toBeTruthy();
    expect(screen.getByText('Detienen a dos por la balacera en Iztapalapa')).toBeTruthy();
  });

  it('cada fila dice de qué fuente vino la nota', () => {
    const fromRss = {
      ...article(6, 'Cateo de la FGR en Monterrey', null, 'Milenio'),
      providers: ['google_news_rss', 'indice_local'],
    };
    render(<ResultsList articles={[fromRss]} total={1} colors={new Map()} />);

    expect(screen.getByText('vía Google News RSS · Índice local')).toBeTruthy();
  });

  it('sin historias no hay chevron ni aviso', () => {
    render(
      <ResultsList
        articles={[article(5, 'Nota sola', null, 'Milenio')]}
        total={1}
        colors={new Map()}
      />,
    );

    expect(screen.queryByRole('button', { name: /medio/ })).toBeNull();
    expect(screen.queryByText(/tarjetas/)).toBeNull();
  });
});

describe('secciones por categoría (ADR-0109, D5)', () => {
  const huachicol = { id: 7, name: 'Huachicol', color: '#A3E635', symbol: null };
  const homicidio = { id: 5, name: 'Homicidio', color: '#FF4D6D', symbol: null };
  const notes = [
    {
      ...article(11, 'Aseguran pipa con combustible robado', null, 'Milenio'),
      category: huachicol,
    },
    { ...article(12, 'Hallan toma clandestina en Salamanca', null, 'AM'), category: huachicol },
    { ...article(13, 'Asesinan a dos en Celaya', null, 'Infobae'), category: homicidio },
  ];

  it('con varias categorías, cada una es una sección con su conteo que se pliega', () => {
    render(<ResultsList articles={notes} total={3} colors={new Map()} />);

    const sections = screen.getAllByRole('button', { name: /: \d+ notas?$/ });
    expect(sections.map((b) => b.getAttribute('aria-label'))).toEqual([
      'Huachicol: 2 notas',
      'Homicidio: 1 nota',
    ]);
    expect(screen.getByText('Hallan toma clandestina en Salamanca')).toBeTruthy();

    const [first] = sections;
    if (!first) throw new Error('falta la sección');
    fireEvent.click(first);

    expect(first.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByText('Hallan toma clandestina en Salamanca')).toBeNull();
    expect(screen.getByText('Asesinan a dos en Celaya')).toBeTruthy();
  });

  it('con una sola categoría no hay secciones', () => {
    render(<ResultsList articles={notes.slice(0, 2)} total={2} colors={new Map()} />);

    expect(screen.queryByRole('button', { name: /: \d+ notas?$/ })).toBeNull();
  });
});
