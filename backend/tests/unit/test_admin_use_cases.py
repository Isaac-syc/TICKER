import pytest

from helpdesk.application.use_cases.roles import CreateRole, DeleteRole, UpdateRole
from helpdesk.application.use_cases.tickets import CreateTicket, TransitionTicket
from helpdesk.application.use_cases.users import CreateUser, UpdateUser
from helpdesk.domain.audit.entities import AuditAction, RequestContext
from helpdesk.domain.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from helpdesk.domain.identity.entities import validate_password
from helpdesk.domain.identity.permissions import ALL_PERMISSIONS, Permission
from helpdesk.domain.tickets.workflow import Priority, TicketStatus
from tests.unit.conftest import World

CTX = RequestContext(ip="127.0.0.1", request_id="r1")


@pytest.mark.parametrize("pwd", ["corta1!", "solominusculasmuylarga", "SINNUMEROSNISIMBOLOS"])
def test_password_policy_rejects_weak(pwd: str) -> None:
    with pytest.raises(ValidationError):
        validate_password(pwd)


def test_password_policy_accepts_strong() -> None:
    validate_password("Mesa-De-Ayuda-2026")


async def test_create_user_requires_permission_and_unique_email(world: World) -> None:
    uc = CreateUser(world.uow, world.clock, world.hasher)
    kwargs = {
        "email": "nuevo@test.mx",
        "full_name": "Nuevo Usuario",
        "role_id": world.roles["usuario"].id,
        "password": "Contraseña#2026",
        "ctx": CTX,
    }
    with pytest.raises(PermissionDeniedError):
        await uc.execute(world.user, **kwargs)  # type: ignore[arg-type]
    created = await uc.execute(world.admin, **kwargs)  # type: ignore[arg-type]
    assert created.email == "nuevo@test.mx"
    assert world.store.audit[-1].action == AuditAction.USER_CREATED
    with pytest.raises(ConflictError):
        await uc.execute(world.admin, **kwargs)  # type: ignore[arg-type]


async def test_admin_cannot_deactivate_self_nor_remove_last_admin(world: World) -> None:
    uc = UpdateUser(world.uow, world.clock)
    with pytest.raises(ValidationError):
        await uc.execute(world.admin, world.admin.id, ctx=CTX, is_active=False)
    with pytest.raises(ValidationError):
        await uc.execute(world.admin, world.admin.id, ctx=CTX, role_id=world.roles["usuario"].id)


async def test_deactivating_user_revokes_sessions(world: World) -> None:
    from datetime import timedelta
    from uuid import uuid4

    from helpdesk.domain.identity.sessions import AuthSession

    s = AuthSession.start(
        user_id=world.user.id, token_hash=uuid4().hex, ttl=timedelta(days=1), now=world.clock.now()
    )
    world.store.sessions[s.id] = s
    await UpdateUser(world.uow, world.clock).execute(
        world.admin, world.user.id, ctx=CTX, is_active=False
    )
    assert world.store.sessions[s.id].revoked_at is not None


async def test_new_role_works_without_code_changes(world: World) -> None:
    role = await CreateRole(world.uow, world.clock).execute(
        world.admin,
        name="Tecnico",
        description="Atiende tickets",
        permissions=["tickets:read_all", "tickets:work", "tickets:comment"],
        single_tab_session=False,
        ctx=CTX,
    )
    assert role.name == "tecnico"
    tech = world.tech
    tech.role = role
    world.store.users[tech.id] = tech
    assert tech.can(Permission.TICKETS_WORK)
    assert not tech.can(Permission.TICKETS_CREATE)


async def test_role_protections(world: World) -> None:
    update = UpdateRole(world.uow, world.clock)
    with pytest.raises(ValidationError):
        await update.execute(
            world.admin, world.roles["admin"].id, ctx=CTX, permissions=["tickets:read_all"]
        )
    with pytest.raises(ValidationError):
        await update.execute(world.admin, world.roles["usuario"].id, ctx=CTX, name="otro")
    with pytest.raises(ValidationError):
        await DeleteRole(world.uow, world.clock).execute(
            world.admin, world.roles["usuario"].id, CTX
        )
    updated = await update.execute(
        world.admin,
        world.roles["admin"].id,
        ctx=CTX,
        permissions=[p.value for p in ALL_PERMISSIONS],
    )
    assert updated.permissions == ALL_PERMISSIONS


async def test_unknown_permission_is_rejected(world: World) -> None:
    with pytest.raises(ValidationError):
        await CreateRole(world.uow, world.clock).execute(
            world.admin,
            name="raro",
            description="",
            permissions=["tickets:hack"],
            single_tab_session=False,
            ctx=CTX,
        )


async def test_create_ticket_and_hidden_from_others(world: World) -> None:
    ticket = await CreateTicket(world.uow, world.clock, world.sla).execute(
        world.user,
        title="No hay internet",
        description="Sin red en el piso 3 desde temprano",
        category_id=1,
        priority=Priority.MEDIUM,
        ctx=CTX,
    )
    assert ticket.code == "TCK-000001"
    with pytest.raises(NotFoundError):  # el técnico no asignado no lo ve
        await TransitionTicket(world.uow, world.clock).execute(
            world.tech, ticket.id, TicketStatus.IN_PROGRESS, None, CTX
        )
    with pytest.raises(ValidationError):
        await CreateTicket(world.uow, world.clock, world.sla).execute(
            world.user,
            title="Categoría inválida",
            description="Esto no debería crearse",
            category_id=99,
            priority=Priority.LOW,
            ctx=CTX,
        )
