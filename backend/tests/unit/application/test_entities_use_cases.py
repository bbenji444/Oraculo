"""Casos de uso de las entidades de un caso con repositorios en memoria y una IA falsa (9.4)."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.application.audit import Actor
from app.application.ports.entities import CaseEntity, MentionView
from app.application.use_cases.cases import AddCaseArticle, CaseInput, CreateCase, UpdateCase
from app.application.use_cases.entities import (
    AnalyzePending,
    ConfirmEntity,
    DiscardEntity,
    ExtractCaseArticle,
    ListCaseEntities,
    QueueExtraction,
)
from app.application.use_cases.reports import LLMPrices
from app.domain.case import CaseChanges
from app.domain.enrichment import LLMUsage
from app.domain.entity_extraction import (
    CaseArticleEntitiesStatus,
    RawProposal,
    TextSource,
)
from app.domain.errors import (
    CaseClosedError,
    CaseForbiddenError,
    CaseNotFoundError,
    EntityNotFoundError,
    EntityReviewError,
    ProviderUnavailableError,
)
from app.domain.geocoding import MentionRole
from app.domain.investigation import (
    CaseMemberRole,
    CaseStatus,
    EntityType,
    InvestigationAction,
    LegalStatus,
    ReviewStatus,
)
from tests.unit.fake_cases import FakeCaseRepository
from tests.unit.fake_entities import (
    FakeEntityQueue,
    FakeEntityRepository,
    FakeExtractor,
    failing_extractor,
)

pytestmark = pytest.mark.anyio

BENJI = Actor("benji", "127.0.0.1")
LECTORA = Actor("lectora")
PRICES = LLMPrices("openai", 0.10, 0.50)
GOOD = RawProposal(
    "person",
    "Julián Ortega Ruiz",
    (),
    "event",
    "alleged",
    0.9,
    "orden de aprehensión contra Julián Ortega Ruiz",
)
INVENTED = RawProposal("person", "Julián Ortega Ruiz", (), "event", None, 0.5, "fue sentenciado")


async def new_case(cases: FakeCaseRepository) -> UUID:
    view = await CreateCase(cases).execute(CaseInput("Homicidio estilista Polanco"), BENJI)
    cases.add_member(view.case.id, "lectora", CaseMemberRole.VIEWER)
    return view.case.id


def mention(
    article_id: int, day: int, hint: LegalStatus | None, mention_id: int, entity_id: int = 1
) -> MentionView:
    return MentionView(
        mention_id,
        entity_id,
        article_id,
        f"Nota {article_id}",
        f"https://medio.mx/{article_id}",
        "Medio",
        datetime(2026, 10, day, tzinfo=UTC),
        "Julián Ortega Ruiz",
        MentionRole.EVENT,
        hint,
        0.9,
        "orden de aprehensión",
    )


def person(entity_id: int = 1, mentions: int = 2) -> CaseEntity:
    hints = [LegalStatus.ALLEGED, LegalStatus.DETAINED, None]
    return CaseEntity(
        entity_id,
        EntityType.PERSON,
        f"Persona {entity_id}",
        (),
        ReviewStatus.SUGGESTED,
        None,
        None,
        None,
        None,
        None,
        tuple(mention(10 + n, 1 + n, hints[n % 3], n, entity_id) for n in range(mentions)),
    )


# --- Leer una nota ---------------------------------------------------------------


async def test_lee_la_nota_revisa_contra_el_texto_y_deja_sugerencias() -> None:
    repo, case_id = FakeEntityRepository(), UUID(int=1)
    repo.add_article(case_id, 7)
    llm = FakeExtractor((GOOD, INVENTED), LLMUsage(2000, 600))

    outcome = await ExtractCaseArticle(repo, llm, PRICES).execute(case_id, 7, BENJI)

    assert outcome is not None
    assert outcome.status is CaseArticleEntitiesStatus.DONE
    assert outcome.cost_usd == pytest.approx(0.0005)
    assert llm.requests[0].text.startswith("Un juez giró orden")
    reviewed = outcome.extraction.reviewed if outcome.extraction else None
    assert reviewed is not None
    assert [p.label for p in reviewed.proposals] == ["Julián Ortega Ruiz"]
    assert len(reviewed.rejected) == 1
    [done] = repo.materialized
    assert done.audit.action == InvestigationAction.CASE_ENTITIES_EXTRACTED
    assert done.audit.payload["status"] == "ok"
    assert done.audit.payload["proposals"] == 1
    assert done.audit.payload["rejected"] == 1
    assert done.audit.payload["tokens_in"] == 2000
    assert repo.status_of(case_id, 7) is CaseArticleEntitiesStatus.DONE


async def test_si_la_nota_ya_se_leyo_para_otro_caso_no_se_vuelve_a_pagar() -> None:
    repo, first, second = FakeEntityRepository(), UUID(int=1), UUID(int=2)
    repo.add_article(first, 7)
    repo.add_article(second, 7)
    llm = FakeExtractor((GOOD,))
    extract = ExtractCaseArticle(repo, llm, PRICES)

    await extract.execute(first, 7, BENJI)
    outcome = await extract.execute(second, 7, BENJI)

    assert len(llm.requests) == 1
    assert outcome is not None
    assert (outcome.reused, outcome.cost_usd) == (True, 0.0)
    assert repo.materialized[1].audit.payload["reused"] is True
    assert repo.materialized[1].audit.payload["tokens_in"] == 0


async def test_nada_que_hacer_si_ya_se_leyo_o_ya_no_esta_en_el_caso() -> None:
    repo, case_id = FakeEntityRepository(), UUID(int=1)
    repo.add_article(case_id, 7, status=CaseArticleEntitiesStatus.DONE)
    llm = FakeExtractor((GOOD,))
    extract = ExtractCaseArticle(repo, llm, PRICES)

    assert await extract.execute(case_id, 7, BENJI) is None
    assert await extract.execute(case_id, 99, BENJI) is None
    assert llm.requests == []


async def test_si_la_quitan_mientras_se_lee_la_lectura_queda_guardada() -> None:
    repo, case_id = FakeEntityRepository(), UUID(int=1)
    repo.add_article(case_id, 7)
    llm = FakeExtractor((GOOD,))

    async def removed(*_: object) -> None:
        return None

    repo.materialize = removed  # type: ignore[method-assign, assignment]  # simula la carrera con "Quitar"

    assert await ExtractCaseArticle(repo, llm, PRICES).execute(case_id, 7, BENJI) is None
    assert repo.saved == 1


async def test_el_tope_del_caso_deja_la_nota_fuera_sin_gastar() -> None:
    repo, case_id = FakeEntityRepository(), UUID(int=1)
    repo.add_article(case_id, 1, status=CaseArticleEntitiesStatus.DONE)
    repo.add_article(case_id, 2)
    llm = FakeExtractor((GOOD,))

    outcome = await ExtractCaseArticle(repo, llm, PRICES, max_articles=1).execute(case_id, 2, BENJI)

    assert outcome is not None
    assert outcome.status is CaseArticleEntitiesStatus.SKIPPED
    assert llm.requests == []


async def test_una_respuesta_invalida_se_cobra_y_queda_fallida() -> None:
    repo, case_id = FakeEntityRepository(), UUID(int=1)
    repo.add_article(case_id, 7)

    outcome = await ExtractCaseArticle(repo, failing_extractor(3000, 20), PRICES).execute(
        case_id, 7, BENJI
    )

    assert outcome is not None
    assert outcome.status is CaseArticleEntitiesStatus.FAILED
    [(_, failure, audit)] = repo.failures
    assert failure.usage == LLMUsage(3000, 20)
    assert failure.cost_usd == pytest.approx(0.00031)
    assert audit.payload["status"] == "failed"
    assert repo.status_of(case_id, 7) is CaseArticleEntitiesStatus.FAILED


async def test_si_la_ia_no_responde_queda_fallida_sin_costo() -> None:
    repo, case_id = FakeEntityRepository(), UUID(int=1)
    repo.add_article(case_id, 7)
    llm = FakeExtractor(error=ProviderUnavailableError("caída", provider="openai"))

    outcome = await ExtractCaseArticle(repo, llm, PRICES).execute(case_id, 7, BENJI)

    assert outcome is not None
    assert (outcome.status, outcome.cost_usd) == (CaseArticleEntitiesStatus.FAILED, 0.0)


async def test_sin_texto_guardado_lee_titulo_y_fragmento() -> None:
    repo, case_id = FakeEntityRepository(), UUID(int=1)
    repo.add_article(case_id, 7, body=None, snippet="Orden contra Julián Ortega Ruiz.")
    llm = FakeExtractor(())

    outcome = await ExtractCaseArticle(repo, llm, PRICES).execute(case_id, 7, BENJI)

    assert llm.requests[0].text == "Orden contra Julián Ortega Ruiz."
    assert outcome is not None
    assert outcome.extraction is not None
    assert outcome.extraction.source is TextSource.TITLE_SNIPPET


# --- Encolar --------------------------------------------------------------------


async def test_agregar_una_nota_la_encola_una_sola_vez() -> None:
    cases, repo, queue = FakeCaseRepository(), FakeEntityRepository(), FakeEntityQueue()
    case_id = await new_case(cases)
    cases.articles[7] = object()  # type: ignore[assignment]  # solo importa que exista
    repo.add_article(case_id, 7)
    add = AddCaseArticle(cases, QueueExtraction(repo, queue))

    assert await add.execute(case_id, 7, BENJI) is True
    assert await add.execute(case_id, 7, BENJI) is False

    assert queue.queued == [(case_id, 7, "benji")]
    assert repo.status_of(case_id, 7) is CaseArticleEntitiesStatus.QUEUED


async def test_analizar_pendientes_encola_las_que_faltan_con_su_estimado() -> None:
    cases, repo, queue = FakeCaseRepository(), FakeEntityRepository(), FakeEntityQueue()
    case_id = await new_case(cases)
    repo.add_article(case_id, 1, status=CaseArticleEntitiesStatus.DONE)
    repo.add_article(case_id, 2, status=CaseArticleEntitiesStatus.FAILED)
    repo.add_article(case_id, 3)
    analyze = AnalyzePending(cases, repo, QueueExtraction(repo, queue), PRICES)

    result = await analyze.execute(case_id, BENJI)

    assert result.queued == 2
    assert result.estimated_cost_usd > 0
    assert [a for _, a, _ in queue.queued] == [2, 3]
    with pytest.raises(CaseForbiddenError):
        await analyze.execute(case_id, LECTORA)
    with pytest.raises(CaseNotFoundError):
        await analyze.execute(case_id, Actor("ajena"))


async def test_analizar_pendientes_respeta_el_tope() -> None:
    cases, repo, queue = FakeCaseRepository(), FakeEntityRepository(), FakeEntityQueue()
    case_id = await new_case(cases)
    repo.add_article(case_id, 1, status=CaseArticleEntitiesStatus.DONE)
    repo.add_article(case_id, 2)

    result = await AnalyzePending(
        cases, repo, QueueExtraction(repo, queue), PRICES, max_articles=1
    ).execute(case_id, BENJI)

    assert (result.queued, queue.queued) == (0, [])


# --- Revisar -------------------------------------------------------------------


async def test_listar_ordena_por_menciones_y_un_lector_puede_ver() -> None:
    cases, repo = FakeCaseRepository(), FakeEntityRepository()
    case_id = await new_case(cases)
    repo.add_entity(case_id, person(1, mentions=1))
    repo.add_entity(case_id, person(2, mentions=3))
    repo.add_article(case_id, 5)

    view = await ListCaseEntities(cases, repo, PRICES).execute(
        case_id, LECTORA, ReviewStatus.SUGGESTED
    )

    assert [e.entity_id for e in view.items] == [2, 1]
    assert view.counts[ReviewStatus.SUGGESTED] == 2
    assert view.analysis.pending == 1
    assert view.estimated_pending_cost_usd > 0
    with pytest.raises(CaseNotFoundError):
        await ListCaseEntities(cases, repo, None).execute(
            case_id, Actor("ajena"), ReviewStatus.SUGGESTED
        )


def test_se_sugiere_el_estatus_de_la_nota_mas_reciente_que_lo_dice() -> None:
    entity = person(1, mentions=3)

    assert entity.suggested_legal_status is LegalStatus.DETAINED
    assert entity.article_count == 3


async def test_confirmar_a_una_persona_firma_y_registra_antes_y_despues() -> None:
    cases, repo = FakeCaseRepository(), FakeEntityRepository()
    case_id = await new_case(cases)
    repo.add_entity(case_id, person(1))
    confirm = ConfirmEntity(cases, repo)

    entity, changed = await confirm.execute(case_id, 1, "alleged", BENJI)

    assert changed is True
    assert (entity.review_status, entity.legal_status, entity.reviewed_by) == (
        ReviewStatus.CONFIRMED,
        LegalStatus.ALLEGED,
        "benji",
    )
    [(_, audit)] = repo.reviews
    assert audit.action == InvestigationAction.ENTITY_CONFIRMED
    assert audit.payload["before"] == {"review_status": "suggested", "legal_status": None}
    assert audit.payload["after"] == {"review_status": "confirmed", "legal_status": "alleged"}
    assert audit.payload["suggested_legal_status"] == "detained"
    # Confirmar igual otra vez no repite la bitácora; corregir el estatus sí.
    assert (await confirm.execute(case_id, 1, "alleged", BENJI))[1] is False
    assert (await confirm.execute(case_id, 1, "detained", BENJI))[1] is True
    assert len(repo.reviews) == 2


async def test_confirmar_exige_estatus_legal_valido_y_permisos() -> None:
    cases, repo = FakeCaseRepository(), FakeEntityRepository()
    case_id = await new_case(cases)
    repo.add_entity(case_id, person(1))
    confirm = ConfirmEntity(cases, repo)

    with pytest.raises(EntityReviewError):
        await confirm.execute(case_id, 1, None, BENJI)
    with pytest.raises(EntityReviewError):
        await confirm.execute(case_id, 1, "culpable", BENJI)
    with pytest.raises(EntityNotFoundError):
        await confirm.execute(case_id, 99, "alleged", BENJI)
    with pytest.raises(CaseForbiddenError):
        await confirm.execute(case_id, 1, "alleged", LECTORA)
    assert repo.reviews == []


async def test_descartar_firma_y_no_se_repite() -> None:
    cases, repo = FakeCaseRepository(), FakeEntityRepository()
    case_id = await new_case(cases)
    repo.add_entity(case_id, person(1))
    discard = DiscardEntity(cases, repo)

    entity, changed = await discard.execute(case_id, 1, BENJI)
    _, again = await discard.execute(case_id, 1, BENJI)

    assert (entity.review_status, changed, again) == (ReviewStatus.DISCARDED, True, False)
    assert repo.reviews[0][1].action == InvestigationAction.ENTITY_DISCARDED


async def test_en_un_caso_cerrado_no_se_revisa() -> None:
    cases, repo = FakeCaseRepository(), FakeEntityRepository()
    case_id = await new_case(cases)
    repo.add_entity(case_id, person(1))

    await UpdateCase(cases).execute(case_id, CaseChanges(status=CaseStatus.CLOSED), BENJI)

    with pytest.raises(CaseClosedError):
        await DiscardEntity(cases, repo).execute(case_id, 1, BENJI)
