"""Rutas ``/api/v1/cases``: casos de investigación (Fase 9.3, historia H9.1).

Cada ruta solo traduce HTTP ↔ casos de uso; las reglas, los permisos y la
bitácora viven en ``app.application.use_cases.cases``. Quien pide es el
usuario de desarrollo hasta la Fase 8 (``get_actor``), y solo ve los casos de
los que es miembro: un caso ajeno responde 404 igual que uno inexistente.

Las noticias se agregan y se quitan sin duplicar; quitarla del caso no borra
la noticia.

No hace: no agrega entidades (9.4) ni dibuja el muro (9.6).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status

from app.api.errors import ERROR_RESPONSES, error_responses
from app.api.v1.concepts import get_actor
from app.api.v1.schemas.articles import ArticlePageOut
from app.api.v1.schemas.cases import (
    CaseArticleIn,
    CaseArticleOut,
    CaseIn,
    CaseMemberIn,
    CaseMemberOut,
    CaseMemberSavedOut,
    CaseOut,
    CasePageOut,
    CasePatch,
)
from app.application.audit import Actor
from app.application.ports.cases import CaseRepositoryPort
from app.application.use_cases.cases import (
    DEFAULT_PAGE_SIZE,
    AddCaseArticle,
    AddCaseMember,
    CreateCase,
    GetCase,
    ListCaseArticles,
    ListCaseMembers,
    ListCases,
    RemoveCaseArticle,
    RemoveCaseMember,
    UpdateCase,
)
from app.application.use_cases.search_reads import DEFAULT_ARTICLE_PAGE_SIZE
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


@router.get(
    "/{case_id}/articles",
    response_model=ArticlePageOut,
    summary="Noticias de un caso",
    responses=error_responses(404),
)
async def list_case_articles(
    cases: Cases,
    actor: CurrentActor,
    case_id: CaseId,
    cursor: Annotated[str | None, Query(description="Cursor de la página anterior.")] = None,
    limit: Annotated[
        int, Query(description="Tamaño de página (1 a 200).")
    ] = DEFAULT_ARTICLE_PAGE_SIZE,
) -> ArticlePageOut:
    """Notas del caso con el mismo formato de Explorar, de la más reciente a la más vieja."""
    page = await ListCaseArticles(cases).execute(case_id, actor, cursor, limit)
    return ArticlePageOut.from_page(page)


@router.post(
    "/{case_id}/articles",
    response_model=CaseArticleOut,
    summary="Agregar una noticia al caso",
    responses=error_responses(403, 404, 409),
)
async def add_case_article(
    body: CaseArticleIn, cases: Cases, actor: CurrentActor, case_id: CaseId
) -> CaseArticleOut:
    """Agrega la nota; si ya estaba, responde ``added: false`` sin repetir la bitácora."""
    added = await AddCaseArticle(cases).execute(case_id, body.article_id, actor)
    return CaseArticleOut(article_id=body.article_id, added=added)


@router.delete(
    "/{case_id}/articles/{article_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar una noticia del caso",
    responses=error_responses(403, 404, 409),
)
async def remove_case_article(
    cases: Cases,
    actor: CurrentActor,
    case_id: CaseId,
    article_id: Annotated[int, Path(description="Id de la noticia.")],
) -> Response:
    """Quita la nota del caso; la noticia sigue en el sistema."""
    await RemoveCaseArticle(cases).execute(case_id, article_id, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{case_id}/members",
    response_model=list[CaseMemberOut],
    summary="Quién tiene acceso a un caso",
    responses=error_responses(404),
)
async def list_case_members(
    cases: Cases, actor: CurrentActor, case_id: CaseId
) -> list[CaseMemberOut]:
    """Miembros del caso, el dueño primero. Cualquier miembro los puede ver."""
    members = await ListCaseMembers(cases).execute(case_id, actor)
    return [CaseMemberOut.from_member(m) for m in members]


@router.post(
    "/{case_id}/members",
    response_model=CaseMemberSavedOut,
    summary="Dar acceso a un caso o cambiar el rol",
    responses=error_responses(403, 404, 409),
)
async def add_case_member(
    body: CaseMemberIn, cases: Cases, actor: CurrentActor, case_id: CaseId
) -> CaseMemberSavedOut:
    """Solo el dueño. Roles: ``editor`` o ``viewer`` (el caso tiene un solo dueño)."""
    changed = await AddCaseMember(cases).execute(case_id, body.user_id, body.role, actor)
    return CaseMemberSavedOut(user_id=body.user_id.strip(), role=body.role, changed=changed)


@router.delete(
    "/{case_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Quitar el acceso a un caso",
    responses=error_responses(403, 404, 409),
)
async def remove_case_member(
    cases: Cases,
    actor: CurrentActor,
    case_id: CaseId,
    user_id: Annotated[str, Path(description="Usuario al que se le quita el acceso.")],
) -> Response:
    """Solo el dueño; al dueño no se le quita el acceso."""
    await RemoveCaseMember(cases).execute(case_id, user_id, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
