"""Eliminar y restaurar casos y búsquedas (F12, 27/10/2026).

Benji pidió poder eliminar casos y quitar búsquedas del historial. Eliminar es
**reversible**: la fila se queda en la base con quién y cuándo
(``deleted_at``, ``deleted_by``) y deja de verse. Así un clic equivocado se
deshace (la pantalla ofrece «Deshacer») y la bitácora no pierde nada
(CLAUDE.md §8).

Reglas:
- Un caso lo elimina o restaura solo su dueño: se lleva el caso para todos sus
  miembros. Sus notas siguen en el sistema.
- Una búsqueda la quita del historial quien la lanzó; las corridas automáticas
  del monitor FGR son de todos y cualquiera puede quitarlas. Sus notas siguen
  en el índice y en los casos donde se agregaron.

No hace: no borra nada para siempre.
"""

from uuid import UUID

from app.application.audit import SEARCH_DELETED, SEARCH_RESTORED, Actor, AuditEntry
from app.application.ports.cases import CaseRepositoryPort
from app.application.ports.search_reads import SearchTrashPort
from app.application.use_cases.cases import case_for
from app.application.use_cases.run_search import SearchNotFoundError
from app.domain.case import CaseView, can_delete
from app.domain.errors import CaseForbiddenError, CaseNotFoundError, SearchForbiddenError
from app.domain.investigation import InvestigationAction
from app.domain.search import can_delete_search


def _require_owner(view: CaseView) -> None:
    if not can_delete(view.role):
        raise CaseForbiddenError(
            "Solo el dueño del caso puede eliminarlo o restaurarlo.", {"role": view.role.value}
        )


class DeleteCase:
    """Elimina un caso de forma reversible."""

    def __init__(self, repository: CaseRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los casos.
        """
        self._repository = repository

    async def execute(self, case_id: UUID, actor: Actor) -> None:
        """Elimina el caso: deja de verse para todos sus miembros.

        Args:
            case_id: Caso.
            actor: Quién lo elimina.

        Raises:
            CaseNotFoundError: Si no existe, no es miembro o ya está eliminado.
            CaseForbiddenError: Si no es el dueño.
        """
        view = await case_for(self._repository, case_id, actor)
        _require_owner(view)
        audit = AuditEntry(
            actor,
            InvestigationAction.CASE_DELETED,
            {"name": view.case.name, "status": view.case.status.value},
        )
        await self._repository.set_deleted(
            case_id, deleted=True, user_id=actor.user_id, audit=audit
        )


class RestoreCase:
    """Devuelve un caso eliminado («Deshacer»)."""

    def __init__(self, repository: CaseRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los casos.
        """
        self._repository = repository

    async def execute(self, case_id: UUID, actor: Actor) -> CaseView:
        """Restaura el caso tal como estaba. Si no estaba eliminado, no cambia nada.

        Args:
            case_id: Caso.
            actor: Quién lo restaura.

        Returns:
            El caso restaurado, con el rol de la persona.

        Raises:
            CaseNotFoundError: Si no existe o la persona no es miembro.
            CaseForbiddenError: Si no es el dueño.
        """
        view = await self._repository.get_view(case_id, actor.user_id, include_deleted=True)
        if view is None:
            raise CaseNotFoundError("No existe el caso o no tienes acceso.", {"id": str(case_id)})
        _require_owner(view)
        if view.case.deleted_at is None:
            return view
        audit = AuditEntry(actor, InvestigationAction.CASE_RESTORED, {"name": view.case.name})
        await self._repository.set_deleted(
            case_id, deleted=False, user_id=actor.user_id, audit=audit
        )
        return await case_for(self._repository, case_id, actor)


class DeleteSearch:
    """Quita una búsqueda del historial (reversible)."""

    def __init__(self, trash: SearchTrashPort) -> None:
        """Recibe el acceso a la papelera.

        Args:
            trash: Eliminar y restaurar búsquedas.
        """
        self._trash = trash

    async def execute(self, search_id: UUID, actor: Actor) -> None:
        """Quita la búsqueda del historial. Sus notas siguen en el sistema.

        Args:
            search_id: Búsqueda.
            actor: Quién la quita.

        Raises:
            SearchNotFoundError: Si no existe o ya está eliminada.
            SearchForbiddenError: Si es una búsqueda manual de otra persona.
        """
        owner = await self._trash.ownership(search_id)
        if owner is None or owner.deleted:
            raise SearchNotFoundError("No existe esa búsqueda.", {"id": str(search_id)})
        if not can_delete_search(owner.user_id, owner.trigger, actor.user_id):
            raise SearchForbiddenError(
                "Esa búsqueda es de otra persona: solo ella la puede quitar.",
                {"id": str(search_id)},
            )
        await self._trash.set_deleted(
            search_id, deleted=True, actor_id=actor.user_id, ip=actor.ip, action=SEARCH_DELETED
        )


class RestoreSearch:
    """Devuelve una búsqueda al historial («Deshacer»)."""

    def __init__(self, trash: SearchTrashPort) -> None:
        """Recibe el acceso a la papelera.

        Args:
            trash: Eliminar y restaurar búsquedas.
        """
        self._trash = trash

    async def execute(self, search_id: UUID, actor: Actor) -> None:
        """La devuelve al historial. Si no estaba eliminada, no cambia nada.

        Args:
            search_id: Búsqueda.
            actor: Quién la restaura.

        Raises:
            SearchNotFoundError: Si no existe.
            SearchForbiddenError: Si es una búsqueda manual de otra persona.
        """
        owner = await self._trash.ownership(search_id)
        if owner is None:
            raise SearchNotFoundError("No existe esa búsqueda.", {"id": str(search_id)})
        if not can_delete_search(owner.user_id, owner.trigger, actor.user_id):
            raise SearchForbiddenError(
                "Esa búsqueda es de otra persona: solo ella la puede restaurar.",
                {"id": str(search_id)},
            )
        if not owner.deleted:
            return
        await self._trash.set_deleted(
            search_id, deleted=False, actor_id=actor.user_id, ip=actor.ip, action=SEARCH_RESTORED
        )
