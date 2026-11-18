"""Región «Mundo» para buscar en todo el mundo (18/11/2026, ADR-0112).

Benji: «si yo quisiera buscar bases de datos hackeadas, pero en todo el
mundo, no tengo esa opción». Toda búsqueda va atada a una región; hasta hoy
la más grande era un país. Se agrega una región por encima de los países:

- Valor nuevo ``world`` en el tipo ``region_level``, antes de ``country``.
  Es un nivel propio, no un país: así las consultas que piden países
  (gazetteer, mapa del reporte, «¿en qué país cae este punto?») no la
  confunden con uno.
- Una fila: ``code = 'WLD'`` (código de «World» en el Banco Mundial y la
  ONU), «Mundo», con alias «Todo el mundo» y «Global». Su forma es el
  rectángulo de toda la Tierra; su encuadre (``focus_bbox``) deja fuera la
  Antártida y el Ártico, que no tienen noticias. Sin ``iso_a2``, ``fips_code``
  ni ``name_en``: no filtra por país.

No toca ninguna fila existente. Índices: los de ``regions`` (migración 0002)
ya cubren ``level`` y ``code``.

Revisión: 0048
Anterior: 0047
Fecha: 2026-11-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0048"
down_revision: str | None = "0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Agrega el nivel ``world`` y la fila «Mundo»."""
    # PostgreSQL no deja usar un valor nuevo de un ENUM en la misma
    # transacción que lo agrega: se agrega aparte, ya confirmado.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE region_level ADD VALUE IF NOT EXISTS 'world' BEFORE 'country'")
    op.execute(
        """
        INSERT INTO regions (
            level, code, parent_id, country_code, name, name_norm,
            aliases, aliases_norm, display_prefix, geom, centroid, bbox,
            focus_bbox, source
        ) VALUES (
            'world', 'WLD', NULL, 'WLD', 'Mundo', 'MUNDO',
            ARRAY['Todo el mundo', 'Global'], ARRAY['TODO EL MUNDO', 'GLOBAL'],
            '',
            ST_Multi(ST_MakeEnvelope(-180, -90, 180, 90, 4326)),
            ST_SetSRID(ST_MakePoint(0, 20), 4326),
            ARRAY[-180, -90, 180, 90]::double precision[],
            ARRAY[-180, -58, 180, 75]::double precision[],
            'Monitor de Noticias (ADR-0112)'
        )
        ON CONFLICT (code) DO NOTHING
        """
    )


def downgrade() -> None:
    """Quita la fila «Mundo».

    El valor ``world`` se queda en el tipo: PostgreSQL no permite quitar un
    valor de un ENUM sin recrear el tipo y todas sus columnas. Sin la fila,
    nada lo usa. Falla si hay búsquedas o envíos en «Mundo» (llave foránea
    ``RESTRICT``): hay que borrarlos antes, con aprobación.
    """
    op.execute("DELETE FROM regions WHERE code = 'WLD'")
