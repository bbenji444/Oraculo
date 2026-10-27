// @vitest-environment jsdom
/**
 * Pestaña «God's Eye»: muestra el módulo cuando su servidor responde y, si no,
 * dice cómo levantarlo. Sin red: `fetch` es un sustituto.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { godsEyeUrl } from '../../services/godsEye';
import { GodsEyePage } from './GodsEyePage';

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <GodsEyePage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('godsEyeUrl', () => {
  it('apunta al puerto 4173 de la misma máquina', () => {
    expect(godsEyeUrl({ protocol: 'http:', hostname: 'localhost' })).toBe('http://localhost:4173/');
    expect(godsEyeUrl({ protocol: 'http:', hostname: '127.0.0.1' })).toBe('http://127.0.0.1:4173/');
  });
});

describe('GodsEyePage', () => {
  it('con el servidor arriba, lleva a God’s Eye View completo en una pestaña nueva', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const open = vi.spyOn(window, 'open').mockReturnValue(null);

    renderPage();

    const enter = await screen.findByText("ENTRAR A GOD'S EYE VIEW");
    expect(enter.getAttribute('href')).toBe('http://localhost:4173/');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:4173/',
      expect.objectContaining({ mode: 'no-cors' }),
    );
    fireEvent.click(enter);
    expect(open).toHaveBeenCalledWith('http://localhost:4173/', '_blank', 'noopener,noreferrer');
    // No se enmarca: God's Eye View no se deja mostrar dentro de otra página.
    expect(document.querySelector('iframe')).toBeNull();
    open.mockRestore();
  });

  it('si no responde, dice cómo levantarlo y no ofrece entrar', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    renderPage();

    expect(await screen.findByText("God's Eye View no está corriendo.")).toBeTruthy();
    expect(screen.getByText('wsl make up')).toBeTruthy();
    expect(screen.queryByText("ENTRAR A GOD'S EYE VIEW")).toBeNull();
  });
});
