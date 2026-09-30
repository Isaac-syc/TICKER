"""Lado de lectura (CQRS-lite): consultas con joins que devuelven read models listos para la UI."""

import re
from collections.abc import AsyncIterator, Sequence
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql import Select

from helpdesk.adapters.outbound.persistence.models import (
    AuditLogModel,
    CategoryModel,
    LoginEventModel,
    TicketEventModel,
    TicketModel,
    UserModel,
)
from helpdesk.adapters.outbound.persistence.repositories import escape_like
from helpdesk.application.dto import (
    AuditFilters,
    AuditLogView,
    LoginEventFilters,
    LoginEventView,
    Page,
    PageRequest,
    PersonRef,
    TicketEventView,
    TicketFilters,
    TicketListItem,
    TicketScope,
)
from helpdesk.domain.tickets.entities import TicketEventType, format_ticket_code
from helpdesk.domain.tickets.workflow import (
    ACTIVE_STATUSES,
    PRIORITY_RANK,
    Priority,
    TicketStatus,
)

_CODE_RE = re.compile(r"^(?:tck-?)?0*(\d{1,12})$", re.IGNORECASE)
_ACTIVE = [s.value for s in ACTIVE_STATUSES]

Requester = aliased(UserModel, name="requester")
Assignee = aliased(UserModel, name="assignee")

PRIORITY_ORDER = case(
    {p.value: rank for p, rank in PRIORITY_RANK.items()}, value=TicketModel.priority
)
STATUS_ORDER = case({s.value: i for i, s in enumerate(TicketStatus)}, value=TicketModel.status)
SORTABLE: dict[str, Any] = {
    "created_at": TicketModel.created_at,
    "updated_at": TicketModel.updated_at,
    "due_at": TicketModel.due_at,
    "number": TicketModel.number,
    "title": TicketModel.title,
    "priority": PRIORITY_ORDER,
    "status": STATUS_ORDER,
}


def day_bounds(
    start: date | None, end: date | None, tz: ZoneInfo
) -> tuple[datetime | None, datetime | None]:
    """Convierte fechas locales a un rango [inicio, fin) en datetimes con zona."""
    lo = datetime.combine(start, time.min, tz) if start else None
    hi = datetime.combine(end + timedelta(days=1), time.min, tz) if end else None
    return lo, hi


def scope_condition(scope: TicketScope) -> ColumnElement[bool] | None:
    if scope.user_id is None:
        return None
    return or_(TicketModel.requester_id == scope.user_id, TicketModel.assignee_id == scope.user_id)


def _person(model: UserModel | None) -> PersonRef | None:
    if model is None:
        return None
    return PersonRef(id=model.id, full_name=model.full_name, email=model.email)


class SqlTicketQueries:
    def __init__(self, session: AsyncSession, tz: ZoneInfo) -> None:
        self._s = session
        self._tz = tz

    def _base(self) -> Select[TicketModel, UserModel, UserModel, str]:
        return (
            select(TicketModel, Requester, Assignee, CategoryModel.name)
            .join(Requester, TicketModel.requester_id == Requester.id)
            .outerjoin(Assignee, TicketModel.assignee_id == Assignee.id)
            .join(CategoryModel, TicketModel.category_id == CategoryModel.id)
        )

    def _apply[*Ts](
        self, stmt: Select[*Ts], filters: TicketFilters, scope: TicketScope, now: datetime
    ) -> Select[*Ts]:
        conditions: list[ColumnElement[bool]] = []
        if (cond := scope_condition(scope)) is not None:
            conditions.append(cond)
        if filters.search and (term := filters.search.strip()):
            like = f"%{escape_like(term)}%"
            text_match = or_(TicketModel.title.ilike(like), TicketModel.description.ilike(like))
            if match := _CODE_RE.match(term):
                text_match = or_(text_match, TicketModel.number == int(match.group(1)))
            conditions.append(text_match)
        if filters.statuses:
            conditions.append(TicketModel.status.in_([s.value for s in filters.statuses]))
        if filters.priorities:
            conditions.append(TicketModel.priority.in_([p.value for p in filters.priorities]))
        if filters.category_id is not None:
            conditions.append(TicketModel.category_id == filters.category_id)
        if filters.unassigned:
            conditions.append(TicketModel.assignee_id.is_(None))
        elif filters.assignee_id is not None:
            conditions.append(TicketModel.assignee_id == filters.assignee_id)
        if filters.requester_id is not None:
            conditions.append(TicketModel.requester_id == filters.requester_id)
        if filters.overdue:
            conditions.append(and_(TicketModel.status.in_(_ACTIVE), TicketModel.due_at < now))
        lo, hi = day_bounds(filters.created_from, filters.created_to, self._tz)
        if lo:
            conditions.append(TicketModel.created_at >= lo)
        if hi:
            conditions.append(TicketModel.created_at < hi)
        return stmt.where(*conditions) if conditions else stmt

    @staticmethod
    def _order[*Ts](stmt: Select[*Ts], sort: str) -> Select[*Ts]:
        desc = sort.startswith("-")
        column = SORTABLE.get(sort.lstrip("-"), TicketModel.created_at)
        primary = column.desc() if desc else column.asc()
        return stmt.order_by(primary, TicketModel.number.desc())

    @staticmethod
    def _to_item(row: Any, now: datetime) -> TicketListItem:
        t, requester, assignee, category_name = row
        status = TicketStatus(t.status)
        return TicketListItem(
            id=t.id,
            code=format_ticket_code(t.number),
            title=t.title,
            status=status,
            priority=Priority(t.priority),
            category_id=t.category_id,
            category_name=category_name,
            requester=PersonRef(requester.id, requester.full_name, requester.email),
            assignee=_person(assignee),
            due_at=t.due_at,
            created_at=t.created_at,
            updated_at=t.updated_at,
            resolved_at=t.resolved_at,
            closed_at=t.closed_at,
            is_overdue=status in ACTIVE_STATUSES and now > t.due_at,
        )

    async def list(
        self, filters: TicketFilters, scope: TicketScope, page: PageRequest, now: datetime
    ) -> Page[TicketListItem]:
        count_stmt = self._apply(select(func.count(TicketModel.id)), filters, scope, now)
        total = await self._s.scalar(count_stmt) or 0
        stmt = self._order(self._apply(self._base(), filters, scope, now), filters.sort)
        rows = await self._s.execute(stmt.offset(page.offset).limit(page.page_size))
        return Page(
            items=[self._to_item(r, now) for r in rows],
            total=total,
            page=page.page,
            page_size=page.page_size,
        )

    async def get_item(self, ticket_id: UUID, now: datetime) -> TicketListItem | None:
        row = (await self._s.execute(self._base().where(TicketModel.id == ticket_id))).first()
        return self._to_item(row, now) if row else None

    async def get_description(self, ticket_id: UUID) -> str | None:
        return await self._s.scalar(
            select(TicketModel.description).where(TicketModel.id == ticket_id)
        )

    async def events(self, ticket_id: UUID) -> Sequence[TicketEventView]:
        rows = await self._s.execute(
            select(TicketEventModel, UserModel)
            .join(UserModel, TicketEventModel.actor_id == UserModel.id)
            .where(TicketEventModel.ticket_id == ticket_id)
            .order_by(TicketEventModel.created_at, TicketEventModel.id)
        )
        return [
            TicketEventView(
                id=e.id,
                type=TicketEventType(e.type),
                actor=PersonRef(u.id, u.full_name, u.email),
                created_at=e.created_at,
                from_status=TicketStatus(e.from_status) if e.from_status else None,
                to_status=TicketStatus(e.to_status) if e.to_status else None,
                comment=e.comment,
                data=e.data or {},
            )
            for e, u in rows
        ]

    async def iter_export(
        self, filters: TicketFilters, scope: TicketScope, now: datetime
    ) -> AsyncIterator[TicketListItem]:
        stmt = self._order(self._apply(self._base(), filters, scope, now), filters.sort)
        result = await self._s.stream(stmt.execution_options(yield_per=500))
        async for row in result:
            yield self._to_item(row, now)


class SqlLogQueries:
    def __init__(self, session: AsyncSession, tz: ZoneInfo) -> None:
        self._s = session
        self._tz = tz

    # --- inicios de sesión ---
    def _login_stmt(self, filters: LoginEventFilters) -> Select[LoginEventModel, str]:
        stmt = select(LoginEventModel, UserModel.full_name).outerjoin(
            UserModel, LoginEventModel.user_id == UserModel.id
        )
        if filters.email:
            stmt = stmt.where(
                LoginEventModel.email.ilike(f"%{escape_like(filters.email.strip().lower())}%")
            )
        if filters.success is not None:
            stmt = stmt.where(LoginEventModel.success.is_(filters.success))
        lo, hi = day_bounds(filters.date_from, filters.date_to, self._tz)
        if lo:
            stmt = stmt.where(LoginEventModel.created_at >= lo)
        if hi:
            stmt = stmt.where(LoginEventModel.created_at < hi)
        return stmt.order_by(LoginEventModel.created_at.desc(), LoginEventModel.id.desc())

    @staticmethod
    def _login_view(e: LoginEventModel, name: str | None) -> LoginEventView:
        return LoginEventView(
            id=e.id,
            email=e.email,
            user_id=e.user_id,
            user_name=name,
            success=e.success,
            reason=e.reason,
            ip=e.ip,
            user_agent=e.user_agent,
            created_at=e.created_at,
        )

    async def login_events(
        self, filters: LoginEventFilters, page: PageRequest
    ) -> Page[LoginEventView]:
        stmt = self._login_stmt(filters)
        total = (
            await self._s.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
            or 0
        )
        rows = await self._s.execute(stmt.offset(page.offset).limit(page.page_size))
        return Page(
            items=[self._login_view(e, n) for e, n in rows],
            total=total,
            page=page.page,
            page_size=page.page_size,
        )

    async def iter_login_events(self, filters: LoginEventFilters) -> AsyncIterator[LoginEventView]:
        result = await self._s.stream(self._login_stmt(filters).execution_options(yield_per=1000))
        async for e, n in result:
            yield self._login_view(e, n)

    # --- auditoría ---
    def _audit_stmt(self, filters: AuditFilters) -> Select[AuditLogModel, UserModel]:
        actor = aliased(UserModel, name="actor")
        stmt = select(AuditLogModel, actor).outerjoin(actor, AuditLogModel.actor_id == actor.id)
        if filters.action:
            stmt = stmt.where(AuditLogModel.action == filters.action)
        if filters.actor_id:
            stmt = stmt.where(AuditLogModel.actor_id == filters.actor_id)
        if filters.entity_type:
            stmt = stmt.where(AuditLogModel.entity_type == filters.entity_type)
        lo, hi = day_bounds(filters.date_from, filters.date_to, self._tz)
        if lo:
            stmt = stmt.where(AuditLogModel.created_at >= lo)
        if hi:
            stmt = stmt.where(AuditLogModel.created_at < hi)
        return stmt.order_by(AuditLogModel.created_at.desc(), AuditLogModel.id.desc())

    @staticmethod
    def _audit_view(e: AuditLogModel, actor: UserModel | None) -> AuditLogView:
        return AuditLogView(
            id=e.id,
            action=e.action,
            actor=_person(actor),
            entity_type=e.entity_type,
            entity_id=e.entity_id,
            metadata=e.metadata_ or {},
            ip=e.ip,
            request_id=e.request_id,
            created_at=e.created_at,
        )

    async def audit_logs(self, filters: AuditFilters, page: PageRequest) -> Page[AuditLogView]:
        stmt = self._audit_stmt(filters)
        total = (
            await self._s.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
            or 0
        )
        rows = await self._s.execute(stmt.offset(page.offset).limit(page.page_size))
        return Page(
            items=[self._audit_view(e, a) for e, a in rows],
            total=total,
            page=page.page,
            page_size=page.page_size,
        )

    async def iter_audit_logs(self, filters: AuditFilters) -> AsyncIterator[AuditLogView]:
        result = await self._s.stream(self._audit_stmt(filters).execution_options(yield_per=1000))
        async for e, a in result:
            yield self._audit_view(e, a)

    async def audit_actions(self) -> Sequence[str]:
        rows = await self._s.scalars(
            select(AuditLogModel.action).distinct().order_by(AuditLogModel.action)
        )
        return list(rows)
