// @vitest-environment jsdom
/** Cronología del expediente: las notas sin fecha de publicación también se ven. */
import { cleanup, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { Article, Platform } from '../../services/searches';
import { useTimelineStore } from '../../store/timeline';
import { Chronology } from './Chronology';

function note(id: number, publishedAt: string | null, platform: Platform, title: string): Article {
  return {
    article_id: id,
    title,
    source_name: null,
    source_domain: null,
    url: `https://medio.mx/${String(id)}`,
    published_at: publishedAt,
    summary: null,
    event_type: null,
    event_date: null,
    extraction_status: 'ok',
    enrichment_status: 'ok',
    concepts: [],
    primary_location: null,
    in_region: null,
    providers: [],
    platform,
  };
}

// Prueba real del 19/11/2026 en la VM («hackeo a bases de datos», Mundo): la
// pestaña decía «Instagram 1» y la cronología «No hay notas con estos
// filtros». Google web no le pone fecha a casi ninguna publicación de redes.
const NEWS = note(1, '2026-11-18T12:00:00Z', 'news', 'Hackean la base de datos de un hospital');
const POST = note(2, null, 'instagram', 'Filtran datos de millones de usuarios');

beforeEach(() => {
  useTimelineStore.getState().clear();
});
afterEach(cleanup);

describe('Chronology', () => {
  it('una publicación sin fecha sale al final, en «Sin fecha de publicación»', () => {
    render(<Chronology articles={[NEWS, POST]} variant="dossier" />);

    const undated = screen.getByRole('list', { name: 'Notas sin fecha de publicación' });
    expect(within(undated).getByText(POST.title)).toBeTruthy();
    expect(screen.getByText(NEWS.title)).toBeTruthy();
  });

  it('con la pestaña de Instagram, la publicación sin fecha no desaparece', () => {
    useTimelineStore.getState().setPlatform('instagram');

    render(<Chronology articles={[NEWS, POST]} variant="dossier" />);

    expect(screen.queryByText('No hay notas con estos filtros.')).toBeNull();
    expect(screen.getByText(POST.title)).toBeTruthy();
    expect(screen.queryByText(NEWS.title)).toBeNull();
  });

  it('con un tramo de fechas elegido, las sin fecha no se cuelan', () => {
    // El tramo filtra por publicación: una nota sin fecha no cae en ninguno.
    useTimelineStore
      .getState()
      .toggleRange([Date.parse('2026-11-18T00:00:00Z'), Date.parse('2026-11-19T00:00:00Z')]);

    render(<Chronology articles={[NEWS, POST]} variant="dossier" />);

    expect(screen.getByText(NEWS.title)).toBeTruthy();
    expect(screen.queryByText(POST.title)).toBeNull();
  });
});
