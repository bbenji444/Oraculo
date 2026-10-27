"""Caso de investigación: reglas, datos y permisos (Fase 9.3, historia H9.1).

Un caso agrupa las noticias (y, desde la 9.4, las entidades) de una
investigación. Aquí viven sus reglas, que se aplican igual al crear y al
editar:

- Nombre de 1 a 120 caracteres y descripción de hasta 2,000.
- Sensibilidad: normal, reservado o confidencial (``Sensitivity``).
- **Solo un caso abierto cambia.** Cerrado o archivado es de solo lectura:
  lo único que se puede hacer es reabrirlo (decisión D5 de la 9.3).
- La fecha de cierre sigue al estado (``closed_at_for``), igual que el CHECK
  ``cases_closed_at_matches_status`` de la base.
- Permisos por rol (``case_members``): el dueño y los editores cambian el
  caso; solo el dueño administra quién entra. Un lector solo mira.

No hace: no sabe de base de datos ni de HTTP; no decide quién es miembro
(eso lo lee el repositorio).
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.concept import Problem, clean_text
from app.domain.errors import CaseValidationError
from app.domain.investigation import CaseMemberRole, CaseStatus, Sensitivity
from app.domain.names import normalize_name

NAME_MIN_LENGTH = 1
# Cabe en el renglón de la lista de casos y en el título del muro.
NAME_MAX_LENGTH = 120
# Una descripción de investigación, no un expediente: los detalles van en las
# notas del investigador (9.7).
DESCRIPTION_MAX_LENGTH = 2_000


@dataclass(frozen=True, slots=True)
class CaseDraft:
    """Datos de un caso ya validados, todavía sin guardar.

    Se construye solo con ``CaseDraft.validated``.

    Attributes:
        name: Nombre tal como se muestra.
        description: Para qué es el caso.
        sensitivity: Nivel de reserva.
    """

    name: str
    description: str
    sensitivity: Sensitivity

    @property
    def name_norm(self) -> str:
        """Nombre para comparar y ordenar (mayúsculas, sin acentos, con Ñ)."""
        return normalize_name(self.name)

    @classmethod
    def validated(cls, name: str, description: str, sensitivity: str) -> "CaseDraft":
        """Limpia y valida los datos de un caso.

        Args:
            name: Nombre escrito por la persona.
            description: Descripción (puede ir vacía).
            sensitivity: ``normal``, ``restricted`` o ``confidential``.

        Returns:
            El borrador limpio (espacios colapsados en el nombre).

        Raises:
            CaseValidationError: Con todos los problemas, cada uno con su campo.

        Example:
            >>> CaseDraft.validated(" Homicidio estilista Polanco ", "", "normal").name
            'Homicidio estilista Polanco'
        """
        problems: list[Problem] = []
        clean_name = clean_text(name)
        if not NAME_MIN_LENGTH <= len(clean_name) <= NAME_MAX_LENGTH:
            problems.append(
                Problem("name", f"El nombre debe tener entre 1 y {NAME_MAX_LENGTH} caracteres.")
            )
        clean_description = description.strip()
        if len(clean_description) > DESCRIPTION_MAX_LENGTH:
            problems.append(
                Problem(
                    "description",
                    f"La descripción admite hasta {DESCRIPTION_MAX_LENGTH:,} caracteres.",
                )
            )
        try:
            level = Sensitivity(sensitivity)
        except ValueError:
            problems.append(
                Problem("sensitivity", "La sensibilidad debe ser normal, reservado o confidencial.")
            )
            level = Sensitivity.NORMAL
        if problems:
            raise CaseValidationError(
                "El caso tiene datos inválidos; revisa los campos marcados.",
                {"problemas": [{"campo": p.field, "mensaje": p.message} for p in problems]},
            )
        return cls(name=clean_name, description=clean_description, sensitivity=level)


@dataclass(frozen=True, slots=True)
class CaseChanges:
    """Cambios a un caso: ``None`` significa "no cambia".

    Attributes:
        name: Nombre nuevo.
        description: Descripción nueva.
        sensitivity: Sensibilidad nueva.
        status: Estado nuevo (cerrar, archivar o reabrir).
    """

    name: str | None = None
    description: str | None = None
    sensitivity: str | None = None
    status: str | None = None

    @property
    def touches_data(self) -> bool:
        """Si cambia algo además del estado (no se permite en un caso cerrado)."""
        return any(v is not None for v in (self.name, self.description, self.sensitivity))


@dataclass(frozen=True, slots=True)
class Case:
    """Un caso guardado.

    Attributes:
        id: Identificador.
        name: Nombre.
        description: Descripción.
        status: Abierto, cerrado o archivado.
        sensitivity: Nivel de reserva.
        created_by: Quién lo creó.
        closed_at: Cuándo se cerró (``None`` si está abierto).
        created_at: Cuándo se creó.
        updated_at: Último cambio (también al agregar o quitar notas).
        article_count: Cuántas noticias tiene.
        deleted_at: Cuándo se eliminó (``None`` si sigue vivo). Eliminar es
            reversible: el caso se queda en la base y se puede restaurar.
    """

    id: UUID
    name: str
    description: str
    status: CaseStatus
    sensitivity: Sensitivity
    created_by: str
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    article_count: int
    deleted_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CaseView:
    """Un caso visto por una persona: el caso y su rol en él.

    Attributes:
        case: El caso.
        role: Rol de quien lo ve.
        has_article: Si contiene la nota por la que se preguntó (``None`` si
            no se preguntó por ninguna).
    """

    case: Case
    role: CaseMemberRole
    has_article: bool | None = None


def can_delete(role: CaseMemberRole) -> bool:
    """Si el rol puede eliminar (o restaurar) el caso.

    Solo el dueño: eliminar se lleva el caso para todos sus miembros.

    Args:
        role: Rol en el caso.

    Returns:
        ``True`` solo para el dueño.
    """
    return role is CaseMemberRole.OWNER


def can_edit(role: CaseMemberRole) -> bool:
    """Si el rol puede cambiar el caso (datos, estado y noticias).

    Args:
        role: Rol en el caso.

    Returns:
        ``True`` para dueño y editor.
    """
    return role in (CaseMemberRole.OWNER, CaseMemberRole.EDITOR)


def can_manage_members(role: CaseMemberRole) -> bool:
    """Si el rol puede agregar o quitar miembros.

    Args:
        role: Rol en el caso.

    Returns:
        ``True`` solo para el dueño.
    """
    return role is CaseMemberRole.OWNER


def is_read_only(status: CaseStatus) -> bool:
    """Si el caso no admite cambios hasta que se reabra (D5).

    Args:
        status: Estado del caso.

    Returns:
        ``True`` si está cerrado o archivado.
    """
    return status is not CaseStatus.OPEN


def closed_at_for(status: CaseStatus, current: datetime | None, now: datetime) -> datetime | None:
    """Fecha de cierre que corresponde a un estado.

    Args:
        status: Estado nuevo.
        current: Fecha de cierre que tenía.
        now: Ahora.

    Returns:
        ``None`` si queda abierto; la fecha que ya tenía si ya estaba cerrado
        (archivar un caso cerrado no cambia cuándo se cerró); si no, ``now``.
    """
    if status is CaseStatus.OPEN:
        return None
    return current or now


# Un identificador de usuario de texto (hasta la Fase 8, como ``created_by``).
USER_ID_MAX_LENGTH = 100


@dataclass(frozen=True, slots=True)
class CaseMember:
    """Una persona con acceso a un caso.

    Attributes:
        user_id: Usuario.
        role: Dueño, editor o lector.
        added_by: Quién le dio acceso.
        created_at: Desde cuándo.
    """

    user_id: str
    role: CaseMemberRole
    added_by: str
    created_at: datetime
