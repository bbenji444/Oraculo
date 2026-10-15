/**
 * Nombres y descripciones en español de cada componente de /health.
 *
 * Los nombres técnicos (`database`, `worker`) vienen de la API; aquí se
 * traducen a algo que un analista entienda sin capacitación.
 */

interface ComponentLabel {
  title: string;
  description: string;
}

const LABELS: Record<string, ComponentLabel> = {
  api: { title: 'API', description: 'Recibe las peticiones de esta pantalla.' },
  database: {
    title: 'Base de datos',
    description: 'PostgreSQL con PostGIS: regiones, noticias e historial.',
  },
  redis: { title: 'Cola y caché', description: 'Redis: fila de tareas y resultados recientes.' },
  worker: { title: 'Procesador de búsquedas', description: 'Worker que ejecuta las búsquedas.' },
};

/**
 * Devuelve el título y la descripción de un componente.
 *
 * @param name Nombre técnico que envía la API.
 * @returns La etiqueta en español; si el componente es nuevo y no está en la
 *   lista, usa su nombre técnico para no ocultarlo.
 */
export function componentLabel(name: string): ComponentLabel {
  return LABELS[name] ?? { title: name, description: 'Componente del sistema.' };
}
