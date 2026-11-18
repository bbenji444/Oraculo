/**
 * Lógica del formulario de conceptos que no depende de React (ADR-0109, ADR-0110).
 *
 * Qué textos lleva cada modo de búsqueda, cómo se aplica la propuesta de la
 * IA al borrador y cuándo hay que pedírsela al guardar. Así se prueba sin
 * dibujar el formulario.
 *
 * No hace: no llama a la API ni guarda nada.
 */
import type { ConceptInput, QueryMode, TermSuggestion } from '../../services/concepts';

/** Textos de un modo: qué hace y cómo se llaman sus campos. */
export interface ModeCopy {
  /** Una línea que dice cómo se busca; solo se muestra en los exactos. */
  explanation: string | null;
  descriptionLabel: string;
  descriptionHint: string;
  keywordsLabel: string;
  keywordsHint: string;
}

export const MODE_COPY: Record<QueryMode, ModeCopy> = {
  open: {
    explanation: null,
    descriptionLabel: '¿Qué noticias quieres seguir?',
    descriptionHint:
      'Escríbelo como se lo contarías a un colega. La IA juzga cada nota contra este texto.',
    keywordsLabel: 'Frases de búsqueda',
    // 12 = OPEN_MAX_PHRASES del backend: cada frase es una consulta.
    keywordsHint:
      'Opcional: si las dejas vacías, la IA las propone al guardar. Cada frase es una búsqueda (hasta 12), mejor de 2 o 3 palabras: «roban autos», «hallan fosa».',
  },
  exact: {
    // Solo los que ya existían (FGR, subdivisiones): los nuevos son abiertos.
    explanation:
      'Este concepto se busca con frases exactas, entre comillas, como la FGR y las subdivisiones.',
    descriptionLabel: 'Descripción (opcional)',
    descriptionHint: 'Para quien lo lea en la lista.',
    keywordsLabel: 'Palabras clave',
    keywordsHint:
      'Una nota entra si menciona cualquiera. Enter o coma para agregar; puedes pegar una lista.',
  },
};

/**
 * Pone la propuesta de la IA en el borrador.
 *
 * Las frases y exclusiones se reemplazan (la persona pidió otra propuesta).
 * El nombre solo se llena si estaba vacío, para no borrar el que ya escribió.
 *
 * @param draft Borrador actual del formulario.
 * @param suggestion Lo que propuso la IA.
 * @returns El borrador con la propuesta.
 * @example applySuggestion({ ...draft, name: '' }, propuesta).name // 'Robo de vehículos'
 */
export function applySuggestion(draft: ConceptInput, suggestion: TermSuggestion): ConceptInput {
  return {
    ...draft,
    name: draft.name.trim() === '' ? suggestion.name : draft.name,
    keywords: suggestion.keywords,
    exclude_terms: suggestion.exclude_terms,
    query_mode: suggestion.query_mode,
  };
}

/**
 * Si al guardar hay que pedirle a la IA lo que falta.
 *
 * Basta con escribir qué noticias se quieren seguir: si faltan el nombre o
 * las frases, la IA los propone antes de guardar (ADR-0110). Los conceptos
 * exactos no se tocan.
 *
 * @param draft Borrador del formulario.
 * @returns `true` si es «como en Google», tiene descripción y le falta algo.
 */
export function needsProposal(draft: ConceptInput): boolean {
  if (draft.query_mode !== 'open' || draft.description.trim() === '') return false;
  return draft.name.trim() === '' || draft.keywords.length === 0;
}

/**
 * Llena solo lo que falta con la propuesta de la IA, sin pisar lo escrito.
 *
 * @param draft Borrador del formulario.
 * @param suggestion Lo que propuso la IA.
 * @returns El borrador con nombre y frases; las exclusiones de la IA solo
 *   entran si también se usan sus frases.
 */
export function fillMissing(draft: ConceptInput, suggestion: TermSuggestion): ConceptInput {
  const useTerms = draft.keywords.length === 0;
  return {
    ...draft,
    name: draft.name.trim() === '' ? suggestion.name : draft.name,
    keywords: useTerms ? suggestion.keywords : draft.keywords,
    exclude_terms:
      useTerms && draft.exclude_terms.length === 0 ? suggestion.exclude_terms : draft.exclude_terms,
  };
}
