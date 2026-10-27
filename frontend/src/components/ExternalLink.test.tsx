// @vitest-environment jsdom
/** Enlaces a la nota original: siempre en una pestaña nueva (27/10/2026). */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ExternalLink } from './ExternalLink';

const URL = 'https://tribuna.com.mx/seguridad/nota';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('enlace a la nota original', () => {
  it('un clic normal la abre en una ventana nueva, no en la del monitor', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    render(<ExternalLink href={URL}>Ver nota original ↗</ExternalLink>);

    const link = screen.getByRole('link', { name: 'Ver nota original ↗' });
    const event = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
    link.dispatchEvent(event);

    expect(open).toHaveBeenCalledWith(URL, '_blank', 'noopener,noreferrer');
    // El monitor no navega: el clic no sigue el enlace en esta pestaña.
    expect(event.defaultPrevented).toBe(true);
    expect(link.getAttribute('target')).toBe('_blank');
  });

  it('Ctrl+clic se lo deja al navegador', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    render(<ExternalLink href={URL}>Ver nota original ↗</ExternalLink>);

    fireEvent.click(screen.getByRole('link'), { button: 0, ctrlKey: true });

    expect(open).not.toHaveBeenCalled();
  });
});
