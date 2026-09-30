from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from helpdesk.application.ports import (
    AccessToken,
    Clock,
    LoginRateLimiter,
    PasswordHasher,
    TabLeaseStore,
    TokenService,
    UnitOfWorkFactory,
)
from helpdesk.application.use_cases._common import UseCase, audit
from helpdesk.domain.audit.entities import (
    AuditAction,
    LoginAttempt,
    LoginFailureReason,
    RequestContext,
)
from helpdesk.domain.errors import AuthenticationError, TooManyAttemptsError, ValidationError
from helpdesk.domain.identity.entities import Principal, User, normalize_email, validate_password
from helpdesk.domain.identity.sessions import AuthSession

INVALID_CREDENTIALS = "Correo o contraseña incorrectos."
INVALID_SESSION = "Tu sesión expiró. Inicia sesión de nuevo."


@dataclass(frozen=True)
class AuthResult:
    access: AccessToken
    refresh_token: str
    refresh_expires_at: datetime
    session_id: UUID
    user: User


class _SessionIssuer(UseCase):
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        tokens: TokenService,
        refresh_ttl: timedelta,
    ) -> None:
        super().__init__(uow_factory, clock)
        self._tokens = tokens
        self._refresh_ttl = refresh_ttl

    def _new_session(
        self, user: User, now: datetime, ctx: RequestContext, family_id: UUID | None = None
    ) -> tuple[AuthSession, str]:
        raw = self._tokens.new_refresh_token()
        session = AuthSession.start(
            user_id=user.id,
            token_hash=self._tokens.hash_refresh_token(raw),
            ttl=self._refresh_ttl,
            now=now,
            family_id=family_id,
            ip=ctx.ip,
            user_agent=ctx.user_agent,
        )
        return session, raw

    def _result(self, user: User, session: AuthSession, raw: str) -> AuthResult:
        return AuthResult(
            access=self._tokens.issue_access(user, session.family_id),
            refresh_token=raw,
            refresh_expires_at=session.expires_at,
            session_id=session.family_id,
            user=user,
        )


class Login(_SessionIssuer):
    _dummy_hash: str | None = None

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        tokens: TokenService,
        refresh_ttl: timedelta,
        hasher: PasswordHasher,
        limiter: LoginRateLimiter,
    ) -> None:
        super().__init__(uow_factory, clock, tokens, refresh_ttl)
        self._hasher = hasher
        self._limiter = limiter

    def _burn_time(self, password: str) -> None:
        """Verifica contra un hash señuelo para que un correo inexistente tarde lo mismo."""
        if Login._dummy_hash is None:
            Login._dummy_hash = self._hasher.hash("timing-attack-dummy-password")
        self._hasher.verify(password, Login._dummy_hash)

    async def execute(self, email: str, password: str, ctx: RequestContext) -> AuthResult:
        now = self._clock.now()
        key = email.strip().lower()

        async with self._uow() as uow:

            async def fail(user: User | None, reason: LoginFailureReason) -> None:
                await uow.audit.record_login(
                    LoginAttempt(
                        email=key[:254],
                        user_id=user.id if user else None,
                        success=False,
                        reason=reason,
                        created_at=now,
                        ip=ctx.ip,
                        user_agent=ctx.user_agent,
                    )
                )
                await uow.commit()

            if await self._limiter.is_locked(key):
                await fail(None, LoginFailureReason.LOCKED)
                raise TooManyAttemptsError(
                    "Demasiados intentos fallidos. Intenta de nuevo en unos minutos."
                )
            try:
                user = await uow.users.get_by_email(normalize_email(key))
            except ValidationError:
                user = None

            if user is None:
                self._burn_time(password)
                await self._limiter.register_failure(key)
                await fail(None, LoginFailureReason.INVALID_CREDENTIALS)
                raise AuthenticationError(INVALID_CREDENTIALS)
            if not self._hasher.verify(password, user.password_hash):
                await self._limiter.register_failure(key)
                await fail(user, LoginFailureReason.INVALID_CREDENTIALS)
                raise AuthenticationError(INVALID_CREDENTIALS)
            if not user.is_active:
                await fail(user, LoginFailureReason.INACTIVE_USER)
                raise AuthenticationError("Tu usuario está desactivado. Contacta al administrador.")

            await self._limiter.reset(key)
            session, raw = self._new_session(user, now, ctx)
            user.record_login(now)
            await uow.sessions.add(session)
            await uow.users.save(user)
            await uow.audit.record_login(
                LoginAttempt(
                    email=user.email,
                    user_id=user.id,
                    success=True,
                    created_at=now,
                    ip=ctx.ip,
                    user_agent=ctx.user_agent,
                )
            )
            await uow.commit()
            return self._result(user, session, raw)


class RefreshSession(_SessionIssuer):
    """Rota el refresh token. Si se reutiliza uno ya rotado (fuera de la ventana de gracia),
    se asume robo y se revoca toda la familia de sesiones."""

    async def execute(self, refresh_token: str, ctx: RequestContext) -> AuthResult:
        now = self._clock.now()
        token_hash = self._tokens.hash_refresh_token(refresh_token)
        async with self._uow() as uow:
            current = await uow.sessions.get_by_token_hash(token_hash)
            if current is None or current.is_expired(now):
                raise AuthenticationError(INVALID_SESSION)

            if current.is_revoked and not current.rotated_recently(now):
                await uow.sessions.revoke_family(current.family_id, now)
                if current.replaced_by is not None:
                    await audit(
                        uow,
                        AuditAction.REFRESH_REUSE_DETECTED,
                        actor=None,
                        entity_type="session",
                        entity_id=current.family_id,
                        ctx=ctx,
                        now=now,
                        user_id=str(current.user_id),
                    )
                await uow.commit()
                raise AuthenticationError(INVALID_SESSION)

            if not await uow.sessions.is_family_active(current.family_id, now):
                raise AuthenticationError(INVALID_SESSION)

            user = await uow.users.get(current.user_id)
            if user is None or not user.is_active:
                await uow.sessions.revoke_family(current.family_id, now)
                await uow.commit()
                raise AuthenticationError(INVALID_SESSION)

            session, raw = self._new_session(user, now, ctx, family_id=current.family_id)
            current.revoke(now, replaced_by=session.id)
            await uow.sessions.add(session)
            await uow.sessions.save(current)
            await uow.commit()
            return self._result(user, session, raw)


class Logout(UseCase):
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        tokens: TokenService,
        leases: TabLeaseStore,
    ) -> None:
        super().__init__(uow_factory, clock)
        self._tokens = tokens
        self._leases = leases

    async def execute(
        self, refresh_token: str | None, tab_id: str | None, ctx: RequestContext
    ) -> None:
        if not refresh_token:
            return
        now = self._clock.now()
        async with self._uow() as uow:
            session = await uow.sessions.get_by_token_hash(
                self._tokens.hash_refresh_token(refresh_token)
            )
            if session is None:
                return
            await uow.sessions.revoke_family(session.family_id, now)
            user = await uow.users.get(session.user_id)
            await audit(
                uow,
                AuditAction.LOGOUT,
                actor=user,
                entity_type="session",
                entity_id=session.family_id,
                ctx=ctx,
                now=now,
            )
            await uow.commit()
        if tab_id:
            await self._leases.release(session.user_id, tab_id)


class AuthenticateRequest(UseCase):
    """Valida el access token y carga al usuario vigente (permisos siempre frescos)."""

    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock, tokens: TokenService) -> None:
        super().__init__(uow_factory, clock)
        self._tokens = tokens

    async def execute(self, access_token: str) -> Principal:
        claims = self._tokens.decode_access(access_token)
        async with self._uow() as uow:
            user = await uow.users.get(claims.user_id)
            if user is None or not user.is_active:
                raise AuthenticationError(INVALID_SESSION)
            if not await uow.sessions.is_family_active(claims.session_id, self._clock.now()):
                raise AuthenticationError(INVALID_SESSION)
            return Principal(user=user, session_id=claims.session_id)


class ChangeOwnPassword(UseCase):
    def __init__(
        self, uow_factory: UnitOfWorkFactory, clock: Clock, hasher: PasswordHasher
    ) -> None:
        super().__init__(uow_factory, clock)
        self._hasher = hasher

    async def execute(
        self, principal: Principal, current_password: str, new_password: str, ctx: RequestContext
    ) -> None:
        now = self._clock.now()
        async with self._uow() as uow:
            user = await uow.users.get(principal.user.id)
            if user is None or not self._hasher.verify(current_password, user.password_hash):
                raise AuthenticationError("La contraseña actual no es correcta.")
            validate_password(new_password)
            user.set_password_hash(self._hasher.hash(new_password), now)
            await uow.users.save(user)
            await audit(
                uow,
                AuditAction.USER_PASSWORD_CHANGED,
                actor=user,
                entity_type="user",
                entity_id=user.id,
                ctx=ctx,
                now=now,
            )
            await uow.commit()
