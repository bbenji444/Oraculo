/** Plataformas de las notas (ADR-0117): nombre, conteo, pestañas y quién publicó. */
import { describe, expect, it } from 'vitest';

import type { Article } from '../../services/searches';
import {
  originalLinkLabel,
  outletName,
  PLATFORMS,
  platformOf,
  platformsIn,
  platformTabs,
  tabChoice,
} from './platforms';

type Source = Pick<Article, 'platform' | 'source_name' | 'source_domain'>;

const on = (platform?: Article['platform']): Pick<Article, 'platform'> =>
  platform === undefined ? {} : { platform };

describe('platformOf', () => {
  it('lee la plataforma de la API; sin el dato es noticia', () => {
    expect(platformOf(on('facebook'))).toBe('facebook');
    expect(platformOf(on('x'))).toBe('x');
    // Respuestas de antes del 18/11/2026 (o en caché) no traen el campo.
    expect(platformOf(on())).toBe('news');
  });

  it('una plataforma que la pantalla no conoce cuenta como «Otros sitios»', () => {
    const unknown = { platform: 'mastodon' } as unknown as Pick<Article, 'platform'>;
    expect(platformOf(unknown)).toBe('web');
  });
});

describe('las plataformas del contrato', () => {
  it('son las mismas que manda el servidor, con su nombre en español', () => {
    expect(PLATFORMS.map((p) => [p.id, p.label])).toEqual([
      ['news', 'Noticias'],
      ['facebook', 'Facebook'],
      ['x', 'X'],
      ['youtube', 'YouTube'],
      ['instagram', 'Instagram'],
      ['tiktok', 'TikTok'],
      ['reddit', 'Reddit'],
      ['telegram', 'Telegram'],
      ['web', 'Otros sitios'],
    ]);
  });

  it('X no tiene icono en la letra: va como letra', () => {
    expect(PLATFORMS.find((p) => p.id === 'x')?.icon).toBeNull();
    expect(PLATFORMS.filter((p) => p.icon === null)).toHaveLength(1);
  });
});

describe('platformsIn', () => {
  it('cuenta en el orden fijo de las pestañas y solo las que tienen notas', () => {
    const notes = [on('x'), on(), on('facebook'), on('news'), on('x'), on('youtube')];
    expect(platformsIn(notes).map((p) => [p.id, p.count])).toEqual([
      ['news', 2],
      ['facebook', 1],
      ['x', 2],
      ['youtube', 1],
    ]);
    expect(platformsIn([])).toEqual([]);
  });
});

describe('platformTabs', () => {
  it('suma la elegida aunque ya no tenga notas, para poder quitarla', () => {
    const notes = [on(), on('facebook')];
    expect(platformTabs(notes, []).map((p) => p.id)).toEqual(['news', 'facebook']);
    expect(platformTabs(notes, ['x']).map((p) => [p.id, p.count])).toEqual([
      ['news', 1],
      ['facebook', 1],
      ['x', 0],
    ]);
  });
});

describe('tabChoice', () => {
  it('tocar una deja solo esa; volver a tocarla regresa a «Todo»', () => {
    expect(tabChoice([], 'facebook')).toBe('facebook');
    expect(tabChoice(['facebook'], 'facebook')).toBeNull();
    expect(tabChoice(['facebook'], 'x')).toBe('x');
    // Con varias elegidas en «Filtro», tocar una deja solo esa.
    expect(tabChoice(['facebook', 'x'], 'facebook')).toBe('facebook');
  });
});

describe('textos', () => {
  it('el botón del original dice dónde se abre', () => {
    expect(originalLinkLabel('news')).toBe('Ver nota original');
    expect(originalLinkLabel('facebook')).toBe('Ver publicación en Facebook');
    expect(originalLinkLabel('x')).toBe('Ver publicación en X');
    expect(originalLinkLabel('web')).toBe('Ver página original');
  });

  it('quien publicó, sin repetir la red que ya dice la marca', () => {
    const source = (s: Partial<Source>): Source => ({
      platform: 'news',
      source_name: null,
      source_domain: null,
      ...s,
    });
    // Google web: «Facebook · Ignacio Gómez Villaseñor», «X · ivillasenor».
    expect(
      outletName(source({ platform: 'facebook', source_name: 'Facebook · Ignacio Gómez' })),
    ).toBe('Ignacio Gómez');
    expect(outletName(source({ platform: 'x', source_name: 'X · ivillasenor' }))).toBe(
      'ivillasenor',
    );
    // Google News RSS: «Facebook» a secas, con el dominio facebook.com.
    expect(
      outletName(
        source({ platform: 'facebook', source_name: 'Facebook', source_domain: 'facebook.com' }),
      ),
    ).toBeNull();
    expect(outletName(source({ platform: 'youtube', source_domain: 'youtube.com' }))).toBeNull();
    // Un medio en YouTube conserva su nombre.
    expect(outletName(source({ platform: 'youtube', source_name: 'Milenio' }))).toBe('Milenio');
    // Medios y otros sitios: el nombre o, si falta, el dominio.
    expect(outletName(source({ source_domain: 'sinembargo.mx' }))).toBe('sinembargo.mx');
    // Noticias destacadas de Google web: «Noticias · Quinta Fuerza».
    expect(outletName(source({ source_name: 'Noticias · Quinta Fuerza' }))).toBe('Quinta Fuerza');
    expect(outletName(source({ source_name: 'Noticias', source_domain: 'quintafuerza.mx' }))).toBe(
      'quintafuerza.mx',
    );
    expect(outletName(source({ platform: 'web', source_name: 'Quinta Fuerza' }))).toBe(
      'Quinta Fuerza',
    );
  });
});
