from datetime import datetime
from typing import Any

from helpdesk.application.dto import TicketScope
from helpdesk.application.ports import Clock, UnitOfWork, UnitOfWorkFactory
from helpdesk.domain.audit.entities import AuditAction, AuditEntry, RequestContext
from helpdesk.domain.errors import PermissionDeniedError
from helpdesk.domain.identity.entities import User
from helpdesk.domain.identity.permissions import Permission


class UseCase:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow_factory
        self._clock = clock


def require(user: User, *permissions: Permission) -> None:
    missing = [p for p in permissions if not user.can(p)]
    if missing:
        raise PermissionDeniedError()


def ticket_scope_for(user: User) -> TicketScope:
    if user.can(Permission.TICKETS_READ_ALL):
        return TicketScope()
    if user.can(Permission.TICKETS_READ_OWN):
        return TicketScope(user_id=user.id)
    raise PermissionDeniedError("Tu rol no puede consultar tickets.")


async def audit(
    uow: UnitOfWork,
    action: AuditAction,
    *,
    actor: User | None,
    entity_type: str,
    entity_id: object | None,
    ctx: RequestContext,
    now: datetime,
    **metadata: Any,
) -> None:
    await uow.audit.record(
        AuditEntry(
            action=action,
            actor_id=actor.id if actor else None,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            created_at=now,
            metadata=metadata,
            ip=ctx.ip,
            request_id=ctx.request_id,
        )
    )
