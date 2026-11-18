"""Configuración compartida de pytest."""

import os

import pytest

# Las pruebas entran sin llave (AUTH_MODE=dev), aunque el .env de la máquina
# diga otra cosa; las del candado arman su propia configuración con keys.
# Va antes de cualquier import de la app: get_settings() se lee una sola vez.
os.environ["AUTH_MODE"] = "dev"
# Las pruebas nunca llaman a internet (CLAUDE.md §7): sin esto, la aplicación
# armada con create_app y una llave de SearchApi preguntaría su saldo real a
# GET /api/v1/me (ADR-0115). Las pruebas del saldo usan un MockTransport.
os.environ["SEARCHAPI_BALANCE_CHECK"] = "false"


@pytest.fixture
def anyio_backend() -> str:
    """Las pruebas asíncronas corren con asyncio, igual que uvicorn."""
    return "asyncio"
