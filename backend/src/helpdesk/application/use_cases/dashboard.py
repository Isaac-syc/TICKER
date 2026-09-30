from datetime import date, timedelta

from helpdesk.application.dto import DashboardData, DashboardQuery
from helpdesk.application.use_cases._common import UseCase, require, ticket_scope_for
from helpdesk.domain.errors import ValidationError
from helpdesk.domain.identity.entities import User
from helpdesk.domain.identity.permissions import Permission

MAX_RANGE_DAYS = 366


class GetDashboard(UseCase):
    async def execute(
        self,
        actor: User,
        *,
        today: date,
        date_from: date | None = None,
        date_to: date | None = None,
        category_id: int | None = None,
    ) -> DashboardData:
        require(actor, Permission.DASHBOARD_VIEW)
        end = date_to or today
        start = date_from or end - timedelta(days=29)
        if start > end:
            raise ValidationError("La fecha inicial no puede ser mayor que la final.")
        if (end - start).days > MAX_RANGE_DAYS:
            raise ValidationError("El rango máximo es de un año.")
        query = DashboardQuery(
            date_from=start, date_to=end, scope=ticket_scope_for(actor), category_id=category_id
        )
        async with self._uow() as uow:
            return await uow.analytics.dashboard(query, self._clock.now())
