"""Configuración compartida de pytest."""

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Las pruebas asíncronas corren con asyncio, igual que uvicorn."""
    return "asyncio"
