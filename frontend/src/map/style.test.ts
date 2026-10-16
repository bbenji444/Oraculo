import { describe, expect, it } from 'vitest';

import { BASEMAP_SWITCH_ZOOM, buildMapStyle, featureLabel, INTERACTIVE_LAYERS } from './style';

const ORIGIN = 'http://localhost:8080';

describe('buildMapStyle', () => {
  const style = buildMapStyle(ORIGIN);

  it('usa la proyección de globo', () => {
    expect(style.projection).toEqual({ type: 'globe' });
  });

  it('pide teselas, fuentes y sprite al mismo origen, nunca a terceros', () => {
    const urls = [
      style.glyphs,
      style.sprite,
      ...Object.values(style.sources).map((s) => ('url' in s ? s.url : '')),
    ];

    expect(urls.every((url) => typeof url === 'string' && url.includes(ORIGIN))).toBe(true);
    expect(style.sources.states).toMatchObject({
      type: 'vector',
      url: `pmtiles://${ORIGIN}/tiles/states.pmtiles`,
    });
  });

  it('no duplica el mapa base: el mundo hasta el zoom de cambio y México desde ahí', () => {
    const world = style.layers.filter((l) => l.id.startsWith('basemap_world-'));
    const mexico = style.layers.filter((l) => l.id.startsWith('basemap_mexico-'));

    expect(world.length).toBeGreaterThan(10);
    expect(world.length).toBe(mexico.length);
    expect(world.every((l) => (l.maxzoom ?? 24) <= BASEMAP_SWITCH_ZOOM)).toBe(true);
    expect(mexico.every((l) => (l.minzoom ?? 0) >= BASEMAP_SWITCH_ZOOM)).toBe(true);
  });

  it('tiene un solo fondo, al principio', () => {
    const backgrounds = style.layers.filter((l) => l.type === 'background');

    expect(backgrounds).toHaveLength(1);
    expect(style.layers[0]?.type).toBe('background');
  });

  it('dibuja las capas de INEGI encima del mapa base, en los zooms de §12', () => {
    const ids = style.layers.map((l) => l.id);
    const firstRegion = ids.indexOf('countries-fill');
    const zoomOf = (id: string) => style.layers.find((l) => l.id === id)?.minzoom ?? 0;

    const lastBasemap = Math.max(
      ...ids.map((id, index) => (id.startsWith('basemap_') ? index : -1)),
    );

    expect(firstRegion).toBeGreaterThan(lastBasemap);
    expect(zoomOf('states-line')).toBe(2);
    expect(zoomOf('municipalities-line')).toBe(5);
    expect(zoomOf('localities-point')).toBe(10);
    expect(INTERACTIVE_LAYERS.every((id) => ids.includes(id))).toBe(true);
  });

  it('las capas del mapa base tienen ids únicos', () => {
    const ids = style.layers.map((l) => l.id);

    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe('featureLabel', () => {
  it('municipios y localidades llevan su prefijo', () => {
    expect(
      featureLabel({ name: 'Iztapalapa', display_prefix: 'Alcaldía', level: 'municipality' }),
    ).toBe('Alcaldía Iztapalapa');
    expect(
      featureLabel({ name: 'La Cañada', display_prefix: 'Localidad', level: 'locality' }),
    ).toBe('Localidad La Cañada');
  });

  it('países y estados solo con su nombre', () => {
    expect(featureLabel({ name: 'Jalisco', display_prefix: 'Estado', level: 'state' })).toBe(
      'Jalisco',
    );
  });

  it('sin nombre no hay tooltip', () => {
    expect(featureLabel({ level: 'state' })).toBeNull();
    expect(featureLabel({ name: 42 })).toBeNull();
  });
});
