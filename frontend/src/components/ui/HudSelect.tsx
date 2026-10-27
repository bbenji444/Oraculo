/**
 * Menú desplegable de la consola táctica (27/10/2026, styles/hud.css).
 *
 * Reemplaza al `<select>` del navegador, cuya lista dibuja Windows y no se
 * puede estilizar (salía blanca o gris). Al abrir:
 * - la lista aparece con un pequeño despliegue;
 * - la opción bajo el mouse o el teclado se ilumina con una barra de luz;
 * - la elegida lleva una palomita;
 * - la flecha del campo gira.
 *
 * Accesible con el patrón «combobox de solo selección» de ARIA 1.2: el campo
 * es el que tiene el foco, las flechas mueven la opción activa
 * (`aria-activedescendant`), Enter o Espacio eligen, Escape cierra y escribir
 * salta a la opción que empieza así. Funciona con `<label htmlFor>`.
 *
 * La lista se dibuja en `document.body` (portal) con posición fija: así no la
 * recorta ningún panel con `overflow`, y abre hacia arriba si abajo no cabe.
 *
 * No hace: no guarda el valor (lo recibe y avisa con `onChange`).
 */
import {
  type CSSProperties,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';

import { matchTypeahead, type MenuPlacement, menuPlacement, moveIndex } from '../../ui/select';

export interface HudSelectOption<T extends string | number> {
  value: T;
  label: string;
}

interface HudSelectProps<T extends string | number> {
  value: T;
  options: readonly HudSelectOption<T>[];
  onChange: (value: T) => void;
  /** Para enlazarlo con un `<label htmlFor>`. */
  id?: string;
  /** Nombre para el lector de pantalla, si no hay `<label>`. */
  label?: string;
  disabled?: boolean;
  /** Más compacto (filtros, formularios chicos). */
  size?: 'md' | 'sm';
  /** Borde rojo: el servidor rechazó el valor. */
  invalid?: boolean;
  className?: string;
}

// Lo escrito para buscar se olvida tras esta pausa (como en un <select>).
const TYPEAHEAD_RESET_MS = 600;
// Las primeras opciones entran escalonadas; las demás, juntas.
const MAX_STAGGER = 8;

export function HudSelect<T extends string | number>({
  value,
  options,
  onChange,
  id,
  label,
  disabled = false,
  size = 'md',
  invalid = false,
  className = '',
}: HudSelectProps<T>) {
  const autoId = useId();
  const triggerId = id ?? `${autoId}-campo`;
  const listId = `${autoId}-lista`;
  const optionId = (index: number) => `${autoId}-opcion-${String(index)}`;
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const typed = useRef({ text: '', at: 0 });
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [place, setPlace] = useState<MenuPlacement | null>(null);
  const selectedIndex = options.findIndex((option) => option.value === value);
  const selected = options[selectedIndex];

  const openMenu = () => {
    if (disabled || options.length === 0) return;
    setActive(selectedIndex >= 0 ? selectedIndex : 0);
    setOpen(true);
  };
  const close = useCallback(() => {
    setOpen(false);
    setPlace(null);
  }, []);
  const choose = (index: number) => {
    const option = options[index];
    if (option && option.value !== value) onChange(option.value);
    close();
    triggerRef.current?.focus();
  };

  // Se coloca antes de pintar, junto al campo; y otra vez si algo se mueve.
  useLayoutEffect(() => {
    if (!open) return;
    const reposition = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;
      setPlace(
        menuPlacement(trigger.getBoundingClientRect(), {
          width: window.innerWidth,
          height: window.innerHeight,
        }),
      );
    };
    reposition();
    // En captura: también cuando se desplaza un panel, no solo la página.
    window.addEventListener('scroll', reposition, true);
    window.addEventListener('resize', reposition);
    return () => {
      window.removeEventListener('scroll', reposition, true);
      window.removeEventListener('resize', reposition);
    };
  }, [open]);

  // Clic fuera del campo y de la lista: se cierra.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || listRef.current?.contains(target)) return;
      close();
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, [open, close]);

  // La opción activa siempre a la vista, sin mover la página (solo la lista).
  useEffect(() => {
    const list = listRef.current;
    const item = list?.children[active] as HTMLElement | undefined;
    if (!list || !item) return;
    if (item.offsetTop < list.scrollTop) list.scrollTop = item.offsetTop;
    else if (item.offsetTop + item.offsetHeight > list.scrollTop + list.clientHeight) {
      list.scrollTop = item.offsetTop + item.offsetHeight - list.clientHeight;
    }
  }, [active, place]);

  const typeahead = (key: string) => {
    const now = Date.now();
    const text = now - typed.current.at < TYPEAHEAD_RESET_MS ? typed.current.text + key : key;
    typed.current = { text, at: now };
    const from = text.length > 1 ? active - 1 : active;
    const found = matchTypeahead(
      options.map((option) => option.label),
      text,
      from,
    );
    if (found < 0) return;
    if (open) setActive(found);
    else {
      const option = options[found];
      if (option) onChange(option.value);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const count = options.length;
    const key = event.key;
    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(key)) {
        event.preventDefault();
        openMenu();
      } else if (key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        typeahead(key);
      }
      return;
    }
    const moves: Record<string, number> = {
      ArrowDown: 1,
      ArrowUp: -1,
      PageDown: 5,
      PageUp: -5,
      Home: -count,
      End: count,
    };
    const delta = moves[key];
    if (delta !== undefined) {
      event.preventDefault();
      setActive((current) => moveIndex(current, delta, count));
    } else if (key === 'Enter' || key === ' ') {
      event.preventDefault();
      choose(active);
    } else if (key === 'Escape') {
      event.preventDefault();
      close();
    } else if (key === 'Tab') {
      close();
    } else if (key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      typeahead(key);
    }
  };

  const menuStyle: CSSProperties | undefined = place
    ? {
        left: place.left,
        minWidth: place.minWidth,
        maxHeight: place.maxHeight,
        ...(place.above ? { bottom: place.bottom } : { top: place.top }),
      }
    : undefined;

  return (
    <>
      <button
        ref={triggerRef}
        id={triggerId}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && active >= 0 ? optionId(active) : undefined}
        aria-label={label}
        aria-invalid={invalid || undefined}
        disabled={disabled}
        onClick={() => {
          if (open) close();
          else openMenu();
        }}
        onKeyDown={onKeyDown}
        className={`hud-select ${size === 'sm' ? 'hud-select--sm' : ''} ${
          invalid ? 'border-rose-500/70' : ''
        } ${className}`}
      >
        <span className="min-w-0 truncate">{selected?.label ?? ''}</span>
        <svg aria-hidden="true" viewBox="0 0 16 16" className="hud-select-chevron">
          <path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" />
        </svg>
      </button>
      {open &&
        place &&
        createPortal(
          <ul
            ref={listRef}
            id={listId}
            role="listbox"
            aria-labelledby={label ? undefined : triggerId}
            aria-label={label}
            data-above={place.above}
            className="hud-menu"
            style={menuStyle}
          >
            {options.map((option, index) => (
              <li
                key={String(option.value)}
                id={optionId(index)}
                role="option"
                aria-selected={index === selectedIndex}
                data-active={index === active}
                className="hud-menu-option"
                style={{ '--i': Math.min(index, MAX_STAGGER) } as CSSProperties}
                // Al mover el mouse, no al «entrar»: cuando el teclado desplaza la
                // lista, otra opción queda bajo el cursor quieto y el navegador
                // avisa mouseenter; con eso Enter elegía esa y no la del teclado
                // (pasó con «j» → «Guerrero», 27/10/2026).
                onPointerMove={() => {
                  if (index !== active) setActive(index);
                }}
                // mousedown y no click: así el campo no pierde el foco antes.
                onMouseDown={(event) => {
                  event.preventDefault();
                  choose(index);
                }}
              >
                <span className="min-w-0 truncate">{option.label}</span>
                {index === selectedIndex && (
                  <svg aria-hidden="true" viewBox="0 0 16 16" className="hud-menu-check">
                    <path
                      d="m3.5 8.5 3 3 6-7"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                )}
              </li>
            ))}
          </ul>,
          document.body,
        )}
    </>
  );
}
