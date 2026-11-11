"""Envíos en PostgreSQL (F12.11, ADR-0039).

Implementa ``DeliveryStorePort`` sobre las tablas de las migraciones 0035,
0037 y 0042: cuentas, destinatarios, la regla de cada fuente, guías de envío y
sus intentos. Destinatarios y guías tienen dueño y seguridad por filas: con
el engine de la API cada persona lee y escribe solo lo suyo (ADR-0045).

No hace: no manda nada ni decide reintentos (eso es del caso de uso).
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncEngine

from app.application.pagination import TimeCursor
from app.application.ports.deliveries import (
    AttemptRecord,
    Delivery,
    DeliveryAccount,
    DeliveryRule,
    NewDelivery,
    Recipient,
    RuleDraft,
)
from app.domain.deliveries import (
    DEFAULT_OWNER,
    AccountProvider,
    AccountStatus,
    DeliveryChannel,
    DeliveryStatus,
    RecipientDraft,
)
from app.domain.errors import DeliveryNotFoundError

_RULES_ALL = text(
    "SELECT id, source, channel, account_id, is_active FROM delivery_rules "
    "WHERE (CAST(:source AS text) IS NULL OR source = :source) ORDER BY id"
)
_RULES_ACTIVE = text(
    "SELECT id, source, channel, account_id, is_active FROM delivery_rules "
    "WHERE (CAST(:source AS text) IS NULL OR source = :source) AND is_active ORDER BY id"
)
# Una regla por fuente y canal (índice único delivery_rules_source_channel).
_SAVE_RULE = text(
    "INSERT INTO delivery_rules (source, channel, account_id, is_active) "
    "VALUES (:source, :channel, :account_id, :active) "
    "ON CONFLICT (source, channel) DO UPDATE SET account_id = EXCLUDED.account_id, "
    "is_active = EXCLUDED.is_active, updated_at = now() "
    "RETURNING id, source, channel, account_id, is_active"
)
_DELIVERY_SELECT = """
    SELECT d.id, d.rule_id, d.source, d.source_ref, d.channel, d.account_id, d.recipient_id,
           r.name AS recipient_name, d.destination, d.subject, d.attachment_name, d.status,
           d.attempts, d.last_error, d.provider_ref, d.is_test, d.created_at, d.sent_at,
           d.next_attempt_at, d.scheduled_for, d.owner
    FROM deliveries d LEFT JOIN delivery_recipients r ON r.id = d.recipient_id
"""


def _account(row: Row) -> DeliveryAccount:
    return DeliveryAccount(
        row.id,
        AccountProvider(row.provider),
        row.label,
        row.address,
        row.external_id,
        AccountStatus(row.status),
    )


def _recipient(row: Row) -> Recipient:
    return Recipient(
        row.id,
        RecipientDraft(row.name, row.email, row.phone, row.is_active, tuple(row.hours or ())),
        row.owner,
    )


def _rule(row: Row) -> DeliveryRule:
    return DeliveryRule(
        row.id,
        RuleDraft(
            source=row.source,
            channel=DeliveryChannel(row.channel),
            account_id=row.account_id,
            is_active=row.is_active,
        ),
    )


def _delivery(row: Row) -> Delivery:
    return Delivery(
        id=row.id,
        rule_id=row.rule_id,
        source=row.source,
        source_ref=row.source_ref,
        channel=DeliveryChannel(row.channel),
        account_id=row.account_id,
        recipient_id=row.recipient_id,
        recipient_name=row.recipient_name,
        destination=row.destination,
        subject=row.subject,
        attachment_name=row.attachment_name,
        status=DeliveryStatus(row.status),
        attempts=row.attempts,
        last_error=row.last_error,
        provider_ref=row.provider_ref,
        is_test=row.is_test,
        created_at=row.created_at,
        sent_at=row.sent_at,
        next_attempt_at=row.next_attempt_at,
        scheduled_for=row.scheduled_for,
        owner=row.owner,
    )


class PostgresDeliveryStore:
    """``DeliveryStorePort`` en PostgreSQL."""

    def __init__(self, engine: AsyncEngine) -> None:
        """Recibe el motor de la base.

        Args:
            engine: Motor asíncrono de SQLAlchemy.
        """
        self._engine = engine

    # --- Cuentas ---

    async def list_accounts(self) -> list[DeliveryAccount]:
        """Ver ``DeliveryStorePort.list_accounts``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id, provider, label, address, external_id, status FROM "
                    "delivery_accounts ORDER BY id"
                )
            )
            return [_account(r) for r in rows]

    async def get_account(self, account_id: int) -> DeliveryAccount | None:
        """Ver ``DeliveryStorePort.get_account``."""
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT id, provider, label, address, external_id, status FROM "
                        "delivery_accounts WHERE id = :id"
                    ),
                    {"id": account_id},
                )
            ).first()
        return _account(row) if row else None

    async def save_account(
        self,
        provider: AccountProvider,
        label: str,
        external_id: str | None,
        status: AccountStatus,
        address: str | None = None,
    ) -> DeliveryAccount:
        """Ver ``DeliveryStorePort.save_account``."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "INSERT INTO delivery_accounts (provider, label, external_id, status, "
                        "address) "
                        "VALUES (:provider, :label, :external_id, :status, :address) "
                        "ON CONFLICT (external_id) DO UPDATE SET label = EXCLUDED.label, "
                        "status = EXCLUDED.status, updated_at = now() "
                        "RETURNING id, provider, label, address, external_id, status"
                    ),
                    {
                        "provider": provider.value,
                        "label": label,
                        "external_id": external_id,
                        "status": status.value,
                        "address": address,
                    },
                )
            ).one()
        return _account(row)

    async def update_account(
        self, account_id: int, status: AccountStatus, address: str | None
    ) -> DeliveryAccount:
        """Ver ``DeliveryStorePort.update_account``."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "UPDATE delivery_accounts SET status = :status, address = :address, "
                        "updated_at = now() WHERE id = :id RETURNING id, provider, label, address, "
                        "external_id, status"
                    ),
                    {"id": account_id, "status": status.value, "address": address},
                )
            ).first()
        if row is None:
            raise DeliveryNotFoundError("No existe esa cuenta de envío.", {"id": account_id})
        return _account(row)

    # --- Destinatarios ---

    async def list_recipients(self) -> list[Recipient]:
        """Ver ``DeliveryStorePort.list_recipients``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id, name, email, phone, is_active, hours, owner "
                    "FROM delivery_recipients "
                    "ORDER BY name, id"
                )
            )
            return [_recipient(r) for r in rows]

    async def get_recipient(self, recipient_id: int) -> Recipient | None:
        """Ver ``DeliveryStorePort.get_recipient``."""
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT id, name, email, phone, is_active, hours, owner "
                        "FROM delivery_recipients "
                        "WHERE id = :id"
                    ),
                    {"id": recipient_id},
                )
            ).first()
        return _recipient(row) if row else None

    async def create_recipient(self, data: RecipientDraft, owner: str) -> Recipient:
        """Ver ``DeliveryStorePort.create_recipient``."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "INSERT INTO delivery_recipients (name, email, phone, is_active, hours, "
                        "owner) VALUES (:name, :email, :phone, :active, "
                        "CAST(:hours AS smallint[]), :owner) "
                        "RETURNING id, name, email, phone, is_active, hours, owner"
                    ),
                    {
                        "name": data.name,
                        "email": data.email,
                        "phone": data.phone,
                        "active": data.is_active,
                        "hours": list(data.hours),
                        "owner": owner,
                    },
                )
            ).one()
        return _recipient(row)

    async def update_recipient(self, recipient_id: int, data: RecipientDraft) -> Recipient:
        """Ver ``DeliveryStorePort.update_recipient``."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "UPDATE delivery_recipients SET name = :name, email = :email, "
                        "phone = :phone, is_active = :active, "
                        "hours = CAST(:hours AS smallint[]), updated_at = now() "
                        "WHERE id = :id RETURNING id, name, email, phone, is_active, hours, owner"
                    ),
                    {
                        "id": recipient_id,
                        "name": data.name,
                        "email": data.email,
                        "phone": data.phone,
                        "active": data.is_active,
                        "hours": list(data.hours),
                    },
                )
            ).first()
        if row is None:
            raise DeliveryNotFoundError("No existe ese destinatario.", {"id": recipient_id})
        return _recipient(row)

    # --- Reglas ---

    async def list_rules(
        self, source: str | None = None, active_only: bool = False
    ) -> list[DeliveryRule]:
        """Ver ``DeliveryStorePort.list_rules``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                _RULES_ACTIVE if active_only else _RULES_ALL, {"source": source}
            )
            return [_rule(r) for r in rows]

    async def save_rule(self, data: RuleDraft) -> DeliveryRule:
        """Ver ``DeliveryStorePort.save_rule``."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    _SAVE_RULE,
                    {
                        "source": data.source,
                        "channel": data.channel.value,
                        "account_id": data.account_id,
                        "active": data.is_active,
                    },
                )
            ).one()
        return _rule(row)

    async def delete_recipient(self, recipient_id: int) -> bool:
        """Ver ``DeliveryStorePort.delete_recipient``."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    text("DELETE FROM delivery_recipients WHERE id = :id RETURNING id"),
                    {"id": recipient_id},
                )
            ).first()
        return row is not None

    # --- Guías de envío ---

    async def create_deliveries(self, deliveries: Sequence[NewDelivery]) -> list[UUID]:
        """Ver ``DeliveryStorePort.create_deliveries``."""
        created: list[UUID] = []
        async with self._engine.begin() as conn:
            for d in deliveries:
                row = (
                    await conn.execute(
                        text(
                            "INSERT INTO deliveries (id, rule_id, source, source_ref, channel, "
                            "account_id, recipient_id, destination, subject, attachment_name, "
                            "idempotency_key, is_test, scheduled_for, next_attempt_at, owner) "
                            "VALUES (:id, :rule_id, "
                            ":source, :source_ref, :channel, :account_id, :recipient_id, "
                            ":destination, :subject, :attachment, :key, :is_test, :scheduled_for, "
                            "now(), COALESCE(CAST(:owner AS text), (SELECT r.owner FROM "
                            "delivery_recipients r WHERE r.id = :recipient_id), :default_owner)) "
                            "ON CONFLICT (idempotency_key) DO NOTHING RETURNING id"
                        ),
                        {
                            "id": d.id,
                            "rule_id": d.rule_id,
                            "source": d.source,
                            "source_ref": d.source_ref,
                            "channel": d.channel.value,
                            "account_id": d.account_id,
                            "recipient_id": d.recipient_id,
                            "destination": d.destination,
                            "subject": d.subject,
                            "attachment": d.attachment_name,
                            "key": d.idempotency_key,
                            "is_test": d.is_test,
                            "scheduled_for": d.scheduled_for,
                            "owner": d.owner,
                            "default_owner": DEFAULT_OWNER,
                        },
                    )
                ).first()
                if row is not None:
                    created.append(row.id)
        return created

    async def get_delivery(self, delivery_id: UUID) -> Delivery | None:
        """Ver ``DeliveryStorePort.get_delivery``."""
        async with self._engine.connect() as conn:
            row = (
                await conn.execute(
                    text(_DELIVERY_SELECT + " WHERE d.id = :id"), {"id": delivery_id}
                )
            ).first()
        return _delivery(row) if row else None

    async def due_deliveries(self, now: datetime, limit: int) -> list[Delivery]:
        """Ver ``DeliveryStorePort.due_deliveries``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(
                    _DELIVERY_SELECT + " WHERE d.status = 'pending' AND d.next_attempt_at <= :now "
                    "ORDER BY d.next_attempt_at, d.id LIMIT :limit"
                ),
                {"now": now, "limit": limit},
            )
            return [_delivery(r) for r in rows]

    async def claim(self, delivery_id: UUID) -> bool:
        """Ver ``DeliveryStorePort.claim``."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "UPDATE deliveries SET status = 'sending', updated_at = now() "
                        "WHERE id = :id AND status = 'pending' RETURNING id"
                    ),
                    {"id": delivery_id},
                )
            ).first()
        return row is not None

    async def record_attempt(
        self,
        attempt: AttemptRecord,
        status: DeliveryStatus,
        next_attempt_at: datetime | None,
        provider_ref: str | None,
    ) -> None:
        """Ver ``DeliveryStorePort.record_attempt``."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO delivery_attempts (delivery_id, attempt, ok, provider_status, "
                    "error, started_at, finished_at) VALUES (:id, :attempt, :ok, :provider_status, "
                    ":error, :started, :finished)"
                ),
                {
                    "id": attempt.delivery_id,
                    "attempt": attempt.attempt,
                    "ok": attempt.ok,
                    "provider_status": attempt.provider_status,
                    "error": attempt.error,
                    "started": attempt.started_at,
                    "finished": attempt.finished_at,
                },
            )
            await conn.execute(
                text(
                    "UPDATE deliveries SET status = :status, attempts = :attempt, "
                    "last_error = :error, provider_ref = COALESCE(:ref, provider_ref), "
                    "next_attempt_at = :next, "
                    "sent_at = CASE WHEN CAST(:status AS text) = 'sent' THEN :finished ELSE "
                    "sent_at END, "
                    "updated_at = now() WHERE id = :id"
                ),
                {
                    "id": attempt.delivery_id,
                    "status": status.value,
                    "attempt": attempt.attempt,
                    "error": None if attempt.ok else attempt.error,
                    "ref": provider_ref,
                    "next": next_attempt_at,
                    "finished": attempt.finished_at,
                },
            )

    async def reset_for_retry(self, delivery_id: UUID, now: datetime) -> bool:
        """Ver ``DeliveryStorePort.reset_for_retry``."""
        async with self._engine.begin() as conn:
            row = (
                await conn.execute(
                    text(
                        "UPDATE deliveries SET status = 'pending', next_attempt_at = :now, "
                        "updated_at = now() WHERE id = :id AND status IN ('failed', 'skipped') "
                        "RETURNING id"
                    ),
                    {"id": delivery_id, "now": now},
                )
            ).first()
        return row is not None

    async def history(self, after: TimeCursor | None, limit: int) -> list[Delivery]:
        """Ver ``DeliveryStorePort.history``."""
        where = ""
        params: dict[str, object] = {"limit": limit}
        if after is not None:
            where = " WHERE (d.created_at, d.id) < (:moment, CAST(:after_id AS uuid))"
            params |= {"moment": after.moment, "after_id": after.id}
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(
                    _DELIVERY_SELECT + where + " ORDER BY d.created_at DESC, d.id DESC LIMIT :limit"
                ),
                params,
            )
            return [_delivery(r) for r in rows]

    async def attempts_of(self, delivery_id: UUID) -> list[AttemptRecord]:
        """Ver ``DeliveryStorePort.attempts_of``."""
        async with self._engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT delivery_id, attempt, ok, provider_status, error, started_at, "
                    "finished_at FROM delivery_attempts WHERE delivery_id = :id ORDER BY attempt, "
                    "id"
                ),
                {"id": delivery_id},
            )
            return [
                AttemptRecord(
                    r.delivery_id,
                    r.attempt,
                    r.ok,
                    r.provider_status,
                    r.error,
                    r.started_at,
                    r.finished_at,
                )
                for r in rows
            ]
