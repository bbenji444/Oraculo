/**
 * El muro de un caso sobre el globo de Explorar (Fase 9.6, historia H9.3).
 *
 * - **Al abrir:** vuelo suave que encuadra todos los nodos.
 * - **Nodos que laten** (color por tipo, borde por estatus legal) y **arcos de
 *   luz** (punteados si están sugeridos), con el motor de `map/muro`.
 * - **Clic en una entidad:** el globo se recorre a la izquierda, la cámara la
 *   orbita despacio, lo demás se atenúa y entra el panel por la derecha
 *   (`WallPanel`). Esc o un clic en el vacío regresan.
 * - **Barra superior:** nombre del caso, conteos, «Constelación» (las notas
 *   como puntos de luz) y «✕ Salir del muro».
 * - Mientras la cámara orbita, el mapa baja su resolución (ADR-0102, punto 5.1).
 *
 * Solo entra lo confirmado (ADR-0104); si no hay nada, se dice cómo llenarlo.
 *
 * No hace: no crea el mapa (lo recibe de `ExploreGlobe`) ni cambia datos.
 */
import type { Map as MapLibreMap, MapMouseEvent } from 'maplibre-gl';
import { useEffect, useMemo, useRef, useState } from 'react';

import { useCaseGraph } from '../../hooks/useCaseGraph';
import { flightPixelRatio } from '../../map/flight';
import { globeCamera, flyPadding } from '../../map/framing';
import { easeInOutCubic, flyDurationMs } from '../../map/motion';
import { addWall, WALL_NODE_LAYER } from '../../map/muro/engine';
import type { MuroEngine } from '../../map/muro/labels';
import {
  NODE_ZOOM,
  nodePadding,
  ORBIT_PITCH,
  orbitBearing,
  WALL_MAX_ZOOM,
  wallHash,
} from '../../map/muro/orbit';
import {
  constellationFromGraph,
  KIND_COLOR,
  LEGAL_RING,
  NOTE_PREFIX,
  wallBounds,
  wallFromGraph,
} from '../../map/muro/wall';
import type { CaseGraph } from '../../services/caseGraph';
import { useExplorerStore } from '../../store/explorer';
import { GLASS } from './ui';
import { WallPanel } from './WallPanel';

interface CaseWallProps {
  map: MapLibreMap | null;
}

// Eventos de la persona que detienen la órbita.
const USER_EVENTS = ['mousedown', 'touchstart', 'wheel'] as const;

const LEGEND_KINDS: [string, string][] = [
  ['person', 'persona'],
  ['place', 'lugar'],
  ['org', 'organización'],
  ['vehicle', 'vehículo'],
];
const LEGEND_LEGAL: [keyof typeof LEGAL_RING, string][] = [
  ['alleged', 'señalado'],
  ['detained', 'detenido'],
  ['charged', 'vinculado a proceso'],
  ['victim', 'víctima'],
  ['witness', 'testigo'],
  ['official', 'funcionario'],
];

function screenOf(map: MapLibreMap) {
  const container = map.getContainer();
  return { width: container.clientWidth, height: container.clientHeight };
}

/** Encuadra todos los nodos del muro con un vuelo suave. */
function frameWall(map: MapLibreMap, graph: CaseGraph, constellation: boolean): void {
  const wall = constellation ? constellationFromGraph(graph) : wallFromGraph(graph, null);
  const box = wallBounds(wall) ?? [
    graph.center.lon,
    graph.center.lat,
    graph.center.lon,
    graph.center.lat,
  ];
  const camera = globeCamera(box, screenOf(map), flyPadding(screenOf(map), false), WALL_MAX_ZOOM);
  const center = map.getCenter();
  const motion = useExplorerStore.getState().motion;
  const duration = flyDurationMs(
    { lng: center.lng, lat: center.lat, zoom: map.getZoom() },
    { lng: camera.center[0], lat: camera.center[1], zoom: camera.zoom },
    'region',
    motion,
  );
  map.flyTo({
    center: camera.center,
    zoom: camera.zoom,
    pitch: 35,
    bearing: 0,
    duration,
    padding: { top: 0, bottom: 0, left: 0, right: 0 },
    essential: false,
  });
}

export function CaseWall({ map }: CaseWallProps) {
  const caseId = useExplorerStore((s) => s.wallCaseId);
  const nodeId = useExplorerStore((s) => s.wallNodeId);
  const constellation = useExplorerStore((s) => s.constellation);
  const earth = useExplorerStore((s) => s.earth);
  const motion = useExplorerStore((s) => s.motion);
  const graph = useCaseGraph(caseId);
  const data = graph.data;
  const engineRef = useRef<MuroEngine | null>(null);
  const framedRef = useRef<string | null>(null);
  const [legendOpen, setLegendOpen] = useState(false);
  const [openNote, setOpenNote] = useState<number | null>(null);

  const wall = useMemo(() => {
    if (!data) return null;
    return constellation ? constellationFromGraph(data) : wallFromGraph(data, nodeId);
  }, [data, constellation, nodeId]);

  // Dibujar o actualizar el muro; quitarlo al salir.
  useEffect(() => {
    if (!map || !wall) return;
    if (engineRef.current) {
      engineRef.current.update(wall);
    } else {
      engineRef.current = addWall(map, wall);
    }
  }, [map, wall]);
  useEffect(() => {
    if (caseId !== null) return;
    engineRef.current?.remove();
    engineRef.current = null;
    framedRef.current = null;
  }, [caseId]);
  useEffect(
    () => () => {
      engineRef.current?.remove();
      engineRef.current = null;
    },
    [],
  );

  // Día/noche cambia el estilo del mapa y se lleva las capas del muro: se
  // vuelven a poner cuando el estilo nuevo está listo.
  const earthRef = useRef(earth);
  useEffect(() => {
    if (earthRef.current === earth) return;
    earthRef.current = earth;
    if (!map || !engineRef.current) return;
    const engine = engineRef.current;
    map.once('idle', () => {
      engine.remove();
      engineRef.current = wall ? addWall(map, wall) : null;
    });
  }, [earth, map, wall]);

  // Al abrir el caso (o cambiar de vista): encuadrar todo.
  useEffect(() => {
    if (!map || !data) return;
    const key = `${data.case_id}:${String(constellation)}`;
    if (framedRef.current === key) return;
    // Si el globo todavía se mueve (la entrada desde el espacio al abrir la
    // página), un vuelo nuevo se pisaría con ese: se espera a que termine.
    const frame = () => {
      // Se marca al volar, no antes: si el efecto se repite mientras espera
      // (llegan datos nuevos), no se pierde el encuadre.
      framedRef.current = key;
      frameWall(map, data, constellation);
    };
    if (map.isMoving()) {
      map.once('moveend', frame);
      return () => {
        map.off('moveend', frame);
      };
    }
    frame();
  }, [map, data, constellation]);

  // Clic en un nodo: elegirlo (o abrir la nota en la constelación); en el vacío, soltarlo.
  useEffect(() => {
    if (!map || caseId === null) return;
    const onClick = (event: MapMouseEvent) => {
      const layers = map.getLayer(WALL_NODE_LAYER) ? [WALL_NODE_LAYER] : [];
      const [hit] = map.queryRenderedFeatures(event.point, { layers });
      const id = hit?.properties.nodeId as string | undefined;
      const store = useExplorerStore.getState();
      if (id?.startsWith(NOTE_PREFIX)) {
        setOpenNote(Number(id.slice(NOTE_PREFIX.length)));
        return;
      }
      setOpenNote(null);
      store.selectWallNode(id === undefined ? null : Number(id));
    };
    const onEnter = () => {
      map.getCanvas().style.cursor = 'pointer';
    };
    const onLeave = () => {
      map.getCanvas().style.cursor = '';
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') useExplorerStore.getState().selectWallNode(null);
    };
    map.on('click', onClick);
    map.on('mouseenter', WALL_NODE_LAYER, onEnter);
    map.on('mouseleave', WALL_NODE_LAYER, onLeave);
    window.addEventListener('keydown', onKey);
    return () => {
      map.off('click', onClick);
      map.off('mouseenter', WALL_NODE_LAYER, onEnter);
      map.off('mouseleave', WALL_NODE_LAYER, onLeave);
      window.removeEventListener('keydown', onKey);
    };
  }, [map, caseId]);

  // Nodo elegido: volar a él dejando libre el panel y orbitar despacio.
  useEffect(() => {
    if (!map || !data || nodeId === null) return;
    const node = data.nodes.find((n) => n.id === nodeId);
    if (!node) return;
    const quiet = motion === 'off';
    let frame = 0;
    let stopped = false;
    const restore = () => {
      map.setPixelRatio(window.devicePixelRatio);
    };
    const stop = () => {
      stopped = true;
      cancelAnimationFrame(frame);
      restore();
    };
    const orbit = () => {
      if (quiet || stopped) return;
      map.setPixelRatio(flightPixelRatio(window.devicePixelRatio));
      const start = performance.now();
      const startBearing = map.getBearing();
      const step = (now: number) => {
        if (stopped) return;
        map.jumpTo({ bearing: orbitBearing(startBearing, now - start) });
        frame = requestAnimationFrame(step);
      };
      frame = requestAnimationFrame(step);
    };
    const center = map.getCenter();
    const duration = flyDurationMs(
      { lng: center.lng, lat: center.lat, zoom: map.getZoom() },
      { lng: node.lon, lat: node.lat, zoom: NODE_ZOOM },
      'region',
      motion,
    );
    map.easeTo({
      center: [node.lon, node.lat],
      zoom: Math.max(map.getZoom(), NODE_ZOOM),
      pitch: quiet ? 0 : ORBIT_PITCH,
      padding: nodePadding(map.getContainer().clientWidth),
      duration,
      easing: easeInOutCubic,
    });
    map.once('moveend', orbit);
    for (const name of USER_EVENTS) map.getCanvasContainer().addEventListener(name, stop);
    return () => {
      stop();
      map.off('moveend', orbit);
      for (const name of USER_EVENTS) map.getCanvasContainer().removeEventListener(name, stop);
      map.easeTo({ padding: { top: 0, bottom: 0, left: 0, right: 0 }, duration: 400 });
    };
  }, [map, data, nodeId, motion]);

  if (caseId === null) return null;

  const close = () => {
    useExplorerStore.getState().closeWall();
    window.location.hash = wallHash(null);
  };
  const selected = data?.nodes.find((n) => n.id === nodeId) ?? null;
  const note = data?.notes.find((n) => n.article_id === openNote) ?? null;
  const empty = data?.nodes.length === 0;

  return (
    <>
      <div className="pointer-events-none absolute inset-x-0 top-3 z-20 flex justify-center px-4">
        <div
          role="region"
          aria-label="Muro del caso"
          className={`${GLASS} pointer-events-auto flex max-w-3xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-xs text-slate-300`}
        >
          <span className="font-semibold text-slate-50">Caso: {data?.name ?? 'cargando…'}</span>
          {data && (
            <span>
              {data.nodes.length} {data.nodes.length === 1 ? 'entidad' : 'entidades'} ·{' '}
              {data.edges.length} {data.edges.length === 1 ? 'vínculo' : 'vínculos'} ·{' '}
              {data.notes.length} notas
              {data.hidden_nodes > 0 && ` · +${String(data.hidden_nodes)} más`}
            </span>
          )}
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={constellation}
              onChange={(event) => {
                useExplorerStore.getState().setConstellation(event.target.checked);
                setOpenNote(null);
              }}
            />
            Constelación
          </label>
          <button
            type="button"
            onClick={() => {
              setLegendOpen(!legendOpen);
            }}
            aria-expanded={legendOpen}
            className="text-sky-300 hover:underline"
          >
            Colores
          </button>
          <button
            type="button"
            onClick={close}
            className="rounded-lg bg-slate-800 px-2.5 py-1 font-medium text-slate-100 hover:bg-slate-700"
          >
            ✕ Salir del muro
          </button>
        </div>
      </div>

      {legendOpen && (
        <div className={`${GLASS} absolute left-4 top-20 z-20 w-56 p-3 text-xs text-slate-300`}>
          <p className="mb-1 font-medium text-slate-100">Centro: tipo</p>
          {LEGEND_KINDS.map(([kind, label]) => (
            <p key={kind} className="flex items-center gap-2">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ background: KIND_COLOR[kind] }}
              />
              {label}
            </p>
          ))}
          <p className="mb-1 mt-2 font-medium text-slate-100">Borde: estatus legal</p>
          {LEGEND_LEGAL.map(([code, label]) => (
            <p key={code} className="flex items-center gap-2">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full border-2"
                style={{ borderColor: LEGAL_RING[code] }}
              />
              {label}
            </p>
          ))}
          <p className="mt-2 text-slate-400">Arco punteado: vínculo sugerido sin confirmar.</p>
        </div>
      )}

      {graph.isError && (
        <p
          role="alert"
          className={`${GLASS} absolute left-1/2 top-20 z-20 -translate-x-1/2 px-4 py-2 text-xs text-rose-300`}
        >
          No se pudo abrir el muro: {graph.error.message}
        </p>
      )}
      {empty && !constellation && (
        <div
          className={`${GLASS} absolute left-1/2 top-20 z-20 max-w-md -translate-x-1/2 px-4 py-3 text-sm text-slate-200`}
        >
          Este caso aún no tiene entidades confirmadas. Al muro solo llega lo que confirma una
          persona: ve a{' '}
          <a href="#/casos" className="text-sky-300 hover:underline">
            Casos → Entidades
          </a>{' '}
          y confirma a las personas, lugares y organizaciones que sirvan.
        </div>
      )}

      {selected && data && !constellation && (
        <WallPanel
          caseId={data.case_id}
          node={selected}
          graph={data}
          onClose={() => {
            useExplorerStore.getState().selectWallNode(null);
          }}
        />
      )}
      {note && (
        <div className={`${GLASS} absolute bottom-24 right-4 z-20 w-80 p-4 text-sm text-slate-200`}>
          <p className="font-medium text-slate-50">{note.title}</p>
          <p className="mt-1 text-xs text-slate-400">
            {note.entity_ids.length} entidades confirmadas del caso aparecen aquí.
          </p>
          <div className="mt-2 flex gap-3 text-xs">
            <a
              href={note.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sky-300 hover:underline"
            >
              Ver nota original ↗
            </a>
            <button
              type="button"
              onClick={() => {
                setOpenNote(null);
              }}
              className="text-slate-300 hover:underline"
            >
              Cerrar
            </button>
          </div>
        </div>
      )}
    </>
  );
}
