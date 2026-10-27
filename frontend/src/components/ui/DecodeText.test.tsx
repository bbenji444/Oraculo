// @vitest-environment jsdom
/**
 * El texto que se descifra no debe tragarse clics (Benji, 27/10/2026).
 *
 * Mientras se anima, el texto vive en elementos internos que se crean al
 * empezar y se borran al terminar. Si el mouse se presiona sobre uno y se
 * suelta cuando ya no existe, el navegador no cuenta el clic: había que
 * esperar a que terminara la animación para cambiar de pestaña. Esos
 * elementos no deben recibir el mouse; así el clic cae siempre en el enlace.
 */
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DecodeText } from './DecodeText';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('DecodeText', () => {
  it('mientras se anima, sus partes internas no reciben el mouse', () => {
    vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'performance'] });
    render(
      <a href="#/conceptos">
        <DecodeText text="Conceptos" />
      </a>,
    );
    const link = screen.getByRole('link', { name: 'Conceptos' });

    const outer = link.querySelector('span');
    if (!outer) throw new Error('Falta el texto del enlace');
    fireEvent.mouseEnter(outer);
    act(() => {
      vi.advanceTimersByTime(100);
    });

    const inner = [...link.querySelectorAll('span span')];
    expect(inner.length).toBeGreaterThan(0);
    for (const element of inner) {
      expect(element.classList.contains('pointer-events-none')).toBe(true);
    }
    // El enlace sigue llamándose igual mientras se anima.
    expect(screen.getByRole('link', { name: 'Conceptos' })).toBe(link);
  });

  it('al terminar queda un solo texto, sin partes internas', () => {
    vi.useFakeTimers({ toFake: ['requestAnimationFrame', 'performance'] });
    render(<DecodeText text="Casos" />);

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(screen.getByText('Casos').children).toHaveLength(0);
  });
});
