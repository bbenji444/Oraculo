/**
 * Reglas de la caja de "chips" de palabras clave y exclusiones.
 *
 * Solo ayudan a escribir: pegar una lista separada por comas o renglones,
 * no repetir palabras y ver los problemas antes de guardar. La validación
 * definitiva la hace el backend (app/domain/concept.py).
 */

/**
 * Normaliza un término para compararlo como lo hace el backend: mayúsculas,
 * sin acentos ni diéresis, conservando la Ñ, sin espacios repetidos.
 *
 * @param term Palabra o frase.
 * @returns El término normalizado.
 * @example normalizeTerm('Hackéo') // 'HACKEO'; normalizeTerm('niño') // 'NIÑO'
 */
export function normalizeTerm(term: string): string {
  const decomposed = term.toUpperCase().normalize('NFD');
  let kept = '';
  for (const char of decomposed) {
    // ̃ es la tilde de la Ñ: se conserva solo si sigue a una N.
    if (/\p{M}/u.test(char)) {
      if (char === '̃' && kept.endsWith('N')) kept += char;
      continue;
    }
    kept += char;
  }
  return kept.normalize('NFC').split(/\s+/).filter(Boolean).join(' ');
}

/**
 * Agrega lo que la persona escribió o pegó a la lista, sin repetir.
 *
 * @param current Términos actuales.
 * @param text Texto nuevo; puede traer varios separados por coma o renglón.
 * @returns La lista nueva (los repetidos se ignoran sin avisar).
 */
export function addTerms(current: readonly string[], text: string): string[] {
  const seen = new Set(current.map(normalizeTerm));
  const result = [...current];
  for (const raw of text.split(/[,\n]/)) {
    const term = raw.split(/\s+/).filter(Boolean).join(' ');
    const norm = normalizeTerm(term);
    if (term === '' || seen.has(norm)) continue;
    seen.add(norm);
    result.push(term);
  }
  return result;
}

// Mismos caracteres que rechaza el backend: arman frases, grupos y
// operadores en los buscadores (ADR-0009).
const FORBIDDEN = /["()“”:]/;

/**
 * Aviso inmediato para un término que el backend rechazaría.
 *
 * @param term Término.
 * @returns El motivo en español, o `null` si se ve bien.
 */
export function termWarning(term: string): string | null {
  if (FORBIDDEN.test(term)) return 'Sin comillas, paréntesis ni dos puntos.';
  if (term.startsWith('-')) return 'Para excluir, agrégala en Exclusiones.';
  if (/(^|\s)(OR|AND)(\s|$)/i.test(term)) return '"OR" y "AND" son órdenes para los buscadores.';
  if (term.length < 2) return 'Mínimo 2 caracteres.';
  return null;
}
