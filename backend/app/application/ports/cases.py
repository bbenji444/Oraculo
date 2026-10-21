"""Puerto de persistencia de casos de investigación (Fase 9.3).

Lo implementa el repositorio de PostgreSQL (``adapters/persistence``); las
pruebas usan uno en memoria. Cada escritura recibe su ``AuditEntry`` y la
guarda en la misma transacción que el cambio (§9.10).

Toda lectura es **por persona**: un caso solo existe para quien es miembro
(``case_members``). El repositorio nunca devuelve un caso ajeno.

No hace: no valida reglas ni permisos (eso son ``app.domain.case`` y los
casos de uso).
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.application.audit import AuditEntry
from app.application.pagination import TimeCursor
from app.application.ports.search_reads import ArticleItem
from app.domain.case import Case, CaseDraft, CaseView
from app.domain.investigation import CaseStatus


class CaseRepositoryPort(Protocol):
    """Lectura y escritura de ``cases`` y ``case_members``."""

    async def create(self, data: CaseDraft, created_by: str, audit: AuditEntry) -> Case:
        """Guarda un caso nuevo, a quien lo crea como dueño y la bitácora.

        Args:
            data: Datos validados.
            created_by: Usuario que lo crea (queda como ``owner``).
            audit: Registro para la bitácora.

        Returns:
            El caso guardado.
        """
        ...

    async def get_view(self, case_id: UUID, user_id: str) -> CaseView | None:
        """El caso como lo ve una persona.

        Args:
            case_id: Caso.
            user_id: Quién pregunta.

        Returns:
            El caso con el rol de la persona, o ``None`` si no existe o no es
            miembro (las dos cosas se ven igual a propósito).
        """
        ...

    async def list_for_user(
        self,
        user_id: str,
        statuses: Sequence[CaseStatus],
        contains_article: int | None,
        after: TimeCursor | None,
        limit: int,
    ) -> list[CaseView]:
        """Casos donde la persona es miembro, del más reciente al más viejo.

        Args:
            user_id: Quién pregunta.
            statuses: Estados que se quieren.
            contains_article: Si viene, cada caso dice si ya tiene esa nota.
            after: Posición (``updated_at``, ``id``) desde la cual seguir.
            limit: Máximo de registros.

        Returns:
            Hasta ``limit`` casos ordenados por (``updated_at``, ``id``) de
            mayor a menor.
        """
        ...

    async def update(
        self,
        case_id: UUID,
        *,
        data: CaseDraft,
        status: CaseStatus,
        closed_at: datetime | None,
        audit: AuditEntry,
    ) -> Case:
        """Reemplaza los datos y el estado de un caso y registra el cambio.

        Args:
            case_id: Caso.
            data: Datos validados.
            status: Estado nuevo.
            closed_at: Fecha de cierre que corresponde al estado.
            audit: Registro para la bitácora.

        Returns:
            El caso como quedó.
        """
        ...

    async def record_view(self, case_id: UUID, audit: AuditEntry, window_minutes: int) -> bool:
        """Deja ``case.viewed`` en la bitácora, una vez por persona y ventana.

        Args:
            case_id: Caso que se vio.
            audit: Registro (quién y desde qué IP).
            window_minutes: Si la misma persona ya lo vio en estos minutos, no
                se repite (decisión D4 de la 9.3).

        Returns:
            ``True`` si se registró; ``False`` si ya había uno reciente.
        """
        ...

    async def article_exists(self, article_id: int) -> bool:
        """Dice si existe una noticia.

        Args:
            article_id: Noticia.

        Returns:
            ``True`` si existe.
        """
        ...

    async def add_article(
        self, case_id: UUID, article_id: int, added_by: str, audit: AuditEntry
    ) -> bool:
        """Agrega una noticia al caso (si ya estaba, no hace nada).

        Args:
            case_id: Caso.
            article_id: Noticia.
            added_by: Quién la agrega.
            audit: Registro para la bitácora (solo se guarda si se agregó).

        Returns:
            ``True`` si se agregó; ``False`` si ya estaba.
        """
        ...

    async def remove_article(self, case_id: UUID, article_id: int, audit: AuditEntry) -> bool:
        """Quita una noticia del caso (la noticia no se borra).

        Args:
            case_id: Caso.
            article_id: Noticia.
            audit: Registro para la bitácora (solo se guarda si se quitó).

        Returns:
            ``True`` si se quitó; ``False`` si no estaba.
        """
        ...

    async def list_articles(
        self, case_id: UUID, after: TimeCursor | None, limit: int
    ) -> list[ArticleItem]:
        """Noticias del caso, de la más reciente a la más vieja.

        Args:
            case_id: Caso.
            after: Posición (``published_at``, ``id``) desde la cual seguir.
            limit: Máximo de registros.

        Returns:
            Las notas con el mismo formato de Explorar (``in_region`` vacío:
            un caso no tiene región buscada).
        """
        ...
