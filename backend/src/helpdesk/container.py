"""Composition root: el único lugar que conoce todas las implementaciones concretas."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from redis.asyncio import Redis

from helpdesk.adapters.outbound.clock import SystemClock
from helpdesk.adapters.outbound.persistence.database import create_engine, create_session_factory
from helpdesk.adapters.outbound.persistence.uow import SqlAlchemyUnitOfWork
from helpdesk.adapters.outbound.redis_store import RedisLoginRateLimiter, RedisTabLeaseStore
from helpdesk.adapters.outbound.security import Argon2PasswordHasher, JwtTokenService
from helpdesk.application.use_cases import auth, dashboard, logs, roles, tab_lease, tickets, users
from helpdesk.config import Settings
from helpdesk.domain.tickets.sla import SlaPolicy


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.tz = ZoneInfo(settings.app_timezone)
        self.engine = create_engine(settings.database_url, settings.db_pool_size)
        self.session_factory = create_session_factory(self.engine)
        self.redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)

        self.clock = SystemClock()
        self.hasher = Argon2PasswordHasher()
        self.tokens = JwtTokenService(
            secret=settings.jwt_secret.get_secret_value(),
            issuer=settings.jwt_issuer,
            access_ttl=timedelta(minutes=settings.access_token_ttl_minutes),
        )
        self.limiter = RedisLoginRateLimiter(
            self.redis, settings.login_max_attempts, settings.login_lock_minutes * 60
        )
        self.leases = RedisTabLeaseStore(self.redis, settings.tab_lease_ttl_seconds)
        self.sla = SlaPolicy(
            critical_hours=settings.sla_critical_hours,
            high_hours=settings.sla_high_hours,
            medium_hours=settings.sla_medium_hours,
            low_hours=settings.sla_low_hours,
        )
        self.refresh_ttl = timedelta(days=settings.refresh_token_ttl_days)
        self._wire_use_cases()

    def uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory, self.tz)

    def _wire_use_cases(self) -> None:
        u, c = self.uow, self.clock
        # auth
        self.login = auth.Login(u, c, self.tokens, self.refresh_ttl, self.hasher, self.limiter)
        self.refresh = auth.RefreshSession(u, c, self.tokens, self.refresh_ttl)
        self.logout = auth.Logout(u, c, self.tokens, self.leases)
        self.authenticate = auth.AuthenticateRequest(u, c, self.tokens)
        self.change_password = auth.ChangeOwnPassword(u, c, self.hasher)
        # pestaña única
        self.claim_tab = tab_lease.ClaimTab(u, c, self.leases)
        self.ensure_tab = tab_lease.EnsureActiveTab(u, c, self.leases)
        self.takeover_tab = tab_lease.TakeoverTab(u, c, self.leases)
        self.release_tab = tab_lease.ReleaseTab(u, c, self.leases)
        # tickets
        self.create_ticket = tickets.CreateTicket(u, c, self.sla)
        self.update_ticket = tickets.UpdateTicket(u, c, self.sla)
        self.transition_ticket = tickets.TransitionTicket(u, c)
        self.assign_ticket = tickets.AssignTicket(u, c)
        self.comment_ticket = tickets.CommentTicket(u, c)
        self.get_ticket = tickets.GetTicket(u, c)
        self.list_tickets = tickets.ListTickets(u, c)
        self.export_tickets = tickets.ExportTickets(u, c)
        self.list_categories = tickets.ListCategories(u, c)
        self.list_assignees = tickets.ListAssignees(u, c)
        # usuarios y roles
        self.list_users = users.ListUsers(u, c)
        self.get_user = users.GetUser(u, c)
        self.create_user = users.CreateUser(u, c, self.hasher)
        self.update_user = users.UpdateUser(u, c)
        self.reset_password = users.ResetUserPassword(u, c, self.hasher)
        self.export_users = users.ExportUsers(u, c)
        self.list_roles = roles.ListRoles(u, c)
        self.list_permissions = roles.ListPermissions(u, c)
        self.create_role = roles.CreateRole(u, c)
        self.update_role = roles.UpdateRole(u, c)
        self.delete_role = roles.DeleteRole(u, c)
        # analítica y bitácora
        self.get_dashboard = dashboard.GetDashboard(u, c)
        self.list_login_events = logs.ListLoginEvents(u, c)
        self.list_audit_logs = logs.ListAuditLogs(u, c)
        self.list_audit_actions = logs.ListAuditActions(u, c)
        self.export_login_events = logs.ExportLoginEvents(u, c)
        self.export_audit_logs = logs.ExportAuditLogs(u, c)

    async def aclose(self) -> None:
        await self.redis.aclose()
        await self.engine.dispose()
