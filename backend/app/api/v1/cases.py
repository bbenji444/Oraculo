"""Rutas ``/api/v1/cases``: casos de investigación (Fase 9.3, historia H9.1).

Cada ruta solo traduce HTTP ↔ casos de uso; las reglas, los permisos y la
bitácora viven en ``app.application.use_cases.cases``. Quien pide es el
usuario de desarrollo hasta la Fase 8 (``get_actor``), y solo ve los casos de
los que es miembro: un caso ajeno responde 404 igual que uno inexistente.

No hace: no agrega entidades (9.4) ni dibuja el muro (9.6).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, status

from app.api.errors import ERROR_RESPONSES, error_responses
from app.api.v1.concepts import get_actor
from app.api.v1.schemas.cases import CaseIn, CaseOut, CasePageOut, CasePatch
from app.application.audit import Actor
from app.application.ports.cases import CaseRepositoryPort
from app.application.use_cases.cases import (
    DEFAULT_PAGE_SIZE,
    CreateCase,
    GetCase,
    ListCases,
    UpdateCase,
)
from app.domain.investigation import CaseStatus

router = APIRouter(prefix="/cases", tags=["casos"], responses=ERROR_RESPONSES)


def get_case_repository(request: Request) -> CaseRepositoryPort:
    """Repositorio creado al arrancar la aplicación (las pruebas lo reemplazan).

    Args:
        request: Petición actual.

    Returns:
        El repositorio compartido.
    """
    repository: CaseRepositoryPort = request.app.state.case_repository
    return repository


Cases = Annotated[CaseRepositoryPort, Depends(get_case_repository)]
CurrentActor = Annotated[Actor, Depends(get_actor)]
CaseId = Annotated[UUID, Path(description="Id del caso.")]


@router.get("", response_model=CasePageOut, summary="Mis casos")
async def list_cases(  # noqa: PLR0913 — un parámetro de URL por filtro, todo por nombre (*)
    cases: Cases,
    actor: CurrentActor,
    *,
    case_status: Annotated[
        CaseStatus | None,
        Query(alias="status", description="open, closed o archived; vacío: abiertos y cerrados."),
    ] = None,
    contains_article: Annotated[
        int | None, Query(description="Si viene, cada caso dice si ya tiene esa nota.")
    ] = None,
    cursor: Annotated[str | None, Query(description="Cursor de la página anterior.")] = None,
    limit: Annotated[int, Query(description="Tamaño de página (1 a 200).")] = DEFAULT_PAGE_SIZE,
) -> CasePageOut:
    """Casos de los que la persona es miembro, del más reciente al más viejo."""
    page = await ListCases(cases).execute(actor, case_status, contains_article, cursor, limit)
    return CasePageOut.from_page(page)


@router.post(
    "",
    response_model=CaseOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un caso",
)
async def create_case(body: CaseIn, cases: Cases, actor: CurrentActor) -> CaseOut:
    """Valida, guarda (quien lo crea queda como dueño) y registra en la bitácora."""
    return CaseOut.from_view(await CreateCase(cases).execute(body.to_input(), actor))


@router.get(
    "/{case_id}",
    response_model=CaseOut,
    summary="Abrir un caso",
    responses=error_responses(404),
)
async def get_case(cases: Cases, actor: CurrentActor, case_id: CaseId) -> CaseOut:
    """Datos del caso y el rol de quien lo abre. Queda en la bitácora como ``case.viewed``."""
    return CaseOut.from_view(await GetCase(cases).execute(case_id, actor))


@router.patch(
    "/{case_id}",
    response_model=CaseOut,
    summary="Editar, cerrar, archivar o reabrir un caso",
    responses=error_responses(403, 404, 409),
)
async def update_case(
    body: CasePatch, cases: Cases, actor: CurrentActor, case_id: CaseId
) -> CaseOut:
    """Cambia solo los campos enviados. Un caso cerrado solo cambia de estado."""
    return CaseOut.from_view(await UpdateCase(cases).execute(case_id, body.to_changes(), actor))
