"""Categorías de noticias: de qué delito trata cada nota (F12.4, ADR-0029).

El catálogo vive en la base (tabla ``categories``) para poder afinarlo sin
tocar código. La IA elige una categoría por nota y propone además una
etiqueta libre; si nombra una categoría que no existe, la nota va a la de
respaldo («Otros») y la etiqueta se conserva para el análisis de frecuencias.

Esta categoría es el **delito**. Lo que hizo la autoridad (detención, cateo,
sentencia) sigue en ``articles.event_type``.

Desde el 02/11/2026 el catálogo se edita en pantalla (Conceptos ›
Subdivisiones): ``CategoryChanges`` valida lo que cambia. Lo que se edita
vale para las notas que se clasifiquen después; las ya clasificadas no
cambian.

No hace: no llama a la IA ni lee la base.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.authority import Authority
from app.domain.errors import CategoryValidationError, DomainError
from app.domain.names import normalize_name

# Mismo formato que los colores de los conceptos.
_COLOR = re.compile(r"^#[0-9A-F]{6}$")
# La IA lee la descripción en cada lote: más larga solo encarece sin ayudar.
MAX_CATEGORY_DESCRIPTION_CHARS = 400
MAX_CATEGORY_NAME_CHARS = 60

# Una etiqueta libre más larga no aporta para el análisis y llenaría la base.
MAX_RAW_LABEL_CHARS = 80


class MissingOtherCategoryError(DomainError):
    """El catálogo no tiene la categoría de respaldo («Otros»).

    La migración 0026 la siembra; si alguien la borró, clasificar no puede
    garantizar que toda nota quede en alguna categoría.
    """

    code = "missing_other_category"


@dataclass(frozen=True, slots=True)
class Category:
    """Una categoría del catálogo.

    Attributes:
        category_id: Id en ``categories``.
        name: Nombre para mostrar («Narcotráfico y delitos contra la salud»).
        description: Qué debe entender la IA por esta categoría.
        is_other: Si es la de respaldo («Otros»).
        color: Color en pantalla (``#RRGGBB``), cuando se decida.
        symbol: Símbolo en pantalla, cuando se decida.
        is_active: Si la IA la usa al clasificar (las apagadas no se ofrecen).
        topic_concept_id: Su tema general para buscar sin la FGR, si tiene
            (``concepts.category_id``, 02/11/2026).
    """

    category_id: int
    name: str
    description: str
    is_other: bool = False
    color: str | None = None
    symbol: str | None = None
    is_active: bool = True
    topic_concept_id: int | None = None


@dataclass(frozen=True, slots=True)
class CategoryChanges:
    """Lo que cambia de una subdivisión; ``None`` deja el campo igual.

    Attributes:
        name: Nombre nuevo.
        description: Lo que debe entender la IA por ella.
        color: Color en ``#RRGGBB``.
        is_active: Prenderla o apagarla.
    """

    name: str | None = None
    description: str | None = None
    color: str | None = None
    is_active: bool | None = None

    def apply_to(self, current: Category) -> Category:
        """Aplica y valida los cambios.

        Args:
            current: La subdivisión como está.

        Returns:
            La subdivisión como quedaría.

        Raises:
            CategoryValidationError: Si el nombre queda vacío o muy largo, la
                descripción es muy larga, el color no es ``#RRGGBB`` o se
                intenta apagar «Otros» (toda nota debe tener a dónde ir).

        Example:
            >>> CategoryChanges(color="#ff4d6d").apply_to(homicidio).color
            '#FF4D6D'
        """
        problems: list[dict[str, str]] = []
        name = " ".join((current.name if self.name is None else self.name).split())
        if not name:
            problems.append({"campo": "name", "mensaje": "Escribe el nombre."})
        elif len(name) > MAX_CATEGORY_NAME_CHARS:
            problems.append(
                {"campo": "name", "mensaje": f"Máximo {MAX_CATEGORY_NAME_CHARS} caracteres."}
            )
        description = current.description if self.description is None else self.description
        description = description.strip()
        if len(description) > MAX_CATEGORY_DESCRIPTION_CHARS:
            problems.append(
                {
                    "campo": "description",
                    "mensaje": f"Máximo {MAX_CATEGORY_DESCRIPTION_CHARS} caracteres.",
                }
            )
        color = current.color if self.color is None else self.color.strip().upper()
        if color is not None and not _COLOR.match(color):
            problems.append({"campo": "color", "mensaje": "Usa un color como #FF4D6D."})
        is_active = current.is_active if self.is_active is None else self.is_active
        if current.is_other and not is_active:
            problems.append(
                {
                    "campo": "is_active",
                    "mensaje": "«Otros» no se apaga: es a donde va lo que no encaja.",
                }
            )
        if problems:
            raise CategoryValidationError(
                "La subdivisión no cumple sus reglas.", {"problemas": problems}
            )
        return Category(
            category_id=current.category_id,
            name=name,
            description=description,
            is_other=current.is_other,
            color=color,
            symbol=current.symbol,
            is_active=is_active,
            topic_concept_id=current.topic_concept_id,
        )

    @property
    def name_norm(self) -> str | None:
        """El nombre nuevo para comparar, o ``None`` si no cambia."""
        return normalize_name(self.name) if self.name is not None else None


@dataclass(frozen=True, slots=True)
class CategoryChoice:
    """La categoría que quedó para una nota.

    Attributes:
        article_id: Nota.
        category: Categoría del catálogo (nunca ``None``: lo que no encaja es «Otros»).
        raw_label: Etiqueta libre que propuso la IA, recortada, o ``None``.
        authority: Quién actúa en el hecho (F12.5, ADR-0030), o ``None``.
    """

    article_id: int
    category: Category
    raw_label: str | None
    authority: Authority | None = None


def other_category(categories: Sequence[Category]) -> Category:
    """La categoría de respaldo («Otros»).

    Args:
        categories: Catálogo activo.

    Returns:
        La que tiene ``is_other``.

    Raises:
        MissingOtherCategoryError: Si no hay ninguna.
    """
    for category in categories:
        if category.is_other:
            return category
    raise MissingOtherCategoryError("Falta la categoría «Otros» en el catálogo.")


def choose_category(
    article_id: int,
    label: str | None,
    raw_label: str | None,
    categories: Sequence[Category],
    authority: Authority | None = None,
) -> CategoryChoice:
    """Convierte la respuesta de la IA en una categoría del catálogo.

    La categoría se busca por nombre normalizado (mayúsculas, sin acentos),
    así «narcotrafico y delitos contra la salud» cuenta igual. Lo que no
    coincide con ninguna va a «Otros».

    Args:
        article_id: Nota.
        label: Nombre de categoría que respondió la IA.
        raw_label: Etiqueta libre que propuso la IA.
        categories: Catálogo activo.
        authority: Quién actúa según la IA; se guarda tal cual.

    Returns:
        La categoría elegida, la etiqueta recortada y quién actúa.

    Raises:
        MissingOtherCategoryError: Si el catálogo no tiene «Otros».

    Example:
        >>> choose_category(7, "Huachicol y delitos contra hidrocarburos", "robo de gas", cats)
        CategoryChoice(article_id=7, category=Category(...), raw_label='robo de gas')
    """
    wanted = normalize_name(label or "")
    match = next((c for c in categories if normalize_name(c.name) == wanted), None)
    clean_raw = " ".join((raw_label or "").split())[:MAX_RAW_LABEL_CHARS] or None
    return CategoryChoice(article_id, match or other_category(categories), clean_raw, authority)
