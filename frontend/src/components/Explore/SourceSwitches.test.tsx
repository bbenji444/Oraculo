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

  it('BrowserWork avisa que tarda más', () => {
    const bing: SourceOption = {
      id: 'browserwork_bing',
      label: 'Bing (BrowserWork)',
      paid: false,
      slow: true,
      configured: true,
      default_on: false,
    };
    render(<SourceSwitches options={[bing]} chosen={[]} onChange={vi.fn()} />);

    const sw = screen.getByRole('switch', { name: /Bing/ });
    expect(sw.getAttribute('aria-checked')).toBe('false');
    expect(sw.textContent).toContain('Gratis · tarda más');
  });

  it('una fuente sin configurar se ve apagada y no se puede encender', () => {
    render(<SourceSwitches options={OPTIONS} chosen={['google_news_rss']} onChange={vi.fn()} />);

    const local = screen.getByRole('switch', { name: /Índice local/ });
    expect(local.getAttribute('aria-checked')).toBe('false');
    expect((local as HTMLButtonElement).disabled).toBe(true);
    expect(local.textContent).toContain('No configurada');
  });

  it('junto a Google web dice cuántos créditos quedan, si el servidor lo sabe (ADR-0115)', () => {
    // Sin `credits_remaining`: como llega de un servidor que no lo sabe.
    const withoutCredits: SourceOption = {
      id: 'searchapi_web',
      label: 'Google web',
      paid: true,
      configured: true,
      default_on: true,
    };
    const web: SourceOption = { ...withoutCredits, credits_remaining: 46 };
    const { rerender } = render(
      <SourceSwitches options={[web]} chosen={['searchapi_web']} onChange={vi.fn()} />,
    );
    expect(screen.getByRole('switch', { name: /Google web/ }).textContent).toContain(
      'Gasta créditos · quedan 46',
    );

    rerender(
      <SourceSwitches
        options={[{ ...web, credits_remaining: 1 }]}
        chosen={['searchapi_web']}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('switch', { name: /Google web/ }).textContent).toContain(
      'Gasta créditos · queda 1',
    );

    // Sin saldo: lo dice en lugar de «Gasta créditos» (el servidor ya la apaga).
    rerender(
      <SourceSwitches
        options={[{ ...web, credits_remaining: 0 }]}
        chosen={[]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole('switch', { name: /Google web/ }).textContent).toContain(
      'Sin créditos',
    );

    // Sin el dato (servidor viejo o cuenta sin consultar): como antes.
    rerender(
      <SourceSwitches options={[withoutCredits]} chosen={['searchapi_web']} onChange={vi.fn()} />,
    );
    const note = screen.getByRole('switch', { name: /Google web/ }).textContent;
    expect(note).toContain('Gasta créditos');
    expect(note).not.toContain('queda');
  });
});
