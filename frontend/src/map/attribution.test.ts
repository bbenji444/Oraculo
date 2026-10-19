// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';

import { collapseAttributionOnStart } from './attribution';

const SHOW = 'maplibregl-compact-show';

/**
 * Imita el control de atribución de MapLibre 6.14 (attribution_control.ts):
 * un <details> con su botón <summary> que alterna la clase al hacer clic.
 */
function fakeMap() {
  const map = document.createElement('div');
  const control = document.createElement('details');
  control.className = 'maplibregl-ctrl maplibregl-ctrl-attrib';
  const button = document.createElement('summary');
  button.className = 'maplibregl-ctrl-attrib-button';
  button.addEventListener('click', () => {
    control.classList.toggle(SHOW);
  });
  control.append(button);
  map.append(control);
  document.body.append(map);
  return { map, control, button };
}

// MutationObserver avisa en una microtarea: se espera a que corra.
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

afterEach(() => {
  document.body.replaceChildren();
});

describe('atribución plegada al iniciar', () => {
  it('cuando MapLibre la abre sola al cargar, se pliega', async () => {
    const { map, control } = fakeMap();
    collapseAttributionOnStart(map);

    // Así la abre MapLibre cuando llegan los créditos de las fuentes.
    control.classList.add('maplibregl-compact', SHOW);
    await flush();

    expect(control.classList.contains(SHOW)).toBe(false);
  });

  it('después, el botón "i" la abre y la cierra como siempre', async () => {
    const { map, control, button } = fakeMap();
    collapseAttributionOnStart(map);
    control.classList.add('maplibregl-compact', SHOW);
    await flush();

    button.click();
    await flush();
    expect(control.classList.contains(SHOW)).toBe(true);

    button.click();
    expect(control.classList.contains(SHOW)).toBe(false);
  });

  it('si ya estaba abierta al crear el mapa, se pliega de inmediato', () => {
    const { map, control } = fakeMap();
    control.classList.add('maplibregl-compact', SHOW);

    collapseAttributionOnStart(map);

    expect(control.classList.contains(SHOW)).toBe(false);
  });

  it('sin control de atribución no hace nada', () => {
    const map = document.createElement('div');

    expect(() => {
      collapseAttributionOnStart(map)();
    }).not.toThrow();
  });
});
