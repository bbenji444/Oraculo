// @vitest-environment jsdom
/** Eliminar pide confirmación y se puede deshacer (27/10/2026). */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ConfirmDelete } from './ConfirmDelete';
import { UNDO_TOAST_MS, UndoToast } from './UndoToast';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('eliminar con confirmación', () => {
  it('el primer clic no borra: pregunta, y «Cancelar» no hace nada', () => {
    const onConfirm = vi.fn();
    render(<ConfirmDelete what="la búsqueda" onConfirm={onConfirm} />);

    fireEvent.click(screen.getByRole('button', { name: 'Eliminar la búsqueda' }));
    expect(onConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Eliminar la búsqueda' })).toBeTruthy();
  });

  it('«Sí, eliminar» confirma', () => {
    const onConfirm = vi.fn();
    render(<ConfirmDelete what="el caso" label="Eliminar caso" onConfirm={onConfirm} />);

    fireEvent.click(screen.getByRole('button', { name: 'Eliminar caso el caso' }));
    fireEvent.click(screen.getByRole('button', { name: 'Sí, eliminar' }));

    expect(onConfirm).toHaveBeenCalledOnce();
  });
});

describe('aviso para deshacer', () => {
  it('«Deshacer» avisa y el aviso se va solo', () => {
    vi.useFakeTimers();
    const onUndo = vi.fn();
    const onClose = vi.fn();
    render(<UndoToast message="Se eliminó el caso." onUndo={onUndo} onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: 'Deshacer' }));
    expect(onUndo).toHaveBeenCalledOnce();
    act(() => {
      vi.advanceTimersByTime(UNDO_TOAST_MS);
    });

    expect(onClose).toHaveBeenCalledOnce();
  });
});
