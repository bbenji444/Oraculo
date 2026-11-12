"""Reglas de la revisión en bloque (F12, ADR-0107)."""

import pytest

from app.domain.bulk_review import BULK_REVIEW_MAX_ITEMS, check_bulk_review
from app.domain.errors import BulkReviewError
from app.domain.investigation import ReviewStatus


def test_confirmar_o_descartar_varias_distintas_pasa() -> None:
    check_bulk_review(ReviewStatus.CONFIRMED, [1, 2, 3])
    check_bulk_review(ReviewStatus.DISCARDED, list(range(BULK_REVIEW_MAX_ITEMS)))


@pytest.mark.parametrize(
    ("status", "keys", "message"),
    [
        (ReviewStatus.SUGGESTED, [1], "solo se confirma o se descarta"),
        (ReviewStatus.CONFIRMED, [], "al menos un elemento"),
        (ReviewStatus.CONFIRMED, [4, 9, 4], "más de una vez"),
        (ReviewStatus.DISCARDED, list(range(BULK_REVIEW_MAX_ITEMS + 1)), "hasta 500"),
    ],
)
def test_lo_que_no_se_puede_revisar_en_bloque(
    status: ReviewStatus, keys: list[int], message: str
) -> None:
    with pytest.raises(BulkReviewError, match=message):
        check_bulk_review(status, keys)
