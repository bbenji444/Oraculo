"""``ReportMapPort`` con PostGIS: el mapa estático del reporte en SVG (§15, ADR-0018).

Dibuja la región buscada con:
- sus subregiones coloreadas según cuántas notas tiene cada una;
- las regiones vecinas en gris, para ubicarse;
- el contorno de la región;
- un punto por nota, con anillo punteado si solo se ubicó por estado o
  país (igual que en el globo, §14.2).

PostGIS hace el trabajo pesado: simplifica cada polígono según el tamaño de
la región (``ST_SimplifyPreserveTopology``) y lo convierte a trazos SVG
(``ST_AsSVG``). La proyección es equirectangular, con la longitud
multiplicada por el coseno de la latitud media para que la región no se vea
estirada. A esta escala no hace falta más.

No hace: no decide qué se cuenta (eso es ``BuildReport``) ni arma el PDF.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from html import escape

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.ports.reports import MapPoint, SubregionCount
from app.domain.aggregates import AggregateLevel
from app.domain.region import Region, RegionLevel

# Paleta secuencial (de pocas a muchas notas), legible impresa en blanco y
# negro. Sin notas: gris muy claro.
CLASS_FILLS = ("#dbeafe", "#93c5fd", "#3b82f6", "#1d4ed8", "#1e3a8a")
NO_NOTES_FILL = "#f8fafc"
CONTEXT_FILL = "#e2e8f0"
BORDER_COLOR = "#94a3b8"
OUTLINE_COLOR = "#0f172a"
POINT_COLOR = "#e11d48"
# Margen alrededor de la región: 4 % de su lado mayor, para que el contorno
# no toque el marco.
MARGIN_SHARE = 0.04
# Tolerancia de simplificación: 1/1500 del lado mayor (~2 km para todo
# México, ~300 m para Jalisco). A tamaño de página no se nota y evita SVG
# pesados en estados con cientos de municipios (Oaxaca tiene 570).
SIMPLIFY_SHARE = 1 / 1500
# Decimales de las coordenadas en grados: 4 ≈ 11 m, de sobra para una página.
SVG_DIGITS = 4
# Tamaños relativos al lado mayor de la región (medidos a ojo en el PDF).
POINT_SHARE = 0.007
LABEL_SHARE = 0.022
BORDER_SHARE = 0.0012
OUTLINE_SHARE = 0.004
# Solo se nombran las subregiones con más notas: más nombres tapan el mapa.
MAX_LABELS = 8
# Lado mínimo en grados (~1 km): una localidad sin polígono es solo un punto.
MIN_SIZE_DEGREES = 0.01
# Ancho de referencia del SVG; el PDF lo escala al ancho de la página.
SVG_WIDTH = 1000

# Las tres consultas convierten igual cada polígono a trazos SVG: lo
# simplifican (:tol), corrigen la longitud por la latitud media (:kx) y
# redondean a :digits decimales.
_SUBREGIONS = text(
    """
    SELECT r.code, r.name,
           ST_AsSVG(ST_Scale(ST_SimplifyPreserveTopology(r.geom, :tol), :kx, 1), 0, :digits)
               AS path,
           ST_X(r.centroid) AS lon, ST_Y(r.centroid) AS lat
    FROM regions r
    WHERE r.geom IS NOT NULL AND (
        (:itself AND r.id = :region_id) OR (NOT :itself AND r.parent_id = :region_id)
    )
    ORDER BY r.code
    """
)
_OUTLINE = text(
    """
    SELECT ST_AsSVG(ST_Scale(ST_SimplifyPreserveTopology(r.geom, :tol), :kx, 1), 0, :digits)
    FROM regions r
    WHERE r.id = :id AND r.geom IS NOT NULL
    """
)
_CONTEXT = text(
    """
    SELECT ST_AsSVG(ST_Scale(ST_SimplifyPreserveTopology(r.geom, :tol), :kx, 1), 0, :digits)
               AS path
    FROM regions r
    WHERE r.level = CAST(:level AS region_level) AND r.id <> :region_id AND r.geom IS NOT NULL
      AND r.geom && ST_MakeEnvelope(:west, :south, :east, :north, 4326)
    """
)


@dataclass(frozen=True, slots=True)
class LegendClass:
    """Un color de la leyenda del mapa.

    Attributes:
        label: Rango de notas ("1", "2–3").
        fill: Color de relleno.
    """

    label: str
    fill: str


def _bounds(max_count: int) -> list[tuple[int, int]]:
    classes = min(len(CLASS_FILLS), max_count)
    return [
        (math.floor(i * max_count / classes) + 1, math.floor((i + 1) * max_count / classes))
        for i in range(classes)
    ]


def legend(max_count: int) -> list[LegendClass]:
    """Rangos de notas y sus colores, en intervalos iguales de 1 al máximo.

    Args:
        max_count: Notas de la subregión con más notas.

    Returns:
        Hasta 5 clases; ninguna si no hay notas.

    Example:
        >>> [c.label for c in legend(7)]
        ['1', '2', '3–4', '5', '6–7']
    """
    return [
        LegendClass(str(low) if low == high else f"{low}–{high}", CLASS_FILLS[i])
        for i, (low, high) in enumerate(_bounds(max_count))
    ]


def fill_for(count: int, max_count: int) -> str:
    """Color de una subregión según sus notas.

    Args:
        count: Notas de la subregión.
        max_count: Notas de la subregión con más notas.

    Returns:
        El color de su clase, o el gris de "sin notas".
    """
    if count <= 0:
        return NO_NOTES_FILL
    for i, (_low, high) in enumerate(_bounds(max_count)):
        if count <= high:
            return CLASS_FILLS[i]
    return CLASS_FILLS[-1]


@dataclass(frozen=True, slots=True)
class _Frame:
    """Encuadre del mapa en coordenadas proyectadas."""

    kx: float
    size: float
    west: float
    south: float
    east: float
    north: float

    @classmethod
    def of(cls, region: Region) -> "_Frame":
        box = region.bbox
        size = max(box.east - box.west, box.north - box.south, MIN_SIZE_DEGREES)
        margin = size * MARGIN_SHARE
        kx = math.cos(math.radians((box.north + box.south) / 2))
        return cls(
            kx, size, box.west - margin, box.south - margin, box.east + margin, box.north + margin
        )

    def view_box(self) -> tuple[float, float, float, float]:
        # ST_AsSVG invierte la latitud (y = -lat), como espera SVG.
        return (
            self.west * self.kx,
            -self.north,
            (self.east - self.west) * self.kx,
            self.north - self.south,
        )

    def x(self, lon: float) -> float:
        return lon * self.kx

    @staticmethod
    def y(lat: float) -> float:
        return -lat


def _num(value: float) -> str:
    return f"{value:.{SVG_DIGITS}f}"


class PostgisStaticMap:
    """Dibuja el mapa estático con las geometrías de ``regions``."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el engine compartido.

        Args:
            engine: Engine asíncrono de SQLAlchemy (psycopg).
        """
        self._engine = engine

    async def render(
        self,
        region: Region,
        level: AggregateLevel,
        counts: Sequence[SubregionCount],
        points: Sequence[MapPoint],
    ) -> str:
        """Ver ``ReportMapPort.render``."""
        frame = _Frame.of(region)
        geometry = {"tol": frame.size * SIMPLIFY_SHARE, "kx": frame.kx, "digits": SVG_DIGITS}
        # Otro país o una localidad no tienen subregiones dibujables: se
        # dibujan a sí mismos.
        itself = level is AggregateLevel.COUNTRY or region.level is RegionLevel.LOCALITY
        async with self._engine.connect() as conn:
            shapes = list(
                (
                    await conn.execute(
                        _SUBREGIONS, {**geometry, "itself": itself, "region_id": region.id}
                    )
                ).mappings()
            )
            outline_id = region.id if region.has_polygon else (region.parent_id or region.id)
            outline = (
                await conn.execute(_OUTLINE, {**geometry, "id": outline_id})
            ).scalar_one_or_none()
            context = [
                row.path
                for row in await conn.execute(
                    _CONTEXT,
                    {
                        **geometry,
                        "level": region.level.value,
                        "region_id": region.id,
                        "west": frame.west,
                        "south": frame.south,
                        "east": frame.east,
                        "north": frame.north,
                    },
                )
            ]
        return _svg(frame, region, _Layers(shapes, outline, context), counts, points)


@dataclass(frozen=True, slots=True)
class _Layers:
    """Lo que se lee de la base: subregiones, contorno y vecinas."""

    shapes: list[RowMapping]
    outline: str | None
    context: list[str]


def _svg(
    frame: _Frame,
    region: Region,
    layers: _Layers,
    counts: Sequence[SubregionCount],
    points: Sequence[MapPoint],
) -> str:
    shapes, outline, context = layers.shapes, layers.outline, layers.context
    by_code = {c.code: c.count for c in counts}
    max_count = max(by_code.values(), default=0)
    x0, y0, width, height = frame.view_box()
    pixel_height = round(SVG_WIDTH * height / width)
    border = _num(frame.size * BORDER_SHARE)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" class="report-map" '
        f'viewBox="{_num(x0)} {_num(y0)} {_num(width)} {_num(height)}" '
        f'width="{SVG_WIDTH}" height="{pixel_height}" role="img">',
        f"<title>Notas por subregión en {escape(region.display_name)}</title>",
        f'<g fill="{CONTEXT_FILL}" stroke="#ffffff" stroke-width="{border}">',
        *(f'<path d="{path}"/>' for path in context),
        "</g>",
        f'<g stroke="{BORDER_COLOR}" stroke-width="{border}">',
        *(
            f'<path d="{row["path"]}" fill="{fill_for(by_code.get(row["code"], 0), max_count)}">'
            f"<title>{escape(row['name'])}: {by_code.get(row['code'], 0)}</title></path>"
            for row in shapes
        ),
        "</g>",
    ]
    if outline:
        parts.append(
            f'<path d="{outline}" fill="none" stroke="{OUTLINE_COLOR}" '
            f'stroke-width="{_num(frame.size * OUTLINE_SHARE)}"/>'
        )
    parts.extend(_points(frame, points))
    parts.extend(_labels(frame, shapes, by_code))
    parts.append("</svg>")
    return "".join(parts)


def _points(frame: _Frame, points: Sequence[MapPoint]) -> list[str]:
    radius = frame.size * POINT_SHARE
    stroke = _num(radius / 3)
    out = []
    for point in points:
        cx, cy = _num(frame.x(point.lon)), _num(frame.y(point.lat))
        if point.coarse:
            # Anillo punteado: solo se sabe el estado o el país (§14.2).
            dash = _num(radius / 2)
            out.append(
                f'<circle cx="{cx}" cy="{cy}" r="{_num(radius * 1.6)}" fill="none" '
                f'stroke="{POINT_COLOR}" stroke-width="{stroke}" '
                f'stroke-dasharray="{dash} {dash}"/>'
            )
        else:
            out.append(
                f'<circle cx="{cx}" cy="{cy}" r="{_num(radius)}" fill="{POINT_COLOR}" '
                f'fill-opacity="0.85" stroke="#ffffff" stroke-width="{stroke}"/>'
            )
    return out


def _labels(frame: _Frame, shapes: list[RowMapping], by_code: dict[str, int]) -> list[str]:
    ranked = sorted(
        (row for row in shapes if by_code.get(row["code"], 0) > 0),
        key=lambda row: (-by_code[row["code"]], row["name"]),
    )[:MAX_LABELS]
    size = _num(frame.size * LABEL_SHARE)
    halo = _num(frame.size * LABEL_SHARE / 4)
    out = []
    for row in ranked:
        x, y = _num(frame.x(row["lon"])), _num(frame.y(row["lat"]))
        name = escape(row["name"])
        # Primero un halo blanco y encima el texto: se lee sobre cualquier color.
        common = f'x="{x}" y="{y}" font-size="{size}" text-anchor="middle"'
        out.append(
            f'<text {common} fill="#ffffff" stroke="#ffffff" stroke-width="{halo}">{name}</text>'
        )
        out.append(f'<text {common} fill="{OUTLINE_COLOR}">{name}</text>')
    return out
