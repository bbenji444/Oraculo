"""Concepto: plantilla de búsqueda definida por el analista (especificación §7).

Un concepto tiene nombre, descripción, palabras clave, términos de
exclusión, color y un interruptor de activo. Aquí viven sus reglas, que se
aplican igual al crear, al editar y al probar un borrador:

- Nombre de 2 a 80 caracteres. Que sea único lo comprueba el caso de uso
  contra la base, comparando ``name_norm`` (sin mayúsculas ni acentos).
- De 1 a 50 palabras clave y hasta 50 exclusiones, cada una de 2 a 80
  caracteres, sin repetidas (se comparan normalizadas: "Hackeo" = "hackéo").
- Ninguna exclusión puede ser también palabra clave: se anularían.
- Sin caracteres que los buscadores interpretan como órdenes (ADR-0009).
- Color ``#RRGGBB``; descripción de hasta 500 caracteres.

Si algo falla se informan **todos** los problemas a la vez, cada uno con su
campo, para que la persona corrija el formulario de una sola pasada.

No hace: no sabe de base de datos ni de HTTP; no arma consultas (eso es
``app.domain.queries``).
"""

import re
from dataclasses import dataclass
from datetime import datetime

from app.domain.errors import ConceptValidationError
from app.domain.names import normalize_name

NAME_MIN_LENGTH = 2
# Cabe en una columna de tabla y en el chip del panel de búsqueda.
NAME_MAX_LENGTH = 80
DESCRIPTION_MAX_LENGTH = 500
# Muy por encima de lo útil (el ejemplo de §7.1 tiene 5): evita conceptos que
# generen decenas de consultas y gasten créditos sin control.
MAX_TERMS = 50
# Una palabra de 1 letra no sirve para buscar; 80 caracteres alcanzan para
# frases como "privación ilegal de la libertad".
TERM_MIN_LENGTH = 2
TERM_MAX_LENGTH = 80
_COLOR = re.compile(r"^#[0-9A-F]{6}$")
# Comillas, paréntesis y dos puntos arman frases, grupos y operadores
# (site:, sourcecountry:) en Google y GDELT (ADR-0009).
_FORBIDDEN_CHARS = frozenset('"()“”:')
# OR y AND sueltos son operadores booleanos en los tres proveedores.
_OPERATOR_WORDS = frozenset({"OR", "AND"})

KEYWORDS_FIELD = "keywords"
EXCLUDE_FIELD = "exclude_terms"


@dataclass(frozen=True, slots=True)
class Problem:
    """Un problema de validación, ligado al campo del formulario.

    Attributes:
        field: Campo (``name``, ``keywords``...).
        message: Explicación en español.
    """

    field: str
    message: str


def clean_text(value: str) -> str:
    """Quita espacios al inicio y al final y colapsa los repetidos.

    Args:
        value: Texto escrito por la persona.

    Returns:
        El texto limpio, conservando mayúsculas y acentos.
    """
    return " ".join(value.split())


def _term_problems(field: str, term: str) -> list[Problem]:
    problems = []
    if not TERM_MIN_LENGTH <= len(term) <= TERM_MAX_LENGTH:
        problems.append(
            Problem(
                field,
                f'"{term}": cada palabra debe tener entre {TERM_MIN_LENGTH} y '
                f"{TERM_MAX_LENGTH} caracteres.",
            )
        )
    if _FORBIDDEN_CHARS & set(term):
        problems.append(
            Problem(
                field,
                f'"{term}": no puede llevar comillas, paréntesis ni dos puntos; '
                "los buscadores los interpretan como órdenes.",
            )
        )
    if term.startswith("-"):
        problems.append(
            Problem(
                field,
                f'"{term}": no puede empezar con guion. Para excluir una palabra, '
                "agrégala en Exclusiones.",
            )
        )
    if _OPERATOR_WORDS & set(term.upper().split()):
        problems.append(
            Problem(field, f'"{term}": "OR" y "AND" sueltos son órdenes para los buscadores.')
        )
    return problems


def _clean_terms(
    field: str, label: str, terms: tuple[str, ...]
) -> tuple[tuple[str, ...], list[Problem]]:
    """Limpia una lista de términos y reporta vacíos, repetidos y caracteres prohibidos."""
    cleaned = tuple(t for t in (clean_text(raw) for raw in terms) if t)
    problems: list[Problem] = []
    if len(cleaned) > MAX_TERMS:
        problems.append(Problem(field, f"Máximo {MAX_TERMS} {label}."))
    seen: set[str] = set()
    for term in cleaned:
        problems.extend(_term_problems(field, term))
        norm = normalize_name(term)
        if norm in seen:
            problems.append(
                Problem(field, f'"{term}" está repetida (se compara sin mayúsculas ni acentos).')
            )
        seen.add(norm)
    return cleaned, problems


@dataclass(frozen=True, slots=True)
class ConceptDraft:
    """Datos de un concepto ya validados, todavía sin guardar.

    Se construye solo con ``ConceptDraft.validated`` para que nunca exista
    un borrador que no cumpla las reglas.

    Attributes:
        name: Nombre tal como se muestra.
        description: Para qué sirve el concepto.
        keywords: Palabras o frases que se buscan (al menos una).
        exclude_terms: Palabras o frases que descartan una nota.
        color: Color en ``#RRGGBB`` (mayúsculas).
        is_active: Si aparece en el panel de búsqueda.
    """

    name: str
    description: str
    keywords: tuple[str, ...]
    exclude_terms: tuple[str, ...]
    color: str
    is_active: bool

    @property
    def name_norm(self) -> str:
        """Nombre para comparar: "secuestro" y "Secuestro" son el mismo concepto."""
        return normalize_name(self.name)

    @classmethod
    def validated(  # noqa: PLR0913 — un argumento por campo del concepto, todos por nombre (*)
        cls,
        *,
        name: str,
        description: str,
        keywords: tuple[str, ...],
        exclude_terms: tuple[str, ...],
        color: str,
        is_active: bool = True,
    ) -> "ConceptDraft":
        """Limpia y valida los datos de un concepto.

        Args:
            name: Nombre escrito por la persona.
            description: Descripción.
            keywords: Palabras clave.
            exclude_terms: Términos de exclusión.
            color: Color en hexadecimal (``#2e86de`` o ``#2E86DE``).
            is_active: Si aparece en el panel de búsqueda.

        Returns:
            El borrador limpio: espacios colapsados, términos vacíos
            descartados y color en mayúsculas.

        Raises:
            ConceptValidationError: Con la lista completa de problemas.

        Example:
            >>> ConceptDraft.validated(name=" Secuestro ", description="",
            ...     keywords=("secuestro", "plagio"), exclude_terms=(), color="#e74c3c")
            ConceptDraft(name='Secuestro', ..., color='#E74C3C', is_active=True)
        """
        problems: list[Problem] = []
        clean_name = clean_text(name)
        if not NAME_MIN_LENGTH <= len(clean_name) <= NAME_MAX_LENGTH:
            problems.append(
                Problem(
                    "name",
                    f"El nombre debe tener entre {NAME_MIN_LENGTH} y {NAME_MAX_LENGTH} caracteres.",
                )
            )
        clean_description = description.strip()
        if len(clean_description) > DESCRIPTION_MAX_LENGTH:
            problems.append(
                Problem(
                    "description",
                    f"La descripción admite hasta {DESCRIPTION_MAX_LENGTH} caracteres.",
                )
            )
        clean_keywords, keyword_problems = _clean_terms(KEYWORDS_FIELD, "palabras clave", keywords)
        problems.extend(keyword_problems)
        if not clean_keywords:
            problems.append(Problem(KEYWORDS_FIELD, "Agrega al menos una palabra clave."))
        clean_excludes, exclude_problems = _clean_terms(EXCLUDE_FIELD, "exclusiones", exclude_terms)
        problems.extend(exclude_problems)
        keyword_norms = {normalize_name(k) for k in clean_keywords}
        for term in clean_excludes:
            if normalize_name(term) in keyword_norms:
                problems.append(
                    Problem(
                        EXCLUDE_FIELD,
                        f'"{term}" está como palabra clave y como exclusión; se anularían.',
                    )
                )
        clean_color = color.strip().upper()
        if not _COLOR.match(clean_color):
            problems.append(
                Problem("color", "El color debe tener el formato #RRGGBB, por ejemplo #2E86DE.")
            )
        if problems:
            raise ConceptValidationError(
                "El concepto tiene datos inválidos; revisa los campos marcados.",
                {"problemas": [{"campo": p.field, "mensaje": p.message} for p in problems]},
            )
        return cls(
            name=clean_name,
            description=clean_description,
            keywords=clean_keywords,
            exclude_terms=clean_excludes,
            color=clean_color,
            is_active=is_active,
        )


@dataclass(frozen=True, slots=True)
class ConceptChanges:
    """Cambios parciales a un concepto (PATCH): ``None`` = no cambia.

    Attributes:
        name: Nombre nuevo.
        description: Descripción nueva.
        keywords: Lista completa nueva de palabras clave.
        exclude_terms: Lista completa nueva de exclusiones.
        color: Color nuevo.
        is_active: Activar o desactivar.
    """

    name: str | None = None
    description: str | None = None
    keywords: tuple[str, ...] | None = None
    exclude_terms: tuple[str, ...] | None = None
    color: str | None = None
    is_active: bool | None = None

    def apply_to(self, current: ConceptDraft) -> ConceptDraft:
        """Combina los cambios con el concepto actual y vuelve a validar todo.

        Se valida el resultado completo, no solo lo que cambió: por ejemplo,
        una exclusión nueva puede chocar con una palabra clave que no cambió.

        Args:
            current: Datos actuales del concepto.

        Returns:
            El concepto resultante, validado.

        Raises:
            ConceptValidationError: Si el resultado no cumple las reglas.
        """
        return ConceptDraft.validated(
            name=current.name if self.name is None else self.name,
            description=current.description if self.description is None else self.description,
            keywords=current.keywords if self.keywords is None else self.keywords,
            exclude_terms=(
                current.exclude_terms if self.exclude_terms is None else self.exclude_terms
            ),
            color=current.color if self.color is None else self.color,
            is_active=current.is_active if self.is_active is None else self.is_active,
        )


@dataclass(frozen=True, slots=True)
class Concept:
    """Concepto guardado.

    Attributes:
        id: Identificador.
        data: Sus datos validados.
        created_by: Usuario que lo creó.
        created_at: Fecha de creación (UTC).
        updated_at: Fecha de la última edición (UTC).
    """

    id: int
    data: ConceptDraft
    created_by: str
    created_at: datetime
    updated_at: datetime

    @property
    def keywords(self) -> tuple[str, ...]:
        """Palabras clave (atajo para ``build_queries``)."""
        return self.data.keywords

    @property
    def exclude_terms(self) -> tuple[str, ...]:
        """Exclusiones (atajo para ``build_queries``)."""
        return self.data.exclude_terms
