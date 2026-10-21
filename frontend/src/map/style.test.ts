import { describe, expect, it } from 'vitest';

import {
  BASEMAP_SWITCH_ZOOM,
  basemapFlavor,
  buildMapStyle,
  EARTH_FADE_END_ZOOM,
  EARTH_LAYER,
  featureLabel,
  INTERACTIVE_LAYERS,
  LABELS_MIN_ZOOM,
  WORLD_POLYGON_OVERLAP_ZOOMS,
} from './style';

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

  it('no duplica etiquetas: el mundo hasta el zoom de cambio y México desde ahí', () => {
    const world = style.layers.filter((l) => l.id.startsWith('basemap_world-'));
    const mexico = style.layers.filter((l) => l.id.startsWith('basemap_mexico-'));
    const worldLabels = world.filter((l) => l.type === 'symbol');

    expect(world.length).toBeGreaterThan(10);
    expect(world.length).toBe(mexico.length);
    expect(worldLabels.every((l) => (l.maxzoom ?? 24) <= BASEMAP_SWITCH_ZOOM)).toBe(true);
    expect(mexico.every((l) => (l.minzoom ?? 0) >= BASEMAP_SWITCH_ZOOM)).toBe(true);
  });

  it('los polígonos del mundo siguen debajo de México un poco más (sin huecos al inclinar)', () => {
    const worldPolygons = style.layers.filter(
      (l) => l.id.startsWith('basemap_world-') && l.type !== 'symbol',
    );

    expect(
      worldPolygons.every(
        (l) => (l.maxzoom ?? 24) <= BASEMAP_SWITCH_ZOOM + WORLD_POLYGON_OVERLAP_ZOOMS,
      ),
    ).toBe(true);
    expect(worldPolygons.some((l) => (l.maxzoom ?? 24) > BASEMAP_SWITCH_ZOOM)).toBe(true);
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

    // Las etiquetas del mapa base van al final, encima de todo.
    const lastBasemap = Math.max(
      ...style.layers.map((l, index) =>
        l.id.startsWith('basemap_') && l.type !== 'symbol' ? index : -1,
      ),
    );

    expect(firstRegion).toBeGreaterThan(lastBasemap);
    expect(zoomOf('states-line')).toBe(2);
    expect(zoomOf('municipalities-line')).toBe(5);
    expect(zoomOf('localities-point')).toBe(10);
    expect(INTERACTIVE_LAYERS.every((id) => ids.includes(id))).toBe(true);
  });

  it('la textura de la NASA tapa el mapa base y se desvanece al acercarse', () => {
    const ids = style.layers.map((l) => l.id);
    const night = style.layers.find((l) => l.id === EARTH_LAYER.night);
    const lastWorldPolygon = Math.max(
      ...style.layers.map((l, index) =>
        l.id.startsWith('basemap_world-') && l.type !== 'symbol' ? index : -1,
      ),
    );

    expect(style.sources.earth_night).toMatchObject({
      type: 'raster',
      url: `pmtiles://${ORIGIN}/tiles/earth_night.pmtiles`,
    });
    expect(ids.indexOf(EARTH_LAYER.night)).toBeGreaterThan(lastWorldPolygon);
    expect(ids.indexOf(EARTH_LAYER.night)).toBeLessThan(ids.indexOf('countries-fill'));
    expect(night?.maxzoom).toBe(EARTH_FADE_END_ZOOM);
    expect(night?.layout).toEqual({ visibility: 'visible' });
    expect(style.layers.find((l) => l.id === EARTH_LAYER.day)?.layout).toEqual({
      visibility: 'none',
    });
  });

  it('de día se ve la otra textura', () => {
    const day = buildMapStyle(ORIGIN, 'day');

    expect(day.layers.find((l) => l.id === EARTH_LAYER.day)?.layout).toEqual({
      visibility: 'visible',
    });
  });

  it('de día el mapa de calles es claro; de noche, oscuro', () => {
    const day = buildMapStyle(ORIGIN, 'day');
    const backgroundOf = (s: typeof style) =>
      s.layers.find((l) => l.type === 'background')?.paint as Record<string, unknown>;

    expect(style.sprite).toBe(`${ORIGIN}/tiles/basemap-assets/sprites/v4/dark`);
    expect(day.sprite).toBe(`${ORIGIN}/tiles/basemap-assets/sprites/v4/light`);
    expect(basemapFlavor('day')).toBe('light');
    expect(basemapFlavor('night')).toBe('dark');
    // Mismas capas en los dos modos: solo cambian los colores.
    expect(day.layers.map((l) => l.id)).toEqual(style.layers.map((l) => l.id));
    expect(backgroundOf(day)['background-color']).not.toEqual(
      backgroundOf(style)['background-color'],
    );
  });

  it('las etiquetas del mundo no ensucian la vista de globo', () => {
    const labels = style.layers.filter(
      (l) => l.id.startsWith('basemap_world-') && l.type === 'symbol',
    );

    expect(labels.length).toBeGreaterThan(0);
    expect(labels.every((l) => (l.minzoom ?? 0) >= LABELS_MIN_ZOOM)).toBe(true);
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
