/**
 * Fondo de universo detrás del globo (ADR-0017): la esfera de estrellas y Vía
 * Láctea de la NASA vista desde dentro, más estrellas propias nítidas. Gira con
 * la cámara del mapa (`useCameraStore`), así el universo acompaña al globo.
 *
 * Rendimiento (26/10/2026: la tarjeta Intel integrada de Benji se reiniciaba y
 * Chrome le quitaba el 3D a la página):
 * - La foto 8K se baja una vez, se decodifica fuera del hilo principal y se
 *   parte en piezas de 2048 px (`skyTiles`) que se suben a la tarjeta una por
 *   cuadro. Subirla entera de un golpe era la operación más larga de la página.
 * - Solo se dibuja cuando la cámara se mueve o cambia el tamaño, a 30 cuadros
 *   por segundo como máximo. Quieto, no gasta nada. Fuera de Explorar
 *   («drift») deriva solo, muy despacio, a 24 cuadros por segundo.
 * - Es uno solo para toda la aplicación (lo monta `App`), detrás de todas
 *   las pestañas: no hay una segunda copia que ocupe la tarjeta.
 * - Sin suavizado de bordes: a un cielo de estrellas no le sirve y cuesta
 *   memoria de video.
 * - Al salir de Explorar se suelta el contexto de la tarjeta de inmediato.
 *
 * No hace: no dibuja la Tierra (eso es MapLibre, encima de este lienzo).
 */
import { useEffect, useRef } from 'react';
import {
  AdditiveBlending,
  BackSide,
  BufferAttribute,
  BufferGeometry,
  Color,
  Mesh,
  PerspectiveCamera,
  Points,
  Scene,
  ShaderMaterial,
  SphereGeometry,
  SRGBColorSpace,
  Texture,
  WebGLRenderer,
} from 'three';

import {
  makeStars,
  SKY_FIELD_OF_VIEW,
  skyTiles,
  DRIFT_FPS,
  driftView,
  SPACE_FPS,
  spacePixelRatio,
  STAR_MAX_SIZE,
  STARMAP_BLACK_POINT,
  STARMAP_GAIN,
  starCameraRotation,
  starTextureFor,
} from '../../map/space';
import { useCameraStore } from '../../store/camera';

// Radio de la esfera del cielo (su campo de visión es SKY_FIELD_OF_VIEW).
const SKY_RADIUS = 100;
// Segmentos de cada pieza: la esfera entera queda con unos 64 × 32, como antes.
const TILE_SEGMENTS = 16;
// Las estrellas propias van un poco dentro de la esfera para quedar encima.
const STARS_RADIUS = 95;
const MS_PER_SECOND = 1000;

// El cielo de la NASA con punto negro: se resta el piso tenue (la bruma de la
// foto) y se aclara lo demás. La textura llega ya en luz lineal (three.js la
// decodifica de sRGB) y `colorspace_fragment` la regresa a la pantalla.
const SKY_VERTEX = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;
const SKY_FRAGMENT = /* glsl */ `
  uniform sampler2D map;
  uniform float blackPoint;
  uniform float gain;
  varying vec2 vUv;
  void main() {
    vec3 color = texture2D(map, vUv).rgb;
    color = max(color - blackPoint, 0.0) / (1.0 - blackPoint) * gain;
    gl_FragColor = vec4(color, 1.0);
    #include <colorspace_fragment>
  }
`;

// Las estrellas grandes se dibujan más brillantes; las chicas, tenues.
const STAR_VERTEX = /* glsl */ `
  attribute float size;
  attribute float tint;
  uniform float maxSize;
  uniform float pixelRatio;
  varying float vAlpha;
  varying vec3 vColor;
  void main() {
    vAlpha = clamp(size / maxSize, 0.35, 1.0);
    // Colores de estrellas reales: azuladas, blancas y algunas amarillas o naranjas.
    vec3 blue = vec3(0.72, 0.82, 1.0);
    vec3 white = vec3(1.0, 0.98, 0.95);
    vec3 warm = vec3(1.0, 0.84, 0.64);
    vColor = tint < 0.5 ? mix(blue, white, tint * 2.0) : mix(white, warm, (tint - 0.5) * 2.0);
    gl_PointSize = size * pixelRatio;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;
const STAR_FRAGMENT = /* glsl */ `
  varying float vAlpha;
  varying vec3 vColor;
  void main() {
    // Núcleo nítido con un halo corto (gaussiana), como una estrella en una
    // foto: no un círculo plano ni un cuadrito.
    float d = length(gl_PointCoord - 0.5);
    float glow = exp(-d * d * 22.0);
    gl_FragColor = vec4(vColor * glow, glow * vAlpha);
  }
`;

/**
 * Cómo se mueve el cielo:
 * - «camera» (Explorar): sigue a la cámara del globo y solo se dibuja cuando
 *   ella se mueve.
 * - «drift» (Casos, Conceptos, Historial…): deriva solo, muy despacio
 *   (`driftView`), a DRIFT_FPS cuadros por segundo.
 */
export type SkyMode = 'camera' | 'drift';

interface SpaceBackgroundProps {
  mode?: SkyMode;
}

export function SpaceBackground({ mode = 'camera' }: SpaceBackgroundProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const modeRef = useRef(mode);
  // Desde dónde y cuándo empezó a derivar: así al cambiar de pestaña no salta.
  const driftRef = useRef({ startLng: 0, startMs: 0 });
  const requestDrawRef = useRef<() => void>(() => undefined);

  useEffect(() => {
    if (mode === 'drift' && modeRef.current !== 'drift') {
      driftRef.current = {
        startLng: useCameraStore.getState().view.lng,
        startMs: performance.now(),
      };
    }
    modeRef.current = mode;
    requestDrawRef.current();
  }, [mode]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    // Un lienzo nuevo en cada montaje: al salir se suelta su contexto
    // (forceContextLoss) y ese lienzo ya no sirve para otro.
    const canvas = document.createElement('canvas');
    canvas.className = 'absolute inset-0 h-full w-full';
    host.append(canvas);
    const renderer = new WebGLRenderer({ canvas, antialias: false, alpha: false });
    renderer.setPixelRatio(spacePixelRatio(window.devicePixelRatio));
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.setClearColor(new Color('#02030a'));

    const scene = new Scene();
    const camera = new PerspectiveCamera(SKY_FIELD_OF_VIEW, 1, 0.1, SKY_RADIUS * 2);
    camera.rotation.order = 'YXZ';

    const stars = makeStars();
    const geometry = new BufferGeometry();
    geometry.setAttribute(
      'position',
      new BufferAttribute(
        Float32Array.from(stars.flatMap((s) => [s.x, s.y, s.z].map((v) => v * STARS_RADIUS))),
        3,
      ),
    );
    // Tamaños en pixeles CSS: el shader los multiplica por la resolución actual.
    geometry.setAttribute(
      'size',
      new BufferAttribute(Float32Array.from(stars.map((s) => s.size)), 1),
    );
    geometry.setAttribute(
      'tint',
      new BufferAttribute(Float32Array.from(stars.map((s) => s.tint)), 1),
    );
    const pixelRatioUniform = { value: renderer.getPixelRatio() };
    const material = new ShaderMaterial({
      vertexShader: STAR_VERTEX,
      fragmentShader: STAR_FRAGMENT,
      uniforms: { maxSize: { value: STAR_MAX_SIZE }, pixelRatio: pixelRatioUniform },
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
    });
    scene.add(new Points(geometry, material));

    let disposed = false;
    // Función y no la variable: dentro de la carga asíncrona TypeScript daría
    // por hecho que sigue en falso (cambia en la limpieza, entre los await).
    const isDisposed = () => disposed;
    const tiles: { mesh: Mesh<SphereGeometry, ShaderMaterial>; texture: Texture }[] = [];

    const resize = () => {
      const { clientWidth, clientHeight } = canvas;
      // La escala se vuelve a leer cada vez (ver spacePixelRatio).
      renderer.setPixelRatio(spacePixelRatio(window.devicePixelRatio));
      pixelRatioUniform.value = renderer.getPixelRatio();
      renderer.setSize(clientWidth, clientHeight, false);
      camera.aspect = clientWidth / Math.max(1, clientHeight);
      camera.updateProjectionMatrix();
    };
    const draw = () => {
      if (disposed || renderer.getContext().isContextLost()) return;
      const drift = driftRef.current;
      const view =
        modeRef.current === 'drift'
          ? driftView(drift.startLng, performance.now() - drift.startMs)
          : useCameraStore.getState().view;
      const rotation = starCameraRotation(view);
      camera.rotation.set(rotation.x, rotation.y, rotation.z);
      renderer.render(scene, camera);
    };

    // Un dibujo por cuadro como mucho y a 30 por segundo: los movimientos de la
    // cámara llegan a 60 por segundo mientras el globo gira. Al derivar se
    // dibuja sin parar, pero a DRIFT_FPS.
    let frame = 0;
    let lastDraw = 0;
    const frameDraw = (now: number) => {
      const drifting = modeRef.current === 'drift';
      if (now - lastDraw < MS_PER_SECOND / (drifting ? DRIFT_FPS : SPACE_FPS)) {
        frame = requestAnimationFrame(frameDraw);
        return;
      }
      frame = 0;
      lastDraw = now;
      draw();
      if (drifting) requestDraw();
    };
    function requestDraw() {
      if (frame || disposed || document.hidden) return;
      frame = requestAnimationFrame(frameDraw);
    }
    requestDrawRef.current = requestDraw;

    // La foto: se baja, se decodifica fuera del hilo principal y se sube a la
    // tarjeta en piezas, una por cuadro (ver SKY_TILE_PX).
    const addTiles = async () => {
      const name = starTextureFor(renderer.capabilities.maxTextureSize);
      const response = await fetch(`/tiles/space/${name}`);
      const full = await createImageBitmap(await response.blob());
      const pieces = skyTiles(full.width, full.height);
      for (const piece of pieces) {
        if (isDisposed()) break;
        // imageOrientation «flipY»: three.js no voltea las ImageBitmap y la
        // esfera espera la foto con el norte arriba.
        const bitmap = await createImageBitmap(full, piece.x, piece.y, piece.width, piece.height, {
          imageOrientation: 'flipY',
        });
        if (isDisposed()) {
          bitmap.close();
          break;
        }
        const texture = new Texture(bitmap);
        texture.flipY = false;
        texture.colorSpace = SRGBColorSpace;
        texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
        texture.needsUpdate = true;
        const mesh = new Mesh(
          new SphereGeometry(
            SKY_RADIUS,
            TILE_SEGMENTS,
            TILE_SEGMENTS,
            piece.phiStart,
            piece.phiLength,
            piece.thetaStart,
            piece.thetaLength,
          ),
          new ShaderMaterial({
            vertexShader: SKY_VERTEX,
            fragmentShader: SKY_FRAGMENT,
            uniforms: {
              map: { value: texture },
              blackPoint: { value: STARMAP_BLACK_POINT },
              gain: { value: STARMAP_GAIN },
            },
            side: BackSide,
          }),
        );
        // Se sube ya (no en el siguiente dibujo) y se espera un cuadro antes
        // de la siguiente pieza: así la tarjeta nunca hace una subida larga.
        renderer.initTexture(texture);
        tiles.push({ mesh, texture });
        scene.add(mesh);
        requestDraw();
        await new Promise((resolve) => requestAnimationFrame(resolve));
      }
      full.close();
    };
    addTiles().catch(() => {
      // Sin la foto queda el cielo negro con las estrellas propias: no es error
      // para el analista (por ejemplo, si se sale de Explorar mientras carga).
    });

    resize();
    requestDraw();
    const observer = new ResizeObserver(() => {
      resize();
      requestDraw();
    });
    observer.observe(canvas);
    // Un cambio de escala solo (zoom del navegador, otra pantalla) no siempre
    // cambia el tamaño en CSS: se escucha aparte, y se vuelve a escuchar con la
    // escala nueva cada vez que cambia.
    let scaleQuery: MediaQueryList | null = null;
    const onScale = () => {
      resize();
      requestDraw();
      watchScale();
    };
    function watchScale() {
      scaleQuery?.removeEventListener('change', onScale);
      // Sin matchMedia (navegadores viejos, pruebas) basta el ResizeObserver.
      if (typeof window.matchMedia !== 'function') return;
      scaleQuery = window.matchMedia(`(resolution: ${String(window.devicePixelRatio)}dppx)`);
      scaleQuery.addEventListener('change', onScale);
    }
    watchScale();
    // Solo se dibuja cuando la cámara se mueve.
    const unsubscribe = useCameraStore.subscribe(requestDraw);
    const onVisibility = () => {
      requestDraw();
    };
    document.addEventListener('visibilitychange', onVisibility);
    // Si el navegador devuelve la tarjeta, three.js vuelve a subir lo que
    // necesita; aquí solo hace falta volver a pintar.
    canvas.addEventListener('webglcontextrestored', requestDraw);

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      unsubscribe();
      observer.disconnect();
      scaleQuery?.removeEventListener('change', onScale);
      document.removeEventListener('visibilitychange', onVisibility);
      canvas.removeEventListener('webglcontextrestored', requestDraw);
      geometry.dispose();
      material.dispose();
      for (const { mesh, texture } of tiles) {
        mesh.geometry.dispose();
        mesh.material.dispose();
        texture.dispose();
        const image: unknown = texture.image;
        if (image instanceof ImageBitmap) image.close();
      }
      renderer.dispose();
      // Suelta el contexto ya, sin esperar al recolector: Chrome limita cuántos
      // contextos 3D puede haber y cada uno ocupa memoria de video.
      renderer.forceContextLoss();
      canvas.remove();
    };
  }, []);

  return <div ref={hostRef} className="absolute inset-0" aria-hidden="true" />;
}
