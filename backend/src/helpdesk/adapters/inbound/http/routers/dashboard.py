from datetime import date

from fastapi import APIRouter

from helpdesk.adapters.inbound.http.deps import Actor, ContainerDep
from helpdesk.adapters.inbound.http.routers._shared import ERRORS
from helpdesk.adapters.inbound.http.schemas import DashboardOut
from helpdesk.domain.identity.permissions import Permission

router = APIRouter(prefix="/dashboard", tags=["dashboard"], responses=ERRORS)


@router.get("", response_model=DashboardOut, summary="KPIs y series para el dashboard")
async def dashboard(
    actor: Actor,
    c: ContainerDep,
    date_from: date | None = None,
    date_to: date | None = None,
    category_id: int | None = None,
) -> DashboardOut:
    today = c.clock.now().astimezone(c.tz).date()
    data = await c.get_dashboard.execute(
        actor, today=today, date_from=date_from, date_to=date_to, category_id=category_id
    )
    end = date_to or today
    return DashboardOut.model_validate(
        {
            **{f: getattr(data, f) for f in data.__dataclass_fields__},
            "date_from": data.trend[0].day if data.trend else (date_from or end),
            "date_to": end,
            "scope": "all" if actor.can(Permission.TICKETS_READ_ALL) else "own",
        }
    )
