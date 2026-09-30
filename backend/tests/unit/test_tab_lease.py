from datetime import timedelta
from uuid import uuid4

import pytest

from helpdesk.application.use_cases.tab_lease import (
    ClaimTab,
    EnsureActiveTab,
    ReleaseTab,
    TakeoverTab,
)
from helpdesk.domain.audit.entities import AuditAction, RequestContext
from helpdesk.domain.errors import TabConflictError, ValidationError
from helpdesk.domain.identity.entities import Principal
from helpdesk.domain.identity.sessions import AuthSession
from tests.unit.conftest import World

CTX = RequestContext()
TAB_A = "tab-aaaaaaaa"
TAB_B = "tab-bbbbbbbb"


def principal(w: World, user_attr: str = "observer") -> Principal:
    user = getattr(w, user_attr)
    session = AuthSession.start(
        user_id=user.id, token_hash=uuid4().hex, ttl=timedelta(days=1), now=w.clock.now()
    )
    w.store.sessions[session.id] = session
    return Principal(user=user, session_id=session.family_id)


async def test_roles_without_restriction_are_not_affected(world: World) -> None:
    p = principal(world, "user")
    status = await ClaimTab(world.uow, world.clock, world.leases).execute(p, None)
    assert status.required is False
    assert status.granted is True
    await EnsureActiveTab(world.uow, world.clock, world.leases).execute(p, None)


async def test_second_tab_is_blocked(world: World) -> None:
    p = principal(world)
    claim = ClaimTab(world.uow, world.clock, world.leases)
    ensure = EnsureActiveTab(world.uow, world.clock, world.leases)

    assert (await claim.execute(p, TAB_A)).granted
    blocked = await claim.execute(p, TAB_B)
    assert blocked.required
    assert not blocked.granted
    assert not blocked.other_device

    await ensure.execute(p, TAB_A)
    with pytest.raises(TabConflictError):
        await ensure.execute(p, TAB_B)
    with pytest.raises(TabConflictError):
        await ensure.execute(p, None)


async def test_invalid_tab_id(world: World) -> None:
    with pytest.raises(ValidationError):
        await ClaimTab(world.uow, world.clock, world.leases).execute(principal(world), "x")


async def test_takeover_from_other_device_revokes_old_session(world: World) -> None:
    old_device = principal(world)
    new_device = principal(world)
    claim = ClaimTab(world.uow, world.clock, world.leases)
    await claim.execute(old_device, TAB_A)

    status = await claim.execute(new_device, TAB_B)
    assert not status.granted
    assert status.other_device

    result = await TakeoverTab(world.uow, world.clock, world.leases).execute(new_device, TAB_B, CTX)
    assert result.granted
    assert result.other_device
    old_sessions = [
        s for s in world.store.sessions.values() if s.family_id == old_device.session_id
    ]
    assert all(s.revoked_at is not None for s in old_sessions)
    assert world.store.audit[-1].action == AuditAction.SESSION_TAKEOVER

    with pytest.raises(TabConflictError):
        await EnsureActiveTab(world.uow, world.clock, world.leases).execute(old_device, TAB_A)


async def test_release_frees_the_lease(world: World) -> None:
    p = principal(world)
    claim = ClaimTab(world.uow, world.clock, world.leases)
    await claim.execute(p, TAB_A)
    await ReleaseTab(world.uow, world.clock, world.leases).execute(p, TAB_A)
    assert (await claim.execute(p, TAB_B)).granted
