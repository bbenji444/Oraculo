/**
 * Texto que se «descifra» letra por letra (27/10/2026).
 *
 * Al aparecer, y otra vez al pasar el mouse encima, sus letras pasan por
 * caracteres de terminal hasta quedar en el texto real, en menos de medio
 * segundo. Se usa en títulos y pestañas. El lector de pantalla recibe siempre
 * el texto real.
 *
 * No hace: no cambia el tamaño del texto (los caracteres de relleno ocupan lo
 * mismo con la fuente Orbitron, de ancho casi fijo en mayúsculas).
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { DECODE_MS, decodeAt, prefersReducedMotion } from '../../ui/motion';

interface DecodeTextProps {
  text: string;
  /** También al pasar el mouse (por defecto, sí). */
  onHover?: boolean;
  className?: string;
}

export function DecodeText({ text, onHover = true, className }: DecodeTextProps) {
  const [shown, setShown] = useState(text);
  const frameRef = useRef(0);

  const play = useCallback(() => {
    if (prefersReducedMotion()) return;
    cancelAnimationFrame(frameRef.current);
    const start = performance.now();
    const tick = (now: number) => {
      const t = (now - start) / DECODE_MS;
      setShown(t >= 1 ? text : decodeAt(text, t));
      if (t < 1) frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);
  }, [text]);

  useEffect(() => {
    play();
    return () => {
      cancelAnimationFrame(frameRef.current);
    };
  }, [play]);

  return (
    <span className={className} aria-label={text} onMouseEnter={onHover ? play : undefined}>
      <span aria-hidden="true">{shown}</span>
    </span>
  );
}
