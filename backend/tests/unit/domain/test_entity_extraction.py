"""Revisión de lo que propone la IA contra el texto de la nota (Fase 9.4, ADR-0105).

La nota es inventada (nombres ficticios): las pruebas no guardan datos de
personas reales.
"""

from datetime import UTC, datetime

import pytest

from app.domain.enrichment import MAX_TEXT_CHARS
from app.domain.entity_extraction import (
    MAX_ALIASES,
    REJECTION_LABEL,
    AnalyzedText,
    MentionHint,
    RawProposal,
    RejectionReason,
    TextSource,
    analyzed_text,
    confirmed_legal_status,
    estimated_extraction_usage,
    find_quote,
    legal_status_from,
    match_region,
    review_proposals,
    suggested_legal_status,
)
from app.domain.errors import EntityReviewError
from app.domain.geocoding import MentionRole
from app.domain.investigation import EVIDENCE_SPAN_MAX_CHARS, EntityType, LegalStatus

TITLE = "Giran orden de aprehensión contra empresario por homicidio en Polanco"
BODY = (
    "Un juez emitió una orden de aprehensión contra el empresario Julián Ortega Ruiz, "
    "señalado como presunto autor intelectual del asesinato del estilista Ramón Salas, "
    "conocido como “Ramy Style”. El crimen ocurrió en la colonia Polanco, en la alcaldía "
    "Miguel Hidalgo. La Fiscalía capitalina informó que Ortega Ruiz, alias Julián N, "
    "permanece prófugo. Una camioneta Jeep Cherokee blanca fue localizada."
)
TEXT = AnalyzedText(TITLE, BODY, TextSource.FULL_TEXT)


def proposal(
    label: str = "Julián Ortega Ruiz",
    evidence: str = "una orden de aprehensión contra el empresario Julián Ortega Ruiz",
    *,
    kind: str = "person",
    aliases: tuple[str, ...] = (),
    role: str = "event",
    legal: str | None = "alleged",
    confidence: float = 0.9,
) -> RawProposal:
    return RawProposal(kind, label, aliases, role, legal, confidence, evidence)


# --- Buscar la cita ---------------------------------------------------------------


def test_la_cita_se_encuentra_sin_importar_mayusculas_espacios_ni_comillas() -> None:
    found = find_quote('conocido como  "RAMY STYLE"', BODY)

    assert found is not None
    assert BODY[found[0] : found[1]] == "conocido como “Ramy Style”"


def test_se_quitan_los_puntos_suspensivos_que_agrega_la_ia() -> None:
    found = find_quote("…del asesinato del estilista Ramón Salas…", BODY)

    assert found is not None
    assert BODY[found[0] : found[1]] == "del asesinato del estilista Ramón Salas"


def test_una_cita_que_no_esta_no_se_encuentra() -> None:
    assert find_quote("fue detenido en Tlalpan", BODY) is None
    assert find_quote("  …  ", BODY) is None


def test_un_nombre_se_busca_como_palabra_completa() -> None:
    assert find_quote("Ana", "La señora Mariana Díaz", whole_words=True) is None
    assert find_quote("Ana", "La señora Ana Díaz", whole_words=True) == (10, 13)
    assert find_quote("Ana", "La señora Mariana Díaz") == (14, 17)


def test_los_acentos_si_cuentan() -> None:
    # Literal es literal: "Ramon" sin acento no es lo que dice la nota.
    assert find_quote("Ramon Salas", BODY) is None


# --- Revisar las propuestas -------------------------------------------------------


def test_una_propuesta_con_su_cita_queda_como_sugerencia() -> None:
    reviewed = review_proposals([proposal(evidence="UNA ORDEN DE APREHENSIÓN contra")], TEXT)

    assert reviewed.rejected == ()
    (item,) = reviewed.proposals
    assert item.type is EntityType.PERSON
    assert item.label == "Julián Ortega Ruiz"
    assert item.label_norm == "JULIAN ORTEGA RUIZ"
    assert item.role is MentionRole.EVENT
    assert item.legal_status_hint is LegalStatus.ALLEGED
    # La cita guardada es la de la nota, no la que escribió la IA.
    assert item.evidence_span == "una orden de aprehensión contra"
    assert item.char_start is not None
    assert BODY[item.char_start : item.char_end] == item.evidence_span


def test_una_cita_inventada_se_descarta() -> None:
    reviewed = review_proposals([proposal(evidence="fue detenido por la policía")], TEXT)

    assert reviewed.proposals == ()
    assert reviewed.rejected[0].reason is RejectionReason.EVIDENCE_NOT_IN_TEXT
    assert REJECTION_LABEL[reviewed.rejected[0].reason] == "la cita no está en la nota"


def test_un_nombre_que_no_esta_en_la_nota_se_descarta() -> None:
    invented = proposal("Julián Ortega Ruiz de la Garza", evidence="Julián Ortega Ruiz")

    reviewed = review_proposals([invented], TEXT)

    assert reviewed.rejected[0].reason is RejectionReason.NAME_NOT_IN_TEXT


def test_si_el_nombre_no_esta_pero_un_alias_si_el_alias_es_el_nombre() -> None:
    expanded = proposal(
        "Fiscalía General de Justicia de la Ciudad de México",
        "La Fiscalía capitalina informó",
        kind="org",
        aliases=("Fiscalía capitalina",),
        legal=None,
    )

    (item,) = review_proposals([expanded], TEXT).proposals

    assert item.label == "Fiscalía capitalina"
    assert item.aliases == ()


def test_los_alias_se_limpian_y_solo_quedan_los_que_dice_la_nota() -> None:
    raw = proposal(
        aliases=("Ortega Ruiz", "ortega  ruiz", "Julián Ortega Ruiz", "El Patrón", " Julián N "),
    )

    (item,) = review_proposals([raw], TEXT).proposals

    assert item.aliases == ("Ortega Ruiz", "Julián N")


def test_los_alias_tienen_tope() -> None:
    aliases = tuple(f"Alias{n}" for n in range(MAX_ALIASES + 3))
    body = f"Julián Ortega Ruiz, también llamado {' '.join(aliases)}."
    text = AnalyzedText("Nota", body, TextSource.FULL_TEXT)
    raw = proposal(evidence="Julián Ortega Ruiz", aliases=aliases)

    (item,) = review_proposals([raw], text).proposals

    assert len(item.aliases) == MAX_ALIASES


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("detained", LegalStatus.DETAINED),
        ("Señalado", LegalStatus.ALLEGED),
        ("vinculado a  proceso", LegalStatus.CHARGED),
        ("culpable", None),
        ("sospechoso", None),
        (None, None),
    ],
)
def test_el_estatus_legal_solo_admite_los_codigos(
    given: str | None, expected: LegalStatus | None
) -> None:
    assert legal_status_from(given) is expected


def test_el_estatus_legal_es_solo_de_personas() -> None:
    place = proposal(
        "Polanco", "El crimen ocurrió en la colonia Polanco", kind="place", legal="victim"
    )

    (item,) = review_proposals([place], TEXT).proposals

    assert item.type is EntityType.PLACE
    assert item.legal_status_hint is None


def test_tipos_que_no_se_extraen_y_nombres_vacios_se_descartan() -> None:
    reviewed = review_proposals(
        [
            proposal("55 1234 5678", "Julián Ortega Ruiz", kind="phone"),
            proposal("cosa", "Julián Ortega Ruiz", kind="planeta"),
            proposal("  ", "Julián Ortega Ruiz"),
        ],
        TEXT,
    )

    assert [r.reason for r in reviewed.rejected] == [
        RejectionReason.UNSUPPORTED_TYPE,
        RejectionReason.UNSUPPORTED_TYPE,
        RejectionReason.BLANK_LABEL,
    ]


def test_la_misma_cita_repetida_cuenta_una_vez_pero_otra_cita_es_otra_mencion() -> None:
    reviewed = review_proposals(
        [
            proposal(),
            proposal(),
            proposal(evidence="informó que Ortega Ruiz, alias Julián N"),
        ],
        TEXT,
    )

    assert len(reviewed.proposals) == 2
    assert [r.reason for r in reviewed.rejected] == [RejectionReason.DUPLICATE]


def test_una_cita_larga_se_recorta_sin_perder_el_nombre() -> None:
    filler = "dijeron los vecinos que la zona es tranquila y que nunca pasa nada " * 6
    body = f"{filler}hasta que llegó Julián Ortega Ruiz al lugar. {filler}"
    text = AnalyzedText("Nota", body, TextSource.FULL_TEXT)

    (item,) = review_proposals([proposal(evidence=body)], text).proposals

    assert len(item.evidence_span) <= EVIDENCE_SPAN_MAX_CHARS
    assert "Julián Ortega Ruiz" in item.evidence_span
    assert body[item.char_start : item.char_end].strip() == item.evidence_span
    # Corta en límite de palabra.
    assert item.char_start is not None
    assert body[item.char_start - 1] == " "


def test_una_cita_del_titulo_no_tiene_posicion_en_el_cuerpo() -> None:
    raw = proposal("Polanco", "homicidio en Polanco", kind="place", legal=None)

    (item,) = review_proposals([raw], TEXT).proposals

    assert item.evidence_span == "homicidio en Polanco"
    assert (item.char_start, item.char_end) == (None, None)


def test_la_confianza_se_acota_y_un_rol_raro_es_mencion() -> None:
    (item,) = review_proposals([proposal(confidence=3.5, role="protagonista")], TEXT).proposals

    assert item.confidence == 1.0
    assert item.role is MentionRole.MENTIONED


# --- Texto que lee la IA ----------------------------------------------------------


def test_con_texto_completo_se_usa_el_cuerpo_recortado() -> None:
    text = analyzed_text("Título", "palabra " * 2000, "fragmento", full_text=True)

    assert text.source is TextSource.FULL_TEXT
    assert len(text.body) <= MAX_TEXT_CHARS


def test_sin_texto_extraido_o_ya_borrado_es_titulo_y_fragmento() -> None:
    fallback = analyzed_text("Título", "Título. Fragmento.", "Fragmento.", full_text=False)
    purged = analyzed_text("Título", None, "Fragmento del medio.", full_text=True)
    nothing = analyzed_text("Título", None, None, full_text=False)

    assert (fallback.source, fallback.body) == (TextSource.TITLE_SNIPPET, "Título. Fragmento.")
    assert (purged.source, purged.body) == (TextSource.TITLE_SNIPPET, "Fragmento del medio.")
    assert nothing.body == ""


# --- Estatus sugerido, lugares y confirmación -------------------------------------


def test_se_sugiere_el_estatus_de_la_nota_mas_reciente_que_lo_dice() -> None:
    hints = [
        MentionHint(datetime(2026, 10, 1, tzinfo=UTC), 1, LegalStatus.ALLEGED),
        MentionHint(datetime(2026, 10, 9, tzinfo=UTC), 2, LegalStatus.DETAINED),
        MentionHint(datetime(2026, 10, 12, tzinfo=UTC), 3, None),
        MentionHint(None, 9, LegalStatus.MENTIONED),
    ]

    assert suggested_legal_status(hints) is LegalStatus.DETAINED
    assert suggested_legal_status([hints[2]]) is None
    # Misma fecha: gana la mención más nueva.
    same_day = datetime(2026, 10, 9, tzinfo=UTC)
    assert (
        suggested_legal_status(
            [MentionHint(same_day, 5, LegalStatus.CHARGED), MentionHint(same_day, 4, None)]
        )
        is LegalStatus.CHARGED
    )


def test_un_lugar_se_liga_a_la_region_ya_resuelta_de_la_misma_nota() -> None:
    locations = [("Ciudad de México", None), ("colonia  Polanco", 77), ("Polanco", 88)]

    assert match_region(["POLANCO"], locations) == 88
    assert match_region(["COLONIA POLANCO"], locations) == 77
    assert match_region(["TLALPAN"], locations) is None


def test_confirmar_a_una_persona_exige_su_estatus_legal() -> None:
    assert confirmed_legal_status(EntityType.PERSON, "victim") is LegalStatus.VICTIM
    with pytest.raises(EntityReviewError, match="elige su estatus legal"):
        confirmed_legal_status(EntityType.PERSON, None)
    with pytest.raises(EntityReviewError, match="desconocido") as error:
        confirmed_legal_status(EntityType.PERSON, "culpable")
    permitted = error.value.details["permitidos"]
    assert isinstance(permitted, list)
    assert "culpable" not in permitted


def test_lo_que_no_es_persona_se_confirma_sin_estatus_legal() -> None:
    assert confirmed_legal_status(EntityType.ORG, None) is None
    with pytest.raises(EntityReviewError, match="Solo las personas"):
        confirmed_legal_status(EntityType.PLACE, "victim")


def test_estimacion_de_tokens_antes_de_gastar() -> None:
    usage = estimated_extraction_usage(5)

    assert usage.tokens_in > 0
    assert usage.tokens_out > 0
    assert usage == estimated_extraction_usage(1) + estimated_extraction_usage(4)


def test_las_comillas_que_envuelven_toda_la_cita_se_quitan() -> None:
    found = find_quote("«el asesinato del estilista Ramón Salas.»", BODY)

    assert found is not None
    assert BODY[found[0] : found[1]] == "el asesinato del estilista Ramón Salas"
