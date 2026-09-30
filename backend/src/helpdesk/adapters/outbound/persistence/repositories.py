from collections.abc import AsyncIterator, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from helpdesk.adapters.outbound.persistence.mappers import (
    apply_ticket,
    apply_user,
    event_to_model,
    role_to_domain,
    ticket_to_domain,
    user_to_domain,
)
from helpdesk.adapters.outbound.persistence.models import (
    AuditLogModel,
    AuthSessionModel,
    CategoryModel,
    LoginEventModel,
    RoleModel,
    RolePermissionModel,
    TicketModel,
    UserModel,
)
from helpdesk.application.dto import Category, Page, PageRequest, UserFilters
from helpdesk.domain.audit.entities import AuditEntry, LoginAttempt
from helpdesk.domain.identity.entities import Role, User
from helpdesk.domain.identity.permissions import Permission
from helpdesk.domain.identity.sessions import AuthSession
from helpdesk.domain.tickets.entities import Ticket


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, user_id: UUID) -> User | None:
        model = await self._s.get(UserModel, user_id)
        return user_to_domain(model) if model else None

    async def get_by_email(self, email: str) -> User | None:
        model = await self._s.scalar(select(UserModel).where(UserModel.email == email))
        return user_to_domain(model) if model else None

    async def add(self, user: User) -> None:
        model = UserModel(id=user.id)
        apply_user(model, user)
        self._s.add(model)
        await self._s.flush()

    async def save(self, user: User) -> None:
        model = await self._s.get(UserModel, user.id)
        if model is None:
            raise LookupError(user.id)
        apply_user(model, user)
        await self._s.flush()
        # La relación role puede haber cambiado de id: se recarga para lecturas posteriores.
        await self._s.refresh(model, ["role"])

    def _filtered(self, filters: UserFilters) -> Select[UserModel]:
        stmt = select(UserModel)
        if filters.search:
            term = f"%{escape_like(filters.search.strip())}%"
            stmt = stmt.where(or_(UserModel.full_name.ilike(term), UserModel.email.ilike(term)))
        if filters.role_id:
            stmt = stmt.where(UserModel.role_id == filters.role_id)
        if filters.is_active is not None:
            stmt = stmt.where(UserModel.is_active == filters.is_active)
        return stmt

    async def list(self, filters: UserFilters, page: PageRequest) -> Page[User]:
        stmt = self._filtered(filters)
        total = await self._s.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = await self._s.scalars(
            stmt.order_by(UserModel.full_name).offset(page.offset).limit(page.page_size)
        )
        return Page(
            items=[user_to_domain(m) for m in rows.unique()],
            total=total,
            page=page.page,
            page_size=page.page_size,
        )

    async def iter_all(self, filters: UserFilters) -> AsyncIterator[User]:
        rows = await self._s.scalars(self._filtered(filters).order_by(UserModel.full_name))
        for model in rows.unique():
            yield user_to_domain(model)

    def _with_permission(self, permission: Permission) -> Select[UserModel]:
        has_perm = exists().where(
            RolePermissionModel.role_id == UserModel.role_id,
            RolePermissionModel.permission_code == permission.value,
        )
        return select(UserModel).where(UserModel.is_active.is_(True), has_perm)

    async def list_with_permission(self, permission: Permission) -> Sequence[User]:
        rows = await self._s.scalars(
            self._with_permission(permission).order_by(UserModel.full_name)
        )
        return [user_to_domain(m) for m in rows.unique()]

    async def count_active_with_permission(self, permission: Permission) -> int:
        stmt = self._with_permission(permission).subquery()
        return await self._s.scalar(select(func.count()).select_from(stmt)) or 0

    async def count_by_role(self, role_id: UUID) -> int:
        stmt = select(func.count()).select_from(UserModel).where(UserModel.role_id == role_id)
        return await self._s.scalar(stmt) or 0


class SqlRoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, role_id: UUID) -> Role | None:
        model = await self._s.get(RoleModel, role_id)
        return role_to_domain(model) if model else None

    async def get_by_name(self, name: str) -> Role | None:
        model = await self._s.scalar(select(RoleModel).where(RoleModel.name == name))
        return role_to_domain(model) if model else None

    async def list(self) -> Sequence[Role]:
        rows = await self._s.scalars(
            select(RoleModel).order_by(RoleModel.is_system.desc(), RoleModel.name)
        )
        return [role_to_domain(m) for m in rows]

    @staticmethod
    def _sync_permissions(model: RoleModel, permissions: frozenset[Permission]) -> None:
        wanted = {p.value for p in permissions}
        model.permission_links = [
            link for link in model.permission_links if link.permission_code in wanted
        ]
        current = {link.permission_code for link in model.permission_links}
        for code in sorted(wanted - current):
            model.permission_links.append(RolePermissionModel(permission_code=code))

    async def add(self, role: Role) -> None:
        model = RoleModel(
            id=role.id,
            name=role.name,
            description=role.description,
            single_tab_session=role.single_tab_session,
            is_system=role.is_system,
            permission_links=[],
        )
        self._sync_permissions(model, role.permissions)
        self._s.add(model)
        await self._s.flush()

    async def save(self, role: Role) -> None:
        model = await self._s.get(RoleModel, role.id)
        if model is None:
            raise LookupError(role.id)
        model.name = role.name
        model.description = role.description
        model.single_tab_session = role.single_tab_session
        self._sync_permissions(model, role.permissions)
        await self._s.flush()

    async def delete(self, role_id: UUID) -> None:
        await self._s.execute(delete(RoleModel).where(RoleModel.id == role_id))


class SqlCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def list(self) -> Sequence[Category]:
        rows = await self._s.scalars(
            select(CategoryModel).order_by(CategoryModel.sort_order, CategoryModel.name)
        )
        return [Category(id=m.id, name=m.name) for m in rows]

    async def get(self, category_id: int) -> Category | None:
        model = await self._s.get(CategoryModel, category_id)
        return Category(id=model.id, name=model.name) if model else None


class SqlTicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, ticket_id: UUID) -> Ticket | None:
        model = await self._s.get(TicketModel, ticket_id)
        return ticket_to_domain(model) if model else None

    async def add(self, ticket: Ticket) -> None:
        model = TicketModel(id=ticket.id)
        apply_ticket(model, ticket)
        self._s.add(model)
        await self._s.flush()  # RETURNING trae el número de la secuencia (eager_defaults)
        ticket.number = model.number
        self._add_events(ticket)
        await self._s.flush()

    async def save(self, ticket: Ticket) -> None:
        model = await self._s.get(TicketModel, ticket.id)
        if model is None:
            raise LookupError(ticket.id)
        apply_ticket(model, ticket)
        self._add_events(ticket)
        await self._s.flush()

    def _add_events(self, ticket: Ticket) -> None:
        self._s.add_all(event_to_model(e) for e in ticket.pull_events())


class SqlAuthSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    @staticmethod
    def _to_domain(m: AuthSessionModel) -> AuthSession:
        return AuthSession(
            id=m.id,
            family_id=m.family_id,
            user_id=m.user_id,
            token_hash=m.token_hash,
            created_at=m.created_at,
            expires_at=m.expires_at,
            revoked_at=m.revoked_at,
            replaced_by=m.replaced_by,
            ip=m.ip,
            user_agent=m.user_agent,
        )

    async def get_by_token_hash(self, token_hash: str) -> AuthSession | None:
        model = await self._s.scalar(
            select(AuthSessionModel).where(AuthSessionModel.token_hash == token_hash)
        )
        return self._to_domain(model) if model else None

    async def add(self, session: AuthSession) -> None:
        self._s.add(
            AuthSessionModel(
                id=session.id,
                family_id=session.family_id,
                user_id=session.user_id,
                token_hash=session.token_hash,
                created_at=session.created_at,
                expires_at=session.expires_at,
                revoked_at=session.revoked_at,
                replaced_by=session.replaced_by,
                ip=session.ip,
                user_agent=(session.user_agent or "")[:512] or None,
            )
        )
        await self._s.flush()

    async def save(self, session: AuthSession) -> None:
        await self._s.execute(
            update(AuthSessionModel)
            .where(AuthSessionModel.id == session.id)
            .values(revoked_at=session.revoked_at, replaced_by=session.replaced_by)
        )

    async def revoke_family(self, family_id: UUID, now: datetime) -> None:
        await self._s.execute(
            update(AuthSessionModel)
            .where(AuthSessionModel.family_id == family_id, AuthSessionModel.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke_all_for_user(self, user_id: UUID, now: datetime) -> None:
        await self._s.execute(
            update(AuthSessionModel)
            .where(AuthSessionModel.user_id == user_id, AuthSessionModel.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def is_family_active(self, family_id: UUID, now: datetime) -> bool:
        stmt = select(
            exists().where(
                AuthSessionModel.family_id == family_id,
                AuthSessionModel.revoked_at.is_(None),
                AuthSessionModel.expires_at > now,
            )
        )
        return bool(await self._s.scalar(stmt))


class SqlAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def record(self, entry: AuditEntry) -> None:
        self._s.add(
            AuditLogModel(
                action=entry.action.value,
                actor_id=entry.actor_id,
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                metadata_=entry.metadata,
                ip=entry.ip,
                request_id=entry.request_id,
                created_at=entry.created_at,
            )
        )

    async def record_login(self, attempt: LoginAttempt) -> None:
        self._s.add(
            LoginEventModel(
                email=attempt.email,
                user_id=attempt.user_id,
                success=attempt.success,
                reason=attempt.reason.value if attempt.reason else None,
                ip=attempt.ip,
                user_agent=(attempt.user_agent or "")[:512] or None,
                created_at=attempt.created_at,
            )
        )
