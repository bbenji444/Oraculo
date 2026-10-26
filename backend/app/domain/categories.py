"""Categorías de noticias: de qué delito trata cada nota (F12.4, ADR-0029).

El catálogo vive en la base (tabla ``categories``) para poder afinarlo sin
tocar código. La IA elige una categoría por nota y propone además una
etiqueta libre; si nombra una categoría que no existe, la nota va a la de
respaldo («Otros») y la etiqueta se conserva para el análisis de frecuencias.

Esta categoría es el **delito**. Lo que hizo la autoridad (detención, cateo,
sentencia) sigue en ``articles.event_type``.

No hace: no llama a la IA ni lee la base.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.authority import Authority
from app.domain.errors import DomainError
from app.domain.names import normalize_name

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
    """

    category_id: int
    name: str
    description: str
    is_other: bool = False
    color: str | None = None
    symbol: str | None = None


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
