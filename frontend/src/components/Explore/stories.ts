/**
 * Junta las notas de la misma historia (el mismo hecho en varios medios,
 * ADR-0026) para que la lista muestre una tarjeta por historia con
 * «▸ +N medios». Lógica pura: no sabe de React ni del store.
 *
 * No hace: no decide qué notas son la misma historia (eso lo calcula el
 * backend y llega en `story_id`).
 */
import type { Article } from '../../services/searches';

/** Una tarjeta de la lista: la nota que se muestra y las demás de su historia. */
export interface StoryGroup {
  /** La primera de la historia en el orden de la lista. */
  lead: Article;
  /** Las demás notas visibles de la misma historia, en el orden de la lista. */
  others: Article[];
}

/**
 * Agrupa las notas visibles por `story_id`, respetando el orden de la lista:
 * cada historia aparece donde aparece su primera nota.
 *
 * @param articles Notas visibles, ya filtradas y ordenadas.
 * @returns Una tarjeta por historia; las notas solas, una tarjeta cada una.
 * @example
 * groupByStory([a1, b1, a2]) // a1 y a2 con story_id 7
 * // → [{ lead: a1, others: [a2] }, { lead: b1, others: [] }]
 */
export function groupByStory(articles: readonly Article[]): StoryGroup[] {
  const groups: StoryGroup[] = [];
  const byStory = new Map<number, StoryGroup>();
  for (const article of articles) {
    const storyId = article.story_id ?? null;
    const existing = storyId === null ? undefined : byStory.get(storyId);
    if (existing) {
      existing.others.push(article);
      continue;
    }
    const group: StoryGroup = { lead: article, others: [] };
    groups.push(group);
    if (storyId !== null) byStory.set(storyId, group);
  }
  return groups;
}

/**
 * Texto del botón que despliega la historia.
 *
 * @param count Cuántas notas más hay en la historia.
 * @returns «+1 medio» o «+3 medios».
 */
export function moreOutletsLabel(count: number): string {
  return `+${String(count)} ${count === 1 ? 'medio' : 'medios'}`;
}
