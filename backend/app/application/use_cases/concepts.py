"""Casos de uso de conceptos: CRUD, borrado lógico y "Probar concepto".

Reglas que viven aquí (las del concepto en sí están en ``app.domain.concept``):

- El nombre es único entre los conceptos vigentes; se avisa con un 409 y un
  mensaje claro antes de intentar guardar.
- Cada cambio queda en la bitácora con quién, qué y desde dónde.
- Borrar es lógico si el concepto ya se usó en búsquedas (el historial
  sigue mostrando su nombre) y físico si no (especificación §13).
- "Probar concepto" arma las consultas sin llamar a ningún proveedor, para
  un concepto guardado o para un borrador que todavía no se guarda.

No hace: no sabe de HTTP ni de SQL.
"""

from dataclasses import dataclass

from app.application.audit import (
    CONCEPT_CREATED,
    CONCEPT_DELETED,
    CONCEPT_UPDATED,
    Actor,
    AuditEntry,
    concept_snapshot,
)
from app.application.clock import Today, mexico_city_today
from app.application.pagination import NameCursor, Page, decode_cursor, encode_cursor
from app.application.ports.concepts import ConceptRepositoryPort
from app.application.ports.regions import RegionRepositoryPort
from app.domain.concept import Concept, ConceptChanges, ConceptDraft
from app.domain.errors import (
    ConceptNameTakenError,
    ConceptNotFoundError,
    InvalidRequestError,
    RegionNotFoundError,
)
from app.domain.queries import DateWindow, PlannedQuery, place_for
from app.domain.query_builder import ConceptTerms, build_queries
from app.domain.region import RegionDetail

# Los conceptos son pocas decenas: 100 por página cubren la tabla completa.
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 200


@dataclass(frozen=True, slots=True)
class ConceptInput:
    """Datos de un concepto tal como llegan del formulario, sin validar.

    Attributes:
        name: Nombre.
        description: Descripción.
        keywords: Palabras clave.
        exclude_terms: Exclusiones.
        color: Color en hexadecimal.
        is_active: Si aparece en el panel de búsqueda.
    """

    name: str
    description: str
    keywords: tuple[str, ...]
    exclude_terms: tuple[str, ...]
    color: str
    is_active: bool = True

    def validated(self) -> ConceptDraft:
        """Aplica las reglas del dominio.

        Returns:
            El borrador validado.

        Raises:
            ConceptValidationError: Con todos los problemas encontrados.
        """
        return ConceptDraft.validated(
            name=self.name,
            description=self.description,
            keywords=self.keywords,
            exclude_terms=self.exclude_terms,
            color=self.color,
            is_active=self.is_active,
        )


def _name_taken_error(data: ConceptDraft) -> ConceptNameTakenError:
    return ConceptNameTakenError(
        f'Ya existe un concepto llamado "{data.name}" (sin importar mayúsculas ni acentos).',
        {"name": data.name},
    )


async def _get_or_fail(repository: ConceptRepositoryPort, concept_id: int) -> Concept:
    concept = await repository.get(concept_id)
    if concept is None:
        raise ConceptNotFoundError("No existe ese concepto.", {"id": concept_id})
    return concept


class ListConcepts:
    """Lista conceptos en orden alfabético, por páginas."""

    def __init__(self, repository: ConceptRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los conceptos.
        """
        self._repository = repository

    async def execute(
        self, active: bool | None = None, cursor: str | None = None, limit: int = DEFAULT_PAGE_SIZE
    ) -> Page[Concept]:
        """Devuelve una página.

        Args:
            active: ``True`` solo activos (panel de búsqueda), ``False`` solo
                inactivos, ``None`` todos (administración).
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
        after = decode_cursor(cursor) if cursor else None
        rows = await self._repository.list_concepts(active, after, limit + 1)
        items = rows[:limit]
        has_more = len(rows) > limit
        next_cursor = (
            encode_cursor(NameCursor(items[-1].data.name_norm, items[-1].id))
            if has_more and items
            else None
        )
        return Page(tuple(items), next_cursor)


class GetConcept:
    """Detalle de un concepto vigente."""

    def __init__(self, repository: ConceptRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los conceptos.
        """
        self._repository = repository

    async def execute(self, concept_id: int) -> Concept:
        """Busca el concepto.

        Args:
            concept_id: Identificador.

        Returns:
            El concepto.

        Raises:
            ConceptNotFoundError: Si no existe o fue borrado.
        """
        return await _get_or_fail(self._repository, concept_id)


class CreateConcept:
    """Crea un concepto y lo registra en la bitácora."""

    def __init__(self, repository: ConceptRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los conceptos.
        """
        self._repository = repository

    async def execute(self, data: ConceptInput, actor: Actor) -> Concept:
        """Valida y guarda.

        Args:
            data: Datos del formulario.
            actor: Quién lo crea.

        Returns:
            El concepto guardado.

        Raises:
            ConceptValidationError: Si los datos no cumplen las reglas.
            ConceptNameTakenError: Si el nombre ya está en uso.
        """
        draft = data.validated()
        if await self._repository.name_taken(draft.name_norm, None):
            raise _name_taken_error(draft)
        audit = AuditEntry(actor, CONCEPT_CREATED, {"after": concept_snapshot(draft)})
        return await self._repository.create(draft, actor.user_id, audit)


class UpdateConcept:
    """Edita un concepto (también activar o desactivar) y registra el cambio."""

    def __init__(self, repository: ConceptRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los conceptos.
        """
        self._repository = repository

    async def execute(self, concept_id: int, changes: ConceptChanges, actor: Actor) -> Concept:
        """Aplica los cambios.

        Si en realidad nada cambia, no se escribe ni se registra nada.

        Args:
            concept_id: Identificador.
            changes: Campos que cambian.
            actor: Quién edita.

        Returns:
            El concepto como quedó.

        Raises:
            ConceptNotFoundError: Si no existe o fue borrado.
            ConceptValidationError: Si el resultado no cumple las reglas.
            ConceptNameTakenError: Si el nombre nuevo ya está en uso.
        """
        current = await _get_or_fail(self._repository, concept_id)
        updated = changes.apply_to(current.data)
        if updated == current.data:
            return current
        if updated.name_norm != current.data.name_norm and await self._repository.name_taken(
            updated.name_norm, concept_id
        ):
            raise _name_taken_error(updated)
        before, after = concept_snapshot(current.data), concept_snapshot(updated)
        changed = [field for field in after if after[field] != before[field]]
        audit = AuditEntry(
            actor, CONCEPT_UPDATED, {"before": before, "after": after, "changed": changed}
        )
        return await self._repository.update(concept_id, updated, audit)


@dataclass(frozen=True, slots=True)
class DeleteResult:
    """Cómo se borró un concepto.

    Attributes:
        logical: ``True`` si solo se marcó como borrado (tenía búsquedas).
    """

    logical: bool


class DeleteConcept:
    """Borra un concepto: lógico si tiene búsquedas, físico si no (§13)."""

    def __init__(self, repository: ConceptRepositoryPort) -> None:
        """Recibe el repositorio.

        Args:
            repository: Acceso a los conceptos.
        """
        self._repository = repository

    async def execute(self, concept_id: int, actor: Actor) -> DeleteResult:
        """Borra el concepto.

        Args:
            concept_id: Identificador.
            actor: Quién lo borra.

        Returns:
            Si el borrado fue lógico o físico.

        Raises:
            ConceptNotFoundError: Si no existe o ya fue borrado.
        """
        current = await _get_or_fail(self._repository, concept_id)
        logical = await self._repository.is_used_in_searches(concept_id)
        audit = AuditEntry(
            actor,
            CONCEPT_DELETED,
            {"before": concept_snapshot(current.data), "logical": logical},
        )
        await self._repository.delete(concept_id, logical=logical, audit=audit)
        return DeleteResult(logical=logical)


@dataclass(frozen=True, slots=True)
class QueryPreview:
    """Resultado de "Probar concepto".

    Attributes:
        concept_name: Nombre del concepto probado.
        region: Región elegida, con sus ancestros (migas de pan).
        window: Rango de fechas.
        queries: Consultas que se enviarían, en orden de proveedor.
    """

    concept_name: str
    region: RegionDetail
    window: DateWindow
    queries: tuple[PlannedQuery, ...]

    @property
    def total_credits(self) -> int:
        """Créditos estimados de todas las consultas."""
        return sum(q.estimated_credits for q in self.queries)


class PreviewConceptQueries:
    """Muestra las consultas que generaría un concepto, sin gastar créditos (H2)."""

    def __init__(
        self,
        concepts: ConceptRepositoryPort,
        regions: RegionRepositoryPort,
        today: Today = mexico_city_today,
    ) -> None:
        """Recibe los repositorios y el reloj.

        Args:
            concepts: Acceso a los conceptos.
            regions: Acceso al catálogo de regiones.
            today: Fecha de hoy en la Ciudad de México (las pruebas la fijan).
        """
        self._concepts = concepts
        self._regions = regions
        self._today = today

    async def for_saved(self, concept_id: int, region_id: int, days: int) -> QueryPreview:
        """Consultas de un concepto guardado.

        Args:
            concept_id: Concepto.
            region_id: Región elegida.
            days: Últimos N días (1 a 90).

        Returns:
            Las consultas por proveedor.

        Raises:
            ConceptNotFoundError: Si el concepto no existe.
            RegionNotFoundError: Si la región no existe.
            InvalidRequestError: Si ``days`` está fuera de rango.
            QueryTooLongError: Si una consulta no cabe en su proveedor.
        """
        concept = await _get_or_fail(self._concepts, concept_id)
        return await self._preview(concept.data.name, concept, region_id, days)

    async def for_draft(self, data: ConceptInput, region_id: int, days: int) -> QueryPreview:
        """Consultas de un concepto que todavía no se guarda.

        Args:
            data: Datos del formulario.
            region_id: Región elegida.
            days: Últimos N días (1 a 90).

        Returns:
            Las consultas por proveedor.

        Raises:
            ConceptValidationError: Si el borrador no cumple las reglas.
            RegionNotFoundError: Si la región no existe.
            InvalidRequestError: Si ``days`` está fuera de rango.
            QueryTooLongError: Si una consulta no cabe en su proveedor.
        """
        draft = data.validated()
        return await self._preview(draft.name, draft, region_id, days)

    async def _preview(
        self, name: str, concept: ConceptTerms, region_id: int, days: int
    ) -> QueryPreview:
        window = DateWindow.last_days(days, self._today())
        facts = await self._regions.place_facts(region_id)
        region = await self._regions.get(region_id)
        if facts is None or region is None:
            raise RegionNotFoundError("No existe esa región.", {"id": region_id})
        ancestors = await self._regions.ancestors(region_id)
        queries = build_queries(concept, place_for(facts), window)
        return QueryPreview(name, RegionDetail(region, tuple(ancestors)), window, tuple(queries))
