"""Contratos HTTP (Pydantic). Se generan tipos TypeScript a partir del OpenAPI resultante."""

from datetime import date, datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from helpdesk.domain.identity.permissions import Permission
from helpdesk.domain.tickets.entities import TicketEventType
from helpdesk.domain.tickets.workflow import Priority, TicketStatus

T = TypeVar("T")


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorBody(Schema):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorOut(Schema):
    error: ErrorBody


class PageOut(Schema, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


# --- auth ---------------------------------------------------------------------------------------
class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class RoleRef(Schema):
    id: UUID
    name: str
    single_tab_session: bool


class MeOut(Schema):
    id: UUID
    email: str
    full_name: str
    role: RoleRef
    permissions: list[Permission]
    last_login_at: datetime | None


class TokenOut(Schema):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: MeOut


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class TabStatusOut(Schema):
    required: bool
    granted: bool
    other_device: bool


# --- tickets ------------------------------------------------------------------------------------
class PersonOut(Schema):
    id: UUID
    full_name: str
    email: str


class TicketItemOut(Schema):
    id: UUID
    code: str
    title: str
    status: TicketStatus
    priority: Priority
    category_id: int
    category_name: str
    requester: PersonOut
    assignee: PersonOut | None
    due_at: datetime
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None
    is_overdue: bool


class TicketEventOut(Schema):
    id: UUID
    type: TicketEventType
    actor: PersonOut
    created_at: datetime
    from_status: TicketStatus | None
    to_status: TicketStatus | None
    comment: str | None
    data: dict[str, Any]


class TicketDetailOut(Schema):
    ticket: TicketItemOut
    description: str
    events: list[TicketEventOut]
    allowed_transitions: list[TicketStatus]
    can_edit: bool
    can_comment: bool
    can_assign: bool


class TicketCreateIn(BaseModel):
    title: str = Field(min_length=5, max_length=160)
    description: str = Field(min_length=10, max_length=5000)
    category_id: int
    priority: Priority = Priority.MEDIUM


class TicketCreatedOut(Schema):
    id: UUID
    code: str


class TicketUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=5, max_length=160)
    description: str | None = Field(default=None, min_length=10, max_length=5000)
    category_id: int | None = None
    priority: Priority | None = None


class TransitionIn(BaseModel):
    status: TicketStatus
    comment: str | None = Field(default=None, max_length=2000)


class AssignIn(BaseModel):
    assignee_id: UUID | None


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class CategoryOut(Schema):
    id: int
    name: str


# --- dashboard ----------------------------------------------------------------------------------
class LabeledCountOut(Schema):
    key: str
    label: str
    value: int


class TrendPointOut(Schema):
    day: date
    created: int
    resolved: int


class AssigneeStatOut(Schema):
    user: PersonOut
    open: int
    resolved: int
    avg_resolution_hours: float | None


class KpisOut(Schema):
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


class DashboardOut(Schema):
    date_from: date
    date_to: date
    scope: str
    kpis: KpisOut
    by_status: list[LabeledCountOut]
    by_priority: list[LabeledCountOut]
    by_category: list[LabeledCountOut]
    backlog_aging: list[LabeledCountOut]
    trend: list[TrendPointOut]
    top_assignees: list[AssigneeStatOut]


# --- usuarios y roles ---------------------------------------------------------------------------
class UserOut(Schema):
    id: UUID
    email: str
    full_name: str
    role: RoleRef
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime


# El formato del correo lo valida el dominio (normalize_email); email-validator rechaza
# dominios reservados como .test que usamos en desarrollo.
class UserCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    full_name: str = Field(min_length=2, max_length=120)
    role_id: UUID
    password: str = Field(min_length=10, max_length=256)


class UserUpdateIn(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=254)
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role_id: UUID | None = None
    is_active: bool | None = None


class ResetPasswordIn(BaseModel):
    new_password: str = Field(min_length=10, max_length=256)


class RoleOut(Schema):
    id: UUID
    name: str
    description: str
    permissions: list[Permission]
    single_tab_session: bool
    is_system: bool
    user_count: int


class RoleCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=40, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]+$")
    description: str = Field(default="", max_length=255)
    permissions: list[Permission] = Field(default_factory=list)
    single_tab_session: bool = False


class RoleUpdateIn(BaseModel):
    name: str | None = Field(
        default=None, min_length=2, max_length=40, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]+$"
    )
    description: str | None = Field(default=None, max_length=255)
    permissions: list[Permission] | None = None
    single_tab_session: bool | None = None


class PermissionOut(Schema):
    code: Permission
    group: str
    description: str


# --- bitácora -----------------------------------------------------------------------------------
class LoginEventOut(Schema):
    id: int
    email: str
    user_id: UUID | None
    user_name: str | None
    success: bool
    reason: str | None
    ip: str | None
    user_agent: str | None
    created_at: datetime


class AuditLogOut(Schema):
    id: int
    action: str
    actor: PersonOut | None
    entity_type: str
    entity_id: str | None
    metadata: dict[str, Any]
    ip: str | None
    request_id: str | None
    created_at: datetime


class HealthOut(Schema):
    status: str
    checks: dict[str, str] = Field(default_factory=dict)
