/**
 * Tarjeta de la región seleccionada: migas de pan navegables, nombre, nivel,
 * clave, punto representativo y alias.
 */
import type { RegionDetail } from '../../services/regions';
import { codeLabel, formatPoint, LEVEL_LABEL } from './labels';

interface RegionCardProps {
  detail: RegionDetail | undefined;
  isLoading: boolean;
  error: Error | null;
  onSelect: (regionId: number) => void;
  onClose: () => void;
}

export function RegionCard({ detail, isLoading, error, onSelect, onClose }: RegionCardProps) {
  return (
    <section
      aria-label="Región seleccionada"
      className="rounded-xl border border-slate-700/80 bg-slate-900/90 p-4 shadow-lg shadow-black/30 backdrop-blur"
    >
      <div className="flex items-start justify-between gap-3">
        {detail ? (
          <nav aria-label="Ubicación" className="flex flex-wrap items-center gap-1 text-xs">
            {detail.ancestors.map((ancestor) => (
              <span key={ancestor.id} className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => {
                    onSelect(ancestor.id);
                  }}
                  className="rounded text-sky-300 hover:text-sky-200 hover:underline focus-visible:outline-2 focus-visible:outline-sky-400"
                >
                  {ancestor.name}
                </button>
                <span aria-hidden="true" className="text-slate-600">
                  ›
                </span>
              </span>
            ))}
            <span className="text-slate-300">{detail.name}</span>
          </nav>
        ) : (
          <span className="h-4 w-40 animate-pulse rounded bg-slate-800" />
        )}
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar"
          className="-mr-1 -mt-1 rounded-md p-1 text-slate-500 hover:bg-slate-800 hover:text-slate-200"
        >
          <svg aria-hidden="true" viewBox="0 0 20 20" className="size-4 fill-current">
            <path d="m10 8.94 4.47-4.47 1.06 1.06L11.06 10l4.47 4.47-1.06 1.06L10 11.06l-4.47 4.47-1.06-1.06L8.94 10 4.47 5.53l1.06-1.06L10 8.94Z" />
          </svg>
        </button>
      </div>

      {isLoading && <p className="mt-3 text-sm text-slate-400">Cargando región…</p>}
      {error && <p className="mt-3 text-sm text-rose-300">{error.message}</p>}

      {detail && (
        <>
          <h2 className="mt-2 text-lg font-semibold leading-tight text-slate-50">
            {detail.display_name}
          </h2>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
            <dt className="text-slate-500">Nivel</dt>
            <dd className="text-slate-200">{LEVEL_LABEL[detail.level]}</dd>
            <dt className="text-slate-500">{codeLabel(detail.level)}</dt>
            <dd className="font-mono text-slate-200">{detail.code}</dd>
            <dt className="text-slate-500">Punto</dt>
            <dd className="tabular-nums text-slate-200">
              {formatPoint(detail.point.lon, detail.point.lat)}
            </dd>
          </dl>
          {!detail.has_polygon && (
            <p className="mt-3 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
              Localidad rural sin polígono: INEGI solo registra su punto.
            </p>
          )}
          {detail.aliases.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              <span className="text-xs text-slate-500">También conocida como</span>
              {detail.aliases.map((alias) => (
                <span
                  key={alias}
                  className="rounded-md bg-slate-800 px-2 py-0.5 text-xs text-slate-300"
                >
                  {alias}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
