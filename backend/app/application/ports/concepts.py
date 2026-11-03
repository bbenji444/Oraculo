"""Puerto de persistencia de conceptos.

Lo implementa el repositorio de PostgreSQL (``adapters/persistence``); las
pruebas usan uno en memoria. Cada escritura recibe su ``AuditEntry`` y la
guarda en la misma transacción que el cambio.

No hace: no valida reglas (eso es ``app.domain.concept`` y los casos de uso).
"""

from typing import Protocol

from app.application.audit import AuditEntry
from app.application.pagination import NameCursor
from app.domain.concept import Concept, ConceptDraft


class ConceptRepositoryPort(Protocol):
    """Lectura y escritura de ``concepts`` (solo los no borrados)."""

    async def list_concepts(
        self, active: bool | None, after: NameCursor | None, limit: int
    ) -> list[Concept]:
        """Conceptos en orden alfabético, después del cursor.

        Args:
            active: ``True`` solo activos, ``False`` solo inactivos, ``None`` todos.
            after: Posición desde la cual seguir.
            limit: Máximo de registros.

        Returns:
            Hasta ``limit`` conceptos ordenados por (``name_norm``, ``id``).
        """
        ...

    async def get(self, concept_id: int) -> Concept | None:
        """Busca un concepto vigente por id.

        Args:
            concept_id: Identificador.

        Returns:
            El concepto, o ``None`` si no existe o fue borrado.
        """
        ...

    async def for_category(self, category_id: int) -> Concept | None:
        """El tema general vigente de una subdivisión (02/11/2026).

        Args:
            category_id: La categoría («Homicidio»).

        Returns:
            Su concepto, o ``None`` si todavía no tiene.
        """
        ...

    async def name_taken(self, name_norm: str, except_id: int | None) -> bool:
        """Dice si otro concepto vigente ya usa ese nombre.

        Args:
            name_norm: Nombre normalizado.
            except_id: Concepto que se está editando (no cuenta contra sí mismo).

        Returns:
            ``True`` si el nombre está ocupado.
        """
        ...

    async def create(self, data: ConceptDraft, created_by: str, audit: AuditEntry) -> Concept:
        """Guarda un concepto nuevo y su registro de auditoría.

        Args:
            data: Datos validados.
            created_by: Usuario que lo crea.
            audit: Registro para la bitácora.

        Returns:
            El concepto guardado.

        Raises:
            ConceptNameTakenError: Si otro concepto ganó el nombre al mismo tiempo.
        """
        ...

    async def update(self, concept_id: int, data: ConceptDraft, audit: AuditEntry) -> Concept:
        """Reemplaza los datos de un concepto y registra el cambio.

        Args:
            concept_id: Identificador.
            data: Datos nuevos, validados.
            audit: Registro para la bitácora.

        Returns:
            El concepto actualizado.

        Raises:
            ConceptNotFoundError: Si ya no existe.
            ConceptNameTakenError: Si otro concepto ganó el nombre al mismo tiempo.
        """
        ...

    async def delete(self, concept_id: int, *, logical: bool, audit: AuditEntry) -> None:
        """Borra un concepto (lógico o físico) y registra el borrado.

        Args:
            concept_id: Identificador.
            logical: ``True`` marca ``deleted_at``; ``False`` borra la fila.
            audit: Registro para la bitácora.

        Raises:
            ConceptNotFoundError: Si ya no existe.
        """
        ...

    async def is_used_in_searches(self, concept_id: int) -> bool:
        """Dice si alguna búsqueda usó el concepto (decide el tipo de borrado).

        Args:
            concept_id: Identificador.

        Returns:
            ``True`` si hay búsquedas que lo usaron.
        """
        ...
