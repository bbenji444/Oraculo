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
 * En el celular (Benji, 11/11/2026: «no se tiene que andar amontonando todo»)
 * no caben juntos: la consola y el expediente se turnan. Con resultados, el
 * expediente ocupa la pantalla y la consola queda como una pastilla abajo; al
 * tocarla, la consola se abre y el expediente se pliega a su pestaña.
 *
 * No hace: no pide datos ni decide qué notas se ven; ExplorePage se las pasa,
 * las mismas que al globo.
 */
import { useEffect, useRef, useState } from 'react';

import { useMediaQuery } from '../../hooks/useMediaQuery';
import type { Article, Search } from '../../services/searches';
import { useExplorerStore } from '../../store/explorer';
import { useMandoStore } from '../../store/mando';
import { GlobeControls, MyCasesToggle, PrecisionLegend } from '../Explore/Controls';
import { PHONE_QUERY } from '../Explore/ui';
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
  const phone = useMediaQuery(PHONE_QUERY, false);
  const dossierOpen = useMandoStore((s) => s.dossierOpen);
  const minimized = useMandoStore((s) => s.dockMinimized);
  const dockHeight = useMandoStore((s) => s.dockHeight);
  const dossierShown = hasResults && dossierOpen;
  const wasMinimized = useRef(minimized);

  // Celular: al abrirse el expediente, la consola se hace pastilla.
  useEffect(() => {
    if (phone && dossierShown) useMandoStore.getState().setDockMinimized(true);
  }, [phone, dossierShown]);

  // Celular: mientras se ve una noticia, el expediente se aparta para que se
  // vea el globo volar a su lugar; al cerrarla, regresa (Benji, 11/11/2026).
  const articleId = useExplorerStore((s) => s.articleId);
  const hiddenForArticle = useRef(false);
  useEffect(() => {
    const store = useMandoStore.getState();
    if (phone && articleId !== null && store.dossierOpen) {
      hiddenForArticle.current = true;
      store.setDossierOpen(false);
    }
    if (articleId === null && hiddenForArticle.current) {
      hiddenForArticle.current = false;
      store.setDossierOpen(true);
    }
  }, [phone, articleId]);

  // Celular: al abrir la consola desde la pastilla, el expediente se pliega.
  // Solo en ese cambio (de pastilla a consola), no al llegar a la pantalla.
  useEffect(() => {
    if (phone && hasResults && wasMinimized.current && !minimized) {
      useMandoStore.getState().setDossierOpen(false);
    }
    wasMinimized.current = minimized;
  }, [phone, hasResults, minimized]);

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
          bottomReserve={phone ? dockHeight : undefined}
        />
      )}

      <div
        className="pointer-events-none absolute bottom-4 left-4 flex justify-center"
        style={{ right: rightReserve + DOCK_MARGIN_PX }}
      >
        <div ref={dockRef} className="pointer-events-auto relative w-full max-w-[62rem]">
          <MissionDock active={active} />
        </div>
      </div>

      {phone && !dossierShown && <PhoneGlobeMenu />}

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

/**
 * Celular: «Mis casos», giro, día o noche, velocidad y la leyenda caben en un
 * botón redondo arriba a la izquierda; al tocarlo se despliegan (Benji,
 * 11/11/2026: «de una manera muy comprimida»).
 */
function PhoneGlobeMenu() {
  const [open, setOpen] = useState(false);
  return (
    <div className="pointer-events-none absolute left-3 top-3 z-20 flex flex-col items-start gap-2">
      <button
        type="button"
        aria-expanded={open}
        aria-label={open ? 'Cerrar las opciones del globo' : 'Opciones del globo'}
        title="Opciones del globo"
        onClick={() => {
          setOpen((current) => !current);
        }}
        className="globo-menu-boton pointer-events-auto"
      >
        <svg
          viewBox="0 0 24 24"
          width="18"
          height="18"
          aria-hidden="true"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
        >
          {open ? (
            <path d="M6 6l12 12M18 6 6 18" />
          ) : (
            <>
              <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
              <circle cx="16" cy="7" r="2" />
              <circle cx="10" cy="17" r="2" />
            </>
          )}
        </svg>
      </button>
      {open && (
        <div className="globo-menu pointer-events-auto flex max-w-[calc(100vw-1.5rem)] flex-col items-start gap-2">
          <div className="flex flex-wrap gap-2">
            <MyCasesToggle />
          </div>
          <GlobeControls />
          <PrecisionLegend />
        </div>
      )}
    </div>
  );
}
