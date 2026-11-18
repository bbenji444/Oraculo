// @vitest-environment jsdom
/** Pestañas de plataforma del expediente, como las de Google (ADR-0117). */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { Article, Platform } from '../../services/searches';
import { useTimelineStore } from '../../store/timeline';
import { PlatformTabs } from './PlatformTabs';

function note(id: number, platform?: Platform): Article {
  return {
    article_id: id,
    title: `Nota ${String(id)}`,
    source_name: null,
    source_domain: null,
    url: `https://medio.mx/${String(id)}`,
    published_at: '2026-11-18T12:00:00Z',
    summary: null,
    event_type: null,
    event_date: null,
    extraction_status: 'ok',
    enrichment_status: 'ok',
    concepts: [],
    primary_location: null,
    in_region: null,
    providers: [],
    ...(platform ? { platform } : {}),
  };
}

// 3 noticias (una sin el campo, como las respuestas viejas), 2 de Facebook y 1 de X.
const NOTES = [
  note(1, 'news'),
  note(2),
  note(3, 'news'),
  note(4, 'facebook'),
  note(5, 'facebook'),
  note(6, 'x'),
];

const group = () => screen.getByRole('group', { name: 'Filtrar por plataforma' });
const tab = (name: RegExp) => within(group()).getByRole('button', { name });

beforeEach(() => {
  useTimelineStore.getState().clear();
});
afterEach(cleanup);

describe('PlatformTabs', () => {
  it('«Todo» y una pestaña por plataforma presente, con su conteo', () => {
    render(<PlatformTabs articles={NOTES} />);

    const names = within(group())
      .getAllByRole('button')
      .map((b) => b.getAttribute('aria-label'));
    expect(names).toEqual(['Todo: 6 notas', 'Noticias: 3 notas', 'Facebook: 2 notas', 'X: 1 nota']);
    // YouTube no trae notas: no sale.
    expect(within(group()).queryByRole('button', { name: /^YouTube/ })).toBeNull();
    expect(tab(/^Todo/).getAttribute('aria-pressed')).toBe('true');
  });

  it('tocar una deja solo esa; volver a tocarla regresa a «Todo»', () => {
    render(<PlatformTabs articles={NOTES} />);

    fireEvent.click(tab(/^Facebook/));
    expect(useTimelineStore.getState().platforms).toEqual(['facebook']);
    expect(tab(/^Facebook/).getAttribute('aria-pressed')).toBe('true');
    expect(tab(/^Todo/).getAttribute('aria-pressed')).toBe('false');

    fireEvent.click(tab(/^X/));
    expect(useTimelineStore.getState().platforms).toEqual(['x']);

    fireEvent.click(tab(/^X/));
    expect(useTimelineStore.getState().platforms).toEqual([]);
    expect(tab(/^Todo/).getAttribute('aria-pressed')).toBe('true');
  });

  it('«Todo» quita la plataforma elegida', () => {
    useTimelineStore.getState().setPlatform('facebook');
    render(<PlatformTabs articles={NOTES} />);

    fireEvent.click(tab(/^Todo/));
    expect(useTimelineStore.getState().platforms).toEqual([]);
  });

  it('con una sola plataforma la fila no aparece', () => {
    render(<PlatformTabs articles={[note(1, 'news'), note(2)]} />);
    expect(screen.queryByRole('group', { name: 'Filtrar por plataforma' })).toBeNull();
  });

  it('si la elegida se queda sola o sin notas, la fila sigue para regresar a «Todo»', () => {
    useTimelineStore.getState().setPlatform('x');
    render(<PlatformTabs articles={[note(1, 'news')]} />);

    expect(tab(/^X/).getAttribute('aria-label')).toBe('X: 0 notas');
    fireEvent.click(tab(/^Todo/));
    expect(useTimelineStore.getState().platforms).toEqual([]);
  });
});
