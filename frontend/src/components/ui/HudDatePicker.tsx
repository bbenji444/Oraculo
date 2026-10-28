/**
 * Campo de fecha con calendario de la consola táctica (28/10/2026).
 *
 * Reemplaza al `<input type="date">`: su calendario lo dibuja el navegador y
 * no se puede estilizar (salía gris, como de Windows). Benji pidió que el
 * calendario tuviera «este estilo y efecto». Al abrir:
 * - el calendario se despliega desde el campo, hacia abajo o hacia arriba
 *   según quepa;
 * - al cambiar de mes, los días entran deslizándose del lado al que se va;
 * - el día bajo el mouse se ilumina, hoy lleva un aro y el elegido brilla;
 * - con `rangeFrom` y `rangeTo`, los días entre las dos fechas se marcan como
 *   una banda.
 *
 * Teclado: las flechas mueven el día (arriba y abajo, de semana en semana),
 * RePág y AvPág cambian de mes, Enter elige y Escape cierra.
 *
 * El calendario se dibuja en `document.body` (portal), como `HudSelect`, para
 * que no lo recorte ningún panel.
 *
 * No hace: no guarda el valor (lo recibe y avisa con `onChange`).
 */
import {
  type CSSProperties,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';

import {
  addDays,
  isIsoDate,
  longDate,
  monthGrid,
  monthOf,
  type MonthView,
  monthTitle,
  outOfBounds,
  shiftMonth,
  shortDate,
  todayInMexico,
  WEEKDAYS,
} from '../../ui/calendar';

interface HudDatePickerProps {
  /** `AAAA-MM-DD`, o vacío si no hay fecha. */
  value: string | undefined;
  onChange: (value: string | undefined) => void;
  /** Para enlazarlo con un `<label htmlFor>`. */
  id?: string;
  /** Nombre del calendario para el lector de pantalla («Desde»). */
  label: string;
  /** Primer y último día que se puede elegir. */
  min?: string;
  max?: string;
  /** El rango elegido, para marcar la banda entre las dos fechas. */
  rangeFrom?: string;
  rangeTo?: string;
}

// Medidas del calendario abierto, en píxeles (para decidir hacia dónde abre).
const CALENDAR_WIDTH = 288;
const CALENDAR_HEIGHT = 352;
const GAP = 6;
const VIEWPORT_MARGIN = 12;
// Las flechas: un día a los lados, una semana arriba y abajo.
const KEY_STEP: Readonly<Record<string, number>> = {
  ArrowLeft: -1,
  ArrowRight: 1,
  ArrowUp: -7,
  ArrowDown: 7,
};

interface Placement {
  left: number;
  top?: number;
  bottom?: number;
  above: boolean;
}

function placeNear(anchor: DOMRect): Placement {
  const below = window.innerHeight - anchor.bottom - GAP - VIEWPORT_MARGIN;
  const room = anchor.top - GAP - VIEWPORT_MARGIN;
  const above = below < CALENDAR_HEIGHT && room > below;
  const maxLeft = Math.max(VIEWPORT_MARGIN, window.innerWidth - CALENDAR_WIDTH - VIEWPORT_MARGIN);
  const left = Math.min(Math.max(anchor.left, VIEWPORT_MARGIN), maxLeft);
  return above
    ? { left, above, bottom: window.innerHeight - anchor.top + GAP }
    : { left, above, top: anchor.bottom + GAP };
}

export function HudDatePicker({
  value,
  onChange,
  id,
  label,
  min,
  max,
  rangeFrom,
  rangeTo,
}: HudDatePickerProps) {
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const today = todayInMexico();
  const chosen = isIsoDate(value) ? value : undefined;
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<Placement | null>(null);
  const [view, setView] = useState<MonthView>(() => monthOf(chosen ?? today));
  // Hacia dónde se movió el mes, para que los días entren de ese lado.
  const [direction, setDirection] = useState<1 | -1>(1);
  const [focused, setFocused] = useState(chosen ?? today);

  const close = useCallback(() => {
    setOpen(false);
    setPlace(null);
  }, []);
  const openCalendar = () => {
    const start = chosen ?? (max !== undefined && today > max ? max : today);
    setView(monthOf(start));
    setFocused(start);
    setOpen(true);
  };
  const choose = (iso: string | undefined) => {
    onChange(iso);
    close();
    triggerRef.current?.focus();
  };
  const goMonth = (delta: number) => {
    setDirection(delta > 0 ? 1 : -1);
    setView((current) => shiftMonth(current, delta));
  };

  // Se coloca antes de pintar, junto al campo; y otra vez si algo se mueve.
  useLayoutEffect(() => {
    if (!open) return;
    const reposition = () => {
      const trigger = triggerRef.current;
      if (trigger) setPlace(placeNear(trigger.getBoundingClientRect()));
    };
    reposition();
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
    return () => {
      window.removeEventListener('scroll', reposition, true);
      window.removeEventListener('resize', reposition);
    };
  }, [open]);

  // Clic fuera del campo y del calendario: se cierra.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      close();
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, [open, close]);

  // El día con el foco del teclado siempre tiene el foco del navegador.
  useEffect(() => {
    if (!open || !place) return;
    panelRef.current?.querySelector<HTMLButtonElement>(`[data-iso="${focused}"]`)?.focus();
  }, [open, place, focused, view]);

  const onGridKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = KEY_STEP[event.key];
    if (step !== undefined) {
      event.preventDefault();
      const next = addDays(focused, step);
      const nextView = monthOf(next);
      if (nextView.month !== view.month || nextView.year !== view.year) {
        setDirection(step > 0 ? 1 : -1);
        setView(nextView);
      }
      setFocused(next);
    } else if (event.key === 'PageUp' || event.key === 'PageDown') {
      event.preventDefault();
      goMonth(event.key === 'PageUp' ? -1 : 1);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      close();
      triggerRef.current?.focus();
    }
  };

  const days = monthGrid(view);
  const bandFrom = isIsoDate(rangeFrom) ? rangeFrom : undefined;
  const bandTo = isIsoDate(rangeTo) ? rangeTo : undefined;
  const style: CSSProperties | undefined = place
    ? { left: place.left, width: CALENDAR_WIDTH, top: place.top, bottom: place.bottom }
    : undefined;

  return (
    <>
      <button
        ref={triggerRef}
        id={id}
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => {
          if (open) close();
          else openCalendar();
        }}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' && !open) {
            event.preventDefault();
            openCalendar();
          }
        }}
        className="hud-select hud-select--sm hud-date"
      >
        <span className={chosen ? 'tabular-nums' : 'text-slate-500'}>
          {chosen ? shortDate(chosen) : 'dd/mm/aaaa'}
        </span>
        <svg aria-hidden="true" viewBox="0 0 16 16" className="hud-select-chevron">
          <rect x="2" y="3" width="12" height="11" rx="2" fill="none" stroke="currentColor" />
          <path d="M2 6.5h12M5.5 1.5v3M10.5 1.5v3" fill="none" stroke="currentColor" />
        </svg>
      </button>
      {open &&
        place &&
        createPortal(
          <div
            ref={panelRef}
            role="dialog"
            aria-label={`Elegir fecha: ${label}`}
            data-above={place.above}
            className="hud-calendar"
            style={style}
          >
            <div className="flex items-center justify-between gap-2">
              <button
                type="button"
                onClick={() => {
                  goMonth(-1);
                }}
                aria-label="Mes anterior"
                className="hud-icon-btn size-7 text-sm"
              >
                ‹
              </button>
              {/* key: el título nuevo entra con un destello al cambiar de mes. */}
              <p key={`${String(view.year)}-${String(view.month)}`} className="hud-calendar-title">
                {monthTitle(view)}
              </p>
              <button
                type="button"
                onClick={() => {
                  goMonth(1);
                }}
                aria-label="Mes siguiente"
                className="hud-icon-btn size-7 text-sm"
              >
                ›
              </button>
            </div>
            <div className="hud-calendar-week" aria-hidden="true">
              {WEEKDAYS.map((day) => (
                <span key={day}>{day}</span>
              ))}
            </div>
            <div
              key={`${String(view.year)}-${String(view.month)}`}
              role="group"
              aria-label={monthTitle(view)}
              className="hud-calendar-grid"
              style={{ '--dir': direction } as CSSProperties}
              onKeyDown={onGridKey}
            >
              {days.map((day, index) => {
                const disabled = outOfBounds(day.iso, min, max);
                const inBand =
                  bandFrom !== undefined &&
                  bandTo !== undefined &&
                  day.iso > bandFrom &&
                  day.iso < bandTo;
                const isEdge = day.iso === bandFrom || day.iso === bandTo;
                return (
                  <button
                    key={day.iso}
                    type="button"
                    data-iso={day.iso}
                    tabIndex={day.iso === focused ? 0 : -1}
                    disabled={disabled}
                    aria-label={longDate(day.iso)}
                    aria-pressed={day.iso === chosen}
                    data-outside={day.inMonth ? undefined : ''}
                    data-today={day.iso === today ? '' : undefined}
                    data-band={inBand ? '' : undefined}
                    data-edge={isEdge ? '' : undefined}
                    className="hud-calendar-day"
                    style={{ '--i': index % 7 } as CSSProperties}
                    onClick={() => {
                      choose(day.iso);
                    }}
                  >
                    {day.day}
                  </button>
                );
              })}
            </div>
            <div className="flex items-center justify-between border-t border-sky-400/10 pt-2">
              <button
                type="button"
                onClick={() => {
                  choose(undefined);
                }}
                className="hud-calendar-link"
              >
                Borrar
              </button>
              <button
                type="button"
                disabled={outOfBounds(today, min, max)}
                onClick={() => {
                  choose(today);
                }}
                className="hud-calendar-link"
              >
                Hoy
              </button>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
