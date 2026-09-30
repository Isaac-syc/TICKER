from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse

from helpdesk.adapters.inbound.http.deps import Actor, ContainerDep, Ctx
from helpdesk.adapters.inbound.http.routers._shared import (
    CSV_RESPONSE,
    ERRORS,
    csv_response,
    page_out,
)
from helpdesk.adapters.inbound.http.schemas import (
    AssignIn,
    CategoryOut,
    CommentIn,
    PageOut,
    PersonOut,
    TicketCreatedOut,
    TicketCreateIn,
    TicketDetailOut,
    TicketItemOut,
    TicketUpdateIn,
    TransitionIn,
)
from helpdesk.application.dto import PageRequest, TicketFilters
from helpdesk.domain.identity.entities import User
from helpdesk.domain.tickets.workflow import Priority, TicketStatus

router = APIRouter(tags=["tickets"], responses=ERRORS)

SORT_PATTERN = r"^-?(created_at|updated_at|due_at|number|title|priority|status)$"


def ticket_filters(
    search: Annotated[str | None, Query(max_length=120)] = None,
    status: Annotated[list[TicketStatus] | None, Query()] = None,
    priority: Annotated[list[Priority] | None, Query()] = None,
    category_id: int | None = None,
    assignee_id: UUID | None = None,
    unassigned: bool = False,
    requester_id: UUID | None = None,
    overdue: bool = False,
    created_from: date | None = None,
    created_to: date | None = None,
    sort: Annotated[str, Query(pattern=SORT_PATTERN)] = "-created_at",
) -> TicketFilters:
    return TicketFilters(
        search=search,
        statuses=tuple(status or ()),
        priorities=tuple(priority or ()),
        category_id=category_id,
        assignee_id=assignee_id,
        unassigned=unassigned,
        requester_id=requester_id,
        overdue=overdue,
        created_from=created_from,
        created_to=created_to,
        sort=sort,
    )


Filters = Annotated[TicketFilters, Depends(ticket_filters)]


async def _detail(c: ContainerDep, actor: User, ticket_id: UUID) -> TicketDetailOut:
    return TicketDetailOut.model_validate(await c.get_ticket.execute(actor, ticket_id))


@router.get("/tickets", response_model=PageOut[TicketItemOut], summary="Listar tickets")
async def list_tickets(
    actor: Actor,
    c: ContainerDep,
    filters: Filters,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageOut[TicketItemOut]:
    result = await c.list_tickets.execute(actor, filters, PageRequest(page, page_size))
    return page_out(result, TicketItemOut)


@router.post(
    "/tickets",
    response_model=TicketCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="Crear ticket",
)
async def create_ticket(
    body: TicketCreateIn, actor: Actor, c: ContainerDep, ctx: Ctx
) -> TicketCreatedOut:
    ticket = await c.create_ticket.execute(
        actor,
        title=body.title,
        description=body.description,
        category_id=body.category_id,
        priority=body.priority,
        ctx=ctx,
    )
    return TicketCreatedOut(id=ticket.id, code=ticket.code)


@router.get(
    "/tickets/export.csv",
    response_class=StreamingResponse,
    responses=CSV_RESPONSE,
    summary="Exportar tickets a CSV (respeta los filtros)",
)
async def export_tickets(
    actor: Actor, c: ContainerDep, ctx: Ctx, filters: Filters
) -> StreamingResponse:
    return csv_response(await c.export_tickets.execute(actor, filters, ctx), c)


@router.get("/tickets/{ticket_id}", response_model=TicketDetailOut, summary="Detalle de ticket")
async def get_ticket(ticket_id: UUID, actor: Actor, c: ContainerDep) -> TicketDetailOut:
    return await _detail(c, actor, ticket_id)


@router.patch("/tickets/{ticket_id}", response_model=TicketDetailOut, summary="Editar ticket")
async def update_ticket(
    ticket_id: UUID, body: TicketUpdateIn, actor: Actor, c: ContainerDep, ctx: Ctx
) -> TicketDetailOut:
    await c.update_ticket.execute(
        actor,
        ticket_id,
        ctx=ctx,
        title=body.title,
        description=body.description,
        category_id=body.category_id,
        priority=body.priority,
    )
    return await _detail(c, actor, ticket_id)


@router.post(
    "/tickets/{ticket_id}/transitions",
    response_model=TicketDetailOut,
    summary="Cambiar estatus",
)
async def transition_ticket(
    ticket_id: UUID, body: TransitionIn, actor: Actor, c: ContainerDep, ctx: Ctx
) -> TicketDetailOut:
    await c.transition_ticket.execute(actor, ticket_id, body.status, body.comment, ctx)
    return await _detail(c, actor, ticket_id)


@router.post("/tickets/{ticket_id}/assign", response_model=TicketDetailOut, summary="Asignar")
async def assign_ticket(
    ticket_id: UUID, body: AssignIn, actor: Actor, c: ContainerDep, ctx: Ctx
) -> TicketDetailOut:
    await c.assign_ticket.execute(actor, ticket_id, body.assignee_id, ctx)
    return await _detail(c, actor, ticket_id)


@router.post("/tickets/{ticket_id}/comments", response_model=TicketDetailOut, summary="Comentar")
async def comment_ticket(
    ticket_id: UUID, body: CommentIn, actor: Actor, c: ContainerDep, ctx: Ctx
) -> TicketDetailOut:
    await c.comment_ticket.execute(actor, ticket_id, body.body, ctx)
    return await _detail(c, actor, ticket_id)


# --- catálogos ------------------------------------------------------------------------------------
@router.get("/catalog/categories", response_model=list[CategoryOut], tags=["catalog"])
async def categories(_: Actor, c: ContainerDep) -> list[CategoryOut]:
    return [CategoryOut.model_validate(x) for x in await c.list_categories.execute()]


@router.get(
    "/catalog/assignees",
    response_model=list[PersonOut],
    tags=["catalog"],
    summary="Usuarios que pueden atender tickets",
)
async def assignees(actor: Actor, c: ContainerDep) -> list[PersonOut]:
    return [PersonOut.model_validate(x) for x in await c.list_assignees.execute(actor)]
