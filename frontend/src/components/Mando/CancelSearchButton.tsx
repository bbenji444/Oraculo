/**
 * «Cancelar búsqueda» mientras el barrido corre (19/11/2026, ADR-0118).
 *
 * Benji: «tiene que estar la opción de cancelar búsqueda por si me equivoqué
 * en algo o necesito regresar y editar». Al cancelar, la consola vuelve a
 * «Ajustar consulta» con lo mismo que se pidió, para corregirlo y lanzarlo
 * otra vez.
 *
 * Lo usa la consola del Centro de mando (`MissionDock`). No hace: no borra la
 * búsqueda (queda en Historial como «cancelada», con lo que alcanzó a gastar)
 * ni se ofrece en las corridas automáticas, que no se cancelan.
 */
import { useCancelSearch } from '../../hooks/useSearches';
import type { Search } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { useMandoStore } from '../../store/mando';
import { Icon } from '../ui/Icon';

function backToConsole() {
  useMandoStore.getState().setEditing(true);
  // Como «Ajustar consulta»: el globo vuelve a la vista general.
  useExplorerStore.getState().showOverview();
}

export function CancelSearchButton({ search }: { search: Search }) {
  const cancel = useCancelSearch(backToConsole);
  if (search.trigger === 'automatic') return null;
  return (
    <>
      {cancel.error && (
        <span role="alert" className="text-xs text-rose-300">
          {cancel.error.message}
        </span>
      )}
      <button
        type="button"
        disabled={cancel.isPending}
        onClick={() => {
          cancel.mutate(search.search_id);
        }}
        title="Detener la búsqueda y volver a la consulta para corregirla"
        className="hud-btn hud-btn--sm hud-btn--danger shrink-0"
      >
        <Icon name="close" /> {cancel.isPending ? 'Cancelando…' : 'Cancelar búsqueda'}
      </button>
    </>
  );
}
