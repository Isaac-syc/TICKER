from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from helpdesk.application.dto import (
    Category,
    Cell,
    Page,
    PageRequest,
    PersonRef,
    TabularExport,
    TicketDetail,
    TicketFilters,
    TicketListItem,
)
from helpdesk.application.labels import PRIORITY_LABELS, STATUS_LABELS
from helpdesk.application.ports import Clock, UnitOfWork, UnitOfWorkFactory
from helpdesk.application.use_cases._common import UseCase, audit, require, ticket_scope_for
from helpdesk.domain.audit.entities import AuditAction, RequestContext
from helpdesk.domain.errors import NotFoundError, ValidationError
from helpdesk.domain.identity.entities import User
from helpdesk.domain.identity.permissions import Permission
from helpdesk.domain.tickets.entities import Ticket
from helpdesk.domain.tickets.sla import SlaPolicy
from helpdesk.domain.tickets.workflow import ACTIVE_STATUSES, Priority, TicketStatus

NOT_FOUND = "El ticket no existe o no tienes acceso."


async def _load_visible(uow: UnitOfWork, ticket_id: UUID, user: User) -> Ticket:
    ticket = await uow.tickets.get(ticket_id)
    if ticket is None or not ticket.can_be_viewed_by(user):
        raise NotFoundError(NOT_FOUND)
    return ticket


async def _ensure_category(uow: UnitOfWork, category_id: int) -> None:
    if await uow.categories.get(category_id) is None:
        raise ValidationError("La categoría no existe.")


class _TicketUseCase(UseCase):
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock, sla: SlaPolicy) -> None:
        super().__init__(uow_factory, clock)
        self._sla = sla


class CreateTicket(_TicketUseCase):
    async def execute(
        self,
        actor: User,
        *,
        title: str,
        description: str,
        category_id: int,
        priority: Priority,
        ctx: RequestContext,
    ) -> Ticket:
        now = self._clock.now()
        async with self._uow() as uow:
            await _ensure_category(uow, category_id)
            ticket = Ticket.open(
                title=title,
                description=description,
                category_id=category_id,
                priority=priority,
                requester=actor,
                sla=self._sla,
                now=now,
            )
            await uow.tickets.add(ticket)
            await audit(
                uow,
                AuditAction.TICKET_CREATED,
                actor=actor,
                entity_type="ticket",
                entity_id=ticket.id,
                ctx=ctx,
                now=now,
                code=ticket.code,
                priority=priority.value,
            )
            await uow.commit()
            return ticket


class UpdateTicket(_TicketUseCase):
    async def execute(
        self,
        actor: User,
        ticket_id: UUID,
        *,
        ctx: RequestContext,
        title: str | None = None,
        description: str | None = None,
        category_id: int | None = None,
        priority: Priority | None = None,
    ) -> None:
        now = self._clock.now()
        async with self._uow() as uow:
            ticket = await _load_visible(uow, ticket_id, actor)
            if category_id is not None:
                await _ensure_category(uow, category_id)
            ticket.edit(
                actor=actor,
                sla=self._sla,
                now=now,
                title=title,
                description=description,
                category_id=category_id,
                priority=priority,
            )
            await uow.tickets.save(ticket)
            await audit(
                uow,
                AuditAction.TICKET_UPDATED,
                actor=actor,
                entity_type="ticket",
                entity_id=ticket.id,
                ctx=ctx,
                now=now,
                code=ticket.code,
            )
            await uow.commit()


class TransitionTicket(UseCase):
    async def execute(
        self,
        actor: User,
        ticket_id: UUID,
        target: TicketStatus,
        comment: str | None,
        ctx: RequestContext,
    ) -> None:
        now = self._clock.now()
        async with self._uow() as uow:
            ticket = await _load_visible(uow, ticket_id, actor)
            source = ticket.status
            ticket.transition(target, actor=actor, comment=comment, now=now)
            await uow.tickets.save(ticket)
            await audit(
                uow,
                AuditAction.TICKET_STATUS_CHANGED,
                actor=actor,
                entity_type="ticket",
                entity_id=ticket.id,
                ctx=ctx,
                now=now,
                code=ticket.code,
                **{"from": source.value, "to": target.value},
            )
            await uow.commit()


class AssignTicket(UseCase):
    async def execute(
        self, actor: User, ticket_id: UUID, assignee_id: UUID | None, ctx: RequestContext
    ) -> None:
        now = self._clock.now()
        async with self._uow() as uow:
            ticket = await _load_visible(uow, ticket_id, actor)
            assignee = None
            if assignee_id is not None:
                assignee = await uow.users.get(assignee_id)
                if assignee is None:
                    raise ValidationError("El usuario a asignar no existe.")
            ticket.assign(assignee, actor=actor, now=now)
            await uow.tickets.save(ticket)
            await audit(
                uow,
                AuditAction.TICKET_ASSIGNED,
                actor=actor,
                entity_type="ticket",
                entity_id=ticket.id,
                ctx=ctx,
                now=now,
                code=ticket.code,
                assignee_id=str(assignee_id) if assignee_id else None,
            )
            await uow.commit()


class CommentTicket(UseCase):
    async def execute(self, actor: User, ticket_id: UUID, body: str, ctx: RequestContext) -> None:
        now = self._clock.now()
        async with self._uow() as uow:
            ticket = await _load_visible(uow, ticket_id, actor)
            ticket.add_comment(body, actor=actor, now=now)
            await uow.tickets.save(ticket)
            await audit(
                uow,
                AuditAction.TICKET_COMMENTED,
                actor=actor,
                entity_type="ticket",
                entity_id=ticket.id,
                ctx=ctx,
                now=now,
                code=ticket.code,
            )
            await uow.commit()


class GetTicket(UseCase):
    async def execute(self, actor: User, ticket_id: UUID) -> TicketDetail:
        now = self._clock.now()
        async with self._uow() as uow:
            ticket = await _load_visible(uow, ticket_id, actor)
            item = await uow.ticket_queries.get_item(ticket_id, now)
            if item is None:
                raise NotFoundError(NOT_FOUND)
            return TicketDetail(
                ticket=item,
                description=ticket.description,
                events=await uow.ticket_queries.events(ticket_id),
                allowed_transitions=ticket.allowed_transitions_for(actor),
                can_edit=ticket.can_be_edited_by(actor),
                can_comment=ticket.can_be_commented_by(actor),
                can_assign=actor.can(Permission.TICKETS_MANAGE)
                and ticket.status in ACTIVE_STATUSES,
            )


class ListTickets(UseCase):
    async def execute(
        self, actor: User, filters: TicketFilters, page: PageRequest
    ) -> Page[TicketListItem]:
        scope = ticket_scope_for(actor)
        async with self._uow() as uow:
            return await uow.ticket_queries.list(filters, scope, page, self._clock.now())


class ExportTickets(UseCase):
    HEADERS = (
        "Código",
        "Título",
        "Estatus",
        "Prioridad",
        "Categoría",
        "Solicitante",
        "Correo solicitante",
        "Asignado a",
        "Creado",
        "Vence (SLA)",
        "Resuelto",
        "Cerrado",
        "Vencido",
    )

    async def execute(
        self, actor: User, filters: TicketFilters, ctx: RequestContext
    ) -> TabularExport:
        require(actor, Permission.EXPORT_CSV)
        scope = ticket_scope_for(actor)
        now = self._clock.now()
        async with self._uow() as uow:
            await audit(
                uow,
                AuditAction.TICKETS_EXPORTED,
                actor=actor,
                entity_type="ticket",
                entity_id=None,
                ctx=ctx,
                now=now,
                filters={k: str(v) for k, v in vars(filters).items() if v not in (None, (), False)},
            )
            await uow.commit()

        async def rows() -> AsyncIterator[Sequence[Cell]]:
            async with self._uow() as read_uow:
                async for t in read_uow.ticket_queries.iter_export(filters, scope, now):
                    yield (
                        t.code,
                        t.title,
                        STATUS_LABELS[t.status],
                        PRIORITY_LABELS[t.priority],
                        t.category_name,
                        t.requester.full_name,
                        t.requester.email,
                        t.assignee.full_name if t.assignee else "",
                        t.created_at,
                        t.due_at,
                        t.resolved_at,
                        t.closed_at,
                        "Sí" if t.is_overdue else "No",
                    )

        return TabularExport(filename_prefix="tickets", headers=self.HEADERS, rows=rows())


class ListCategories(UseCase):
    async def execute(self) -> Sequence[Category]:
        async with self._uow() as uow:
            return await uow.categories.list()


class ListAssignees(UseCase):
    """Usuarios que pueden atender tickets (para el selector de asignación)."""

    async def execute(self, actor: User) -> Sequence[PersonRef]:
        ticket_scope_for(actor)
        async with self._uow() as uow:
            users = await uow.users.list_with_permission(Permission.TICKETS_WORK)
            return [PersonRef(id=u.id, full_name=u.full_name, email=u.email) for u in users]
