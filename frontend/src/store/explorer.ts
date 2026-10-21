/**
 * Estado de la pantalla Explorar: una sola fuente de verdad (especificación §14.2).
 *
 * El globo, las migas de pan, los filtros encadenados, el panel de búsqueda y
 * la lista leen y escriben aquí: elegir una región en el mapa o en el filtro
 * es la misma acción, así nunca se desincronizan.
 *
 * Día/noche y la velocidad de las animaciones se recuerdan en el navegador
 * (si el navegador no deja guardar, simplemente no se recuerdan).
 *
 * No hace: no pide datos a la API (eso son los hooks de TanStack Query).
 */
import { create } from 'zustand';
import { createJSONStorage, persist, type StateStorage } from 'zustand/middleware';

import { type MotionPreset } from '../map/motion';
import { prefersReducedMotion } from '../map/spin';
import type { EarthMode } from '../map/style';
import type { InRegionFilter, SearchInput } from '../services/searches';

/** Rango de fechas del panel (§14.3): hoy, 7 días, 30 días o personalizado. */
export type RangeKind = 'today' | '7' | '30' | 'custom';

export interface DateRange {
  kind: RangeKind;
  /** AAAA-MM-DD, solo en "personalizado". */
  from?: string;
  to?: string;
}

/** Pestaña de la lista: todas, dentro, fuera o sin ubicación. */
export type ListFilter = 'all' | InRegionFilter;

export interface ExplorerState {
  regionId: number | null;
  conceptIds: number[];
  range: DateRange;
  searchId: string | null;
  articleId: number | null;
  /**
   * Cuántas veces se ha pedido ver una nota. Volver a elegir la misma nota no
   * cambia `articleId`, pero sí esto: así el globo vuelve a volar hacia ella.
   */
  articleRequest: number;
  listFilter: ListFilter;
  /** Interruptor "No relevantes": vale para la lista y el globo a la vez. */
  showIrrelevant: boolean;
  /** Panel izquierdo visible; se oculta para ver el globo completo. */
  panelOpen: boolean;
  earth: EarthMode;
  motion: MotionPreset;
  spinning: boolean;
  /** Último caso al que se agregó una nota: va primero en «Agregar al caso» (9.3). */
  lastCaseId: string | null;
  selectRegion: (regionId: number | null) => void;
  toggleConcept: (conceptId: number) => void;
  setRange: (range: DateRange) => void;
  openSearch: (searchId: string | null) => void;
  /** Reabre una búsqueda guardada con su región, conceptos y fechas (Historial). */
  restoreSearch: (search: {
    searchId: string;
    regionId: number;
    conceptIds: number[];
    dateFrom: string;
    dateTo: string;
  }) => void;
  selectArticle: (articleId: number | null) => void;
  setListFilter: (filter: ListFilter) => void;
  setShowIrrelevant: (showIrrelevant: boolean) => void;
  setPanelOpen: (panelOpen: boolean) => void;
  setEarth: (earth: EarthMode) => void;
  setMotion: (motion: MotionPreset) => void;
  setSpinning: (spinning: boolean) => void;
  setLastCaseId: (caseId: string) => void;
}

// Días de cada rango rápido; "hoy" es el último día (la API cuenta hasta hoy).
const RANGE_DAYS: Record<Exclude<RangeKind, 'custom'>, number> = { today: 1, '7': 7, '30': 30 };

/**
 * Cuerpo para estimar o lanzar la búsqueda, o `null` si aún falta algo.
 *
 * @example searchInput({ regionId: 272, conceptIds: [3], range: { kind: '7' } })
 * // { region_id: 272, concept_ids: [3], days: 7 }
 */
export function searchInput(
  state: Pick<ExplorerState, 'regionId' | 'conceptIds' | 'range'>,
): SearchInput | null {
  if (state.regionId === null || state.conceptIds.length === 0) return null;
  const base = {
    region_id: state.regionId,
    concept_ids: [...state.conceptIds].sort((a, b) => a - b),
  };
  if (state.range.kind !== 'custom') return { ...base, days: RANGE_DAYS[state.range.kind] };
  if (!state.range.from || !state.range.to) return null;
  return { ...base, date_from: state.range.from, date_to: state.range.to };
}

// localStorage puede no existir o fallar (modo privado, almacenamiento lleno):
// entonces la preferencia vale solo mientras dura la página.
const safeStorage: StateStorage = {
  getItem: (name) => {
    try {
      return window.localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem: (name, value) => {
    try {
      window.localStorage.setItem(name, value);
    } catch {
      // Sin almacenamiento disponible: no se recuerda, y no pasa nada más.
    }
  },
  removeItem: (name) => {
    try {
      window.localStorage.removeItem(name);
    } catch {
      // Igual que arriba.
    }
  },
};

export const useExplorerStore = create<ExplorerState>()(
  persist(
    (set) => ({
      regionId: null,
      conceptIds: [],
      range: { kind: '7' },
      searchId: null,
      articleId: null,
      articleRequest: 0,
      listFilter: 'all',
      showIrrelevant: false,
      panelOpen: true,
      earth: 'night',
      // "Menos movimiento" del sistema manda sobre la preferencia guardada.
      motion: prefersReducedMotion() ? 'off' : 'normal',
      spinning: !prefersReducedMotion(),
      lastCaseId: null,
      selectRegion: (regionId) => {
        // Elegir una región detiene el giro: la cámara vuela hacia ella.
        set(regionId === null ? { regionId } : { regionId, spinning: false });
      },
      toggleConcept: (conceptId) => {
        set((state) => ({
          conceptIds: state.conceptIds.includes(conceptId)
            ? state.conceptIds.filter((id) => id !== conceptId)
            : [...state.conceptIds, conceptId],
        }));
      },
      setRange: (range) => {
        set({ range });
      },
      openSearch: (searchId) => {
        // Otra búsqueda: se olvidan la nota elegida y los filtros de la lista.
        set({ searchId, articleId: null, listFilter: 'all', showIrrelevant: false });
      },
      restoreSearch: ({ searchId, regionId, conceptIds, dateFrom, dateTo }) => {
        set({
          searchId,
          regionId,
          conceptIds,
          range: { kind: 'custom', from: dateFrom, to: dateTo },
          articleId: null,
          listFilter: 'all',
          showIrrelevant: false,
          spinning: false,
        });
      },
      selectArticle: (articleId) => {
        set((state) =>
          articleId === null
            ? { articleId }
            : { articleId, articleRequest: state.articleRequest + 1, spinning: false },
        );
      },
      setListFilter: (listFilter) => {
        set({ listFilter });
      },
      setShowIrrelevant: (showIrrelevant) => {
        set({ showIrrelevant });
      },
      setPanelOpen: (panelOpen) => {
        set({ panelOpen });
      },
      setEarth: (earth) => {
        set({ earth });
      },
      setMotion: (motion) => {
        set(motion === 'off' ? { motion, spinning: false } : { motion });
      },
      setSpinning: (spinning) => {
        set({ spinning });
      },
      setLastCaseId: (lastCaseId) => {
        set({ lastCaseId });
      },
    }),
    {
      name: 'monitor-noticias:explorar',
      storage: createJSONStorage(() => safeStorage),
      // Solo preferencias de la persona; la búsqueda y la región no se recuerdan.
      // El último caso usado sí: H9.1 agrega varias notas seguidas al mismo caso.
      partialize: (state) => ({
        earth: state.earth,
        motion: state.motion,
        lastCaseId: state.lastCaseId,
      }),
    },
  ),
);
