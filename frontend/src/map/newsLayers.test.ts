import { describe, expect, it } from 'vitest';

import type { Article } from '../services/searches';
import {
  calloutPlacement,
  dashedRingPixels,
  isOnVisibleSide,
  keepNewsLayers,
  NEWS_DEFAULT_COLOR,
  newsFeatures,
  newsLayers,
  pulseStyle,
  selectedFilter,
} from './newsLayers';

function article(
  id: number,
  location: Partial<NonNullable<Article['primary_location']>> | null,
  relevant: number | null = null,
): Article {
  return {
    article_id: id,
    title: 'Nota',
    source_name: null,
    source_domain: null,
    url: 'https://x.mx',
    published_at: null,
    summary: null,
    event_type: null,
    event_date: null,
    extraction_status: 'ok',
    enrichment_status: 'ok',
    concepts:
      relevant === null
        ? []
        : [
            {
              concept_id: relevant,
              name: 'C',
              is_relevant: true,
              relevance_score: 1,
              relevance_reason: null,
            },
          ],
    primary_location: location && {
      mention: 'X',
      role: 'event',
      precision: 'municipality',
      confidence: 0.95,
      is_primary: true,
      region_id: 1,
      region_code: '14039',
      place: 'Municipio Guadalajara',
      lon: -103.3,
      lat: 20.7,
      ...location,
    },
    in_region: true,
    providers: [],
  };
}

describe('notas como puntos', () => {
  it('solo las ubicadas, con color de su concepto y precisión', () => {
    const geojson = newsFeatures(
      [
        article(1, {}, 3),
        article(2, { precision: 'state' }),
        article(3, null),
        article(4, { lon: null, lat: null }),
      ],
      new Map([[3, '#AA0000']]),
    );

    expect(geojson.features.map((f) => f.id)).toEqual([1, 2]);
    expect(geojson.features[0]?.properties).toEqual({
      id: 1,
      color: '#AA0000',
      coarse: false,
      inRegion: 'true',
    });
    expect(geojson.features[1]?.properties.coarse).toBe(true);
    expect(geojson.features[1]?.properties.color).toBe(NEWS_DEFAULT_COLOR);
    expect(geojson.features[0]?.geometry.coordinates).toEqual([-103.3, 20.7]);
  });
});

describe('capas', () => {
  it('calor, grupos, brillo, punto, anillo y latido, en ese orden', () => {
    expect(newsLayers().map((l) => l.id)).toEqual([
      'news-heat',
      'news-cluster',
      'news-cluster-count',
      'news-glow',
      'news-point',
      'news-coarse',
      'news-pulse',
    ]);
    expect(selectedFilter(7)).toEqual([
      'all',
      ['!', ['has', 'point_count']],
      ['==', ['get', 'id'], 7],
    ]);
  });

  it('el latido crece y se desvanece', () => {
    expect(pulseStyle(0)).toEqual({ radius: 8, opacity: 1 });
    expect(pulseStyle(1)).toEqual({ radius: 30, opacity: 0 });
  });
});

describe('lado visible del globo', () => {
  it('oculta lo que queda detrás o pegado al borde', () => {
    const mexico = { lng: -102, lat: 23 };
    const equator = { lng: 0, lat: 0 };

    expect(isOnVisibleSide(mexico, { lng: -103, lat: 20 })).toBe(true);
    expect(isOnVisibleSide(mexico, { lng: 78, lat: -23 })).toBe(false);
    // Con el margen de 8°: a 80° se ve, a 85° ya se oculta.
    expect(isOnVisibleSide(equator, { lng: 80, lat: 0 })).toBe(true);
    expect(isOnVisibleSide(equator, { lng: 85, lat: 0 })).toBe(false);
  });
});

describe('anillo punteado', () => {
  it('tiene trazos encendidos y huecos', () => {
    const pixels = dashedRingPixels(44, 12);
    const alphas = Array.from({ length: pixels.length / 4 }, (_, i) => pixels[i * 4 + 3]);

    expect(pixels.length).toBe(44 * 44 * 4);
    expect(alphas.some((a) => a === 235)).toBe(true);
    // El centro queda vacío.
    expect(pixels[(22 * 44 + 22) * 4 + 3]).toBe(0);
  });
});

describe('acomodo de la ficha', () => {
  const card = { width: 330, height: 280 };
  const viewport = { width: 1400, height: 800 };

  it('arriba a la derecha del punto cuando cabe', () => {
    expect(calloutPlacement({ x: 600, y: 500 }, card, viewport)).toEqual({
      left: 646,
      top: 184,
      lineX: 646,
      lineY: 448,
    });
  });

  it('se baja si no cabe arriba y pasa a la izquierda si no cabe a la derecha', () => {
    const high = calloutPlacement({ x: 600, y: 100 }, card, viewport);
    const edge = calloutPlacement({ x: 1300, y: 500 }, card, viewport);

    expect(high.top).toBe(12);
    expect(high.lineY).toBeGreaterThanOrEqual(high.top + 16);
    expect(edge.left).toBe(1300 - 46 - 330);
    expect(edge.lineX).toBe(edge.left + 330);
  });

  it('en celular, sin lugar a los lados, va encima del punto y centrada', () => {
    const phone = { width: 375, height: 760 };
    const placed = calloutPlacement({ x: 187, y: 560 }, { width: 330, height: 260 }, phone);

    expect(placed.left).toBeGreaterThanOrEqual(12);
    expect(placed.left + 330).toBeLessThanOrEqual(375 - 12);
    expect(placed.top + 260).toBeLessThanOrEqual(560);
    expect(placed.lineX).toBe(187);
    expect(placed.lineY).toBe(placed.top + 260);
  });

  it('en un mapa más chico que la ficha queda pegada arriba', () => {
    expect(calloutPlacement({ x: 100, y: 100 }, card, { width: 600, height: 200 }).top).toBe(12);
  });
});

describe('cambio de día a noche', () => {
  const base = { version: 8 as const, sources: {}, layers: [] };
  const news = {
    type: 'geojson' as const,
    data: { type: 'FeatureCollection' as const, features: [] },
  };

  it('el estilo nuevo conserva la fuente y las capas de noticias, encima de todo', () => {
    const previous = {
      ...base,
      sources: { news, states: { type: 'vector' as const, url: 'pmtiles://a' } },
      layers: [{ id: 'states-fill', type: 'fill' as const, source: 'states' }, ...newsLayers()],
    };
    const next = {
      ...base,
      sprite: 'light',
      sources: { states: { type: 'vector' as const, url: 'pmtiles://a' } },
      layers: [{ id: 'states-fill', type: 'fill' as const, source: 'states' }],
    };

    const merged = keepNewsLayers(previous, next);

    expect(merged.sprite).toBe('light');
    expect(merged.sources.news).toBe(news);
    expect(merged.layers.map((l) => l.id)).toEqual([
      'states-fill',
      ...newsLayers().map((l) => l.id),
    ]);
  });

  it('sin noticias todavía, el estilo nuevo queda igual', () => {
    expect(keepNewsLayers(undefined, base)).toBe(base);
    expect(keepNewsLayers(base, base)).toBe(base);
  });
});
