"""Endpoint ``GET /api/v1/health``: estado de la API, base de datos, Redis y worker.

Responde 200 si todo está bien y 503 si algún componente falla, para que
herramientas de monitoreo (y nginx más adelante) lo detecten sin leer el JSON.

No hace: no revisa nada por su cuenta; delega en ``CheckSystemHealth``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.v1.schemas.health import HealthOut
from app.application.use_cases.check_health import CheckSystemHealth

router = APIRouter(tags=["diagnóstico"])


def get_check_health(request: Request) -> CheckSystemHealth:
    """Obtiene el caso de uso armado al arrancar la aplicación.

    Es una dependencia de FastAPI: las pruebas la reemplazan con
    ``app.dependency_overrides`` para no necesitar servicios reales.

    Args:
        request: Petición actual (da acceso a ``app.state``).

    Returns:
        El caso de uso compartido.
    """
    use_case: CheckSystemHealth = request.app.state.check_health
    return use_case


@router.get(
    "/health",
    response_model=HealthOut,
    summary="Estado del sistema",
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthOut}},
)
async def health(
    response: Response,
    check_health: Annotated[CheckSystemHealth, Depends(get_check_health)],
) -> HealthOut:
    """Revisa todos los componentes y devuelve su estado."""
    result = await check_health.execute()
    if not result.is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthOut.from_domain(result)
