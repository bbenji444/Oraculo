"""Piezas en memoria para probar los envíos sin base, sin Composio y sin internet."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from app.application.pagination import TimeCursor
from app.application.ports.deliveries import (
    AttemptRecord,
    ConnectionStart,
    Delivery,
    DeliveryAccount,
    DeliveryRule,
    NewDelivery,
    OutgoingMessage,
    Recipient,
    RemoteAccount,
    ReportContent,
    RuleDraft,
    SendResult,
)
from app.domain.deliveries import (
    AccountProvider,
    AccountStatus,
    DeliveryStatus,
    RecipientDraft,
)

NOW = datetime(2026, 11, 7, 13, 5, tzinfo=UTC)


class FakeDeliveryStore:
    """``DeliveryStorePort`` en diccionarios."""

    def __init__(self) -> None:
        self.accounts: dict[int, DeliveryAccount] = {}
        self.recipients: dict[int, Recipient] = {}
        self.rules: dict[int, DeliveryRule] = {}
        self.deliveries: dict[UUID, Delivery] = {}
        self.keys: set[str] = set()
        self.attempts: list[AttemptRecord] = []

    async def list_accounts(self) -> list[DeliveryAccount]:
        return list(self.accounts.values())

    async def get_account(self, account_id: int) -> DeliveryAccount | None:
        return self.accounts.get(account_id)

    async def save_account(
        self,
        provider: AccountProvider,
        label: str,
        external_id: str | None,
        status: AccountStatus,
        address: str | None = None,
    ) -> DeliveryAccount:
        account = DeliveryAccount(
            len(self.accounts) + 1, provider, label, address, external_id, status
        )
        self.accounts[account.id] = account
        return account

    async def update_account(
        self, account_id: int, status: AccountStatus, address: str | None
    ) -> DeliveryAccount:
        account = replace(self.accounts[account_id], status=status, address=address)
        self.accounts[account_id] = account
        return account

    async def list_recipients(self) -> list[Recipient]:
        return list(self.recipients.values())

    async def get_recipient(self, recipient_id: int) -> Recipient | None:
        return self.recipients.get(recipient_id)

    async def create_recipient(self, data: RecipientDraft) -> Recipient:
        recipient = Recipient(len(self.recipients) + 1, data)
        self.recipients[recipient.id] = recipient
        return recipient

    async def update_recipient(self, recipient_id: int, data: RecipientDraft) -> Recipient:
        self.recipients[recipient_id] = Recipient(recipient_id, data)
        return self.recipients[recipient_id]

    async def delete_recipient(self, recipient_id: int) -> bool:
        return self.recipients.pop(recipient_id, None) is not None

    async def list_rules(
        self, source: str | None = None, active_only: bool = False
    ) -> list[DeliveryRule]:
        return [
            r
            for r in self.rules.values()
            if (source is None or r.data.source == source) and (r.data.is_active or not active_only)
        ]

    async def save_rule(self, data: RuleDraft) -> DeliveryRule:
        key = (data.source, data.channel)
        found = [r for r in self.rules.values() if key == (r.data.source, r.data.channel)]
        same = found[0] if found else None
        rule = DeliveryRule(same.id if same else len(self.rules) + 1, data)
        self.rules[rule.id] = rule
        return rule

    async def create_deliveries(self, deliveries: Sequence[NewDelivery]) -> list[UUID]:
        created = []
        for d in deliveries:
            if d.idempotency_key in self.keys:
                continue
            self.keys.add(d.idempotency_key)
            recipient = self.recipients.get(d.recipient_id or 0)
            self.deliveries[d.id] = Delivery(
                id=d.id,
                rule_id=d.rule_id,
                source=d.source,
                source_ref=d.source_ref,
                channel=d.channel,
                account_id=d.account_id,
                recipient_id=d.recipient_id,
                recipient_name=recipient.data.name if recipient else None,
                destination=d.destination,
                subject=d.subject,
                attachment_name=d.attachment_name,
                status=DeliveryStatus.PENDING,
                attempts=0,
                last_error=None,
                provider_ref=None,
                is_test=d.is_test,
                created_at=NOW,
                sent_at=None,
                next_attempt_at=NOW,
                scheduled_for=d.scheduled_for,
            )
            created.append(d.id)
        return created

    async def get_delivery(self, delivery_id: UUID) -> Delivery | None:
        return self.deliveries.get(delivery_id)

    async def due_deliveries(self, now: datetime, limit: int) -> list[Delivery]:
        due = [
            d
            for d in self.deliveries.values()
            if d.status is DeliveryStatus.PENDING and d.next_attempt_at and d.next_attempt_at <= now
        ]
        return due[:limit]

    async def claim(self, delivery_id: UUID) -> bool:
        d = self.deliveries[delivery_id]
        if d.status is not DeliveryStatus.PENDING:
            return False
        self.deliveries[delivery_id] = replace(d, status=DeliveryStatus.SENDING)
        return True

    async def record_attempt(
        self,
        attempt: AttemptRecord,
        status: DeliveryStatus,
        next_attempt_at: datetime | None,
        provider_ref: str | None,
    ) -> None:
        self.attempts.append(attempt)
        d = self.deliveries[attempt.delivery_id]
        self.deliveries[attempt.delivery_id] = replace(
            d,
            status=status,
            attempts=attempt.attempt,
            last_error=None if attempt.ok else attempt.error,
            provider_ref=provider_ref or d.provider_ref,
            next_attempt_at=next_attempt_at,
            sent_at=attempt.finished_at if status is DeliveryStatus.SENT else d.sent_at,
        )

    async def reset_for_retry(self, delivery_id: UUID, now: datetime) -> bool:
        d = self.deliveries[delivery_id]
        self.deliveries[delivery_id] = replace(
            d, status=DeliveryStatus.PENDING, next_attempt_at=now
        )
        return True

    async def history(self, after: TimeCursor | None, limit: int) -> list[Delivery]:
        return list(self.deliveries.values())[:limit]

    async def attempts_of(self, delivery_id: UUID) -> list[AttemptRecord]:
        return [a for a in self.attempts if a.delivery_id == delivery_id]


class FakeReports:
    """``ReportSourcePort`` con una sola corrida."""

    def __init__(self, ref: str | None = "corrida-1", pdf: Path | None = None) -> None:
        self.ref = ref
        self.pdf = pdf

    async def latest_ref(self, source: str) -> str | None:
        return self.ref

    async def content_for(self, source: str, source_ref: str) -> ReportContent | None:
        if source_ref != self.ref:
            return None
        return ReportContent(
            source_ref=source_ref,
            title="Reporte FGR · corrida de las 15:00",
            subject="Reporte FGR · corrida 06/11/2026, 15:00 (CDMX)",
            html_body="<p>Resumen</p>",
            pdf_path=self.pdf,
            slot_hour=15,
        )


class FakeSender:
    """Emisor que contesta lo que se le diga y recuerda lo que mandó."""

    def __init__(self, *results: SendResult, configured: bool = True) -> None:
        self.results = list(results) or [SendResult(True, "202")]
        self.configured = configured
        self.sent: list[OutgoingMessage] = []

    def is_configured(self) -> bool:
        return self.configured

    async def send(self, account: DeliveryAccount, message: OutgoingMessage) -> SendResult:
        self.sent.append(message)
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


class FakeConnector:
    """Conector de cuentas que siempre da el mismo link."""

    def __init__(self, configured: bool = True, remote: RemoteAccount | None = None) -> None:
        self.configured = configured
        self.remote = remote or RemoteAccount(AccountStatus.ACTIVE, "ovitech_22@hotmail.com")

    def is_configured(self) -> bool:
        return self.configured

    async def start(self, provider: AccountProvider, label: str) -> ConnectionStart:
        return ConnectionStart("ca_prueba", "https://connect.composio.dev/link/lk_prueba")

    async def check(self, provider: AccountProvider, external_id: str) -> RemoteAccount:
        return self.remote
