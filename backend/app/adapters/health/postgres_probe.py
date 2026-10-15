"""Revisor de salud de PostgreSQL + PostGIS.

Comprueba que la base responde y que están instaladas las extensiones que el
sistema necesita (PostGIS, pg_trgm y unaccent, ver ADR-0002). Reporta las
versiones de PostgreSQL y PostGIS.

No hace: no crea extensiones (eso lo hace ``make bootstrap`` como
superusuario) ni revisa el esquema de tablas.
"""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.health import ComponentHealth

# Extensiones obligatorias (especificación, sección 5.4).
REQUIRED_EXTENSIONS = ("postgis", "pg_trgm", "unaccent")


class PostgresHealthProbe:
    """Revisa conexión, versión y extensiones de PostgreSQL."""

    name = "database"

    def __init__(self, engine: AsyncEngine) -> None:
        """Guarda el engine con el que se harán las consultas.

        Args:
            engine: Engine asíncrono de SQLAlchemy ya configurado.
        """
        self._engine = engine

    async def check(self) -> ComponentHealth:
        """Consulta la versión del servidor y las extensiones instaladas.

        Returns:
            ``OK`` con versiones si todo está bien; ``ERROR`` si no hay
            conexión o falta alguna extensión.
        """
        try:
            async with self._engine.connect() as conn:
                server_version = (await conn.execute(text("SHOW server_version"))).scalar_one()
                rows = await conn.execute(
                    text(
                        "SELECT extname, extversion FROM pg_extension WHERE extname = ANY(:names)"
                    ),
                    {"names": list(REQUIRED_EXTENSIONS)},
                )
                installed = {str(name): str(version) for name, version in rows}
        except (SQLAlchemyError, OSError) as exc:
            return ComponentHealth.error(
                self.name, f"No se pudo conectar a PostgreSQL ({type(exc).__name__})."
            )

        missing = [name for name in REQUIRED_EXTENSIONS if name not in installed]
        if missing:
            return ComponentHealth.error(
                self.name,
                f"Faltan extensiones: {', '.join(missing)}. Ejecuta `make bootstrap`.",
            )
        return ComponentHealth.ok(
            self.name,
            info={"postgres": str(server_version), **{k: str(v) for k, v in installed.items()}},
        )
