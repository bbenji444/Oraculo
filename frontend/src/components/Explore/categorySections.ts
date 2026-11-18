/**
 * Secciones por categoría de la lista de noticias (ADR-0109, D5): «Huachicol
 * · 12», «Homicidio · 5»… Con los conceptos «como en Google» llegan más notas
 * de temas distintos, y así el analista ve primero de qué se trata cada grupo.
 * Lógica pura: no sabe de React ni del store.
 *
 * No hace: no filtra ni decide la categoría (la pone la IA al buscar,
 * ADR-0029). Una historia va en la sección de su primera nota.
 */
import { categoryColor } from './categoryColor';
import type { StoryGroup } from './stories';

/** Clave de la sección de las notas que la IA todavía no clasifica. */
export const UNCLASSIFIED_KEY = 'sin-clasificar';
const UNCLASSIFIED_NAME = 'Sin clasificar';

/** Una sección de la lista: una categoría con sus tarjetas. */
export interface CategorySection {
  /** Id de la categoría como texto, o `UNCLASSIFIED_KEY`. */
  key: string;
  name: string;
  /** `#RRGGBB` de la categoría, o el gris si no tiene. */
  color: string;
  /** Tarjetas de la sección, en el orden de la lista. */
  groups: StoryGroup[];
  /** Notas de la sección, contando las de cada historia. */
  count: number;
}

/**
 * Reparte las tarjetas de la lista por la categoría de su primera nota.
 *
 * @param groups Tarjetas de la lista (ver `groupByStory`), ya en su orden.
 * @returns Una sección por categoría, de la que tiene más notas a la que
 *   tiene menos (empate: por nombre). «Sin clasificar» siempre va al final.
 * @example
 * sectionsByCategory([robo1, homicidio1, robo2])
 * // → [{ name: 'Robo', count: 2, … }, { name: 'Homicidio', count: 1, … }]
 */
export function sectionsByCategory(groups: readonly StoryGroup[]): CategorySection[] {
  const byKey = new Map<string, CategorySection>();
  for (const group of groups) {
    const category = group.lead.category ?? null;
    const key = category === null ? UNCLASSIFIED_KEY : String(category.id);
    let section = byKey.get(key);
    if (!section) {
      section = {
        key,
        name: category?.name ?? UNCLASSIFIED_NAME,
        color: categoryColor(category),
        groups: [],
        count: 0,
      };
      byKey.set(key, section);
    }
    section.groups.push(group);
    section.count += 1 + group.others.length;
  }
  return [...byKey.values()].sort(
    (a, b) =>
      Number(a.key === UNCLASSIFIED_KEY) - Number(b.key === UNCLASSIFIED_KEY) ||
      b.count - a.count ||
      a.name.localeCompare(b.name, 'es'),
  );
}

/**
 * @param section Una sección de la lista.
 * @param articleId La nota elegida, o nada.
 * @returns Si la nota está en la sección, como principal o dentro de una historia.
 */
export function containsArticle(section: CategorySection, articleId: number | null): boolean {
  if (articleId === null) return false;
  return section.groups.some(
    (group) =>
      group.lead.article_id === articleId ||
      group.others.some((other) => other.article_id === articleId),
  );
}
