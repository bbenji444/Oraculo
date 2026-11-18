/**
 * Fondo de constelación de Oráculo core (ADR-0108) para las pestañas fuera de
 * Explorar: un lienzo 2D con puntos que derivan, líneas entre los cercanos y
 * halos que laten (los cálculos están en `ui/constellation.ts`).
 *
 * A diferencia del de Oráculo:
 * - con «reducir animaciones» del sistema dibuja un solo cuadro y se queda
 *   quieto;
 * - se detiene mientras la pestaña del navegador está oculta;
 * - dibuja a CONSTELLATION_FPS como máximo, porque la tarjeta integrada es la
 *   misma del globo.
 *
 * No hace: no se monta en Explorar (ahí van el globo y sus estrellas, lo decide
 * `App`).
 */
import { useEffect, useRef } from 'react';

import {
  HALO_COLOR,
  haloRadius,
  LINE_COLOR,
  linksBetween,
  makeHalos,
  makeParticles,
  STAR_COLOR,
  stepHalo,
  stepParticle,
} from '../../ui/constellation';

// La mitad de los 60 cuadros por segundo de Oráculo: el fondo se mueve tan
// despacio que no se nota, y deja la tarjeta libre.
const CONSTELLATION_FPS = 30;
const MS_PER_SECOND = 1000;
// Un cuadro de los de Oráculo, que es la unidad de las velocidades.
const MS_PER_ORACULO_FRAME = MS_PER_SECOND / 60;
// Tope de avance tras una pausa larga del navegador, para que no salten.
const MAX_STEPS = 4;

export function Constellation() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext('2d');
    if (!canvas || !context) return;

    let width = 0;
    let height = 0;
    // Sin multiplicar por la densidad de la pantalla, como en Oráculo: son
    // puntos borrosos y así cuesta cuatro veces menos en pantallas finas.
    const resize = () => {
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = width;
      canvas.height = height;
    };
    resize();
    const particles = makeParticles(width, height);
    const halos = makeHalos(width, height);

    const draw = () => {
      context.clearRect(0, 0, width, height);
      context.fillStyle = HALO_COLOR;
      for (const halo of halos) {
        context.beginPath();
        context.arc(halo.x, halo.y, haloRadius(halo), 0, Math.PI * 2);
        context.fill();
      }
      context.fillStyle = STAR_COLOR;
      for (const particle of particles) {
        context.beginPath();
        context.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
        context.fill();
      }
      context.strokeStyle = LINE_COLOR;
      for (const link of linksBetween(particles)) {
        context.lineWidth = link.width;
        context.beginPath();
        context.moveTo(link.from.x, link.from.y);
        context.lineTo(link.to.x, link.to.y);
        context.stroke();
      }
    };

    // Sin matchMedia (navegadores viejos, pruebas) se anima.
    const still =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let frame = 0;
    let last = 0;
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      if (last && now - last < MS_PER_SECOND / CONSTELLATION_FPS) return;
      const steps = last ? Math.min((now - last) / MS_PER_ORACULO_FRAME, MAX_STEPS) : 1;
      last = now;
      for (const halo of halos) stepHalo(halo, width, height, steps);
      for (const particle of particles) stepParticle(particle, width, height, steps);
      draw();
    };
    const start = () => {
      if (still || frame || document.hidden) return;
      last = 0;
      frame = requestAnimationFrame(tick);
    };
    const stop = () => {
      cancelAnimationFrame(frame);
      frame = 0;
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else start();
    };

    draw();
    start();
    document.addEventListener('visibilitychange', onVisibility);
    // Sin ResizeObserver (navegadores viejos) basta el cambio de ventana.
    const onResize = () => {
      resize();
      draw();
    };
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(onResize);
    observer?.observe(canvas);
    window.addEventListener('resize', onResize);
    return () => {
      stop();
      document.removeEventListener('visibilitychange', onVisibility);
      observer?.disconnect();
      window.removeEventListener('resize', onResize);
    };
  }, []);

  return <canvas ref={canvasRef} aria-hidden="true" className="absolute inset-0 h-full w-full" />;
}
