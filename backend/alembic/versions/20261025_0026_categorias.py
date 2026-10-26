"""Categorías de noticias: qué delito trata cada nota (F12.4, ADR-0029).

- ``categories``: catálogo configurable. La lista provisional sale del plan
  de la Fase 12 (§4.4); los colores y símbolos se deciden después con datos
  reales, así que nacen en ``NULL``. Una sola categoría es la de respaldo
  («Otros», ``is_other``), con un índice único parcial que lo garantiza.
- ``articles.category_id``: la categoría que eligió la IA (o ``NULL`` si
  todavía no se clasifica). ``category_raw`` es la etiqueta libre que
  propuso, para el análisis de frecuencias de después, y ``category_version``
  la versión del prompt que la clasificó (si cambia, se vuelve a clasificar).

Índices en la misma migración (CLAUDE.md §6.3): por ``category_id`` (la lista,
la línea de tiempo y el reporte filtran y agrupan por categoría) y el único
de ``name_norm`` (no repetir categorías).

Revisión: 0026
Anterior: 0025
Fecha: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (nombre, nombre normalizado, lo que la IA debe entender por la categoría).
# Lista provisional del plan de la Fase 12 (§4.4), en su orden.
_SEED: tuple[tuple[str, str, str], ...] = (
    (
        "Narcotráfico y delitos contra la salud",
        "NARCOTRAFICO Y DELITOS CONTRA LA SALUD",
        "Producción, transporte o venta de drogas; narcomenudeo; laboratorios; "
        "aseguramiento de droga.",
    ),
    (
        "Delincuencia organizada",
        "DELINCUENCIA ORGANIZADA",
        "Cárteles, grupos criminales y sus líderes, cuando la nota trata del grupo "
        "más que de un delito puntual.",
    ),
    (
        "Secuestro",
        "SECUESTRO",
        "Privación ilegal de la libertad para pedir rescate o por otra razón.",
    ),
    (
        "Desaparición de personas",
        "DESAPARICION DE PERSONAS",
        "Personas desaparecidas, fichas de búsqueda, fosas y búsqueda de restos.",
    ),
    (
        "Homicidio",
        "HOMICIDIO",
        "Asesinatos, ejecuciones, feminicidios y ataques con víctimas mortales.",
    ),
    (
        "Armas y explosivos",
        "ARMAS Y EXPLOSIVOS",
        "Tráfico, portación o aseguramiento de armas, cartuchos, drones o explosivos.",
    ),
    (
        "Huachicol y delitos contra hidrocarburos",
        "HUACHICOL Y DELITOS CONTRA HIDROCARBUROS",
        "Robo o venta ilegal de combustible y gas; tomas clandestinas; huachicol fiscal.",
    ),
    (
        "Lavado de dinero y delitos fiscales",
        "LAVADO DE DINERO Y DELITOS FISCALES",
        "Operaciones con recursos de procedencia ilícita, defraudación fiscal, facturas falsas.",
    ),
    (
        "Corrupción",
        "CORRUPCION",
        "Servidores públicos que abusan del cargo: sobornos, desvío de recursos, "
        "enriquecimiento ilícito.",
    ),
    (
        "Trata de personas",
        "TRATA DE PERSONAS",
        "Explotación sexual o laboral, tráfico de migrantes.",
    ),
    (
        "Extorsión",
        "EXTORSION",
        "Cobro de piso, extorsión telefónica, amenazas para obtener dinero.",
    ),
    (
        "Ciberdelitos",
        "CIBERDELITOS",
        "Fraudes en línea, hackeo, robo de datos, ransomware, pornografía infantil en internet.",
    ),
    (
        "Delitos electorales",
        "DELITOS ELECTORALES",
        "Compra de votos, uso de recursos públicos en campañas, violencia política electoral.",
    ),
    (
        "Otros",
        "OTROS",
        "Cualquier tema que no encaje claramente en las demás categorías.",
    ),
)


def upgrade() -> None:
    """Crea el catálogo, lo siembra y agrega la categoría a las notas."""
    op.execute(
        """
        CREATE TABLE categories (
            id          bigserial PRIMARY KEY,
            name        text NOT NULL CHECK (btrim(name) <> ''),
            name_norm   text NOT NULL,
            description text NOT NULL DEFAULT '',
            color       text,
            symbol      text,
            sort_order  integer NOT NULL DEFAULT 0,
            is_active   boolean NOT NULL DEFAULT true,
            is_other    boolean NOT NULL DEFAULT false,
            created_at  timestamptz NOT NULL DEFAULT now(),
            updated_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX categories_name_norm ON categories (name_norm)")
    op.execute("CREATE UNIQUE INDEX categories_one_other ON categories (is_other) WHERE is_other")
    insert = sa.text(
        "INSERT INTO categories (name, name_norm, description, sort_order, is_other) "
        "VALUES (:name, :norm, :description, :order, :other)"
    )
    for order, (name, norm, description) in enumerate(_SEED, start=1):
        op.execute(
            insert.bindparams(
                name=name, norm=norm, description=description, order=order, other=norm == "OTROS"
            )
        )
    op.execute(
        "ALTER TABLE articles "
        "ADD COLUMN category_id bigint REFERENCES categories (id) ON DELETE SET NULL, "
        "ADD COLUMN category_raw text, "
        "ADD COLUMN category_version text"
    )
    op.execute(
        "CREATE INDEX articles_category ON articles (category_id) WHERE category_id IS NOT NULL"
    )


def downgrade() -> None:
    """Quita la categoría de las notas y el catálogo."""
    op.execute("DROP INDEX articles_category")
    op.execute(
        "ALTER TABLE articles DROP COLUMN category_id, DROP COLUMN category_raw, "
        "DROP COLUMN category_version"
    )
    op.execute("DROP TABLE categories")
