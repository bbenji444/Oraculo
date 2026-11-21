// @vitest-environment jsdom
/**
 * La llave de API se ve una sola vez, al generarla (ADR-0120).
 *
 * Benji, 20/11/2026: «ver una sola vez la api key y después no se pueda ver de
 * nuevo bajo ningún motivo, solo generar una nueva».
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { AccessUser } from '../../services/access';
import { isSessionHeld, page } from '../../services/http';
import { ApiKeyRow } from './ApiKeyRow';

const FULL_KEY = 'orc_live_AbCd1234_secreto';

const PEPE: AccessUser = {
  id: 2,
  username: 'pepe',
  display_name: 'Pepe',
  email: null,
  role: 'user',
  is_active: true,
  created_at: '2026-11-10T18:00:00Z',
  last_seen_at: null,
  active_keys: 0,
  has_password: true,
  must_change_password: false,
  totp_enrolled: false,
  locked_until: null,
  api_key: 'orc_live_Viej0000…',
};

function stubIssue() {
  const issued = {
    key: FULL_KEY,
    info: {
      id: 9,
      user_id: 2,
      masked: 'orc_live_AbCd1234…',
      label: 'Llave de API',
      created_by: 'benji',
      created_at: '2026-11-20T18:00:00Z',
      expires_at: null,
      revoked_at: null,
      last_used_at: null,
      last_used_ip: null,
    },
  };
  const spy = vi.fn<typeof fetch>(() =>
    Promise.resolve(
      new Response(JSON.stringify(issued), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      }),
    ),
  );
  vi.stubGlobal('fetch', spy);
  return spy;
}

function renderRow(user: AccessUser = PEPE, me: string | null = null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (me) client.setQueryData(['auth', 'me'], { username: me });
  return render(
    <QueryClientProvider client={client}>
      <ApiKeyRow user={user} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('ApiKeyRow', () => {
  it('sin botón para volver a ver ni copiar la llave guardada', () => {
    const spy = stubIssue();
    renderRow();

    expect(screen.getByText('orc_live_Viej0000…')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Ver' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Copiar' })).toBeNull();
    expect(spy).not.toHaveBeenCalled();
  });

  it('la completa sale una vez al generar y al cerrar ya no está', async () => {
    const spy = stubIssue();
    renderRow();

    fireEvent.click(screen.getByRole('button', { name: 'Generar nueva' }));
    fireEvent.click(screen.getByRole('button', { name: 'Sí, generar' }));

    const notice = await screen.findByRole('dialog', { name: 'Llave nueva de Pepe' });
    expect(notice.textContent).toContain(FULL_KEY);
    expect(notice.textContent).toContain('no se vuelve a mostrar');
    expect(notice.textContent).toContain('genera una nueva');
    const [url, init] = spy.mock.calls[0] ?? [];
    expect([url, init?.method]).toEqual(['/api/v1/access/users/2/api-key', 'POST']);

    fireEvent.click(screen.getByRole('button', { name: 'Ya la copié, cerrar' }));

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.body.textContent).not.toContain(FULL_KEY);
  });

  it('la propia llave no saca a nadie hasta cerrar el aviso (20/11/2026)', async () => {
    stubIssue();
    const reload = vi.spyOn(page, 'reload').mockImplementation(() => undefined);
    renderRow(PEPE, 'pepe');

    fireEvent.click(screen.getByRole('button', { name: 'Generar nueva' }));
    fireEvent.click(screen.getByRole('button', { name: 'Sí, generar' }));

    const notice = await screen.findByRole('dialog', { name: 'Llave nueva de Pepe' });
    expect(notice.textContent).toContain('Es tu propia llave');
    expect(isSessionHeld()).toBe(true);
    expect(reload).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Ya la copié, cerrar' }));

    expect(isSessionHeld()).toBe(false);
    expect(reload).toHaveBeenCalledOnce();
    reload.mockRestore();
  });

  it('sin llave todavía la genera sin pedir confirmar', async () => {
    stubIssue();
    renderRow({ ...PEPE, api_key: null });

    fireEvent.click(screen.getByRole('button', { name: 'Generar llave' }));

    expect(await screen.findByRole('dialog', { name: 'Llave nueva de Pepe' })).toBeTruthy();
  });
});
