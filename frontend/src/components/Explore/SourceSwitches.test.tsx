// @vitest-environment jsdom
/** Switches de fuentes de la búsqueda manual (F12.2, ADR-0027). */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SourceOption } from '../../services/sources';
import { SourceSwitches } from './SourceSwitches';

afterEach(() => {
  cleanup();
});

const OPTIONS: SourceOption[] = [
  {
    id: 'google_news_rss',
    label: 'Google News RSS',
    paid: false,
    configured: true,
    default_on: true,
  },
  {
    id: 'searchapi',
    label: 'SearchApi (Google News)',
    paid: true,
    configured: true,
    default_on: true,
  },
  { id: 'indice_local', label: 'Índice local', paid: false, configured: false, default_on: true },
];

describe('switches de fuentes', () => {
  it('apagar SearchApi deja solo las demás encendidas', () => {
    const onChange = vi.fn();
    render(
      <SourceSwitches
        options={OPTIONS}
        chosen={['google_news_rss', 'searchapi']}
        onChange={onChange}
      />,
    );

    const searchapi = screen.getByRole('switch', { name: /SearchApi/ });
    expect(searchapi.getAttribute('aria-checked')).toBe('true');
    expect(searchapi.textContent).toContain('Gasta créditos');

    fireEvent.click(searchapi);

    expect(onChange).toHaveBeenCalledWith(['google_news_rss']);
  });

  it('una fuente sin configurar se ve apagada y no se puede encender', () => {
    render(<SourceSwitches options={OPTIONS} chosen={['google_news_rss']} onChange={vi.fn()} />);

    const local = screen.getByRole('switch', { name: /Índice local/ });
    expect(local.getAttribute('aria-checked')).toBe('false');
    expect((local as HTMLButtonElement).disabled).toBe(true);
    expect(local.textContent).toContain('No configurada');
  });
});
