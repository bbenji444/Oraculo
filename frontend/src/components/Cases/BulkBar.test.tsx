// @vitest-environment jsdom
/** Barra de acciones en bloque: descartar pregunta antes, confirmar no (F12). */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { BulkBar } from './BulkBar';

afterEach(() => {
  cleanup();
});

function renderBar(overrides: Partial<Parameters<typeof BulkBar>[0]> = {}) {
  const props = {
    count: '5 entidades',
    detail: '3 personas y 2 lugares',
    canConfirm: true,
    canDiscard: true,
    busy: false,
    onConfirm: vi.fn(),
    onDiscard: vi.fn(),
    onClear: vi.fn(),
    ...overrides,
  };
  render(<BulkBar {...props} />);
  return props;
}

describe('acciones en bloque', () => {
  it('dice cuánto se eligió y confirma con un clic', () => {
    const props = renderBar();

    expect(screen.getByRole('region', { name: 'Acciones en bloque' }).textContent).toContain(
      'Selección: 5 entidades (3 personas y 2 lugares)',
    );
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar 5 entidades' }));

    expect(props.onConfirm).toHaveBeenCalledOnce();
    expect(props.onDiscard).not.toHaveBeenCalled();
  });

  it('descartar pregunta primero, y «Cancelar» no descarta nada', () => {
    const props = renderBar();

    fireEvent.click(screen.getByRole('button', { name: 'Descartar 5 entidades' }));
    expect(props.onDiscard).not.toHaveBeenCalled();
    expect(screen.getByText(/¿Descartar 5 entidades\?/)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));

    expect(props.onDiscard).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Descartar 5 entidades' })).toBeTruthy();
  });

  it('dice dónde quedan: «Descartadas» en entidades, «Descartados» en vínculos', () => {
    renderBar();
    fireEvent.click(screen.getByRole('button', { name: 'Descartar 5 entidades' }));
    expect(screen.getByText(/Quedan en «Descartadas»/)).toBeTruthy();
    cleanup();

    renderBar({ count: '3 vínculos', discardedTab: 'Descartados' });
    fireEvent.click(screen.getByRole('button', { name: 'Descartar 3 vínculos' }));
    expect(screen.getByText(/¿Descartar 3 vínculos\? Quedan en «Descartados»/)).toBeTruthy();
  });

  it('«Sí, descartar» descarta', () => {
    const props = renderBar();

    fireEvent.click(screen.getByRole('button', { name: 'Descartar 5 entidades' }));
    fireEvent.click(screen.getByRole('button', { name: 'Sí, descartar' }));

    expect(props.onDiscard).toHaveBeenCalledOnce();
  });

  it('solo ofrece lo que tiene sentido en el estado y se apaga mientras guarda', () => {
    const props = renderBar({ canConfirm: false, busy: true });

    expect(screen.queryByRole('button', { name: /^Confirmar/ })).toBeNull();
    const clear = screen.getByRole('button', { name: 'Quitar selección' });
    expect((clear as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(clear);
    expect(props.onClear).not.toHaveBeenCalled();
  });
});
