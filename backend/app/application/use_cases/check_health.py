"""Caso de uso: revisar la salud de todos los componentes del sistema.

Lo usa el endpoint ``GET /api/v1/health``. Revisa todos los componentes en
paralelo, con un límite de tiempo por componente, para que un servicio caído
o lento no deje colgada la revisión completa.

No hace: no decide el código HTTP ni el formato de la respuesta (eso es de la
API) y no sabe cómo se revisa cada componente (eso es de los adaptadores).
"""

import asyncio
import logging
import time
from collections.abc import Sequence

from app.application.ports.health import HealthProbePort
from app.domain.health import ComponentHealth, SystemHealth

logger = logging.getLogger(__name__)

# Milisegundos por segundo, para reportar latencias legibles.
_MS_PER_SECOND = 1000


class CheckSystemHealth:
    """Revisa en paralelo cada componente y arma el estado del sistema.

    Example:
        >>> use_case = CheckSystemHealth([db_probe, redis_probe], timeout_seconds=2.0)
        >>> health = await use_case.execute()
        >>> health.status
        <SystemStatus.OK: 'ok'>
    """

    def __init__(self, probes: Sequence[HealthProbePort], timeout_seconds: float) -> None:
        """Prepara el caso de uso.

        Args:
            probes: Revisores de cada componente, en el orden en que deben
                aparecer en la respuesta.
            timeout_seconds: Tiempo máximo que se espera a cada componente.

        Raises:
            ValueError: Si ``timeout_seconds`` no es positivo.
        """
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds debe ser mayor que cero")
        self._probes = tuple(probes)
        self._timeout_seconds = timeout_seconds

    async def execute(self) -> SystemHealth:
        """Revisa todos los componentes.

        Returns:
            El estado de cada componente y el estado agregado. Nunca lanza
            excepciones por un componente fallido: lo reporta como error.
        """
        results = await asyncio.gather(*(self._check_one(probe) for probe in self._probes))
        return SystemHealth(components=tuple(results))

    async def _check_one(self, probe: HealthProbePort) -> ComponentHealth:
        """Revisa un componente aplicando el límite de tiempo y midiendo latencia."""
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(probe.check(), timeout=self._timeout_seconds)
        except TimeoutError:
            result = ComponentHealth.error(
                probe.name,
                f"No respondió en {self._timeout_seconds:g} segundos.",
            )
        except Exception as exc:
            # Cualquier fallo inesperado de un adaptador se reporta como error
            # del componente: /health debe responder siempre, aunque algo falle.
            logger.warning(
                "Falla inesperada al revisar un componente",
                extra={"component": probe.name, "error_type": type(exc).__name__},
            )
            result = ComponentHealth.error(probe.name, f"Error inesperado: {type(exc).__name__}")
        elapsed_ms = (time.perf_counter() - started) * _MS_PER_SECOND
        return result.with_latency(round(elapsed_ms, 1))
