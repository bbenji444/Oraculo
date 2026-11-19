"""Cancelar una búsqueda que todavía corre (19/11/2026, ADR-0118).

Benji: «tiene que estar la opción de cancelar búsqueda por si me equivoqué en
algo o necesito regresar y editar».

Cancelar marca la fila como ``cancelled`` en el momento. El worker lo revisa
entre etapas y antes de cada nota de la IA, se detiene y guarda lo que
alcanzó a gastar (créditos y tokens) en la bitácora (CLAUDE.md §8).

Reglas:
- Solo quien la lanzó, y solo búsquedas manuales: una corrida automática del
  monitor FGR alimenta el reporte y los envíos de todos.
- Si ya terminó, no hay nada que cancelar (409).

No hace: no borra la búsqueda ni sus notas (para quitarla del historial está
``DeleteSearch``) ni detiene una consulta a un proveedor que ya salió: esa se
cobra igual.
"""

from uuid import UUID

from app.application.audit import Actor
from app.application.ports.search_reads import SearchCancelPort
from app.application.use_cases.run_search import SearchNotFoundError
from app.domain.errors import SearchAlreadyFinishedError, SearchForbiddenError
from app.domain.search import SearchTrigger, can_cancel_search


class CancelSearch:
    """Detiene una búsqueda manual que todavía corre."""

    def __init__(self, searches: SearchCancelPort) -> None:
        """Recibe el acceso a las búsquedas.

        Args:
            searches: Dueño de la búsqueda y la cancelación.
        """
        self._searches = searches

    async def execute(self, search_id: UUID, actor: Actor) -> None:
        """Cancela la búsqueda; el worker se detiene en su siguiente revisión.

        Args:
            search_id: Búsqueda.
            actor: Quién la cancela.

        Raises:
            SearchNotFoundError: Si no existe o está eliminada.
            SearchForbiddenError: Si es de otra persona o es automática.
            SearchAlreadyFinishedError: Si ya terminó.
        """
        owner = await self._searches.ownership(search_id)
        if owner is None or owner.deleted:
            raise SearchNotFoundError("No existe esa búsqueda.", {"id": str(search_id)})
        if not can_cancel_search(owner.user_id, owner.trigger, actor.user_id):
            message = (
                "Las corridas automáticas del monitor FGR no se cancelan."
                if owner.trigger is SearchTrigger.AUTOMATIC
                else "Esa búsqueda es de otra persona: solo ella la puede cancelar."
            )
            raise SearchForbiddenError(message, {"id": str(search_id)})
        if not await self._searches.cancel(search_id, actor_id=actor.user_id, ip=actor.ip):
            raise SearchAlreadyFinishedError(
                "La búsqueda ya terminó: no hay nada que cancelar.", {"id": str(search_id)}
            )
