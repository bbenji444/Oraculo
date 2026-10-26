/**
 * Temas de la cronología (F12.7, ADR-0032): junta los hechos que hablan de la
 * misma persona o caso para que no llenen la lista.
 *
 * Por qué: en la corrida FGR del 26/10/2026, 34 de 87 hechos eran del caso
 * Jáuregui (la carta, la caravana, la vinculación, las columnas...). Son
 * hechos distintos y no deben fundirse en una historia (ADR-0026), pero 34
 * renglones seguidos tapan todo lo demás. Aquí se vuelven un solo bloque
 * «Jáuregui · 34 hechos» que se despliega.
 *
 * Regla (sin IA, calibrada con esa corrida): un **nombre propio** es una
 * palabra con mayúscula inicial que no abre el título («Vinculan a Jáuregui»).
 * Si el mismo nombre sale en al menos `THEME_MIN_ITEMS` hechos, es un tema.
 * No cuentan los nombres de lugar (los estados y los lugares de las notas: el
 * filtro por estado ya hace eso) ni palabras de oficio («Fiscalía»,
 * «Gobierno»). Cada hecho va al tema más grande que nombra, aunque su título
 * venga en mayúsculas.
 *
 * No hace: no pide datos ni dibuja (lo usa `Chronology.tsx`).
 */
import type { StoryItem } from './timelineData';
import { STATE_NAMES } from './timelineData';

/** Hechos que necesita un nombre para ser tema (Jáuregui: 34; el siguiente, 3). */
export const THEME_MIN_ITEMS = 5;
// Las palabras más cortas casi nunca son un nombre que distinga («Gran», «Caso»).
const MIN_NAME_LENGTH = 4;
// Palabras con mayúscula que no son una persona ni un caso: instituciones,
// cargos y relleno de títulos. Sin acentos y en mayúsculas.
const NOT_A_THEME = new Set([
  'FISCALIA',
  'GENERAL',
  'REPUBLICA',
  'GOBIERNO',
  'ESTADO',
  'NACIONAL',
  'NOTICIAS',
  'GUARDIA',
  'MARINA',
  'EJERCITO',
  'SECRETARIA',
  'CIUDAD',
  'MEXICO',
  'MUNICIPIO',
  'PODER',
  'JUDICIAL',
  'SENADO',
  'CAMARA',
  'CONGRESO',
  'PALACIO',
]);
const WORD = /[\p{L}]+/gu;

/** Un bloque de hechos que nombran a la misma persona o caso. */
export interface ThemeBlock {
  kind: 'theme';
  /** Clave sin acentos («JAUREGUI»). */
  key: string;
  /** Cómo se muestra: la forma más común en los títulos («Jáuregui»). */
  label: string;
  /** Sus hechos, del más reciente al más viejo. */
  items: StoryItem[];
  /** El más reciente de sus hechos (milisegundos UTC): ahí se coloca el bloque. */
  at: number;
  /** Día del más reciente, como `StoryItem.day`. */
  day: string;
  /** Cuántas notas suman sus hechos. */
  notes: number;
}

/** Un renglón de la cronología: un hecho suelto o un tema. */
export type ChronologyRow = ({ kind: 'item' } & StoryItem) | ThemeBlock;

/** Mayúsculas sin acentos (conserva la Ñ, como `name_norm`). */
export function foldName(word: string): string {
  // Letra por letra, salvo la Ñ: NFD la partiría en N + tilde.
  return word
    .toUpperCase()
    .normalize('NFC')
    .replace(/[^Ñ]/gu, (char) => char.normalize('NFD').replace(/\p{Mn}/gu, ''));
}

/** Los nombres propios de un título: mayúscula inicial y no la primera palabra. */
function namesIn(title: string): Map<string, string> {
  const names = new Map<string, string>();
  const words = title.match(WORD) ?? [];
  words.forEach((word, index) => {
    if (index === 0 || word.length < MIN_NAME_LENGTH) return;
    const first = word.charAt(0);
    const rest = word.slice(1);
    // «Jáuregui» sí; «FGR» o «AGRADECE» (título en mayúsculas) no deciden.
    if (first !== first.toUpperCase() || rest === rest.toUpperCase()) return;
    names.set(foldName(word), word);
  });
  return names;
}

function placeWords(items: readonly StoryItem[]): Set<string> {
  const words = new Set<string>();
  const add = (text: string | null | undefined) => {
    for (const word of text?.match(WORD) ?? []) words.add(foldName(word));
  };
  Object.values(STATE_NAMES).forEach(add);
  for (const item of items) for (const note of item.notes) add(note.primary_location?.place);
  return words;
}

function wordsOf(title: string): Set<string> {
  return new Set((title.match(WORD) ?? []).map(foldName));
}

/**
 * Junta en temas los hechos que nombran a la misma persona o caso.
 *
 * @param items Hechos de la cronología, del más reciente al más viejo.
 * @returns Los renglones en el mismo orden: cada tema ocupa el lugar de su
 *   hecho más reciente y los demás hechos quedan sueltos.
 *
 * @example
 *   groupThemes(storyItems(notas)) // [{kind: 'theme', label: 'Jáuregui', items: [34]}, ...]
 */
export function groupThemes(items: readonly StoryItem[]): ChronologyRow[] {
  const places = placeWords(items);
  const counts = new Map<string, number>();
  const spellings = new Map<string, Map<string, number>>();
  for (const item of items) {
    for (const [key, spelling] of namesIn(item.lead.title)) {
      if (places.has(key) || NOT_A_THEME.has(key)) continue;
      counts.set(key, (counts.get(key) ?? 0) + 1);
      const forms = spellings.get(key) ?? new Map<string, number>();
      forms.set(spelling, (forms.get(spelling) ?? 0) + 1);
      spellings.set(key, forms);
    }
  }
  const candidates = [...counts.entries()]
    .filter(([, count]) => count >= THEME_MIN_ITEMS)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (candidates.length === 0) return items.map((item) => ({ kind: 'item', ...item }));

  // Cada hecho va al tema más grande que nombra (en cualquier caja de letra).
  const members = new Map<string, StoryItem[]>();
  for (const item of items) {
    const words = wordsOf(item.lead.title);
    const theme = candidates.find(([key]) => words.has(key));
    if (theme) members.set(theme[0], [...(members.get(theme[0]) ?? []), item]);
  }
  const blocks = new Map<string, ThemeBlock>();
  for (const [key, list] of members) {
    if (list.length < THEME_MIN_ITEMS) continue;
    const forms = [...(spellings.get(key) ?? new Map<string, number>()).entries()];
    const label = forms.sort((a, b) => b[1] - a[1])[0]?.[0] ?? key;
    const latest = list[0];
    if (!latest) continue;
    blocks.set(key, {
      kind: 'theme',
      key,
      label,
      items: list,
      at: latest.at,
      day: latest.day,
      notes: list.reduce((total, item) => total + item.articleIds.length, 0),
    });
  }

  const rows: ChronologyRow[] = [];
  const placed = new Set<string>();
  const themeOf = new Map<StoryItem, string>();
  for (const [key, block] of blocks) for (const item of block.items) themeOf.set(item, key);
  for (const item of items) {
    const key = themeOf.get(item);
    if (key === undefined) {
      rows.push({ kind: 'item', ...item });
    } else if (!placed.has(key)) {
      placed.add(key);
      const block = blocks.get(key);
      if (block) rows.push(block);
    }
  }
  return rows;
}
