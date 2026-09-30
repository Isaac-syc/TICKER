"""Objetos de lectura (read models) y parámetros de consulta que cruzan la frontera de la app."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from helpdesk.domain.tickets.entities import TicketEventType
from helpdesk.domain.tickets.workflow import Priority, TicketStatus


@dataclass(frozen=True)
class PageRequest:
    page: int = 1
    page_size: int = 20

    def __post_init__(self) -> None:
        object.__setattr__(self, "page", max(1, self.page))
        object.__setattr__(self, "page_size", min(max(1, self.page_size), 100))

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


@dataclass(frozen=True)
class Page[T]:
    items: Sequence[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.page_size))


@dataclass(frozen=True)
class TicketScope:
    """Alcance de visibilidad: None = todos; si no, solo los que solicitó o tiene asignados."""

    user_id: UUID | None = None


@dataclass(frozen=True)
class TicketFilters:
    search: str | None = None
    statuses: tuple[TicketStatus, ...] = ()
    priorities: tuple[Priority, ...] = ()
    category_id: int | None = None
    assignee_id: UUID | None = None
    unassigned: bool = False
    requester_id: UUID | None = None
    overdue: bool = False
    created_from: date | None = None
    created_to: date | None = None
    sort: str = "-created_at"


@dataclass(frozen=True)
class PersonRef:
    id: UUID
    full_name: str
    email: str


@dataclass(frozen=True)
class TicketListItem:
    id: UUID
    code: str
    title: str
    status: TicketStatus
    priority: Priority
    category_id: int
    category_name: str
    requester: PersonRef
    assignee: PersonRef | None
    due_at: datetime
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None
    is_overdue: bool


@dataclass(frozen=True)
class TicketEventView:
    id: UUID
    type: TicketEventType
    actor: PersonRef
    created_at: datetime
    from_status: TicketStatus | None
    to_status: TicketStatus | None
    comment: str | None
    data: dict[str, Any]


@dataclass(frozen=True)
class TicketDetail:
    ticket: TicketListItem
    description: str
    events: Sequence[TicketEventView]
    allowed_transitions: Sequence[TicketStatus]
    can_edit: bool
    can_comment: bool
    can_assign: bool


@dataclass(frozen=True)
class UserFilters:
    search: str | None = None
    role_id: UUID | None = None
    is_active: bool | None = None


@dataclass(frozen=True)
class LoginEventFilters:
    email: str | None = None
    success: bool | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass(frozen=True)
class AuditFilters:
    action: str | None = None
    actor_id: UUID | None = None
    entity_type: str | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass(frozen=True)
class LoginEventView:
    id: int
    email: str
    user_id: UUID | None
    user_name: str | None
    success: bool
    reason: str | None
    ip: str | None
    user_agent: str | None
    created_at: datetime


@dataclass(frozen=True)
class AuditLogView:
    id: int
    action: str
    actor: PersonRef | None
    entity_type: str
    entity_id: str | None
    metadata: dict[str, Any]
    ip: str | None
    request_id: str | None
    created_at: datetime


@dataclass(frozen=True)
class Category:
    id: int
    name: str


# --- Dashboard -------------------------------------------------------------------------------
@dataclass(frozen=True)
class DashboardQuery:
    date_from: date
    date_to: date
    scope: TicketScope = field(default_factory=TicketScope)
    category_id: int | None = None


@dataclass(frozen=True)
class LabeledCount:
    key: str
    label: str
    value: int


@dataclass(frozen=True)
class TrendPoint:
    day: date
    created: int
    resolved: int


@dataclass(frozen=True)
class AssigneeStat:
    user: PersonRef
    open: int
    resolved: int
    avg_resolution_hours: float | None


@dataclass(frozen=True)
class DashboardKpis:
    total: int
    open: int
    in_progress: int
    on_hold: int
    overdue: int
    unassigned: int
    created_in_period: int
    resolved_in_period: int
    mttr_hours: float | None
    sla_compliance: float | None


@dataclass(frozen=True)
class DashboardData:
    kpis: DashboardKpis
    by_status: Sequence[LabeledCount]
    by_priority: Sequence[LabeledCount]
    by_category: Sequence[LabeledCount]
    backlog_aging: Sequence[LabeledCount]
    trend: Sequence[TrendPoint]
    top_assignees: Sequence[AssigneeStat]


# --- Exportación -----------------------------------------------------------------------------
type Cell = str | int | float | bool | datetime | date | None


@dataclass(frozen=True)
class TabularExport:
    """Resultado agnóstico de formato: el adaptador de entrada decide cómo serializarlo."""

    filename_prefix: str
    headers: Sequence[str]
    rows: AsyncIterator[Sequence[Cell]]
