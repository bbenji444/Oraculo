"""Configuración pública que necesita la pantalla (``/app-config``).

Solo datos que el navegador puede ver: la dirección del sistema principal de
Oráculo para el botón de regresar (``ORACULO_URL``) y si la pantalla se abrió
por el gateway de Oráculo (ADR-0119), para que no ofrezca entrar con usuario
y contraseña cuando el acceso lo da Oráculo.

No hace: nunca entrega llaves ni contraseñas (esas no salen del servidor).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.api.auth import via_gateway
from app.api.errors import ERROR_RESPONSES

router = APIRouter(prefix="/app-config", tags=["diagnóstico"], responses=ERROR_RESPONSES)


class AppConfigOut(BaseModel):
    """Lo que la pantalla necesita saber del servidor."""

    oraculo_url: str | None = Field(
        description="Sistema principal de Oráculo; sin valor, no hay botón para regresar.",
        examples=["http://172.25.18.234"],
    )
    via_gateway: bool = Field(
        default=False,
        description=(
            "Si esta petición llegó por el gateway de Oráculo (/m/noticias/). "
            "Entonces el acceso lo da Oráculo y la pantalla no pide usuario ni contraseña."
        ),
    )


def get_app_config(request: Request) -> AppConfigOut:
    """La configuración pública, armada al arrancar la API."""
    config: AppConfigOut = request.app.state.app_config
    return config


@router.get("", response_model=AppConfigOut, summary="Configuración pública de la pantalla")
async def app_config(
    request: Request, config: Annotated[AppConfigOut, Depends(get_app_config)]
) -> AppConfigOut:
    """Datos públicos para la pantalla, como la dirección de Oráculo."""
    return config.model_copy(update={"via_gateway": via_gateway(request)})
