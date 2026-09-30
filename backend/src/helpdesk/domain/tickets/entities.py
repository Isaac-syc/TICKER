from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from helpdesk.domain.errors import (
    InvalidTransitionError,
    PermissionDeniedError,
    ValidationError,
)
from helpdesk.domain.identity.entities import User
from helpdesk.domain.identity.permissions import Permission
from helpdesk.domain.tickets.sla import SlaPolicy
from helpdesk.domain.tickets.workflow import (
    ACTIVE_STATUSES,
    ASSIGNEE_TRANSITIONS,
    REQUESTER_TRANSITIONS,
    REQUIRES_COMMENT,
    TRANSITIONS,
    Priority,
    TicketStatus,
)

TITLE_MAX = 160
DESCRIPTION_MAX = 5000
COMMENT_MAX = 2000


class TicketEventType(StrEnum):
    CREATED = "CREATED"
    STATUS_CHANGED = "STATUS_CHANGED"
    ASSIGNED = "ASSIGNED"
    COMMENTED = "COMMENTED"
    UPDATED = "UPDATED"


@dataclass(frozen=True)
class TicketEvent:
    id: UUID
    ticket_id: UUID
    actor_id: UUID
    type: TicketEventType
    created_at: datetime
    from_status: TicketStatus | None = None
    to_status: TicketStatus | None = None
    comment: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


def format_ticket_code(number: int | None) -> str:
    return f"TCK-{number:06d}" if number is not None else "TCK-PENDIENTE"


def _clean_text(value: str, *, field_name: str, max_len: int, min_len: int = 1) -> str:
    text = value.strip()
    if len(text) < min_len:
        raise ValidationError(f"El campo '{field_name}' es obligatorio.")
    if len(text) > max_len:
        raise ValidationError(f"El campo '{field_name}' excede {max_len} caracteres.")
    return text


@dataclass
class Ticket:
    id: UUID
    title: str
    description: str
    category_id: int
    priority: Priority
    status: TicketStatus
    requester_id: UUID
    assignee_id: UUID | None
    due_at: datetime
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    number: int | None = None
    _pending_events: list[TicketEvent] = field(default_factory=list, repr=False)

    # --- creación -------------------------------------------------------------------------
    @classmethod
    def open(
        cls,
        *,
        title: str,
        description: str,
        category_id: int,
        priority: Priority,
        requester: User,
        sla: SlaPolicy,
        now: datetime,
    ) -> "Ticket":
        if not requester.can(Permission.TICKETS_CREATE):
            raise PermissionDeniedError("Tu rol no puede crear tickets.")
        ticket = cls(
            id=uuid4(),
            title=_clean_text(title, field_name="título", max_len=TITLE_MAX, min_len=5),
            description=_clean_text(
                description, field_name="descripción", max_len=DESCRIPTION_MAX, min_len=10
            ),
            category_id=category_id,
            priority=priority,
            status=TicketStatus.OPEN,
            requester_id=requester.id,
            assignee_id=None,
            due_at=sla.due_at(priority, now),
            created_at=now,
            updated_at=now,
        )
        ticket._record(requester.id, TicketEventType.CREATED, now, to_status=TicketStatus.OPEN)
        return ticket

    # --- consultas ------------------------------------------------------------------------
    @property
    def code(self) -> str:
        return format_ticket_code(self.number)

    def is_overdue(self, now: datetime) -> bool:
        return self.status in ACTIVE_STATUSES and now > self.due_at

    def can_be_viewed_by(self, user: User) -> bool:
        if user.can(Permission.TICKETS_READ_ALL):
            return True
        return user.can(Permission.TICKETS_READ_OWN) and user.id in (
            self.requester_id,
            self.assignee_id,
        )

    def allowed_transitions_for(self, user: User) -> list[TicketStatus]:
        candidates = TRANSITIONS[self.status]
        if user.can(Permission.TICKETS_MANAGE):
            return sorted(candidates)
        allowed: set[TicketStatus] = set()
        is_assignee = self.assignee_id == user.id and user.can(Permission.TICKETS_WORK)
        is_requester = self.requester_id == user.id and user.is_active
        for target in candidates:
            pair = (self.status, target)
            if (is_assignee and pair in ASSIGNEE_TRANSITIONS) or (
                is_requester and pair in REQUESTER_TRANSITIONS
            ):
                allowed.add(target)
        return sorted(allowed)

    def can_be_edited_by(self, user: User) -> bool:
        if user.can(Permission.TICKETS_MANAGE):
            return self.status not in (TicketStatus.CLOSED, TicketStatus.CANCELLED)
        return self.requester_id == user.id and self.status == TicketStatus.OPEN

    def can_be_commented_by(self, user: User) -> bool:
        return user.can(Permission.TICKETS_COMMENT) and (
            user.can(Permission.TICKETS_MANAGE) or user.id in (self.requester_id, self.assignee_id)
        )

    # --- comandos -------------------------------------------------------------------------
    def transition(
        self, target: TicketStatus, *, actor: User, comment: str | None, now: datetime
    ) -> None:
        if target not in TRANSITIONS[self.status]:
            raise InvalidTransitionError(
                f"No se puede pasar de {self.status.value} a {target.value}."
            )
        if target not in self.allowed_transitions_for(actor):
            raise PermissionDeniedError("No puedes realizar este cambio de estatus.")
        clean_comment = comment.strip() if comment else None
        if target in REQUIRES_COMMENT and not clean_comment:
            raise ValidationError("Este cambio de estatus requiere un comentario.")
        if clean_comment and len(clean_comment) > COMMENT_MAX:
            raise ValidationError(f"El comentario excede {COMMENT_MAX} caracteres.")

        source = self.status
        self.status = target
        if target == TicketStatus.RESOLVED:
            self.resolved_at = now
        elif target == TicketStatus.IN_PROGRESS and source == TicketStatus.RESOLVED:
            self.resolved_at = None  # reapertura
        if target in (TicketStatus.CLOSED, TicketStatus.CANCELLED):
            self.closed_at = now
        self.updated_at = now
        self._record(
            actor.id,
            TicketEventType.STATUS_CHANGED,
            now,
            from_status=source,
            to_status=target,
            comment=clean_comment,
        )

    def assign(self, assignee: User | None, *, actor: User, now: datetime) -> None:
        if not actor.can(Permission.TICKETS_MANAGE):
            raise PermissionDeniedError("Solo un administrador de tickets puede asignar.")
        if self.status not in ACTIVE_STATUSES:
            raise ValidationError("Solo se pueden asignar tickets activos.")
        if assignee is not None and not assignee.can(Permission.TICKETS_WORK):
            raise ValidationError("El usuario seleccionado no puede atender tickets.")
        new_id = assignee.id if assignee else None
        if new_id == self.assignee_id:
            return
        previous = self.assignee_id
        self.assignee_id = new_id
        self.updated_at = now
        self._record(
            actor.id,
            TicketEventType.ASSIGNED,
            now,
            data={
                "from": str(previous) if previous else None,
                "to": str(new_id) if new_id else None,
                "to_name": assignee.full_name if assignee else None,
            },
        )

    def edit(
        self,
        *,
        actor: User,
        sla: SlaPolicy,
        now: datetime,
        title: str | None = None,
        description: str | None = None,
        category_id: int | None = None,
        priority: Priority | None = None,
    ) -> None:
        if not self.can_be_edited_by(actor):
            raise PermissionDeniedError("No puedes editar este ticket.")
        changes: dict[str, Any] = {}
        if title is not None:
            new_title = _clean_text(title, field_name="título", max_len=TITLE_MAX, min_len=5)
            if new_title != self.title:
                changes["title"] = new_title
                self.title = new_title
        if description is not None:
            new_desc = _clean_text(
                description, field_name="descripción", max_len=DESCRIPTION_MAX, min_len=10
            )
            if new_desc != self.description:
                changes["description"] = True
                self.description = new_desc
        if category_id is not None and category_id != self.category_id:
            changes["category_id"] = category_id
            self.category_id = category_id
        if priority is not None and priority != self.priority:
            changes["priority"] = {"from": self.priority.value, "to": priority.value}
            self.priority = priority
            self.due_at = sla.due_at(priority, self.created_at)
        if changes:
            self.updated_at = now
            self._record(actor.id, TicketEventType.UPDATED, now, data=changes)

    def add_comment(self, body: str, *, actor: User, now: datetime) -> None:
        if not self.can_be_commented_by(actor):
            raise PermissionDeniedError("No puedes comentar este ticket.")
        text = _clean_text(body, field_name="comentario", max_len=COMMENT_MAX)
        self.updated_at = now
        self._record(actor.id, TicketEventType.COMMENTED, now, comment=text)

    # --- eventos --------------------------------------------------------------------------
    def _record(
        self,
        actor_id: UUID,
        event_type: TicketEventType,
        now: datetime,
        *,
        from_status: TicketStatus | None = None,
        to_status: TicketStatus | None = None,
        comment: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        self._pending_events.append(
            TicketEvent(
                id=uuid4(),
                ticket_id=self.id,
                actor_id=actor_id,
                type=event_type,
                created_at=now,
                from_status=from_status,
                to_status=to_status,
                comment=comment,
                data=data or {},
            )
        )

    def pull_events(self) -> list[TicketEvent]:
        events, self._pending_events = self._pending_events, []
        return events
