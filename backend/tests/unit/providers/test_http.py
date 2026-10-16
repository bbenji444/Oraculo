"""Cliente HTTP compartido: reintentos, errores de dominio y ritmo (sin red)."""

from collections.abc import Callable

import httpx2
import pytest

from app.adapters.providers.http import ProviderHttpClient
from app.domain.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderUnavailableError,
)
from app.domain.queries import Provider

pytestmark = pytest.mark.anyio

URL = "https://proveedor.example/api"


class Recorder:
    """Responde con una lista de respuestas en orden y cuenta las llamadas."""

    def __init__(self, *responses: httpx2.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(
    recorder: Callable[[httpx2.Request], httpx2.Response],
    *,
    sleeps: list[float] | None = None,
    min_interval: float = 0.0,
    rate_limit_wait: float = 0.0,
) -> ProviderHttpClient:
    async def fake_sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return ProviderHttpClient(
        Provider.GDELT,
        timeout_seconds=5,
        max_attempts=3,
        max_concurrency=2,
        min_interval_seconds=min_interval,
        rate_limit_wait_seconds=rate_limit_wait,
        headers={"Authorization": "Bearer secreta"},
        transport=httpx2.MockTransport(recorder),
        sleep=fake_sleep,
    )


async def test_envia_parametros_y_encabezados() -> None:
    recorder = Recorder(httpx2.Response(200, text="ok"))

    response = await client(recorder).get(URL, {"q": "hackeo CDMX"})

    assert response.text == "ok"
    sent = recorder.requests[0]
    assert sent.url.params["q"] == "hackeo CDMX"
    assert sent.headers["Authorization"] == "Bearer secreta"
    # Se presenta con nombre propio, no como "python-httpx2".
    assert sent.headers["User-Agent"].startswith("monitor-noticias/")


async def test_reintenta_un_500_con_espera_creciente_y_luego_responde() -> None:
    sleeps: list[float] = []
    recorder = Recorder(httpx2.Response(503), httpx2.Response(502), httpx2.Response(200))

    response = await client(recorder, sleeps=sleeps).get(URL, {})

    assert response.status_code == 200
    assert len(recorder.requests) == 3
    assert sleeps == [1.0, 2.0]


async def test_reintenta_un_429_y_al_agotar_intentos_lanza_el_error() -> None:
    recorder = Recorder(*(httpx2.Response(429) for _ in range(3)))

    with pytest.raises(ProviderRateLimitError, match="más despacio"):
        await client(recorder).get(URL, {})
    assert len(recorder.requests) == 3


async def test_tras_un_429_espera_al_menos_lo_configurado_y_conserva_el_aviso() -> None:
    sleeps: list[float] = []
    aviso = "Please limit requests to one every 5 seconds"
    recorder = Recorder(
        httpx2.Response(429, text=aviso), httpx2.Response(503), httpx2.Response(200)
    )

    await client(recorder, sleeps=sleeps, rate_limit_wait=15.0).get(URL, {})

    # Tras el 429 espera 15 s; tras el 503, la espera normal (2 s).
    assert sleeps == [15.0, 2.0]


async def test_el_mensaje_del_429_incluye_el_texto_del_proveedor() -> None:
    recorder = Recorder(*(httpx2.Response(429, text="one every 5 seconds") for _ in range(3)))

    with pytest.raises(ProviderRateLimitError, match="one every 5 seconds"):
        await client(recorder).get(URL, {})


@pytest.mark.parametrize("status", [401, 403])
async def test_llave_rechazada_no_se_reintenta(status: int) -> None:
    recorder = Recorder(httpx2.Response(status))

    with pytest.raises(ProviderAuthError) as error:
        await client(recorder).get(URL, {})
    assert len(recorder.requests) == 1
    assert error.value.http_status == status


async def test_otro_4xx_no_se_reintenta_y_conserva_parte_del_cuerpo() -> None:
    recorder = Recorder(httpx2.Response(400, text="Your query was too short"))

    with pytest.raises(ProviderResponseError, match="too short"):
        await client(recorder).get(URL, {})
    assert len(recorder.requests) == 1


async def test_tiempo_agotado_y_red_caida_se_traducen_y_reintentan() -> None:
    request = httpx2.Request("GET", URL)
    recorder = Recorder(
        httpx2.ReadTimeout("lento", request=request),
        httpx2.ConnectError("sin red", request=request),
        httpx2.ConnectError("sin red", request=request),
    )

    with pytest.raises(ProviderUnavailableError, match="No se pudo conectar"):
        await client(recorder).get(URL, {})
    assert len(recorder.requests) == 3


async def test_respeta_la_pausa_minima_entre_peticiones() -> None:
    sleeps: list[float] = []
    recorder = Recorder(httpx2.Response(200), httpx2.Response(200))
    http = client(recorder, sleeps=sleeps, min_interval=5.0)

    await http.get(URL, {})
    await http.get(URL, {})

    # La primera sale de inmediato; la segunda espera casi los 5 s completos.
    assert len(sleeps) == 1
    assert 4.5 < sleeps[0] <= 5.0
    await http.aclose()
