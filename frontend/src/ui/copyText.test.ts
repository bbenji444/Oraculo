// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';

import { copyText } from './copyText';

afterEach(() => {
  vi.restoreAllMocks();
});

describe('copiar al portapapeles', () => {
  it('en http:// (sin navigator.clipboard) copia con el método clásico', async () => {
    // Bug del 10/11/2026: en http://10.244.214.144:8080 «Copiar» no hacía nada.
    const execCommand = vi.fn(() => true);
    Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true });

    const copied = await copyText('Abcd2345Efgh6789');

    expect(copied).toBe(true);
    expect(execCommand).toHaveBeenCalledWith('copy');
    // El cuadro de texto temporal no se queda en la página.
    expect(document.querySelector('textarea')).toBeNull();
  });

  it('avisa si el navegador no dejó copiar', async () => {
    Object.defineProperty(document, 'execCommand', { value: () => false, configurable: true });

    expect(await copyText('x')).toBe(false);
  });
});
