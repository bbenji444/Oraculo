/** Bandas de relevancia en pantalla (ADR-0117): qué se ve, qué se marca y qué no sale nunca. */
import { describe, expect, it } from 'vitest';

import type { Article, Judgement, RelevanceBand } from '../../services/searches';
import { visibleArticles } from './format';
import {
  articleStanding,
  CONFIRMED_SCORE,
  discardedCount,
  discardedToggleLabel,
  isShown,
  judgementBand,
  MIN_RELATED_SCORE,
  standingNote,
} from './relevance';

function judgement(
  isRelevant: boolean,
  score: number,
  reason: string | null = null,
  band?: RelevanceBand,
): Judgement {
  return {
    concept_id: 34,
    name: 'Hacker Eternal',
    is_relevant: isRelevant,
    relevance_score: score,
    relevance_reason: reason,
    ...(band ? { relevance_band: band } : {}),
  };
}

function note(id: number, concepts: Judgement[], extraction = 'ok'): Article {
  return {
    article_id: id,
    title: `Nota ${String(id)}`,
    source_name: null,
    source_domain: null,
    url: `https://medio.mx/${String(id)}`,
    published_at: null,
    summary: null,
    event_type: null,
    event_date: null,
    extraction_status: extraction,
    enrichment_status: 'ok',
    concepts,
    primary_location: null,
    in_region: null,
    providers: [],
  };
}

// Las cuatro bandas del contrato y una nota que la IA no leyó.
const RELEVANT = note(1, [judgement(true, 0.9)]);
const UNCONFIRMED = note(2, [judgement(true, 0.7, 'Menciona a Eternal de pasada.')]);
const RELATED = note(3, [judgement(false, 0.45, 'Es otro hackeo, no el de Eternal.')]);
const UNRELATED = note(4, [judgement(false, 0.1, 'Habla de un partido de futbol.')]);
const UNJUDGED = note(5, []);
const ALL = [RELEVANT, UNCONFIRMED, RELATED, UNRELATED, UNJUDGED];

describe('judgementBand', () => {
  it('manda la banda del servidor cuando viene', () => {
    expect(judgementBand(judgement(false, 0.1, null, 'related'))).toBe('related');
  });

  it('sin banda, la deduce del puntaje con las fronteras del contrato', () => {
    expect(CONFIRMED_SCORE).toBe(0.8);
    expect(MIN_RELATED_SCORE).toBe(0.3);
    expect(judgementBand(judgement(true, 0.8))).toBe('relevant');
    expect(judgementBand(judgement(true, 0.79))).toBe('unconfirmed');
    expect(judgementBand(judgement(true, 0.6))).toBe('unconfirmed');
    expect(judgementBand(judgement(false, 0.59))).toBe('related');
    expect(judgementBand(judgement(false, 0.3))).toBe('related');
    expect(judgementBand(judgement(false, 0.29))).toBe('unrelated');
    expect(judgementBand(judgement(false, 0))).toBe('unrelated');
  });

  it('una no relevante con puntaje alto (la quitó la regla FGR) es cercana', () => {
    expect(judgementBand(judgement(false, 0.9))).toBe('related');
  });
});

describe('articleStanding', () => {
  it('toma la mejor banda entre los conceptos', () => {
    expect(ALL.map(articleStanding)).toEqual([
      'relevant',
      'unconfirmed',
      'related',
      'unrelated',
      'unjudged',
    ]);
    // Relevante para un concepto y ajena para otro: relevante.
    expect(articleStanding(note(6, [judgement(false, 0), judgement(true, 0.95)]))).toBe('relevant');
    // Dos «por confirmar»: por confirmar; una segura basta para relevante.
    expect(articleStanding(note(7, [judgement(true, 0.7), judgement(true, 0.65)]))).toBe(
      'unconfirmed',
    );
    expect(articleStanding(note(8, [judgement(true, 0.7), judgement(true, 0.85)]))).toBe(
      'relevant',
    );
  });

  it('una no relevante que el servidor marcó «relevant» (regla FGR) cuenta como cercana', () => {
    expect(articleStanding(note(9, [judgement(false, 0.9, null, 'relevant')]))).toBe('related');
  });
});

describe('visibleArticles con bandas', () => {
  it('sin el interruptor: solo las relevantes, también las por confirmar', () => {
    expect(visibleArticles(ALL, false)).toEqual([RELEVANT, UNCONFIRMED]);
  });

  it('con «No relevantes»: suma las cercanas y las sin revisar, nunca las ajenas', () => {
    expect(visibleArticles(ALL, true)).toEqual([RELEVANT, UNCONFIRMED, RELATED, UNJUDGED]);
    expect(visibleArticles([UNRELATED], true)).toEqual([]);
  });

  it('con «Ver las que descartó la IA» suma las ajenas, con o sin el interruptor', () => {
    expect(visibleArticles(ALL, false, true)).toEqual([RELEVANT, UNCONFIRMED, UNRELATED]);
    expect(visibleArticles(ALL, true, true)).toEqual(ALL);
  });

  it('cuenta aparte las ajenas, sin decir que no tratan del tema', () => {
    expect(discardedCount(ALL)).toBe(1);
    expect(discardedToggleLabel(1, false)).toBe('Ver la nota que descartó la IA');
    expect(discardedToggleLabel(1, true)).toBe('Ocultar la nota que descartó la IA');
    expect(discardedToggleLabel(12, false)).toBe('Ver las 12 que descartó la IA');
    expect(discardedToggleLabel(12, true)).toBe('Ocultar las 12 que descartó la IA');
    expect(discardedToggleLabel(0, false)).toBeNull();
  });
});

describe('casos reales que motivaron el botón (revisión del 18/11/2026)', () => {
  // «hacker Eternal» (búsquedas 35 y 36): Google trajo las 6 notas correctas,
  // pero la IA solo leyó el título (extraction_status = fallback) y les dio
  // 0.0 a 0.1 («no menciona a Eternal»). Antes no había forma de verlas.
  const ETERNAL = note(
    20,
    [judgement(false, 0.05, 'El título no menciona a Eternal.')],
    'fallback',
  );

  it('una nota de Eternal juzgada solo por el título sale con el botón, no con el interruptor', () => {
    expect(articleStanding(ETERNAL)).toBe('unrelated');
    expect(isShown(ETERNAL, false)).toBe(false);
    expect(isShown(ETERNAL, true)).toBe(false);
    expect(isShown(ETERNAL, false, true)).toBe(true);
    // Lo mismo si el servidor manda la banda.
    const banded = note(21, [judgement(false, 0.05, null, 'unrelated')], 'fallback');
    expect(isShown(banded, true)).toBe(false);
    expect(isShown(banded, false, true)).toBe(true);
    expect(discardedCount([ETERNAL, banded])).toBe(2);
  });

  it('al verla lleva su marca, la razón de la IA y avisa que no leyó la nota completa', () => {
    const shown = standingNote(ETERNAL);
    expect(shown).toMatchObject({
      standing: 'unrelated',
      badge: 'Descartada por la IA',
      reason: 'Por qué no: El título no menciona a Eternal.',
    });
    expect(shown?.hint).toContain('no pudo leer la nota completa');
    expect(shown?.hint).not.toContain('no trata');
    // Con la nota completa leída no se dice eso.
    expect(standingNote(UNRELATED)?.hint).not.toContain('no pudo leer la nota completa');
  });

  it('FGR: una no relevante de puntaje 0 con banda «related» sale con el interruptor', () => {
    // El servidor manda «related» para las no relevantes de los conceptos
    // exactos (FGR, ADR-0114): el monitor se ve como antes con el interruptor.
    const fgr = note(22, [
      {
        concept_id: 13,
        name: 'FGR',
        is_relevant: false,
        relevance_score: 0,
        relevance_reason: 'Es de una fiscalía estatal.',
        relevance_band: 'related',
      },
    ]);
    expect(articleStanding(fgr)).toBe('related');
    expect(isShown(fgr, false)).toBe(false);
    expect(isShown(fgr, true)).toBe(true);
    expect(discardedCount([fgr])).toBe(0);
    expect(standingNote(fgr)).toMatchObject({ badge: 'Cercana' });
  });
});

describe('standingNote', () => {
  it('las relevantes no llevan marca; las ajenas, «Descartada por la IA»', () => {
    expect(standingNote(RELEVANT)).toBeNull();
    expect(standingNote(UNRELATED)).toMatchObject({
      badge: 'Descartada por la IA',
      reason: 'Por qué no: Habla de un partido de futbol.',
    });
  });

  it('por confirmar y cercanas dicen la razón de la IA', () => {
    expect(standingNote(UNCONFIRMED)).toMatchObject({
      badge: 'Por confirmar',
      reason: 'Razón de la IA: Menciona a Eternal de pasada.',
    });
    expect(standingNote(RELATED)).toMatchObject({
      badge: 'Cercana',
      reason: 'Por qué no: Es otro hackeo, no el de Eternal.',
    });
  });

  it('la razón es la del juicio con más puntaje; sin razón no hay renglón', () => {
    const two = note(10, [
      judgement(false, 0.35, 'Poco que ver.'),
      judgement(false, 0.55, 'Es de otro estado.'),
    ]);
    expect(standingNote(two)?.reason).toBe('Por qué no: Es de otro estado.');
    expect(standingNote(note(11, [judgement(false, 0.4)]))?.reason).toBeNull();
    expect(standingNote(UNJUDGED)).toMatchObject({ badge: 'Sin revisar', reason: null });
  });
});
