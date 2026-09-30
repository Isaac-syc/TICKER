"""Administración: usuarios, roles/permisos y bitácora."""

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
    AuditLogOut,
    LoginEventOut,
    PageOut,
    PermissionOut,
    ResetPasswordIn,
    RoleCreateIn,
    RoleOut,
    RoleRef,
    RoleUpdateIn,
    UserCreateIn,
    UserOut,
    UserUpdateIn,
)
from helpdesk.application.dto import AuditFilters, LoginEventFilters, PageRequest, UserFilters
from helpdesk.application.use_cases.roles import RoleWithUsage
from helpdesk.domain.identity.entities import Role, User

router = APIRouter(responses=ERRORS)

PageNum = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        full_name=u.full_name,
        role=RoleRef(id=u.role.id, name=u.role.name, single_tab_session=u.role.single_tab_session),
        is_active=u.is_active,
        last_login_at=u.last_login_at,
        created_at=u.created_at,
    )


def role_out(role: Role, user_count: int) -> RoleOut:
    return RoleOut(
        id=role.id,
        name=role.name,
        description=role.description,
        permissions=sorted(role.permissions),
        single_tab_session=role.single_tab_session,
        is_system=role.is_system,
        user_count=user_count,
    )


# --- usuarios -----------------------------------------------------------------------------------
def user_filters(
    search: Annotated[str | None, Query(max_length=120)] = None,
    role_id: UUID | None = None,
    is_active: bool | None = None,
) -> UserFilters:
    return UserFilters(search=search, role_id=role_id, is_active=is_active)


UserFiltersDep = Annotated[UserFilters, Depends(user_filters)]


@router.get("/users", response_model=PageOut[UserOut], tags=["users"])
async def list_users(
    actor: Actor,
    c: ContainerDep,
    filters: UserFiltersDep,
    page: PageNum = 1,
    page_size: PageSize = 20,
) -> PageOut[UserOut]:
    result = await c.list_users.execute(actor, filters, PageRequest(page, page_size))
    return PageOut[UserOut](
        items=[user_out(u) for u in result.items],
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        pages=result.pages,
    )


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED, tags=["users"])
async def create_user(body: UserCreateIn, actor: Actor, c: ContainerDep, ctx: Ctx) -> UserOut:
    user = await c.create_user.execute(
        actor,
        email=body.email,
        full_name=body.full_name,
        role_id=body.role_id,
        password=body.password,
        ctx=ctx,
    )
    return user_out(user)


@router.get(
    "/users/export.csv", response_class=StreamingResponse, responses=CSV_RESPONSE, tags=["users"]
)
async def export_users(
    actor: Actor, c: ContainerDep, ctx: Ctx, filters: UserFiltersDep
) -> StreamingResponse:
    return csv_response(await c.export_users.execute(actor, filters, ctx), c)


@router.get("/users/{user_id}", response_model=UserOut, tags=["users"])
async def get_user(user_id: UUID, actor: Actor, c: ContainerDep) -> UserOut:
    return user_out(await c.get_user.execute(actor, user_id))


@router.patch("/users/{user_id}", response_model=UserOut, tags=["users"])
async def update_user(
    user_id: UUID, body: UserUpdateIn, actor: Actor, c: ContainerDep, ctx: Ctx
) -> UserOut:
    user = await c.update_user.execute(
        actor,
        user_id,
        ctx=ctx,
        email=body.email,
        full_name=body.full_name,
        role_id=body.role_id,
        is_active=body.is_active,
    )
    return user_out(user)


@router.post(
    "/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT, tags=["users"]
)
async def reset_password(
    user_id: UUID, body: ResetPasswordIn, actor: Actor, c: ContainerDep, ctx: Ctx
) -> None:
    await c.reset_password.execute(actor, user_id, body.new_password, ctx)


# --- roles --------------------------------------------------------------------------------------
@router.get("/roles", response_model=list[RoleOut], tags=["roles"])
async def list_roles(actor: Actor, c: ContainerDep) -> list[RoleOut]:
    items: list[RoleWithUsage] = list(await c.list_roles.execute(actor))
    return [role_out(r.role, r.user_count) for r in items]


@router.get("/roles/permissions", response_model=list[PermissionOut], tags=["roles"])
async def list_permissions(actor: Actor, c: ContainerDep) -> list[PermissionOut]:
    return [PermissionOut.model_validate(p) for p in await c.list_permissions.execute(actor)]


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED, tags=["roles"])
async def create_role(body: RoleCreateIn, actor: Actor, c: ContainerDep, ctx: Ctx) -> RoleOut:
    role = await c.create_role.execute(
        actor,
        name=body.name,
        description=body.description,
        permissions=body.permissions,
        single_tab_session=body.single_tab_session,
        ctx=ctx,
    )
    return role_out(role, 0)


@router.patch("/roles/{role_id}", response_model=RoleOut, tags=["roles"])
async def update_role(
    role_id: UUID, body: RoleUpdateIn, actor: Actor, c: ContainerDep, ctx: Ctx
) -> RoleOut:
    role = await c.update_role.execute(
        actor,
        role_id,
        ctx=ctx,
        name=body.name,
        description=body.description,
        permissions=body.permissions,
        single_tab_session=body.single_tab_session,
    )
    usage = {r.role.id: r.user_count for r in await c.list_roles.execute(actor)}
    return role_out(role, usage.get(role.id, 0))


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["roles"])
async def delete_role(role_id: UUID, actor: Actor, c: ContainerDep, ctx: Ctx) -> None:
    await c.delete_role.execute(actor, role_id, ctx)


# --- bitácora -----------------------------------------------------------------------------------
def login_filters(
    email: Annotated[str | None, Query(max_length=254)] = None,
    success: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> LoginEventFilters:
    return LoginEventFilters(email=email, success=success, date_from=date_from, date_to=date_to)


def audit_filters(
    action: Annotated[str | None, Query(max_length=64)] = None,
    actor_id: UUID | None = None,
    entity_type: Annotated[str | None, Query(max_length=32)] = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> AuditFilters:
    return AuditFilters(
        action=action,
        actor_id=actor_id,
        entity_type=entity_type,
        date_from=date_from,
        date_to=date_to,
    )


LoginFilters = Annotated[LoginEventFilters, Depends(login_filters)]
AuditFiltersDep = Annotated[AuditFilters, Depends(audit_filters)]


@router.get("/logs/logins", response_model=PageOut[LoginEventOut], tags=["logs"])
async def login_events(
    actor: Actor,
    c: ContainerDep,
    filters: LoginFilters,
    page: PageNum = 1,
    page_size: PageSize = 20,
) -> PageOut[LoginEventOut]:
    result = await c.list_login_events.execute(actor, filters, PageRequest(page, page_size))
    return page_out(result, LoginEventOut)


@router.get(
    "/logs/logins/export.csv",
    response_class=StreamingResponse,
    responses=CSV_RESPONSE,
    tags=["logs"],
)
async def export_login_events(
    actor: Actor, c: ContainerDep, ctx: Ctx, filters: LoginFilters
) -> StreamingResponse:
    return csv_response(await c.export_login_events.execute(actor, filters, ctx), c)


@router.get("/logs/audit", response_model=PageOut[AuditLogOut], tags=["logs"])
async def audit_logs(
    actor: Actor,
    c: ContainerDep,
    filters: AuditFiltersDep,
    page: PageNum = 1,
    page_size: PageSize = 20,
) -> PageOut[AuditLogOut]:
    result = await c.list_audit_logs.execute(actor, filters, PageRequest(page, page_size))
    return page_out(result, AuditLogOut)


@router.get("/logs/audit/actions", response_model=list[str], tags=["logs"])
async def audit_actions(actor: Actor, c: ContainerDep) -> list[str]:
    return list(await c.list_audit_actions.execute(actor))


@router.get(
    "/logs/audit/export.csv",
    response_class=StreamingResponse,
    responses=CSV_RESPONSE,
    tags=["logs"],
)
async def export_audit_logs(
    actor: Actor, c: ContainerDep, ctx: Ctx, filters: AuditFiltersDep
) -> StreamingResponse:
    return csv_response(await c.export_audit_logs.execute(actor, filters, ctx), c)
