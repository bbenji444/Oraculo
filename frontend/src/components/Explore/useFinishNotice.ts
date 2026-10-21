/**
 * Avisa cuando la búsqueda que se está viendo termina (§14.3).
 *
 * Una búsqueda tarda de 20 s a un par de minutos; mientras, la persona suele
 * irse a otra pestaña. Al terminar:
 * - devuelve el aviso para mostrarlo unos segundos dentro de la app;
 * - si la pestaña está oculta, cambia su título ("✓ Búsqueda lista: 18 notas")
 *   y lo regresa cuando la persona vuelve.
 *
 * Solo avisa si la vio correr: reabrir una búsqueda vieja del Historial no
 * dispara nada. No hace llamadas HTTP: recibe la búsqueda ya consultada.
 */
import { useEffect, useRef, useState } from 'react';

import { isFinished, type Search } from '../../services/searches';
import { type FinishNotice, finishNotice } from './format';

// Tiempo en pantalla del aviso: suficiente para leerlo sin estorbar.
export const NOTICE_MS = 8000;
// Marca del título de la pestaña: se ve aunque la pestaña esté angosta.
const TITLE_MARK: Record<FinishNotice['tone'], string> = { ok: '✓', warn: '⚠', error: '✕' };

/**
 * @param search Búsqueda abierta (de `useSearch`), o `undefined` si no hay.
 * @returns El aviso mientras se muestra, o `null`; y una función para cerrarlo.
 */
export function useFinishNotice(search: Search | undefined): {
  notice: FinishNotice | null;
  dismiss: () => void;
} {
  const [notice, setNotice] = useState<FinishNotice | null>(null);
  // Última búsqueda vista corriendo: solo esa puede avisar al terminar.
  const runningId = useRef<string | null>(null);

  useEffect(() => {
    if (!search) return;
    if (!isFinished(search.status)) {
      runningId.current = search.search_id;
      return;
    }
    if (runningId.current !== search.search_id) return;
    runningId.current = null;
    const next = finishNotice(search);
    setNotice(next);
    if (!document.hidden) return;
    const original = document.title;
    document.title = `${TITLE_MARK[next.tone]} ${next.text}`;
    const restore = () => {
      if (document.hidden) return;
      document.title = original;
      document.removeEventListener('visibilitychange', restore);
    };
    document.addEventListener('visibilitychange', restore);
  }, [search]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => {
      setNotice(null);
    }, NOTICE_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [notice]);

  return {
    notice,
    dismiss: () => {
      setNotice(null);
    },
  };
}
