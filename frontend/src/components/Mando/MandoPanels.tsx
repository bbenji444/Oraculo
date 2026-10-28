/**
 * Paneles de Explorar en el diseño «Centro de mando» (diseño 3, 27/10/2026,
 * con `?mando` en la URL). Sustituyen la columna de la izquierda del diseño 2:
 *
 * - abajo al centro, la consola de consulta (MissionDock); mide su alto para que
 *   el globo flote encima;
 * - a la derecha, el expediente con los resultados (Dossier);
 * - arriba a la izquierda, los controles del globo y «Mis casos».
 *
 * El radar y el letrero sobre el globo (ScanOverlay) van aparte, debajo de
 * esta capa, porque se dibujan en el centro del globo y no reciben clics.
 *
 * No hace: no pide datos ni decide qué notas se ven; ExplorePage se las pasa,
 * las mismas que al globo.
 */
import { useEffect, useRef } from 'react';

import type { Article, Search } from '../../services/searches';
import { useMandoStore } from '../../store/mando';
import { GlobeControls, MyCasesToggle, PrecisionLegend } from '../Explore/Controls';
import { Dossier } from './Dossier';
import { MissionDock } from './MissionDock';

// Márgenes de la consola: su distancia al borde de abajo y lo que se deja
// libre entre ella y el globo, en píxeles (bottom-4 de Tailwind = 16 px).
const DOCK_MARGIN_PX = 16;
// El alto se redondea a este paso: así el globo no se mueve por un píxel cada
// vez que cambia una palabra de la frase.
const DOCK_STEP_PX = 24;
/**
 * Lo que ocupa el expediente a la derecha (30rem + su margen), en píxeles. Si
 * cambia, cambia también `sm:w-[30rem]` en Dossier y el corrimiento de los
 * controles del mapa en styles/mando.css.
 */
export const DOSSIER_RESERVE_PX = 30 * 16 + 16;

interface MandoPanelsProps {
  active: boolean;
  search: Search | undefined;
  hasResults: boolean;
  articles: Article[];
  relevant: Article[];
  shown: Article[];
  colors: Map<number, string>;
  /** Píxeles reservados a la derecha (el expediente), para no encimarse. */
  rightReserve: number;
}

export function MandoPanels({
  active,
  search,
  hasResults,
  articles,
  relevant,
  shown,
  colors,
  rightReserve,
}: MandoPanelsProps) {
  const dockRef = useRef<HTMLDivElement>(null);

  // El alto de la consola, para que el globo flote encima de ella.
  useEffect(() => {
    const dock = dockRef.current;
    // Sin ResizeObserver (pruebas en jsdom) el globo no se sube; nada más.
    if (!dock || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => {
      const height = Math.ceil(dock.offsetHeight / DOCK_STEP_PX) * DOCK_STEP_PX;
      const reserve = height + 2 * DOCK_MARGIN_PX;
      if (useMandoStore.getState().dockHeight !== reserve) {
        useMandoStore.getState().setDockHeight(reserve);
      }
    });
    observer.observe(dock);
    return () => {
      observer.disconnect();
    };
  }, []);

  // Cada consulta nueva abre su expediente y deja la consola en su renglón.
  const searchId = search?.search_id;
  useEffect(() => {
    useMandoStore.getState().setDossierOpen(true);
    useMandoStore.getState().setEditing(false);
  }, [searchId]);

  return (
    <>
      {hasResults && search && (
        <Dossier
          search={search}
          articles={articles}
          relevant={relevant}
          shown={shown}
          colors={colors}
        />
      )}

      <div
        className="pointer-events-none absolute bottom-4 left-4 flex justify-center"
        style={{ right: rightReserve + DOCK_MARGIN_PX }}
      >
        <div ref={dockRef} className="pointer-events-auto relative w-full max-w-[54rem]">
          <MissionDock active={active} />
        </div>
      </div>

      <div className="pointer-events-none absolute left-4 top-4 hidden flex-col items-start gap-2 sm:flex">
        <div className="pointer-events-auto flex gap-2">
          <MyCasesToggle />
          <GlobeControls />
        </div>
        <div className="pointer-events-auto">
          <PrecisionLegend />
        </div>
      </div>
    </>
  );
}
