"""Armado del pipeline con piezas reales (sin abrir conexiones ni gastar)."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr

from app.adapters.llm.factory import MissingLLMKeyError
from app.application.use_cases.run_search import RunSearch, SearchReport
from app.core.config import Settings
from app.domain.queries import Provider
from app.domain.search import SearchStatus
from app.worker import search_jobs

pytestmark = pytest.mark.anyio


def settings(**changes: Any) -> Settings:
    return Settings().model_copy(
        update={"llm_provider": "openai", "openai_api_key": SecretStr("x"), **changes}
    )


async def test_arma_el_pipeline_y_cierra_todo_al_salir() -> None:
    # Ni el engine ni Redis se conectan hasta usarse: aquí no se usa ninguno.
    async with search_jobs.search_pipeline(settings()) as (use_case, llm, _engine):
        assert isinstance(use_case, RunSearch)
        assert llm.provider == "openai"
        assert Provider.LOCAL_INDEX in use_case.available_providers()


async def test_las_busquedas_usan_google_news_rss_si_esta_encendido() -> None:
    # Bug (F12.2): desde el ADR-0021 el RSS está encendido por defecto, pero la
    # lista de proveedores de las búsquedas nunca lo incluyó y no se consultaba.
    async with search_jobs.search_pipeline(settings(news_rss_enabled=True)) as (use_case, _l, _e):
        assert Provider.GOOGLE_NEWS_RSS in use_case.available_providers()
    async with search_jobs.search_pipeline(settings(news_rss_enabled=False)) as (use_case, _l, _e):
        assert Provider.GOOGLE_NEWS_RSS not in use_case.available_providers()


async def test_sin_llave_de_la_ia_no_arma_nada() -> None:
    with pytest.raises(MissingLLMKeyError):
        async with search_jobs.search_pipeline(settings(openai_api_key=None)):
            pass  # pragma: no cover — no se llega aquí


class FakeStore:
    failed: ClassVar[list[tuple[UUID, str]]] = []

    def __init__(self, _engine: object) -> None:
        pass

    async def fail(self, search_id: UUID, message: str) -> None:
        self.failed.append((search_id, message))


def fake_pipeline(behavior: Callable[[UUID], SearchReport]) -> Any:
    class UseCase:
        async def run(self, search_id: UUID) -> SearchReport:
            return behavior(search_id)

    @asynccontextmanager
    async def pipeline(*_args: Any) -> AsyncIterator[tuple[Any, None, object]]:
        yield UseCase(), None, object()

    return pipeline


async def test_un_error_inesperado_deja_la_busqueda_en_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_id: UUID) -> SearchReport:
        raise RuntimeError("se cayó la base")

    monkeypatch.setattr(search_jobs, "search_pipeline", fake_pipeline(boom))
    monkeypatch.setattr(search_jobs, "PostgresSearchStore", FakeStore)
    search_id = uuid4()

    with pytest.raises(RuntimeError):
        await search_jobs.run_search_job(settings(), search_id)

    assert FakeStore.failed == [(search_id, "Error inesperado (RuntimeError): se cayó la base")]


async def test_una_busqueda_normal_devuelve_su_resumen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        search_jobs,
        "search_pipeline",
        fake_pipeline(lambda search_id: SearchReport(search_id, SearchStatus.COMPLETED)),
    )
    search_id = uuid4()

    report = await search_jobs.run_search_job(settings(), search_id)

    assert report == SearchReport(search_id, SearchStatus.COMPLETED)


async def test_la_purga_de_textos_usa_la_retencion(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[int] = []

    class Articles:
        def __init__(self, _engine: object) -> None:
            pass

        async def purge_texts(self, days: int) -> int:
            asked.append(days)
            return 3

    monkeypatch.setattr(search_jobs, "PostgresArticleStore", Articles)

    assert await search_jobs.purge_article_texts(settings(article_text_retention_days=30)) == 3
    assert asked == [30]
