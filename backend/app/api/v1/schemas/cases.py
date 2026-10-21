"""Esquemas de entrada y salida de ``/api/v1/cases`` (Fase 9.3).

La entrada solo comprueba tipos y pone topes amplios contra peticiones
abusivas; las reglas (largos, sensibilidad, estado) las aplica el dominio,
que responde con mensajes en español por campo (``invalid_case``).

La salida trae cada valor con su etiqueta en español ("reservado",
"cerrado") para que la interfaz no tenga que traducir.

No hace: no valida reglas de negocio.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.application.pagination import Page
from app.application.use_cases.cases import CaseInput
from app.domain.case import Case, CaseChanges, CaseView
from app.domain.investigation import CASE_STATUS_LABEL, SENSITIVITY_LABEL

# Topes de transporte, muy por encima de las reglas del dominio (120 y 2,000
# caracteres): solo evitan cuerpos gigantes.
_MAX_TEXT = 5_000


class CaseIn(BaseModel):
    """Caso nuevo."""

    name: str = Field(max_length=_MAX_TEXT, examples=["Homicidio estilista Polanco"])
    description: str = Field(default="", max_length=_MAX_TEXT)
    sensitivity: str = Field(
        default="normal", max_length=_MAX_TEXT, examples=["normal", "restricted", "confidential"]
    )

    def to_input(self) -> CaseInput:
        """Convierte al dato que reciben los casos de uso.

        Returns:
            Los datos sin validar todavía.
        """
        return CaseInput(self.name, self.description, self.sensitivity)


class CasePatch(BaseModel):
    """Cambios parciales: solo los campos enviados cambian.

    ``status`` cierra (``closed``), archiva (``archived``) o reabre (``open``).
    """

    name: str | None = Field(default=None, max_length=_MAX_TEXT)
    description: str | None = Field(default=None, max_length=_MAX_TEXT)
    sensitivity: str | None = Field(default=None, max_length=_MAX_TEXT)
    status: str | None = Field(default=None, max_length=_MAX_TEXT)

    def to_changes(self) -> CaseChanges:
        """Convierte a los cambios del dominio.

        Returns:
            Los cambios; ``None`` significa "no cambia".
        """
        return CaseChanges(self.name, self.description, self.sensitivity, self.status)


class CaseOut(BaseModel):
    """Un caso, con el rol de quien lo pide."""

    id: UUID
    name: str
    description: str
    status: str
    status_label: str
    sensitivity: str
    sensitivity_label: str
    created_by: str
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    article_count: int
    role: str | None = Field(
        default=None, description="owner, editor o viewer: qué puede hacer quien lo pide."
    )
    has_article: bool | None = Field(
        default=None,
        description="Con ?contains_article=: si el caso ya tiene esa nota.",
    )

    @classmethod
    def from_case(cls, case: Case) -> "CaseOut":
        """Arma la respuesta de un caso recién creado o editado.

        Args:
            case: El caso.

        Returns:
            La respuesta.
        """
        return cls(
            id=case.id,
            name=case.name,
            description=case.description,
            status=case.status.value,
            status_label=CASE_STATUS_LABEL[case.status],
            sensitivity=case.sensitivity.value,
            sensitivity_label=SENSITIVITY_LABEL[case.sensitivity],
            created_by=case.created_by,
            closed_at=case.closed_at,
            created_at=case.created_at,
            updated_at=case.updated_at,
            article_count=case.article_count,
        )

    @classmethod
    def from_view(cls, view: CaseView) -> "CaseOut":
        """Arma la respuesta de un caso visto por una persona.

        Args:
            view: El caso con el rol de la persona.

        Returns:
            La respuesta con ``role`` (y ``has_article`` si se pidió).
        """
        out = cls.from_case(view.case)
        out.role = view.role.value
        out.has_article = view.has_article
        return out


class CasePageOut(BaseModel):
    """Una página de casos."""

    items: list[CaseOut]
    next_cursor: str | None

    @classmethod
    def from_page(cls, page: Page[CaseView]) -> "CasePageOut":
        """Arma la respuesta.

        Args:
            page: Página de casos.

        Returns:
            La respuesta.
        """
        return cls(items=[CaseOut.from_view(v) for v in page.items], next_cursor=page.next_cursor)
