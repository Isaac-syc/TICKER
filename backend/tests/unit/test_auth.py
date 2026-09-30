from datetime import timedelta

import pytest

from helpdesk.application.use_cases.auth import (
    AuthenticateRequest,
    Login,
    Logout,
    RefreshSession,
)
from helpdesk.domain.audit.entities import AuditAction, LoginFailureReason, RequestContext
from helpdesk.domain.errors import AuthenticationError, TooManyAttemptsError
from tests.unit.conftest import World

CTX = RequestContext(ip="10.0.0.1", user_agent="pytest", request_id="req-1")
PASSWORD = "Secreta#2026"


def login_uc(w: World) -> Login:
    return Login(w.uow, w.clock, w.tokens, timedelta(days=7), w.hasher, w.limiter)


def refresh_uc(w: World) -> RefreshSession:
    return RefreshSession(w.uow, w.clock, w.tokens, timedelta(days=7))


async def test_login_success_records_event_and_session(world: World) -> None:
    result = await login_uc(world).execute("  USER@test.mx ", PASSWORD, CTX)
    assert result.user.id == world.user.id
    assert result.access.token
    assert len(world.store.sessions) == 1
    assert world.store.logins[-1].success
    assert world.store.users[world.user.id].last_login_at == world.clock.now()


async def test_login_wrong_password_then_lockout(world: World) -> None:
    uc = login_uc(world)
    for _ in range(3):
        with pytest.raises(AuthenticationError):
            await uc.execute("user@test.mx", "incorrecta", CTX)
    with pytest.raises(TooManyAttemptsError):
        await uc.execute("user@test.mx", PASSWORD, CTX)
    reasons = [a.reason for a in world.store.logins]
    assert reasons[-1] == LoginFailureReason.LOCKED
    assert reasons.count(LoginFailureReason.INVALID_CREDENTIALS) == 3


async def test_login_unknown_email_and_inactive_user(world: World) -> None:
    uc = login_uc(world)
    with pytest.raises(AuthenticationError):
        await uc.execute("nadie@test.mx", PASSWORD, CTX)
    assert world.store.logins[-1].user_id is None

    world.store.users[world.user.id].is_active = False
    with pytest.raises(AuthenticationError):
        await uc.execute("user@test.mx", PASSWORD, CTX)
    assert world.store.logins[-1].reason == LoginFailureReason.INACTIVE_USER


async def test_refresh_rotates_token_and_keeps_family(world: World) -> None:
    first = await login_uc(world).execute("user@test.mx", PASSWORD, CTX)
    world.clock.advance(minutes=10)
    second = await refresh_uc(world).execute(first.refresh_token, CTX)
    assert second.refresh_token != first.refresh_token
    assert second.session_id == first.session_id
    old = next(
        s for s in world.store.sessions.values() if s.token_hash == f"h({first.refresh_token})"
    )
    assert old.revoked_at is not None and old.replaced_by is not None


async def test_refresh_reuse_outside_grace_revokes_family(world: World) -> None:
    first = await login_uc(world).execute("user@test.mx", PASSWORD, CTX)
    await refresh_uc(world).execute(first.refresh_token, CTX)
    world.clock.advance(minutes=5)  # fuera de la ventana de gracia
    with pytest.raises(AuthenticationError):
        await refresh_uc(world).execute(first.refresh_token, CTX)
    assert all(s.revoked_at is not None for s in world.store.sessions.values())
    assert world.store.audit[-1].action == AuditAction.REFRESH_REUSE_DETECTED


async def test_refresh_reuse_inside_grace_is_tolerated(world: World) -> None:
    first = await login_uc(world).execute("user@test.mx", PASSWORD, CTX)
    await refresh_uc(world).execute(first.refresh_token, CTX)
    world.clock.advance(seconds=5)  # otra pestaña refrescó casi al mismo tiempo
    again = await refresh_uc(world).execute(first.refresh_token, CTX)
    assert again.session_id == first.session_id


async def test_logout_revokes_session_and_access_is_rejected(world: World) -> None:
    first = await login_uc(world).execute("user@test.mx", PASSWORD, CTX)
    auth = AuthenticateRequest(world.uow, world.clock, world.tokens)
    principal = await auth.execute(first.access.token)
    assert principal.user.id == world.user.id

    await Logout(world.uow, world.clock, world.tokens, world.leases).execute(
        first.refresh_token, None, CTX
    )
    with pytest.raises(AuthenticationError):
        await auth.execute(first.access.token)
    with pytest.raises(AuthenticationError):
        await refresh_uc(world).execute(first.refresh_token, CTX)
