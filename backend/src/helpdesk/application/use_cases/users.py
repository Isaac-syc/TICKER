from collections.abc import AsyncIterator, Sequence
from uuid import UUID

from helpdesk.application.dto import Cell, Page, PageRequest, TabularExport, UserFilters
from helpdesk.application.ports import Clock, PasswordHasher, UnitOfWork, UnitOfWorkFactory
from helpdesk.application.use_cases._common import UseCase, audit, require
from helpdesk.domain.audit.entities import AuditAction, RequestContext
from helpdesk.domain.errors import ConflictError, NotFoundError, ValidationError
from helpdesk.domain.identity.entities import Role, User, normalize_email, validate_password
from helpdesk.domain.identity.permissions import Permission


class _UserAdminUseCase(UseCase):
    def __init__(
        self, uow_factory: UnitOfWorkFactory, clock: Clock, hasher: PasswordHasher
    ) -> None:
        super().__init__(uow_factory, clock)
        self._hasher = hasher


async def _get_role(uow: UnitOfWork, role_id: UUID) -> Role:
    role = await uow.roles.get(role_id)
    if role is None:
        raise ValidationError("El rol no existe.")
    return role


async def _get_user(uow: UnitOfWork, user_id: UUID) -> User:
    user = await uow.users.get(user_id)
    if user is None:
        raise NotFoundError("El usuario no existe.")
    return user


class ListUsers(UseCase):
    async def execute(self, actor: User, filters: UserFilters, page: PageRequest) -> Page[User]:
        require(actor, Permission.USERS_MANAGE)
        async with self._uow() as uow:
            return await uow.users.list(filters, page)


class GetUser(UseCase):
    async def execute(self, actor: User, user_id: UUID) -> User:
        require(actor, Permission.USERS_MANAGE)
        async with self._uow() as uow:
            return await _get_user(uow, user_id)


class CreateUser(_UserAdminUseCase):
    async def execute(
        self,
        actor: User,
        *,
        email: str,
        full_name: str,
        role_id: UUID,
        password: str,
        ctx: RequestContext,
    ) -> User:
        require(actor, Permission.USERS_MANAGE)
        validate_password(password)
        now = self._clock.now()
        async with self._uow() as uow:
            role = await _get_role(uow, role_id)
            if await uow.users.get_by_email(normalize_email(email)):
                raise ConflictError("Ya existe un usuario con ese correo.")
            user = User.register(
                email=email,
                full_name=full_name,
                password_hash=self._hasher.hash(password),
                role=role,
                now=now,
            )
            await uow.users.add(user)
            await audit(
                uow,
                AuditAction.USER_CREATED,
                actor=actor,
                entity_type="user",
                entity_id=user.id,
                ctx=ctx,
                now=now,
                email=user.email,
                role=role.name,
            )
            await uow.commit()
            return user


class UpdateUser(UseCase):
    async def execute(
        self,
        actor: User,
        user_id: UUID,
        *,
        ctx: RequestContext,
        email: str | None = None,
        full_name: str | None = None,
        role_id: UUID | None = None,
        is_active: bool | None = None,
    ) -> User:
        require(actor, Permission.USERS_MANAGE)
        now = self._clock.now()
        async with self._uow() as uow:
            user = await _get_user(uow, user_id)
            was_admin = user.can(Permission.USERS_MANAGE)
            changes: dict[str, object] = {}

            if email is not None or full_name is not None:
                new_email = normalize_email(email) if email is not None else user.email
                if new_email != user.email:
                    existing = await uow.users.get_by_email(new_email)
                    if existing and existing.id != user.id:
                        raise ConflictError("Ya existe un usuario con ese correo.")
                    changes["email"] = new_email
                if full_name is not None and full_name != user.full_name:
                    changes["full_name"] = full_name
                user.update_profile(email=new_email, full_name=full_name or user.full_name, now=now)

            if role_id is not None and role_id != user.role.id:
                role = await _get_role(uow, role_id)
                if user.id == actor.id and not role.has(Permission.USERS_MANAGE):
                    raise ValidationError("No puedes quitarte a ti mismo la administración.")
                changes["role"] = {"from": user.role.name, "to": role.name}
                user.change_role(role, now)

            if is_active is not None and is_active != user.is_active:
                if user.id == actor.id and not is_active:
                    raise ValidationError("No puedes desactivar tu propio usuario.")
                changes["is_active"] = is_active
                user.set_active(is_active, now)
                if not is_active:
                    await uow.sessions.revoke_all_for_user(user.id, now)

            if was_admin and not user.can(Permission.USERS_MANAGE):
                remaining = await uow.users.count_active_with_permission(Permission.USERS_MANAGE)
                if remaining <= 1:
                    raise ConflictError("No se puede dejar el sistema sin administradores.")

            if changes:
                await uow.users.save(user)
                await audit(
                    uow,
                    AuditAction.USER_UPDATED,
                    actor=actor,
                    entity_type="user",
                    entity_id=user.id,
                    ctx=ctx,
                    now=now,
                    changes=changes,
                )
                await uow.commit()
            return user


class ResetUserPassword(_UserAdminUseCase):
    async def execute(
        self, actor: User, user_id: UUID, new_password: str, ctx: RequestContext
    ) -> None:
        require(actor, Permission.USERS_MANAGE)
        validate_password(new_password)
        now = self._clock.now()
        async with self._uow() as uow:
            user = await _get_user(uow, user_id)
            user.set_password_hash(self._hasher.hash(new_password), now)
            await uow.users.save(user)
            await uow.sessions.revoke_all_for_user(user.id, now)
            await audit(
                uow,
                AuditAction.USER_PASSWORD_RESET,
                actor=actor,
                entity_type="user",
                entity_id=user.id,
                ctx=ctx,
                now=now,
            )
            await uow.commit()


class ExportUsers(UseCase):
    HEADERS = ("Nombre", "Correo", "Rol", "Activo", "Último acceso", "Creado")

    async def execute(
        self, actor: User, filters: UserFilters, ctx: RequestContext
    ) -> TabularExport:
        require(actor, Permission.USERS_MANAGE, Permission.EXPORT_CSV)
        now = self._clock.now()
        async with self._uow() as uow:
            await audit(
                uow,
                AuditAction.USERS_EXPORTED,
                actor=actor,
                entity_type="user",
                entity_id=None,
                ctx=ctx,
                now=now,
            )
            await uow.commit()

        async def rows() -> AsyncIterator[Sequence[Cell]]:
            async with self._uow() as read_uow:
                async for u in read_uow.users.iter_all(filters):
                    yield (
                        u.full_name,
                        u.email,
                        u.role.name,
                        "Sí" if u.is_active else "No",
                        u.last_login_at,
                        u.created_at,
                    )

        return TabularExport(filename_prefix="usuarios", headers=self.HEADERS, rows=rows())
