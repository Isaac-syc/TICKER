from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class AuditAction(StrEnum):
    TICKET_CREATED = "ticket.created"
    TICKET_UPDATED = "ticket.updated"
    TICKET_STATUS_CHANGED = "ticket.status_changed"
    TICKET_ASSIGNED = "ticket.assigned"
    TICKET_COMMENTED = "ticket.commented"
    TICKETS_EXPORTED = "tickets.exported"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_PASSWORD_RESET = "user.password_reset"
    USER_PASSWORD_CHANGED = "user.password_changed"
    USERS_EXPORTED = "users.exported"
    ROLE_CREATED = "role.created"
    ROLE_UPDATED = "role.updated"
    ROLE_DELETED = "role.deleted"
    LOGOUT = "auth.logout"
    REFRESH_REUSE_DETECTED = "auth.refresh_reuse_detected"
    SESSION_TAKEOVER = "auth.session_takeover"
    LOGS_EXPORTED = "logs.exported"


class LoginFailureReason(StrEnum):
    INVALID_CREDENTIALS = "invalid_credentials"
    INACTIVE_USER = "inactive_user"
    LOCKED = "locked"


@dataclass(frozen=True)
class RequestContext:
    """Metadatos de la petición que origina un caso de uso (para auditoría)."""

    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class AuditEntry:
    action: AuditAction
    actor_id: UUID | None
    entity_type: str
    entity_id: str | None
    created_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
    ip: str | None = None
    request_id: str | None = None


@dataclass(frozen=True)
class LoginAttempt:
    email: str
    user_id: UUID | None
    success: bool
    created_at: datetime
    reason: LoginFailureReason | None = None
    ip: str | None = None
    user_agent: str | None = None
