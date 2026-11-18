"""Saldo real de la cuenta de SearchApi (``GET /api/v1/me``, ADR-0115), sin red.

El cuerpo de ejemplo es el de la documentación
(https://www.searchapi.io/docs/account-api, consultada el 18/11/2026).
"""

import json

import httpx2
import pytest
from pydantic import SecretStr

from app.adapters.providers.http import ProviderHttpClient
from app.adapters.providers.searchapi_account import (
    ACCOUNT_URL,
    BALANCE_CACHE_SECONDS,
    BALANCE_RETRY_SECONDS,
    SearchApiBalance,
    build_searchapi_balance,
)
from app.core.config import Settings
from app.domain.queries import Provider

pytestmark = pytest.mark.anyio

# Ejemplo de la documentación: remaining_searches = lo que queda del plan del
# mes + remaining_credits.
DOCUMENTED = {
    "account": {
        "current_month_usage": 4800,
        "monthly_allowance": 10000,
        "remaining_credits": 0,
        "remaining_searches": 5200,
        "has_automatic_early_renewal_enabled": True,
    },
    "api_usage": {"searches_this_hour": 250, "hourly_rate_limit": 200000},
}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Answers:
    """Responde a ``/me`` con la lista de respuestas, en orden, y cuenta las llamadas."""

    def __init__(self, *responses: httpx2.Response) -> None:
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return self.responses.pop(0)


def balance(answers: Answers, clock: Clock | None = None) -> SearchApiBalance:
    http = ProviderHttpClient(
        Provider.SEARCHAPI,
        timeout_seconds=5,
        max_attempts=1,
        max_concurrency=1,
        headers={"Authorization": "Bearer llave-de-prueba"},
        transport=httpx2.MockTransport(answers),
    )
    return SearchApiBalance(http, clock=clock or Clock())


def ok(body: object) -> httpx2.Response:
    return httpx2.Response(200, text=json.dumps(body))


async def test_lee_las_busquedas_que_le_quedan_a_la_cuenta() -> None:
    answers = Answers(ok(DOCUMENTED))

    assert await balance(answers).remaining() == 5200
    [sent] = answers.requests
    assert str(sent.url) == ACCOUNT_URL
    assert sent.headers["Authorization"] == "Bearer llave-de-prueba"
    assert "llave-de-prueba" not in str(sent.url)


async def test_sin_remaining_searches_usa_los_creditos() -> None:
    # La cuenta de prueba de Benji: 46 créditos que no se renuevan (18/11/2026).
    answers = Answers(ok({"account": {"remaining_credits": 46}}))

    assert await balance(answers).remaining() == 46


async def test_guarda_el_saldo_unos_minutos_para_no_preguntar_en_cada_pantalla() -> None:
    clock = Clock()
    answers = Answers(ok(DOCUMENTED), ok({"account": {"remaining_searches": 5199}}))
    account = balance(answers, clock)

    assert await account.remaining() == 5200
    clock.now += BALANCE_CACHE_SECONDS - 1
    assert await account.remaining() == 5200
    assert len(answers.requests) == 1
    clock.now += 2
    assert await account.remaining() == 5199
    assert len(answers.requests) == 2


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(503),
        httpx2.Response(200, text="<html>"),
        ok({"account": {}}),
        ok({"account": {"remaining_searches": "muchas"}}),
        ok(["no", "es", "objeto"]),
    ],
)
async def test_si_no_se_puede_saber_devuelve_none(response: httpx2.Response) -> None:
    assert await balance(Answers(response)).remaining() is None


async def test_si_falla_vuelve_a_preguntar_mas_pronto() -> None:
    clock = Clock()
    answers = Answers(httpx2.Response(503), ok(DOCUMENTED))
    account = balance(answers, clock)

    assert await account.remaining() is None
    clock.now += BALANCE_RETRY_SECONDS - 1
    assert await account.remaining() is None
    clock.now += 2
    assert await account.remaining() == 5200
    assert len(answers.requests) == 2


@pytest.mark.parametrize("status", [401, 403])
async def test_llave_rechazada_es_cero(status: int) -> None:
    # Con la llave rechazada ninguna búsqueda pasaría: no hay qué gastar.
    assert await balance(Answers(httpx2.Response(status))).remaining() == 0


async def test_un_saldo_negativo_cuenta_como_cero() -> None:
    assert await balance(Answers(ok({"account": {"remaining_searches": -3}}))).remaining() == 0


def test_solo_se_arma_con_llave_y_con_la_revision_encendida() -> None:
    def settings(key: str | None, *, check: bool = True) -> Settings:
        return Settings.model_construct(
            searchapi_api_key=SecretStr(key) if key is not None else None,
            searchapi_balance_check=check,
        )

    assert build_searchapi_balance(settings("llave")) is not None
    assert build_searchapi_balance(settings(None)) is None
    assert build_searchapi_balance(settings("")) is None
    assert build_searchapi_balance(settings("llave", check=False)) is None
