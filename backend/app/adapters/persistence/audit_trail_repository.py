"""Lectura de la bitácora (``audit_log``) para la pantalla «Accesos».

Implementa ``AuditTrailPort``. Pagina por cursor sobre ``id`` (la llave
primaria, que crece con el tiempo), nunca con ``OFFSET`` (CLAUDE.md §6.3).
Agrega el nombre de la persona desde ``users``; los que no son personas
(``consola``, ``semilla``, ``anonimo``) quedan sin nombre.

Corre con el contexto de la petición: ``users`` solo se lee como
superusuario (migración 0039), igual que la ruta.

No hace: no escribe; cada repositorio guarda su registro con su cambio.
"""

from collections.abc import Mapping

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.domain.audit_trail import AuditEvent, AuditQuery

# El tema es lo de antes del primer punto de la acción (``access_key``). Se
# compara entero con ``= ANY`` y no con ``LIKE``: en LIKE el ``_`` de
# ``access_key`` sería un comodín.
_EVENTS = text(
    """
    SELECT a.id, a.created_at, a.user_id, u.display_name, a.action, a.entity_type,
           a.entity_id, a.payload, host(a.ip) AS ip
    FROM audit_log a
    LEFT JOIN users u ON u.username = a.user_id
    WHERE (CAST(:before AS bigint) IS NULL OR a.id < CAST(:before AS bigint))
      AND (cardinality(CAST(:prefixes AS text[])) = 0
           OR split_part(a.action, '.', 1) = ANY(CAST(:prefixes AS text[])))
      AND (CAST(:actor AS text) IS NULL OR a.user_id = CAST(:actor AS text))
    ORDER BY a.id DESC
    LIMIT :n
    """
)


def _event(row: RowMapping) -> AuditEvent:
    payload: Mapping[str, object] = row["payload"] or {}
    return AuditEvent(
        event_id=row["id"],
        created_at=row["created_at"],
        actor=row["user_id"],
        actor_name=row["display_name"],
        action=row["action"],
        entity_type=row["entity_type"],
        entity_id=row["entity_id"],
        payload=payload,
        ip=row["ip"],
    )


class PostgresAuditTrail:
    """``AuditTrailPort`` sobre ``audit_log``.

    Args:
        engine: Engine de la API (``create_api_engine``).
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def events(self, query: AuditQuery, limit: int) -> list[AuditEvent]:
        """Registros que cumplen ``query``, del id más alto al más bajo."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                _EVENTS,
                {
                    "before": query.before,
                    "prefixes": list(query.prefixes),
                    "actor": query.actor,
                    "n": limit,
                },
            )
            return [_event(row) for row in rows.mappings()]
