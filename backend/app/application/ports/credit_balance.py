"""Puerto del saldo real de la cuenta de un proveedor de pago (ADR-0115).

El tope mensual local (``SEARCHAPI_MONTHLY_CREDIT_LIMIT``) cuenta lo que
gastó este sistema; el saldo real de la cuenta lo sabe solo el proveedor (la
cuenta de prueba de Benji tenía 46 créditos que no se renuevan, 18/11/2026).
``PlanSearch`` usa este puerto para no ofrecer ni lanzar Google web sin
saldo. La implementación está en
``app/adapters/providers/searchapi_account.py``.

No hace: no gasta créditos ni decide qué fuentes usar.
"""

from typing import Protocol


class CreditBalancePort(Protocol):
    """Lee cuántas búsquedas le quedan a la cuenta del proveedor."""

    async def remaining(self) -> int | None:
        """Búsquedas que le quedan a la cuenta.

        Returns:
            El saldo (0 si la llave fue rechazada), o ``None`` si no se pudo
            saber; entonces se usa el tope mensual local.
        """
        ...
