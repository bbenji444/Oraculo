/**
 * Fondo de universo detrás del globo (ADR-0017): la esfera de estrellas y Vía
 * Láctea de la NASA vista desde dentro, más estrellas propias nítidas que
 * titilan. Gira con la cámara del mapa (`useCameraStore`), así el universo
 * acompaña al globo.
 *
 * Rendimiento: dibuja a 30 cuadros por segundo como máximo, con resolución
 * limitada, y se detiene si la pestaña no está a la vista. Con "menos
 * movimiento" las estrellas no titilan y solo se dibuja al mover la cámara.
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
  TextureLoader,
  WebGLRenderer,
} from 'three';

import {
  makeStars,
  SPACE_FPS,
  SKY_FIELD_OF_VIEW,
  spacePixelRatio,
  STAR_MAX_SIZE,
  STARMAP_BLACK_POINT,
  STARMAP_GAIN,
  starCameraRotation,
  starTextureFor,
  TWINKLE_MIN,
} from '../../map/space';
import { prefersReducedMotion } from '../../map/spin';
import { useCameraStore } from '../../store/camera';

// Radio de la esfera del cielo (su campo de visión es SKY_FIELD_OF_VIEW).
const SKY_RADIUS = 100;
const SPHERE_SEGMENTS = 64;
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
  attribute float phase;
  attribute float tint;
  uniform float time;
  uniform float twinkleMin;
  uniform float maxSize;
  uniform float pixelRatio;
  varying float vAlpha;
  varying vec3 vColor;
  void main() {
    // Titileo lento: cada estrella con su desfase y su propio ritmo.
    float wave = 0.5 + 0.5 * sin(time * (0.4 + 0.3 * fract(phase)) + phase);
    float bright = clamp(size / maxSize, 0.35, 1.0);
    vAlpha = mix(twinkleMin, 1.0, wave) * bright;
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

export function SpaceBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: false });
    renderer.setPixelRatio(spacePixelRatio(window.devicePixelRatio));
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.setClearColor(new Color('#02030a'));

    const scene = new Scene();
    const camera = new PerspectiveCamera(SKY_FIELD_OF_VIEW, 1, 0.1, SKY_RADIUS * 2);
    camera.rotation.order = 'YXZ';

    const textureName = starTextureFor(renderer.capabilities.maxTextureSize);
    const texture = new TextureLoader().load(`/tiles/space/${textureName}`, () => {
      draw();
    });
    texture.colorSpace = SRGBColorSpace;
    texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
    const sky = new Mesh(
      new SphereGeometry(SKY_RADIUS, SPHERE_SEGMENTS, SPHERE_SEGMENTS),
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
    scene.add(sky);

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
      'phase',
      new BufferAttribute(Float32Array.from(stars.map((s) => s.phase)), 1),
    );
    geometry.setAttribute(
      'tint',
      new BufferAttribute(Float32Array.from(stars.map((s) => s.tint)), 1),
    );
    const reduced = prefersReducedMotion();
    const timeUniform = { value: 0 };
    const pixelRatioUniform = { value: renderer.getPixelRatio() };
    const material = new ShaderMaterial({
      vertexShader: STAR_VERTEX,
      fragmentShader: STAR_FRAGMENT,
      uniforms: {
        time: timeUniform,
        twinkleMin: { value: reduced ? 1 : TWINKLE_MIN },
        maxSize: { value: STAR_MAX_SIZE },
        pixelRatio: pixelRatioUniform,
      },
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
    });
    scene.add(new Points(geometry, material));

    const resize = () => {
      const { clientWidth, clientHeight } = canvas;
      // La escala se vuelve a leer cada vez (ver spacePixelRatio).
      renderer.setPixelRatio(spacePixelRatio(window.devicePixelRatio));
      pixelRatioUniform.value = renderer.getPixelRatio();
      renderer.setSize(clientWidth, clientHeight, false);
      camera.aspect = clientWidth / Math.max(1, clientHeight);
      camera.updateProjectionMatrix();
    };
    const applyView = () => {
      const rotation = starCameraRotation(useCameraStore.getState().view);
      camera.rotation.set(rotation.x, rotation.y, rotation.z);
    };
    function draw() {
      applyView();
      renderer.render(scene, camera);
    }

    resize();
    draw();
    const observer = new ResizeObserver(() => {
      resize();
      draw();
    });
    observer.observe(canvas);
    // Un cambio de escala solo (zoom del navegador, otra pantalla) no siempre
    // cambia el tamaño en CSS: se escucha aparte, y se vuelve a escuchar con la
    // escala nueva cada vez que cambia.
    let scaleQuery: MediaQueryList | null = null;
    const onScale = () => {
      resize();
      draw();
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
    // Con "menos movimiento" solo se dibuja cuando la cámara se mueve.
    const unsubscribe = useCameraStore.subscribe(() => {
      if (reduced) draw();
    });

    let frame = 0;
    let last = 0;
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      if (document.hidden || now - last < MS_PER_SECOND / SPACE_FPS) return;
      last = now;
      timeUniform.value = now / MS_PER_SECOND;
      draw();
    };
    if (!reduced) frame = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frame);
      unsubscribe();
      observer.disconnect();
      scaleQuery?.removeEventListener('change', onScale);
      geometry.dispose();
      material.dispose();
      texture.dispose();
      sky.geometry.dispose();
      sky.material.dispose();
      renderer.dispose();
    };
  }, []);

  return <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-hidden="true" />;
}
