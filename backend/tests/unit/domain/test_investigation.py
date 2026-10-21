"""Vocabulario del tablero de investigación (Fase 9.2, ADR-0101, 0104 y 0105)."""

from enum import StrEnum

import pytest

from app.domain.errors import InvalidRequestError
from app.domain.investigation import (
    CASE_ENTITY_STATUS_LABEL,
    CASE_STATUS_LABEL,
    ENTITY_TYPE_LABEL,
    EVIDENCE_SPAN_MAX_CHARS,
    INITIAL_REVIEW_STATUS,
    LEGAL_STATUS_LABEL,
    RELATIONSHIP_LABEL,
    REVIEW_STATUS_LABEL,
    SENSITIVITY_LABEL,
    SYMMETRIC_RELATIONSHIPS,
    CaseEntityStatus,
    CaseStatus,
    EntityType,
    InvestigationAction,
    LegalStatus,
    RelationshipType,
    ReviewStatus,
    Sensitivity,
    ordered_pair,
)


@pytest.mark.parametrize(
    ("enum", "labels"),
    [
        (EntityType, ENTITY_TYPE_LABEL),
        (LegalStatus, LEGAL_STATUS_LABEL),
        (ReviewStatus, REVIEW_STATUS_LABEL),
        (RelationshipType, RELATIONSHIP_LABEL),
        (Sensitivity, SENSITIVITY_LABEL),
        (CaseEntityStatus, CASE_ENTITY_STATUS_LABEL),
        (CaseStatus, CASE_STATUS_LABEL),
    ],
)
def test_cada_valor_tiene_su_etiqueta_en_espanol(
    enum: type[StrEnum], labels: dict[StrEnum, str]
) -> None:
    assert set(labels) == set(enum)
    assert all(label.strip() for label in labels.values())


def test_el_estatus_legal_es_lo_que_dice_la_nota_y_nunca_culpable() -> None:
    assert {s.value for s in LegalStatus} == {
        "mentioned",
        "alleged",
        "detained",
        "charged",
        "victim",
        "witness",
        "official",
    }
    assert LEGAL_STATUS_LABEL[LegalStatus.ALLEGED] == "señalado"
    assert LEGAL_STATUS_LABEL[LegalStatus.CHARGED] == "vinculado a proceso"
    forbidden = {"culpable", "guilty", "convicted", "sentenciado"}
    assert not forbidden & {s.value for s in LegalStatus}
    assert not forbidden & set(LEGAL_STATUS_LABEL.values())


def test_lo_propuesto_nace_sugerido() -> None:
    assert INITIAL_REVIEW_STATUS is ReviewStatus.SUGGESTED


def test_vinculos_simetricos_con_el_id_menor_primero() -> None:
    assert ordered_pair(RelationshipType.SAME_EVENT, 9, 4) == (4, 9)
    assert ordered_pair(RelationshipType.APPEARS_WITH, 4, 9) == (4, 9)
    # Los dirigidos conservan el sentido: la persona es dueña del vehículo.
    assert ordered_pair(RelationshipType.OWNS, 9, 4) == (9, 4)
    assert RelationshipType.OWNS not in SYMMETRIC_RELATIONSHIPS


def test_una_entidad_no_se_vincula_consigo_misma() -> None:
    with pytest.raises(InvalidRequestError, match="consigo misma"):
        ordered_pair(RelationshipType.FAMILY, 7, 7)


def test_ver_un_caso_es_una_accion_de_la_bitacora() -> None:
    assert InvestigationAction.CASE_VIEWED == "case.viewed"
    assert all("." in action.value for action in InvestigationAction)


def test_la_evidencia_es_una_cita_corta() -> None:
    assert EVIDENCE_SPAN_MAX_CHARS == 300
