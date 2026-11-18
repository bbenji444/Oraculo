/**
 * Lógica del formulario de conceptos que no depende de React (ADR-0109).
 *
 * Qué textos lleva cada modo de búsqueda y cómo se aplica la propuesta de la
 * IA al borrador. Así se prueba sin dibujar el formulario.
 *
 * No hace: no llama a la API ni guarda nada.
 */
import type { ConceptInput, QueryMode, TermSuggestion } from '../../services/concepts';

/** Textos de un modo: el botón, qué hace y cómo se llaman sus campos. */
export interface ModeCopy {
  label: string;
  explanation: string;
  descriptionLabel: string;
  descriptionHint: string | null;
  keywordsLabel: string;
  keywordsHint: string;
}

export const MODE_COPY: Record<QueryMode, ModeCopy> = {
  open: {
    label: 'Como en Google',
    explanation:
      'Cada frase se busca sola y sin comillas, como en Google. Trae más notas, y la IA descarta las que no tratan de lo que escribiste.',
    descriptionLabel: 'Lo que buscas, en tus palabras',
    descriptionHint: 'La IA juzga cada nota contra este texto.',
    keywordsLabel: 'Frases',
    // 12 = OPEN_MAX_PHRASES del backend: cada frase es una consulta.
    keywordsHint:
      'Cada frase es una búsqueda (hasta 12). Mejor de 2 o 3 palabras, como un titular: «roban autos», «hallan fosa». Enter o coma para agregar.',
  },
  exact: {
    label: 'Frases exactas',
    explanation:
      'Cada frase se busca tal cual, entre comillas. Trae menos notas, pero más precisas. Así se buscan la FGR y los temas.',
    descriptionLabel: 'Descripción',
    descriptionHint: null,
    keywordsLabel: 'Palabras clave',
    keywordsHint:
      'Una nota entra si menciona cualquiera. Enter o coma para agregar; puedes pegar una lista.',
  },
};

/** Orden de los botones del selector: primero el recomendado para lo nuevo. */
export const MODE_OPTIONS: readonly { value: QueryMode; label: string }[] = [
  { value: 'open', label: MODE_COPY.open.label },
  { value: 'exact', label: MODE_COPY.exact.label },
];

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
