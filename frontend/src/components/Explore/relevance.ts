/**
 * Bandas de relevancia en pantalla (ADR-0117): qué notas se ven, cuáles se
 * marcan «Por confirmar» y cuáles quedan aparte, detrás de su propio botón.
 *
 * Benji comparó con Google y vio que «No relevantes» era basura total: 275
 * de 401 «no» de la IA tenían 0.2 o menos. Desde el 18/11/2026 la IA y el
 * servidor separan cuatro bandas por puntaje:
 *
 * | Banda         | Puntaje     | En pantalla                                              |
 * | ------------- | ----------- | -------------------------------------------------------- |
 * | `relevant`    | 0.8 o más   | siempre                                                  |
 * | `unconfirmed` | 0.6 a 0.79  | siempre, con la marca «Por confirmar»                    |
 * | `related`     | 0.3 a 0.59  | «cercana»: solo con «Incluir las no relevantes»          |
 * | `unrelated`   | menos de 0.3| «descartada por la IA»: solo con «Ver las N que descartó |
 * |               |             | la IA», con su marca y la razón de la IA                 |
 *
 * Las descartadas no se esconden para siempre: la IA casi siempre juzga solo
 * con el título y el fragmento (extraction_status = fallback, los links de
 * Google News no se abren) y así descartó las 6 notas correctas de «hacker
 * Eternal» que Google sí trae (revisión del 18/11/2026). Por eso el renglón
 * nunca dice que «no tratan del tema»: dice que las descartó la IA.
 *
 * El servidor manda la banda de cada juicio (`relevance_band`); para los
 * conceptos exactos (FGR) manda `related` en las no relevantes, así el
 * monitor FGR se ve como antes con el interruptor. Si falta (una respuesta de
 * antes), se deduce aquí del puntaje con las mismas fronteras: la API no dice
 * de qué modo es el concepto y no se adivina.
 *
 * No hace: no dibuja ni pide datos; lo usan `format.visibleArticles`, las
 * tarjetas y el expediente.
 */
import type { Article, Judgement, RelevanceBand } from '../../services/searches';

/**
 * Desde este puntaje la IA está segura de que la nota es relevante; entre el
 * umbral del servidor (`MIN_RELEVANCE_SCORE` = 0.6, backend/app/domain/
 * authority.py) y este valor es relevante «por confirmar» (contrato de bandas
 * del 18/11/2026, ADR-0117).
 */
export const CONFIRMED_SCORE = 0.8;

/**
 * Espejo de `MIN_RELATED_SCORE` del servidor (backend/app/domain/authority.py,
 * ADR-0117): desde este puntaje una nota no relevante es del mismo tema
 * («cercana»); por debajo no tiene nada que ver («ajena») y solo se ve con
 * «Ver las N que descartó la IA».
 */
export const MIN_RELATED_SCORE = 0.3;

/**
 * Banda de un juicio: la que mandó el servidor o, si falta, la que sale del
 * puntaje y de la relevancia final.
 *
 * Se parte de `is_relevant` y no solo del puntaje porque el servidor ya le
 * aplicó la regla FGR (ADR-0030): una nota de una fiscalía estatal puede tener
 * 0.9 y no ser relevante para la FGR.
 *
 * @param judgement Juicio de la IA para un concepto.
 * @returns La banda del juicio.
 * @example judgementBand({ is_relevant: false, relevance_score: 0.45 }) // 'related'
 */
export function judgementBand(
  judgement: Pick<Judgement, 'is_relevant' | 'relevance_score' | 'relevance_band'>,
): RelevanceBand {
  if (judgement.relevance_band) return judgement.relevance_band;
  if (judgement.is_relevant) {
    return judgement.relevance_score >= CONFIRMED_SCORE ? 'relevant' : 'unconfirmed';
  }
  return judgement.relevance_score >= MIN_RELATED_SCORE ? 'related' : 'unrelated';
}

/**
 * Cómo queda una nota frente a la búsqueda: su mejor banda entre todos los
 * conceptos, o `unjudged` si la IA no la leyó (pasó del tope de notas o la IA
 * falló).
 */
export type Standing = RelevanceBand | 'unjudged';

/**
 * La posición de una nota: relevante si algún concepto la marcó relevante
 * («por confirmar» si todos esos juicios son de 0.6 a 0.79); si no, cercana si
 * algún juicio no es ajeno.
 *
 * Una nota no relevante cuya banda del servidor diga `relevant` o
 * `unconfirmed` (la excluyó la regla FGR) cuenta como cercana: es del tema,
 * pero no lo que se pidió.
 *
 * @param article Nota con sus juicios.
 * @returns La posición de la nota.
 */
export function articleStanding(article: Pick<Article, 'concepts'>): Standing {
  const relevant = article.concepts.filter((c) => c.is_relevant);
  if (relevant.length > 0) {
    return relevant.every((c) => judgementBand(c) === 'unconfirmed') ? 'unconfirmed' : 'relevant';
  }
  if (article.concepts.length === 0) return 'unjudged';
  return article.concepts.some((c) => judgementBand(c) !== 'unrelated') ? 'related' : 'unrelated';
}

/**
 * Si una nota se ve en la lista y en el globo.
 *
 * Sin nada prendido, solo las relevantes (también las «por confirmar»). Con
 * «Incluir las no relevantes», además las cercanas y las que la IA no leyó.
 * Las que descartó la IA (ajenas) solo con su propio botón: eran casi toda la
 * basura que Benji veía en «No relevantes», pero entre ellas también caen
 * notas buenas que la IA juzgó solo por el título (18/11/2026).
 *
 * @param article Nota con sus juicios.
 * @param showIrrelevant Si está prendido «Incluir las no relevantes».
 * @param showDiscarded Si se pidió «Ver las N que descartó la IA».
 * @returns Si la nota se muestra.
 * @example isShown(eternalSoloTitulo, true) // false: hace falta el botón
 */
export function isShown(
  article: Pick<Article, 'concepts'>,
  showIrrelevant: boolean,
  showDiscarded = false,
): boolean {
  const standing = articleStanding(article);
  if (standing === 'relevant' || standing === 'unconfirmed') return true;
  if (standing === 'unrelated') return showDiscarded;
  return showIrrelevant;
}

/**
 * Cuántas notas descartó la IA (las ajenas, menos de 0.3): no se ven hasta
 * que se pide con su botón.
 *
 * @param articles Notas de la búsqueda.
 * @returns Cuántas son.
 * @example discardedCount(notas) // 12 → «Ver las 12 que descartó la IA»
 */
export function discardedCount(articles: readonly Pick<Article, 'concepts'>[]): number {
  return articles.filter((article) => articleStanding(article) === 'unrelated').length;
}

/**
 * Texto del botón que muestra u oculta las que descartó la IA.
 *
 * No dice que «no tratan del tema»: muchas veces la IA solo leyó el título y
 * se equivocó (las de «hacker Eternal», 18/11/2026).
 *
 * @param count Cuántas son (ver `discardedCount`).
 * @param open Si ya se están viendo (el botón las oculta).
 * @returns «Ver las 12 que descartó la IA» u «Ocultar las 12…», o `null` si no hay.
 */
export function discardedToggleLabel(count: number, open: boolean): string | null {
  if (count <= 0) return null;
  const verb = open ? 'Ocultar' : 'Ver';
  return count === 1
    ? `${verb} la nota que descartó la IA`
    : `${verb} las ${String(count)} que descartó la IA`;
}

/** Marca y razón de una nota que no es relevante del todo. */
export interface StandingNote {
  standing: Exclude<Standing, 'relevant'>;
  /** Texto de la marca: «Por confirmar», «Cercana», «Descartada por la IA» o «Sin revisar». */
  badge: string;
  /** Qué quiere decir la marca, para la ayuda al pasar el mouse. */
  hint: string;
  /** La razón de la IA, ya con su rótulo («Por qué no: …»), o `null` si no dio. */
  reason: string | null;
}

const BADGES: Readonly<Record<StandingNote['standing'], { badge: string; hint: string }>> = {
  unconfirmed: {
    badge: 'Por confirmar',
    hint: 'La IA la cree relevante, pero sin estar segura: revísala.',
  },
  related: {
    badge: 'Cercana',
    hint: 'Es del mismo tema, pero no de lo que se pidió (otra persona, otro lugar o de pasada).',
  },
  unrelated: {
    badge: 'Descartada por la IA',
    hint: 'La IA dijo que no es de lo que se buscó. Puede equivocarse: revísala.',
  },
  unjudged: {
    badge: 'Sin revisar',
    hint: 'La IA no la leyó (pasó del tope de notas o hubo una falla): no se sabe si sirve.',
  },
};

// `extraction_status` de una nota que no se pudo abrir: la IA la juzgó con el
// título y el fragmento (backend/app/domain/extraction.py, ExtractionStatus).
const TITLE_ONLY = 'fallback';
// Se suma a la ayuda de las no relevantes juzgadas así: es donde más se
// equivoca la IA (las 6 de «hacker Eternal», 18/11/2026).
const TITLE_ONLY_HINT = 'La IA no pudo leer la nota completa: solo vio el título y el fragmento.';

/**
 * La marca y la razón de la IA de una nota «por confirmar», cercana,
 * descartada o sin revisar; para las relevantes no hace falta decir nada.
 *
 * La razón es la del juicio que decide la banda: el relevante con más puntaje
 * («Razón de la IA: …») o, si ninguno lo es, el no relevante con más puntaje
 * («Por qué no: …»). Si una no relevante se juzgó sin leer la nota completa,
 * la ayuda lo dice.
 *
 * @param article Nota con sus juicios (y cómo se leyó, si se sabe).
 * @returns La marca, o `null` si la nota es relevante.
 * @example standingNote(cercana)?.reason // 'Por qué no: Habla de extorsión en Morelos, no en Jalisco.'
 */
export function standingNote(
  article: Pick<Article, 'concepts'> & Partial<Pick<Article, 'extraction_status'>>,
): StandingNote | null {
  const standing = articleStanding(article);
  if (standing === 'relevant') return null;
  const relevant = standing === 'unconfirmed';
  const best = [...article.concepts]
    .filter((c) => c.is_relevant === relevant)
    .sort((a, b) => b.relevance_score - a.relevance_score)[0];
  const text = best?.relevance_reason?.trim();
  const prefix = relevant ? 'Razón de la IA' : 'Por qué no';
  const { badge, hint } = BADGES[standing];
  const titleOnly =
    (standing === 'related' || standing === 'unrelated') &&
    article.extraction_status === TITLE_ONLY;
  return {
    standing,
    badge,
    hint: titleOnly ? `${hint} ${TITLE_ONLY_HINT}` : hint,
    reason: text ? `${prefix}: ${text}` : null,
  };
}
