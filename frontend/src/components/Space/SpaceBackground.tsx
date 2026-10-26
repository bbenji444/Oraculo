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
  CanvasTexture,
  Color,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  Points,
  Scene,
  ShaderMaterial,
  SphereGeometry,
  Sprite,
  SpriteMaterial,
  SRGBColorSpace,
  TextureLoader,
  WebGLRenderer,
} from 'three';

import {
  makeStars,
  SPACE_FPS,
  SPACE_MAX_PIXEL_RATIO,
  STARMAP_EXPOSURE,
  starCameraRotation,
  starTextureFor,
  TWINKLE_MIN,
} from '../../map/space';
import { prefersReducedMotion } from '../../map/spin';
import { subsolarPoint, sunSkyDirection } from '../../map/sun';
import { useCameraStore } from '../../store/camera';

// Radio de la esfera del cielo y campo de visión de su cámara. El campo de
// visión parecido al de MapLibre (~37°) evita que las estrellas "resbalen"
// distinto que el globo al girar.
const SKY_RADIUS = 100;
const FIELD_OF_VIEW = 37;
const SPHERE_SEGMENTS = 64;
// Las estrellas propias van un poco dentro de la esfera para quedar encima.
const STARS_RADIUS = 95;
const MS_PER_SECOND = 1000;
// El Sol: un halo cálido en su dirección real, detrás del globo (se asoma por
// el borde como en un eclipse). Tamaño en unidades del cielo y textura del halo.
const SUN_DISTANCE = 90;
const SUN_SIZE = 46;
const SUN_TEXTURE_PX = 256;
const SUN_UPDATE_MS = 60_000;

/** Halo radial del Sol: núcleo blanco, corona cálida y desvanecido suave. */
function sunHaloTexture(): CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = SUN_TEXTURE_PX;
  canvas.height = SUN_TEXTURE_PX;
  const context = canvas.getContext('2d');
  if (context) {
    const half = SUN_TEXTURE_PX / 2;
    const glow = context.createRadialGradient(half, half, 0, half, half, half);
    glow.addColorStop(0, 'rgba(255,255,255,1)');
    glow.addColorStop(0.06, 'rgba(255,246,220,0.95)');
    glow.addColorStop(0.18, 'rgba(255,214,150,0.45)');
    glow.addColorStop(0.45, 'rgba(120,200,255,0.12)');
    glow.addColorStop(1, 'rgba(0,0,0,0)');
    context.fillStyle = glow;
    context.fillRect(0, 0, SUN_TEXTURE_PX, SUN_TEXTURE_PX);
  }
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  return texture;
}

const STAR_VERTEX = /* glsl */ `
  attribute float size;
  attribute float phase;
  attribute float tint;
  uniform float time;
  uniform float twinkleMin;
  varying float vAlpha;
  varying vec3 vColor;
  void main() {
    // Titileo lento: cada estrella con su desfase y su propio ritmo.
    float wave = 0.5 + 0.5 * sin(time * (0.4 + 0.3 * fract(phase)) + phase);
    vAlpha = mix(twinkleMin, 1.0, wave);
    vColor = mix(vec3(0.75, 0.85, 1.0), vec3(1.0, 0.92, 0.78), tint);
    gl_PointSize = size;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;
const STAR_FRAGMENT = /* glsl */ `
  varying float vAlpha;
  varying vec3 vColor;
  void main() {
    // Punto redondo y difuminado en el borde (no un cuadrito).
    float d = length(gl_PointCoord - 0.5);
    float glow = smoothstep(0.5, 0.0, d);
    gl_FragColor = vec4(vColor * glow, glow * vAlpha);
  }
`;

export function SpaceBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, SPACE_MAX_PIXEL_RATIO));
    renderer.outputColorSpace = SRGBColorSpace;
    renderer.setClearColor(new Color('#02030a'));

    const scene = new Scene();
    const camera = new PerspectiveCamera(FIELD_OF_VIEW, 1, 0.1, SKY_RADIUS * 2);
    camera.rotation.order = 'YXZ';

    const textureName = starTextureFor(
      renderer.capabilities.maxTextureSize,
      window.screen.width * window.devicePixelRatio,
    );
    const texture = new TextureLoader().load(`/tiles/space/${textureName}`, () => {
      draw();
    });
    texture.colorSpace = SRGBColorSpace;
    texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
    const sky = new Mesh(
      new SphereGeometry(SKY_RADIUS, SPHERE_SEGMENTS, SPHERE_SEGMENTS),
      // Color por encima de 1: aclara la textura de la NASA, que viene tenue.
      new MeshBasicMaterial({
        map: texture,
        side: BackSide,
        color: new Color(STARMAP_EXPOSURE, STARMAP_EXPOSURE, STARMAP_EXPOSURE),
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
    const pixelRatio = renderer.getPixelRatio();
    geometry.setAttribute(
      'size',
      new BufferAttribute(Float32Array.from(stars.map((s) => s.size * pixelRatio)), 1),
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
    const material = new ShaderMaterial({
      vertexShader: STAR_VERTEX,
      fragmentShader: STAR_FRAGMENT,
      uniforms: { time: timeUniform, twinkleMin: { value: reduced ? 1 : TWINKLE_MIN } },
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
    });
    scene.add(new Points(geometry, material));

    const sunTexture = sunHaloTexture();
    const sunMaterial = new SpriteMaterial({
      map: sunTexture,
      transparent: true,
      depthWrite: false,
      blending: AdditiveBlending,
    });
    const sun = new Sprite(sunMaterial);
    sun.scale.set(SUN_SIZE, SUN_SIZE, 1);
    const placeSun = () => {
      const direction = sunSkyDirection(subsolarPoint(new Date()));
      sun.position.set(
        direction.x * SUN_DISTANCE,
        direction.y * SUN_DISTANCE,
        direction.z * SUN_DISTANCE,
      );
    };
    placeSun();
    scene.add(sun);
    const sunTimer = window.setInterval(placeSun, SUN_UPDATE_MS);

    const resize = () => {
      const { clientWidth, clientHeight } = canvas;
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
      window.clearInterval(sunTimer);
      sunTexture.dispose();
      sunMaterial.dispose();
      cancelAnimationFrame(frame);
      unsubscribe();
      observer.disconnect();
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
