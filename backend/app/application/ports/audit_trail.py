"""Puerto para leer la bitácora de auditoría (pantalla «Accesos»).

``AuditTrailPort`` entrega registros de ``audit_log`` de lo más nuevo a lo
más viejo, con los filtros de ``AuditQuery``.

No hace: no escribe (cada repositorio guarda su registro junto con su
cambio) ni decide quién puede leer (``ReadAuditTrail``).
"""

from typing import Protocol

from app.domain.audit_trail import AuditEvent, AuditQuery


class AuditTrailPort(Protocol):
    """Dónde se lee la bitácora."""

    async def events(self, query: AuditQuery, limit: int) -> list[AuditEvent]:
        """Registros que cumplen ``query``, del id más alto al más bajo.

        Args:
            query: Grupo, persona y cursor (``before``).
            limit: Cuántos como máximo (puede ser uno más que la página, para
                saber si hay otra).

        Returns:
            Hasta ``limit`` registros.
        """
        ...
