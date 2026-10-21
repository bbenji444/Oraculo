"""Casos de uso de los casos de investigación (Fase 9.3, historia H9.1).

Crear, listar, ver y editar un caso. Toda acción pasa por ``_case_for``, que
pide el caso **como lo ve la persona**: si no es miembro, el caso no existe
para ella (``CaseNotFoundError``, decisión D3). Lo que cambia algo revisa
además el rol (``can_edit``) y que el caso esté abierto (D5).

Cada cambio deja su registro en la bitácora en la misma transacción, y ver
un caso también (``case.viewed``), una vez por persona cada
``CASE_VIEW_DEDUP_MINUTES`` (D4).

Las noticias se agregan y se quitan sin duplicar (D6, D7): la noticia es de
todo el sistema y quitarla del caso no la borra.

Los miembros los administra solo el dueño, y el caso nunca se queda sin él.

No hace: no sabe de HTTP ni de SQL; no agrega entidades (9.4).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.application.audit import Actor, AuditEntry
from app.application.pagination import (
    Page,
    TimeCursor,
    decode_time_cursor,
    encode_time_cursor,
)
from app.application.ports.cases import CaseRepositoryPort
from app.application.ports.search_reads import ArticleItem
from app.application.use_cases.search_reads import (
    DEFAULT_ARTICLE_PAGE_SIZE,
    MAX_ARTICLE_PAGE_SIZE,
    ArticleNotFoundError,
    check_limit,
)
from app.domain.case import (
    USER_ID_MAX_LENGTH,
    Case,
    CaseChanges,
    CaseDraft,
    CaseMember,
    CaseView,
    can_edit,
    can_manage_members,
    closed_at_for,
    is_read_only,
)
from app.domain.concept import clean_text
from app.domain.errors import (
    CaseClosedError,
    CaseForbiddenError,
    CaseNotFoundError,
    CaseOwnerRequiredError,
    CaseValidationError,
    InvalidRequestError,
)
from app.domain.investigation import CaseMemberRole, CaseStatus, InvestigationAction

# Decisión D4 de la 9.3: la pantalla vuelve a pedir el caso al regresar a la
# pestaña; registrar cada recarga llenaría la bitácora sin decir nada nuevo.
CASE_VIEW_DEDUP_MINUTES = 5
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
# La lista de siempre: lo archivado se pide a propósito con el filtro (D5).
DEFAULT_STATUSES = (CaseStatus.OPEN, CaseStatus.CLOSED)

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class CaseInput:
    """Datos de un caso nuevo, tal como llegan (sin validar).

    Attributes:
        name: Nombre.
        description: Descripción.
        sensitivity: ``normal``, ``restricted`` o ``confidential``.
    """

    name: str
    description: str = ""
    sensitivity: str = "normal"


def case_snapshot(case: Case) -> dict[str, object]:
    """Foto de un caso para la bitácora.

    Args:
        case: El caso.

    Returns:
        Diccionario serializable a JSON.
    """
    return {
        "name": case.name,
        "description": case.description,
        "status": case.status.value,
        "sensitivity": case.sensitivity.value,
    }


async def case_for(repository: CaseRepositoryPort, case_id: UUID, actor: Actor) -> CaseView:
    """El caso como lo ve la persona, o el error de "no existe".

    Args:
        repository: Acceso a los casos.
        case_id: Caso.
        actor: Quién pregunta.

    Returns:
        El caso con su rol.

    Raises:
        CaseNotFoundError: Si no existe o la persona no es miembro.
    """
    view = await repository.get_view(case_id, actor.user_id)
    if view is None:
        raise CaseNotFoundError("No existe el caso o no tienes acceso.", {"id": str(case_id)})
    return view


def require_edit(view: CaseView) -> None:
    """Exige que la persona pueda cambiar el caso y que esté abierto.

    Args:
        view: El caso como lo ve la persona.

    Raises:
        CaseForbiddenError: Si su rol solo permite mirar.
        CaseClosedError: Si el caso está cerrado o archivado.
    """
    if not can_edit(view.role):
        raise CaseForbiddenError(
            "Tu rol en este caso solo permite consultarlo.", {"role": view.role.value}
        )
    if is_read_only(view.case.status):
        raise CaseClosedError(
            "El caso está cerrado; reábrelo para cambiarlo.", {"status": view.case.status.value}
        )


class CreateCase:
    """Crea un caso; quien lo crea queda como dueño."""

    def __init__(self, repository: CaseRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los casos.
        """
        self._repository = repository

    async def execute(self, data: CaseInput, actor: Actor) -> CaseView:
        """Valida y guarda.

        Args:
            data: Datos del formulario.
            actor: Quién lo crea.

        Returns:
            El caso guardado, con su rol de dueño.

        Raises:
            CaseValidationError: Si los datos no cumplen las reglas.
        """
        draft = CaseDraft.validated(data.name, data.description, data.sensitivity)
        audit = AuditEntry(
            actor,
            InvestigationAction.CASE_CREATED,
            {
                "after": {
                    "name": draft.name,
                    "description": draft.description,
                    "status": CaseStatus.OPEN.value,
                    "sensitivity": draft.sensitivity.value,
                }
            },
        )
        case = await self._repository.create(draft, actor.user_id, audit)
        return CaseView(case, CaseMemberRole.OWNER)


class ListCases:
    """Los casos de la persona, del más reciente al más viejo, por páginas."""

    def __init__(self, repository: CaseRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los casos.
        """
        self._repository = repository

    async def execute(
        self,
        actor: Actor,
        status: CaseStatus | None = None,
        contains_article: int | None = None,
        cursor: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> Page[CaseView]:
        """Devuelve una página.

        Args:
            actor: Quién pregunta (solo ve sus casos).
            status: Solo ese estado; ``None`` = abiertos y cerrados.
            contains_article: Si viene, cada caso dice si ya tiene esa nota
                (para el botón "Agregar al caso").
            cursor: Cursor de la página anterior.
            limit: Tamaño de página (1 a 200).

        Returns:
            La página con su cursor siguiente.

        Raises:
            InvalidRequestError: Si el límite o el cursor no son válidos.
        """
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise InvalidRequestError(
                f"El límite debe estar entre 1 y {MAX_PAGE_SIZE}.", {"limit": limit}
            )
        after = decode_time_cursor(cursor) if cursor else None
        statuses = (status,) if status else DEFAULT_STATUSES
        rows = await self._repository.list_for_user(
            actor.user_id, statuses, contains_article, after, limit + 1
        )
        items = rows[:limit]
        last = items[-1].case if items else None
        next_cursor = (
            encode_time_cursor(TimeCursor(last.updated_at, str(last.id)))
            if len(rows) > limit and last
            else None
        )
        return Page(items=tuple(items), next_cursor=next_cursor)


class GetCase:
    """Abre un caso y deja en la bitácora que la persona lo vio."""

    def __init__(self, repository: CaseRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los casos.
        """
        self._repository = repository

    async def execute(self, case_id: UUID, actor: Actor) -> CaseView:
        """Devuelve el caso y registra la vista (§9.10).

        Args:
            case_id: Caso.
            actor: Quién lo abre.

        Returns:
            El caso con el rol de la persona.

        Raises:
            CaseNotFoundError: Si no existe o la persona no es miembro.
        """
        view = await case_for(self._repository, case_id, actor)
        await self._repository.record_view(
            case_id, AuditEntry(actor, InvestigationAction.CASE_VIEWED, {}), CASE_VIEW_DEDUP_MINUTES
        )
        return view


class UpdateCase:
    """Edita los datos de un caso, o lo cierra, archiva o reabre."""

    def __init__(self, repository: CaseRepositoryPort, clock: Clock = _utc_now) -> None:
        """Recibe el repositorio y el reloj.

        Args:
            repository: Acceso a los casos.
            clock: Hora actual (las pruebas la fijan).
        """
        self._repository = repository
        self._clock = clock

    async def execute(self, case_id: UUID, changes: CaseChanges, actor: Actor) -> CaseView:
        """Aplica los cambios enviados.

        En un caso cerrado o archivado solo cambia el estado (reabrirlo, o
        archivar uno cerrado); sus datos se cambian ya abierto (D5). Una
        petición sin cambios no escribe nada.

        Args:
            case_id: Caso.
            changes: Campos que cambian (``None`` = no cambia).
            actor: Quién lo cambia.

        Returns:
            El caso como quedó, con el rol de quien lo cambió.

        Raises:
            CaseNotFoundError: Si no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si está cerrado y se quieren cambiar sus datos.
            CaseValidationError: Si los datos o el estado no son válidos.
        """
        view = await case_for(self._repository, case_id, actor)
        if not can_edit(view.role):
            raise CaseForbiddenError(
                "Tu rol en este caso solo permite consultarlo.", {"role": view.role.value}
            )
        current = view.case
        status = _status(changes.status, current.status)
        if not changes.touches_data and status is current.status:
            return view
        if is_read_only(current.status) and changes.touches_data:
            raise CaseClosedError(
                "El caso está cerrado; reábrelo para cambiarlo.", {"status": current.status.value}
            )
        draft = CaseDraft.validated(
            changes.name if changes.name is not None else current.name,
            changes.description if changes.description is not None else current.description,
            changes.sensitivity if changes.sensitivity is not None else current.sensitivity,
        )
        audit = AuditEntry(
            actor,
            _action_for(current.status, status),
            {
                "before": case_snapshot(current),
                "after": {
                    "name": draft.name,
                    "description": draft.description,
                    "status": status.value,
                    "sensitivity": draft.sensitivity.value,
                },
            },
        )
        updated = await self._repository.update(
            case_id,
            data=draft,
            status=status,
            closed_at=closed_at_for(status, current.closed_at, self._clock()),
            audit=audit,
        )
        return CaseView(updated, view.role)


def _status(value: str | None, current: CaseStatus) -> CaseStatus:
    if value is None:
        return current
    try:
        return CaseStatus(value)
    except ValueError as error:
        raise CaseValidationError(
            "El caso tiene datos inválidos; revisa los campos marcados.",
            {
                "problemas": [
                    {
                        "campo": "status",
                        "mensaje": "El estado debe ser abierto, cerrado o archivado.",
                    }
                ]
            },
        ) from error


def _action_for(before: CaseStatus, after: CaseStatus) -> InvestigationAction:
    if before is after:
        return InvestigationAction.CASE_UPDATED
    if after is CaseStatus.OPEN:
        return InvestigationAction.CASE_REOPENED
    if after is CaseStatus.ARCHIVED:
        return InvestigationAction.CASE_ARCHIVED
    return InvestigationAction.CASE_CLOSED


class AddCaseArticle:
    """Agrega una noticia a un caso (historia H9.1). Agregarla dos veces no duplica nada."""

    def __init__(self, repository: CaseRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los casos.
        """
        self._repository = repository

    async def execute(self, case_id: UUID, article_id: int, actor: Actor) -> bool:
        """Agrega la nota y lo registra en la bitácora.

        Args:
            case_id: Caso.
            article_id: Noticia.
            actor: Quién la agrega.

        Returns:
            ``True`` si se agregó; ``False`` si ya estaba (D6: un doble clic no
            deja una segunda fila en la bitácora).

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si el caso está cerrado o archivado.
            ArticleNotFoundError: Si la noticia no existe.
        """
        require_edit(await case_for(self._repository, case_id, actor))
        if not await self._repository.article_exists(article_id):
            raise ArticleNotFoundError("No existe esa nota.", {"id": article_id})
        audit = AuditEntry(
            actor, InvestigationAction.CASE_ARTICLE_ADDED, {"article_id": article_id}
        )
        return await self._repository.add_article(case_id, article_id, actor.user_id, audit)


class RemoveCaseArticle:
    """Quita una noticia de un caso; la noticia sigue en el sistema (D7)."""

    def __init__(self, repository: CaseRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los casos.
        """
        self._repository = repository

    async def execute(self, case_id: UUID, article_id: int, actor: Actor) -> bool:
        """Quita la nota y lo registra en la bitácora.

        Args:
            case_id: Caso.
            article_id: Noticia.
            actor: Quién la quita.

        Returns:
            ``True`` si se quitó; ``False`` si no estaba en el caso.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si su rol solo permite mirar.
            CaseClosedError: Si el caso está cerrado o archivado.
        """
        require_edit(await case_for(self._repository, case_id, actor))
        audit = AuditEntry(
            actor, InvestigationAction.CASE_ARTICLE_REMOVED, {"article_id": article_id}
        )
        return await self._repository.remove_article(case_id, article_id, audit)


class ListCaseArticles:
    """Noticias de un caso, por páginas; cualquier miembro las ve."""

    def __init__(self, repository: CaseRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los casos.
        """
        self._repository = repository

    async def execute(
        self,
        case_id: UUID,
        actor: Actor,
        cursor: str | None = None,
        limit: int = DEFAULT_ARTICLE_PAGE_SIZE,
    ) -> Page[ArticleItem]:
        """Devuelve una página, de la nota más reciente a la más vieja.

        No registra otra vista: la pantalla abre el caso con ``GetCase``, que
        ya la registró.

        Args:
            case_id: Caso.
            actor: Quién pregunta.
            cursor: Cursor de la página anterior.
            limit: Tamaño de página (1 a 200).

        Returns:
            La página con su cursor siguiente.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            InvalidRequestError: Si el límite o el cursor no son válidos.
        """
        check_limit(limit, MAX_ARTICLE_PAGE_SIZE)
        await case_for(self._repository, case_id, actor)
        after = decode_time_cursor(cursor) if cursor else None
        rows = await self._repository.list_articles(case_id, after, limit + 1)
        items = rows[:limit]
        last = items[-1] if items else None
        next_cursor = (
            encode_time_cursor(TimeCursor(last.published_at, str(last.article_id)))
            if len(rows) > limit and last
            else None
        )
        return Page(items=tuple(items), next_cursor=next_cursor)


def _require_owner(view: CaseView) -> None:
    if not can_manage_members(view.role):
        raise CaseForbiddenError(
            "Solo el dueño del caso decide quién tiene acceso.", {"role": view.role.value}
        )


class ListCaseMembers:
    """Quién tiene acceso a un caso; cualquier miembro lo puede ver."""

    def __init__(self, repository: CaseRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los casos.
        """
        self._repository = repository

    async def execute(self, case_id: UUID, actor: Actor) -> list[CaseMember]:
        """Devuelve los miembros, el dueño primero.

        Args:
            case_id: Caso.
            actor: Quién pregunta.

        Returns:
            Los miembros.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
        """
        await case_for(self._repository, case_id, actor)
        return await self._repository.list_members(case_id)


class AddCaseMember:
    """Da acceso a una persona (editor o lector) o le cambia el rol (solo el dueño).

    Hasta la Fase 8 no hay usuarios reales: el identificador es texto, como
    ``created_by``. Esta acción no tiene pantalla todavía (decisión D3).
    """

    def __init__(self, repository: CaseRepositoryPort, clock: Clock = _utc_now) -> None:
        """Recibe el repositorio y el reloj.

        Args:
            repository: Acceso a los casos.
            clock: Hora actual (las pruebas la fijan).
        """
        self._repository = repository
        self._clock = clock

    async def execute(self, case_id: UUID, user_id: str, role: str, actor: Actor) -> bool:
        """Agrega a la persona o le cambia el rol.

        Args:
            case_id: Caso.
            user_id: Persona.
            role: ``editor`` o ``viewer`` (el dueño es uno solo).
            actor: Quién da el acceso (debe ser el dueño).

        Returns:
            ``True`` si se agregó o cambió; ``False`` si ya tenía ese rol.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si quien lo pide no es el dueño.
            CaseOwnerRequiredError: Si se pide un segundo dueño o cambiar el rol del dueño.
            InvalidRequestError: Si el usuario o el rol no son válidos.
        """
        _require_owner(await case_for(self._repository, case_id, actor))
        member = clean_text(user_id)
        if not 1 <= len(member) <= USER_ID_MAX_LENGTH:
            raise InvalidRequestError(
                f"El usuario debe tener entre 1 y {USER_ID_MAX_LENGTH} caracteres.",
                {"user_id": user_id},
            )
        try:
            new_role = CaseMemberRole(role)
        except ValueError as error:
            raise InvalidRequestError("El rol debe ser editor o viewer.", {"role": role}) from error
        if new_role is CaseMemberRole.OWNER or member == actor.user_id:
            raise CaseOwnerRequiredError(
                "El caso tiene un solo dueño; aquí solo se agregan editores o lectores.",
                {"user_id": member, "role": role},
            )
        audit = AuditEntry(
            actor,
            InvestigationAction.CASE_MEMBER_ADDED,
            {"user_id": member, "role": new_role.value},
        )
        return await self._repository.save_member(
            case_id, CaseMember(member, new_role, actor.user_id, self._clock()), audit
        )


class RemoveCaseMember:
    """Quita el acceso de una persona (solo el dueño; al dueño no se le quita)."""

    def __init__(self, repository: CaseRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los casos.
        """
        self._repository = repository

    async def execute(self, case_id: UUID, user_id: str, actor: Actor) -> bool:
        """Quita el acceso y lo registra.

        Args:
            case_id: Caso.
            user_id: Persona.
            actor: Quién lo quita (debe ser el dueño).

        Returns:
            ``True`` si se quitó; ``False`` si no era miembro.

        Raises:
            CaseNotFoundError: Si el caso no existe o la persona no es miembro.
            CaseForbiddenError: Si quien lo pide no es el dueño.
            CaseOwnerRequiredError: Si se intenta quitar al dueño.
        """
        _require_owner(await case_for(self._repository, case_id, actor))
        if user_id == actor.user_id:
            raise CaseOwnerRequiredError(
                "El dueño no se puede quitar del caso: se quedaría sin dueño.",
                {"user_id": user_id},
            )
        audit = AuditEntry(actor, InvestigationAction.CASE_MEMBER_REMOVED, {"user_id": user_id})
        return await self._repository.remove_member(case_id, user_id, audit)
