"""Reglas de la revisión en bloque de un caso (F12, ADR-0107).

Benji pidió (11/11/2026) no confirmar ni descartar una cosa a la vez. Una
revisión en bloque es la misma revisión firmada de siempre (ADR-0104), solo
que para varias entidades o varios vínculos en una sola petición:

- Se confirma o se descarta; nada regresa a «sugerido».
- Cada elemento va una sola vez y hay un tope por petición.
- Todo o nada: si uno no se puede revisar, no se aplica ninguno (lo cumplen
  los casos de uso y el repositorio, en una sola transacción).
- Cada elemento deja su propia entrada en la bitácora, marcada ``bulk``.

Quién lo usa: ``ReviewEntities`` y ``ReviewRelationships``.

No hace: no guarda nada ni revisa permisos.
"""

from collections.abc import Hashable, Sequence

from app.domain.errors import BulkReviewError
from app.domain.investigation import ReviewStatus

# Tope de elementos por petición (decisión de F12, ADR-0107). El caso real más
# grande al 11/11/2026 («Chuy», 3 notas) tiene 36 entidades y 170 vínculos
# sugeridos; 500 cubre un caso de unas diez notas en una sola revisión sin
# dejar una transacción abierta mucho tiempo (cada elemento escribe su
# bitácora).
BULK_REVIEW_MAX_ITEMS = 500


def check_bulk_review(status: ReviewStatus, keys: Sequence[Hashable]) -> None:
    """Valida una revisión en bloque antes de tocar nada.

    Args:
        status: Lo que se quiere hacer: confirmar o descartar.
        keys: Lo que identifica a cada elemento (id de entidad o llave del
            vínculo), en el orden en que llegó.

    Raises:
        BulkReviewError: Si se pide regresar a «sugerido», si no trae
            elementos, si trae más de ``BULK_REVIEW_MAX_ITEMS`` o si alguno
            viene repetido.

    Example:
        >>> check_bulk_review(ReviewStatus.CONFIRMED, [4, 9])
    """
    if status is ReviewStatus.SUGGESTED:
        raise BulkReviewError("En bloque solo se confirma o se descarta.", {})
    if not keys:
        raise BulkReviewError("Elige al menos un elemento para revisar.", {})
    if len(keys) > BULK_REVIEW_MAX_ITEMS:
        raise BulkReviewError(
            f"Se revisan hasta {BULK_REVIEW_MAX_ITEMS} elementos por vez.",
            {"recibidos": len(keys), "maximo": BULK_REVIEW_MAX_ITEMS},
        )
    if len(set(keys)) != len(keys):
        raise BulkReviewError("Un mismo elemento viene más de una vez.", {})
