from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from helpdesk.adapters.outbound.persistence.models import CategoryModel, TicketModel, UserModel
from helpdesk.adapters.outbound.persistence.queries import day_bounds, scope_condition
from helpdesk.application.dto import (
    AssigneeStat,
    DashboardData,
    DashboardKpis,
    DashboardQuery,
    LabeledCount,
    PersonRef,
    TrendPoint,
)
from helpdesk.application.labels import PRIORITY_LABELS, STATUS_LABELS
from helpdesk.domain.tickets.workflow import ACTIVE_STATUSES, Priority, TicketStatus

_ACTIVE = [s.value for s in ACTIVE_STATUSES]
_HOURS = 3600.0

AGING_BUCKETS: list[tuple[str, str, timedelta | None]] = [
    ("lt_1d", "< 1 día", timedelta(days=1)),
    ("1_3d", "1–3 días", timedelta(days=3)),
    ("3_7d", "3–7 días", timedelta(days=7)),
    ("gt_7d", "> 7 días", None),
]


def _hours(expr: Any) -> Any:
    return func.extract("epoch", expr) / _HOURS


class SqlTicketAnalytics:
    def __init__(self, session: AsyncSession, tz: ZoneInfo) -> None:
        self._s = session
        self._tz = tz

    async def dashboard(self, query: DashboardQuery, now: datetime) -> DashboardData:
        start, end = day_bounds(query.date_from, query.date_to, self._tz)
        assert start is not None and end is not None

        base: list[ColumnElement[bool]] = []
        if (cond := scope_condition(query.scope)) is not None:
            base.append(cond)
        if query.category_id is not None:
            base.append(TicketModel.category_id == query.category_id)
        created_in = and_(*base, TicketModel.created_at >= start, TicketModel.created_at < end)
        resolved_in = and_(*base, TicketModel.resolved_at >= start, TicketModel.resolved_at < end)
        active = and_(*base, TicketModel.status.in_(_ACTIVE))

        # --- estado actual del backlog ---
        status_now = dict(
            (
                await self._s.execute(
                    select(TicketModel.status, func.count())
                    .where(*base)
                    .group_by(TicketModel.status)
                )
            ).all()
        )
        overdue = (
            await self._s.scalar(select(func.count()).where(active, TicketModel.due_at < now)) or 0
        )
        unassigned = (
            await self._s.scalar(
                select(func.count()).where(active, TicketModel.assignee_id.is_(None))
            )
            or 0
        )

        # --- periodo ---
        by_status = dict(
            (
                await self._s.execute(
                    select(TicketModel.status, func.count())
                    .where(created_in)
                    .group_by(TicketModel.status)
                )
            ).all()
        )
        by_priority = dict(
            (
                await self._s.execute(
                    select(TicketModel.priority, func.count())
                    .where(created_in)
                    .group_by(TicketModel.priority)
                )
            ).all()
        )
        by_category = (
            await self._s.execute(
                select(CategoryModel.id, CategoryModel.name, func.count(TicketModel.id))
                .join(TicketModel, TicketModel.category_id == CategoryModel.id)
                .where(created_in)
                .group_by(CategoryModel.id, CategoryModel.name)
                .order_by(func.count(TicketModel.id).desc())
            )
        ).all()

        resolved_row = (
            await self._s.execute(
                select(
                    func.count(),
                    func.avg(_hours(TicketModel.resolved_at - TicketModel.created_at)),
                    func.avg(case((TicketModel.resolved_at <= TicketModel.due_at, 1.0), else_=0.0)),
                ).where(resolved_in)
            )
        ).one()
        resolved_count, mttr, sla = resolved_row

        # --- tendencia diaria (en la zona horaria del negocio) ---
        created_day = func.date(func.timezone(str(self._tz), TicketModel.created_at))
        resolved_day = func.date(func.timezone(str(self._tz), TicketModel.resolved_at))
        created_per_day: dict[date, int] = dict(
            (
                await self._s.execute(
                    select(created_day, func.count()).where(created_in).group_by(created_day)
                )
            ).all()
        )
        resolved_per_day: dict[date, int] = dict(
            (
                await self._s.execute(
                    select(resolved_day, func.count()).where(resolved_in).group_by(resolved_day)
                )
            ).all()
        )
        trend = []
        day = query.date_from
        while day <= query.date_to:
            trend.append(TrendPoint(day, created_per_day.get(day, 0), resolved_per_day.get(day, 0)))
            day += timedelta(days=1)

        # --- antigüedad del backlog ---
        age = now - TicketModel.created_at
        whens = [(age < limit, key) for key, _, limit in AGING_BUCKETS if limit is not None]
        bucket = case(*whens, else_=AGING_BUCKETS[-1][0])
        aging: dict[str, int] = dict(
            (
                await self._s.execute(select(bucket, func.count()).where(active).group_by(bucket))
            ).all()
        )

        # --- top de asignados ---
        open_cnt = func.count().filter(TicketModel.status.in_(_ACTIVE))
        resolved_cnt = func.count().filter(
            TicketModel.resolved_at >= start, TicketModel.resolved_at < end
        )
        avg_res = func.avg(_hours(TicketModel.resolved_at - TicketModel.created_at)).filter(
            TicketModel.resolved_at >= start, TicketModel.resolved_at < end
        )
        top_rows = (
            await self._s.execute(
                select(
                    UserModel.id,
                    UserModel.full_name,
                    UserModel.email,
                    open_cnt,
                    resolved_cnt,
                    avg_res,
                )
                .join(TicketModel, TicketModel.assignee_id == UserModel.id)
                .where(*base)
                .group_by(UserModel.id, UserModel.full_name, UserModel.email)
                .order_by(resolved_cnt.desc(), open_cnt.desc())
                .limit(5)
            )
        ).all()

        return DashboardData(
            kpis=DashboardKpis(
                total=sum(status_now.values()),
                open=status_now.get(TicketStatus.OPEN.value, 0),
                in_progress=status_now.get(TicketStatus.IN_PROGRESS.value, 0),
                on_hold=status_now.get(TicketStatus.ON_HOLD.value, 0),
                overdue=overdue,
                unassigned=unassigned,
                created_in_period=sum(by_status.values()),
                resolved_in_period=resolved_count or 0,
                mttr_hours=round(float(mttr), 1) if mttr is not None else None,
                sla_compliance=round(float(sla) * 100, 1) if sla is not None else None,
            ),
            by_status=[
                LabeledCount(s.value, STATUS_LABELS[s], by_status.get(s.value, 0))
                for s in TicketStatus
            ],
            by_priority=[
                LabeledCount(p.value, PRIORITY_LABELS[p], by_priority.get(p.value, 0))
                for p in reversed(Priority)
            ],
            by_category=[LabeledCount(str(cid), name, n) for cid, name, n in by_category],
            backlog_aging=[
                LabeledCount(key, label, aging.get(key, 0)) for key, label, _ in AGING_BUCKETS
            ],
            trend=trend,
            top_assignees=[
                AssigneeStat(
                    user=PersonRef(uid, name, email),
                    open=o,
                    resolved=r,
                    avg_resolution_hours=round(float(a), 1) if a is not None else None,
                )
                for uid, name, email, o, r, a in top_rows
            ],
        )
