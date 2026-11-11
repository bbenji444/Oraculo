"""Ver la bitácora de auditoría desde «Accesos» (solo superusuarios).

Benji, 11/11/2026: «¿a qué bitácora te refieres?». La bitácora ya guardaba
quién vio cada llave, quién entró y quién buscó; ahora se puede leer en
pantalla, por páginas, sin abrir la base.

No hace: no escribe en la bitácora ni la borra (es de solo agregar).
"""

from app.application.ports.audit_trail import AuditTrailPort
from app.application.use_cases.access import require_superuser
from app.domain.access import AuthUser
from app.domain.audit_trail import AuditPage, AuditQuery


class ReadAuditTrail:
    """Lee la bitácora por páginas.

    Args:
        store: Dónde vive la bitácora.
    """

    def __init__(self, store: AuditTrailPort) -> None:
        self._store = store

    async def page(self, admin: AuthUser, query: AuditQuery) -> AuditPage:
        """Una página de la bitácora, de lo más nuevo a lo más viejo.

        Args:
            admin: Quién pregunta.
            query: Grupo, persona, cursor y tamaño de página.

        Returns:
            Los registros y el cursor de la página siguiente (``None`` si ya
            no hay más).

        Raises:
            ForbiddenError: Si quien pregunta no es superusuario.
        """
        require_superuser(admin)
        size = query.size
        # Se pide uno de más: si llega, hay otra página y su cursor es el
        # último de esta.
        rows = await self._store.events(query, size + 1)
        events = tuple(rows[:size])
        more = len(rows) > size
        return AuditPage(events, events[-1].event_id if more else None)
