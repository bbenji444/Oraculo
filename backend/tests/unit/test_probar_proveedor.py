"""Comando make probar-proveedor con repositorios y proveedor falsos (sin red)."""

from datetime import date, datetime
from pathlib import Path

import pytest

from app.application.audit import Actor
from app.application.ports.provider_log import ProviderQueryRecord, QueryRun
from app.application.ports.providers import ProviderResponse
from app.cli.probar_proveedor import (
    LeakedSecretError,
    Plan,
    build_plan,
    confirmed,
    execute,
    redact,
    save_fixture,
)
from app.domain.articles import RawArticle
from app.domain.concept import ConceptDraft
from app.domain.errors import ProviderRateLimitError
from app.domain.queries import DateWindow, PlannedQuery, Provider
from tests.unit.fake_concepts import FakeConceptRepository
from tests.unit.fake_regions import CDMX, MEXICO_FILTER, FakeRegionRepository

pytestmark = pytest.mark.anyio

WEEK = DateWindow.last_days(7, date(2026, 10, 16))
SECRET = "llave-super-secreta"


class FakeProvider:
    def __init__(
        self, response: ProviderResponse | None = None, error: Exception | None = None
    ) -> None:
        self.response = response
        self.error = error
        self.sent: list[PlannedQuery] = []

    @property
    def provider(self) -> Provider:
        return Provider.SEARCHAPI

    def is_configured(self) -> bool:
        return True

    def request_params(self, query: PlannedQuery) -> dict[str, str]:
        return {"q": query.text, "gl": "mx"}

    def estimate_cost(self, query: PlannedQuery) -> int:
        return 1

    async def search(self, query: PlannedQuery) -> ProviderResponse:
        self.sent.append(query)
        if self.error:
            raise self.error
        assert self.response is not None
        return self.response


class FakeLog:
    def __init__(self) -> None:
        self.records: list[tuple[ProviderQueryRecord, Actor | None]] = []

    async def record(self, entry: ProviderQueryRecord, actor: Actor | None = None) -> int:
        self.records.append((entry, actor))
        return len(self.records)

    async def credits_used_since(self, provider: str, since: datetime) -> int:
        return 0

    async def runs_of(self, provider: str, query_text: str) -> list[QueryRun]:
        return []


def concepts() -> FakeConceptRepository:
    repo = FakeConceptRepository()
    repo.add(
        ConceptDraft.validated(
            name="Ciberseguridad",
            description="",
            keywords=("hackeo", "ransomware"),
            exclude_terms=("curso",),
            color="#2E86DE",
        )
    )
    return repo


def response(body: str = '{"ok": true}') -> ProviderResponse:
    article = RawArticle.create(
        provider=Provider.SEARCHAPI,
        provider_rank=1,
        url="https://www.milenio.com/nota",
        title="Hackeo a dependencia",
    )
    return ProviderResponse((article,), 200, {"q": "x"}, body)


async def plan_for(provider: FakeProvider, text: str | None = None) -> Plan:
    return await build_plan(
        provider=provider,
        concepts=concepts(),
        regions=FakeRegionRepository(),
        concept_name="CIBERSEGURIDAD",
        region_code=CDMX.code,
        window=WEEK,
        text=text,
    )


async def test_arma_la_consulta_como_una_busqueda_real() -> None:
    plan = await plan_for(FakeProvider())

    assert plan.breadcrumb == "México › Ciudad de México"
    assert plan.query.text == '(hackeo OR ransomware) ("Ciudad de México" OR CDMX) -curso'
    assert plan.params["gl"] == "mx"
    assert plan.credits == 1


async def test_el_texto_se_puede_reemplazar_para_un_experimento() -> None:
    plan = await plan_for(FakeProvider(), text="hackeo")

    assert plan.query.text == "hackeo"


async def test_concepto_o_region_inexistentes_detienen_el_comando() -> None:
    with pytest.raises(SystemExit, match="No existe el concepto"):
        await build_plan(
            provider=FakeProvider(),
            concepts=concepts(),
            regions=FakeRegionRepository(),
            concept_name="Inventado",
            region_code=CDMX.code,
            window=WEEK,
        )
    with pytest.raises(SystemExit, match="clave 99"):
        await build_plan(
            provider=FakeProvider(),
            concepts=concepts(),
            regions=FakeRegionRepository(),
            concept_name="Ciberseguridad",
            region_code="99",
            window=WEEK,
        )


@pytest.mark.parametrize(
    ("answer", "expected"),
    [("si", True), (" SI ", True), ("no", False), ("", False), ("sí", False)],
)
def test_solo_un_si_explicito_confirma(answer: str, expected: bool) -> None:
    assert confirmed(lambda _prompt: answer) is expected


async def test_ejecuta_registra_creditos_y_quien_la_pidio() -> None:
    provider = FakeProvider(response())
    log = FakeLog()
    plan = await plan_for(provider)

    result = await execute(provider=provider, plan=plan, log=log, actor=Actor("benji"))

    assert result is not None and len(provider.sent) == 1
    [(record, actor)] = log.records
    assert (record.status, record.results_count, record.cost_credits) == ("ok", 1, 1)
    assert actor == Actor("benji")


async def test_un_error_del_proveedor_se_registra_sin_cobrar() -> None:
    provider = FakeProvider(error=ProviderRateLimitError("más despacio", provider="searchapi"))
    log = FakeLog()

    result = await execute(
        provider=provider, plan=await plan_for(provider), log=log, actor=Actor("x")
    )

    assert result is None
    [(record, _)] = log.records
    assert (record.status, record.cost_credits, record.error_message) == (
        "error",
        0,
        "más despacio",
    )


def test_el_fixture_se_guarda_sin_la_llave(tmp_path: Path) -> None:
    body = f'{{"search_metadata": {{"request_url": "https://x/?api_key={SECRET}"}}}}'
    query = PlannedQuery(
        provider=Provider.SEARCHAPI,
        text="hackeo",
        keywords=("hackeo",),
        country=MEXICO_FILTER,
        language="es",
        window=WEEK,
        estimated_credits=1,
    )

    path = save_fixture(
        provider=Provider.SEARCHAPI,
        name="prueba",
        response=response(body),
        query=query,
        secret=SECRET,
        directory=tmp_path,
    )

    saved = path.read_text(encoding="utf-8") + (tmp_path / "searchapi_prueba.meta.json").read_text(
        encoding="utf-8"
    )
    assert SECRET not in saved
    assert "REDACTADO" in saved
    assert path.name == "searchapi_prueba.json"


def test_redact_sin_llave_no_cambia_nada() -> None:
    assert redact("texto", None) == "texto"


def test_redact_quita_cada_aparicion_de_la_llave() -> None:
    assert redact(f"a={SECRET}&b={SECRET}", SECRET) == "a=REDACTADO&b=REDACTADO"
    assert issubclass(LeakedSecretError, RuntimeError)
