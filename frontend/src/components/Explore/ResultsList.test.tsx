// @vitest-environment jsdom
/** La lista de noticias junta en una tarjeta las notas del mismo hecho (F12.1c, ADR-0026). */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { Article } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
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
    expect(chevron.querySelector('[data-icon]')?.getAttribute('data-icon')).toBe('expand_more');
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

  it('una publicación de Facebook lleva su marca y no repite «Facebook» (ADR-0117)', () => {
    const post: Article = {
      ...article(7, 'Denuncian cobro de piso en el mercado', null, 'Facebook'),
      source_domain: 'facebook.com',
      platform: 'facebook',
    };
    const news = article(8, 'Detienen a extorsionador en Zapopan', null, 'Milenio');
    render(<ResultsList articles={[post, news]} total={2} colors={new Map()} variant="dossier" />);

    const [postRow, newsRow] = screen.getAllByRole('listitem');
    if (!postRow || !newsRow) throw new Error('Debería haber dos renglones.');
    const mark = postRow.querySelector('[data-platform]');
    expect(mark?.getAttribute('data-platform')).toBe('facebook');
    expect(mark?.textContent).toBe('Facebook');
    expect(mark?.querySelector('[data-icon]')?.getAttribute('data-icon')).toBe('facebook');
    // «Facebook» sale una vez (la marca), no también como medio.
    expect(postRow.textContent.match(/Facebook/g)).toHaveLength(1);
    // Las noticias de medios no llevan marca.
    expect(newsRow.querySelector('[data-platform]')).toBeNull();
    expect(newsRow.textContent).toContain('Milenio');
  });

  it('X va como letra, sin icono', () => {
    const post: Article = {
      ...article(9, 'Hilo sobre el hackeo', null, 'X · ivillasenor'),
      platform: 'x',
    };
    render(<ResultsList articles={[post]} total={1} colors={new Map()} />);

    const mark = screen.getByRole('listitem').querySelector('[data-platform="x"]');
    expect(mark?.textContent).toBe('X');
    expect(mark?.querySelector('[data-icon]')).toBeNull();
    expect(screen.getByRole('listitem').textContent).toContain('ivillasenor');
  });

  it('las cercanas y las por confirmar dicen por qué, en letra chica', () => {
    const judged = (id: number, relevant: boolean, score: number, reason: string): Article => ({
      ...article(id, `Nota ${String(id)}`, null, 'Milenio'),
      concepts: [
        {
          concept_id: 3,
          name: 'Extorsión',
          is_relevant: relevant,
          relevance_score: score,
          relevance_reason: reason,
        },
      ],
    });
    render(
      <ResultsList
        articles={[
          judged(10, true, 0.95, 'Trata de una extorsión en Jalisco.'),
          judged(11, true, 0.7, 'Menciona extorsión entre otros delitos.'),
          judged(12, false, 0.45, 'Es extorsión, pero en Morelos.'),
        ]}
        total={5}
        colors={new Map()}
        discarded={2}
      />,
    );

    const [sure, unsure, near] = screen.getAllByRole('listitem');
    if (!sure || !unsure || !near) throw new Error('Debería haber tres renglones.');
    expect(sure.querySelector('.standing-badge')).toBeNull();
    expect(sure.textContent).not.toContain('Trata de una extorsión');
    expect(unsure.querySelector('.standing-badge')?.textContent).toBe('Por confirmar');
    expect(unsure.textContent).toContain('Razón de la IA: Menciona extorsión entre otros delitos.');
    expect(near.querySelector('.standing-badge')?.textContent).toBe('Cercana');
    expect(near.textContent).toContain('Por qué no: Es extorsión, pero en Morelos.');
    // Las que descartó la IA no se listan solas: un botón las muestra y las
    // vuelve a ocultar, sin decir que no tratan del tema (ADR-0117).
    expect(screen.queryByText(/no tratar del tema/)).toBeNull();
    const toggle = screen.getByRole('button', { name: 'Ver las 2 que descartó la IA' });
    expect(toggle.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(toggle);
    expect(useExplorerStore.getState().showDiscarded).toBe(true);
    expect(toggle.textContent).toBe('Ocultar las 2 que descartó la IA');
    expect(toggle.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(toggle);
    expect(useExplorerStore.getState().showDiscarded).toBe(false);
  });

  it('una descartada por la IA que se pidió ver lleva su marca y la razón', () => {
    const eternal: Article = {
      ...article(
        13,
        'Hackeo masivo: Eternal expone 746 mil cuentas de Pillofon',
        null,
        'Quinta Fuerza',
      ),
      extraction_status: 'fallback',
      concepts: [
        {
          concept_id: 35,
          name: 'Hacker Eternal',
          is_relevant: false,
          relevance_score: 0.05,
          relevance_reason: 'No menciona a Eternal.',
        },
      ],
    };
    render(<ResultsList articles={[eternal]} total={1} colors={new Map()} />);

    const [row] = screen.getAllByRole('listitem');
    const badge = row?.querySelector('.standing-badge');
    expect(badge?.textContent).toBe('Descartada por la IA');
    expect(badge?.getAttribute('title')).toContain('no pudo leer la nota completa');
    expect(row?.textContent).toContain('Por qué no: No menciona a Eternal.');
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
