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
  /**
   * Subdivisiones elegidas para la FGR («FGR · Homicidio», ADR-0038); vacía =
   * la FGR completa.
   */
  subdivisionIds: number[];
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
  /**
   * La búsqueda plegada a un renglón («Ocultar ‹»). Es aparte de la
   * cronología, que se pliega con su propio botón (Benji, 26/10/2026).
   */
  searchCollapsed: boolean;
  earth: EarthMode;
  motion: MotionPreset;
  spinning: boolean;
  /** Último caso al que se agregó una nota: va primero en «Agregar al caso» (9.3). */
  lastCaseId: string | null;
  /**
   * Fuentes que encendió el analista (switches, F12.2), o `null` si no ha
   * tocado ninguna: entonces valen las de por defecto del servidor.
   */
  sources: string[] | null;
  /** Caso cuyo muro se ve en el globo (9.6); `null` = Explorar normal. */
  wallCaseId: string | null;
  /** Entidad elegida en el muro: la cámara la orbita y el panel la muestra. */
  wallNodeId: number | null;
  /** Vista alterna del muro: las notas como constelación (9.6, D7). */
  constellation: boolean;
  /** Interruptor «Mis casos»: mis casos como marcadores en el globo (9.6, D9). */
  showCases: boolean;
  /**
   * Cuántas veces se pidió volver a la vista de México («Limpiar globo»): el
   * globo vuela cada vez que cambia.
   */
  homeRequest: number;
  /**
   * A dónde vuela el globo con `homeRequest`: México («Limpiar globo») o la
   * vista del Atlántico girando (Centro de mando, «Nueva consulta» y «Ajustar
   * consulta»; Benji, 28/10/2026).
   */
  homeTarget: HomeTarget;
  selectRegion: (regionId: number | null) => void;
  toggleConcept: (conceptId: number) => void;
  toggleSubdivision: (categoryId: number) => void;
  /** Deja estas subdivisiones (vacía = «Todas»). */
  setSubdivisions: (categoryIds: number[]) => void;
  setRange: (range: DateRange) => void;
  openSearch: (searchId: string | null) => void;
  /** Reabre una búsqueda guardada con su región, conceptos y fechas (Historial). */
  restoreSearch: (search: {
    searchId: string;
    regionId: number;
    conceptIds: number[];
    dateFrom: string;
    dateTo: string;
    /** Fuentes con las que se hizo; vacía en búsquedas de antes de F12.2. */
    providers?: string[];
    /** Subdivisiones con que se buscó (ADR-0038). */
    subdivisionIds?: number[];
  }) => void;
  selectArticle: (articleId: number | null) => void;
  setListFilter: (filter: ListFilter) => void;
  setShowIrrelevant: (showIrrelevant: boolean) => void;
  setPanelOpen: (panelOpen: boolean) => void;
  setSearchCollapsed: (searchCollapsed: boolean) => void;
  setEarth: (earth: EarthMode) => void;
  setMotion: (motion: MotionPreset) => void;
  setSpinning: (spinning: boolean) => void;
  setLastCaseId: (caseId: string) => void;
  /** Elige las fuentes encendidas (la lista completa ya calculada). */
  setSources: (sources: string[]) => void;
  openWall: (caseId: string) => void;
  closeWall: () => void;
  selectWallNode: (nodeId: number | null) => void;
  setConstellation: (constellation: boolean) => void;
  setShowCases: (showCases: boolean) => void;
  /**
   * «Limpiar globo» (9.6, D10): quita resultados, nota elegida y muro, y vuelve a
   * la vista de México. Región, conceptos y fechas se quedan en el formulario
   * para buscar otra cosa con un clic; la búsqueda sigue en Historial.
   *
   * @param target A dónde vuela el globo (por defecto, México).
   */
  clearGlobe: (target?: HomeTarget) => void;
  /** Lleva el globo a la vista del Atlántico y lo pone a girar, sin quitar nada. */
  showOverview: () => void;
}

/** A dónde vuelve el globo: México o la vista del Atlántico que gira. */
export type HomeTarget = 'mexico' | 'atlantic';

// Días de cada rango rápido; "hoy" es el último día (la API cuenta hasta hoy).
const RANGE_DAYS: Record<Exclude<RangeKind, 'custom'>, number> = { today: 1, '7': 7, '30': 30 };

/**
 * Cuerpo para estimar o lanzar la búsqueda, o `null` si aún falta algo.
 *
 * Las subdivisiones solo se mandan si van con un concepto que no es tema
 * general (la FGR): solas, el servidor las rechaza.
 *
 * @param state Lo elegido en el formulario.
 * @param providers Fuentes encendidas (sin mandar: las de por defecto).
 * @param subdivisions Subdivisiones para la FGR (`subdivisionIds`).
 * @example searchInput({ regionId: 272, conceptIds: [3], range: { kind: '7' } })
 * // { region_id: 272, concept_ids: [3], days: 7 }
 */
export function searchInput(
  state: Pick<ExplorerState, 'regionId' | 'conceptIds' | 'range'>,
  providers?: string[],
  subdivisions: readonly number[] = [],
): SearchInput | null {
  if (state.regionId === null || state.conceptIds.length === 0) return null;
  // Sin ninguna fuente encendida no hay nada que estimar (F12.2).
  if (providers?.length === 0) return null;
  const base = {
    region_id: state.regionId,
    concept_ids: [...state.conceptIds].sort((a, b) => a - b),
    ...(providers ? { providers } : {}),
    ...(subdivisions.length > 0 ? { category_ids: [...subdivisions].sort((a, b) => a - b) } : {}),
  };
  if (state.range.kind !== 'custom') return { ...base, days: RANGE_DAYS[state.range.kind] };
  if (!state.range.from || !state.range.to) return null;
  return { ...base, date_from: state.range.from, date_to: state.range.to };
}

// localStorage puede no existir o fallar (modo privado, almacenamiento lleno):
// entonces la preferencia vale solo mientras dura la página. También lo usa el
// estado del Centro de mando (store/mando.ts).
export const safeStorage: StateStorage = {
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
      subdivisionIds: [],
      range: { kind: '7' },
      searchId: null,
      articleId: null,
      articleRequest: 0,
      listFilter: 'all',
      showIrrelevant: false,
      panelOpen: true,
      searchCollapsed: false,
      earth: 'night',
      // "Menos movimiento" del sistema manda sobre la preferencia guardada.
      motion: prefersReducedMotion() ? 'off' : 'normal',
      spinning: !prefersReducedMotion(),
      lastCaseId: null,
      sources: null,
      wallCaseId: null,
      wallNodeId: null,
      constellation: false,
      showCases: false,
      homeRequest: 0,
      homeTarget: 'mexico',
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
      toggleSubdivision: (categoryId) => {
        set((state) => ({
          subdivisionIds: state.subdivisionIds.includes(categoryId)
            ? state.subdivisionIds.filter((id) => id !== categoryId)
            : [...state.subdivisionIds, categoryId],
        }));
      },
      setSubdivisions: (subdivisionIds) => {
        set({ subdivisionIds });
      },
      setRange: (range) => {
        set({ range });
      },
      openSearch: (searchId) => {
        // Otra búsqueda: se olvidan la nota elegida y los filtros de la lista.
        set({ searchId, articleId: null, listFilter: 'all', showIrrelevant: false });
      },
      restoreSearch: ({
        searchId,
        regionId,
        conceptIds,
        dateFrom,
        dateTo,
        providers,
        subdivisionIds = [],
      }) => {
        set({
          searchId,
          regionId,
          conceptIds,
          subdivisionIds,
          range: { kind: 'custom', from: dateFrom, to: dateTo },
          // Editar una búsqueda reabierta parte de sus fuentes (si las guardó).
          ...(providers && providers.length > 0 ? { sources: providers } : {}),
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
      setSearchCollapsed: (searchCollapsed) => {
        set({ searchCollapsed });
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
      setSources: (sources) => {
        set({ sources });
      },
      openWall: (wallCaseId) => {
        // El muro ocupa el globo: se quita la nota elegida y se detiene el giro.
        set({
          wallCaseId,
          wallNodeId: null,
          constellation: false,
          articleId: null,
          spinning: false,
        });
      },
      closeWall: () => {
        set({ wallCaseId: null, wallNodeId: null, constellation: false });
      },
      selectWallNode: (wallNodeId) => {
        set({ wallNodeId });
      },
      setConstellation: (constellation) => {
        set({ constellation, wallNodeId: null });
      },
      setShowCases: (showCases) => {
        set({ showCases });
      },
      clearGlobe: (target = 'mexico') => {
        set((state) => ({
          searchId: null,
          articleId: null,
          listFilter: 'all',
          showIrrelevant: false,
          wallCaseId: null,
          wallNodeId: null,
          constellation: false,
          panelOpen: true,
          // Otra búsqueda empieza con el formulario a la vista.
          searchCollapsed: false,
          homeRequest: state.homeRequest + 1,
          homeTarget: target,
        }));
      },
      showOverview: () => {
        set((state) => ({ homeRequest: state.homeRequest + 1, homeTarget: 'atlantic' }));
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
        // Las fuentes que prefiere el analista se recuerdan entre visitas.
        sources: state.sources,
      }),
    },
  ),
);
