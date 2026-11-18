/**
 * Avisos discretos de una búsqueda (ADR-0115): «Sin créditos de Google web:
 * se buscó en noticias» o que la cuenta de SearchApi no respondió.
 *
 * Juntan el aviso con que respondió la búsqueda rápida al lanzarse
 * (`QuickSearchStartedOut.notice`, guardado en `useQuickSearchStore`) y el que
 * deja el worker en el avance (`progress.notice`). Los muestran el avance de
 * la consola, el expediente y el panel del diseño clásico, mientras corre y
 * después: sin ellos el analista no sabía por qué no salían Facebook, X ni
 * YouTube (revisión del 18/11/2026).
 *
 * No hace: no pide datos ni decide los textos (los manda el servidor).
 */
import { type Search, searchNotices } from '../../services/searches';
import { useQuickSearchStore } from '../../store/quickSearch';
import { Icon } from '../ui/Icon';

interface SearchNoticesProps {
  search: Pick<Search, 'search_id' | 'progress'>;
  className?: string;
}

/**
 * Renglones en letra chica con los avisos de la búsqueda.
 *
 * @param props La búsqueda y clases extra.
 * @returns Los avisos, o nada si no hay.
 */
export function SearchNotices({ search, className = '' }: SearchNoticesProps) {
  const launched = useQuickSearchStore((s) => s.last);
  const notices = searchNotices(search, launched);
  if (notices.length === 0) return null;
  return (
    <ul aria-label="Avisos de la búsqueda" className={`space-y-0.5 ${className}`}>
      {notices.map((notice) => (
        <li key={notice} className="search-notice">
          <Icon name="warning" className="search-notice-icon" />
          <span className="min-w-0">{notice}</span>
        </li>
      ))}
    </ul>
  );
}
