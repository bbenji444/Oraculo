"""Verificar extensiones obligatorias de PostgreSQL.

Es la migración base: no crea tablas. Asegura que la base tenga PostGIS,
pg_trgm y unaccent (ADR-0002) antes de que las siguientes migraciones las usen.

PostGIS solo lo puede instalar un superusuario, y las migraciones corren con
el usuario de la aplicación, así que aquí solo se verifica que exista: lo
instala ``make bootstrap``. pg_trgm y unaccent son extensiones "confiables",
así que se crean si faltan.

Revisión: 0001
Anterior:
Fecha: 2026-10-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Crea las extensiones confiables y exige que PostGIS ya exista."""
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    has_postgis = (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'postgis'"))
        .scalar()
    )
    if not has_postgis:
        raise RuntimeError(
            "Falta la extensión PostGIS en esta base. Ejecuta `make bootstrap`, "
            "que la instala como superusuario."
        )


def downgrade() -> None:
    """No borra extensiones: otras bases o datos podrían depender de ellas."""
