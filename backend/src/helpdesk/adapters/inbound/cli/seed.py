"""Seed idempotente: se puede correr en cada despliegue (lo hace el servicio `migrate`)."""

import random
import unicodedata
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from faker import Faker
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from helpdesk.adapters.outbound.clock import SystemClock
from helpdesk.adapters.outbound.persistence.database import create_engine, create_session_factory
from helpdesk.adapters.outbound.persistence.models import (
    CategoryModel,
    PermissionModel,
    TicketModel,
)
from helpdesk.adapters.outbound.persistence.uow import SqlAlchemyUnitOfWork
from helpdesk.adapters.outbound.security import Argon2PasswordHasher
from helpdesk.config import Settings
from helpdesk.domain.identity.entities import Role, User
from helpdesk.domain.identity.permissions import ALL_PERMISSIONS, PERMISSION_INFO, Permission
from helpdesk.domain.tickets.entities import Ticket
from helpdesk.domain.tickets.sla import SlaPolicy
from helpdesk.domain.tickets.workflow import Priority, TicketStatus

log = structlog.get_logger("helpdesk.seed")
P = Permission

BASE_ROLES: list[tuple[str, str, frozenset[Permission], bool]] = [
    ("admin", "Administrador: acceso total", ALL_PERMISSIONS, False),
    (
        "usuario",
        "Usuario: crea tickets y atiende los que tiene asignados",
        frozenset(
            {
                P.TICKETS_CREATE,
                P.TICKETS_READ_OWN,
                P.TICKETS_WORK,
                P.TICKETS_COMMENT,
                P.DASHBOARD_VIEW,
                P.EXPORT_CSV,
            }
        ),
        False,
    ),
    (
        "observador",
        "Observador: solo lectura, limitado a una pestaña",
        frozenset({P.TICKETS_READ_ALL, P.DASHBOARD_VIEW, P.EXPORT_CSV}),
        True,
    ),
]

CATEGORIES = ["Hardware", "Software", "Red", "Accesos y cuentas", "Correo", "Impresoras", "Otro"]

TITLES: dict[str, list[str]] = {
    "Hardware": [
        "Laptop no enciende",
        "Monitor parpadea constantemente",
        "Teclado con teclas que no responden",
        "Solicitud de equipo nuevo para ingreso",
        "Batería de laptop no carga",
    ],
    "Software": [
        "Error al abrir el ERP",
        "Instalación de Office",
        "Actualización de antivirus falla",
        "Licencia de Adobe vencida",
        "El sistema de nómina se congela",
    ],
    "Red": [
        "Sin acceso a internet en piso 3",
        "VPN se desconecta cada 10 minutos",
        "Wi-Fi de sala de juntas lento",
        "No hay acceso a carpeta compartida",
    ],
    "Accesos y cuentas": [
        "Restablecer contraseña de dominio",
        "Alta de usuario en Active Directory",
        "Permisos para carpeta de Finanzas",
        "Cuenta bloqueada por intentos fallidos",
    ],
    "Correo": [
        "No llegan correos externos",
        "Buzón lleno, solicitar ampliación",
        "Configurar correo en celular",
    ],
    "Impresoras": [
        "Impresora de recepción atascada",
        "No aparece la impresora en red",
        "Solicitud de tóner",
    ],
    "Otro": ["Asesoría para videoconferencia", "Mover equipo de lugar", "Solicitud de diadema"],
}

PRIORITY_WEIGHTS = [
    (Priority.LOW, 25),
    (Priority.MEDIUM, 40),
    (Priority.HIGH, 25),
    (Priority.CRITICAL, 10),
]


async def run_seed(settings: Settings) -> None:
    engine = create_engine(settings.database_url, pool_size=2)
    factory = create_session_factory(engine)
    tz = ZoneInfo(settings.app_timezone)
    hasher = Argon2PasswordHasher()
    clock = SystemClock()
    try:
        # 1) Catálogo de permisos (sincronizado con el código)
        async with factory() as s:
            stmt = insert(PermissionModel).values(
                [
                    {"code": p.value, "group_name": g, "description": d}
                    for p, (g, d) in PERMISSION_INFO.items()
                ]
            )
            await s.execute(
                stmt.on_conflict_do_update(
                    index_elements=[PermissionModel.code],
                    set_={
                        "group_name": stmt.excluded.group_name,
                        "description": stmt.excluded.description,
                    },
                )
            )
            # 2) Categorías
            existing = set((await s.scalars(select(CategoryModel.name))).all())
            for order, name in enumerate(CATEGORIES):
                if name not in existing:
                    s.add(CategoryModel(name=name, sort_order=order))
            await s.commit()

        # 3) Roles base y usuarios demo
        async with SqlAlchemyUnitOfWork(factory, tz) as uow:
            roles: dict[str, Role] = {}
            for name, description, perms, single_tab in BASE_ROLES:
                role = await uow.roles.get_by_name(name)
                if role is None:
                    role = Role.create(
                        name=name,
                        description=description,
                        permissions=perms,
                        single_tab_session=single_tab,
                        is_system=True,
                    )
                    await uow.roles.add(role)
                    log.info("seed_role_created", role=name)
                elif name == "admin" and role.permissions != ALL_PERMISSIONS:
                    role.permissions = ALL_PERMISSIONS  # permisos nuevos del código
                    await uow.roles.save(role)
                roles[name] = role

            now = clock.now()
            demo_users = [
                (
                    settings.seed_admin_email,
                    "Ana Administradora",
                    "admin",
                    settings.seed_admin_password,
                ),
                (
                    settings.seed_user_email,
                    "Ulises Usuario",
                    "usuario",
                    settings.seed_user_password,
                ),
                (
                    settings.seed_observer_email,
                    "Olga Observadora",
                    "observador",
                    settings.seed_observer_password,
                ),
            ]
            for email, full_name, role_name, password in demo_users:
                if password is None or await uow.users.get_by_email(email):
                    continue
                user = User.register(
                    email=email,
                    full_name=full_name,
                    password_hash=hasher.hash(password.get_secret_value()),
                    role=roles[role_name],
                    now=now,
                )
                await uow.users.add(user)
                log.info("seed_user_created", email=email, role=role_name)
            await uow.commit()

        if settings.seed_demo_data:
            await _seed_demo_tickets(settings, factory, tz, hasher, clock)
        log.info("seed_done")
    finally:
        await engine.dispose()


async def _seed_demo_tickets(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    tz: ZoneInfo,
    hasher: Argon2PasswordHasher,
    clock: SystemClock,
) -> None:
    async with session_factory() as s:
        if (await s.scalar(select(func.count(TicketModel.id)))) or not settings.seed_user_password:
            log.info("seed_demo_skipped", reason="ya hay tickets o falta SEED_USER_PASSWORD")
            return
        categories = {m.name: m.id for m in await s.scalars(select(CategoryModel))}

    rng = random.Random(2026)
    fake = Faker("es_MX")
    Faker.seed(2026)
    sla = SlaPolicy(
        settings.sla_critical_hours,
        settings.sla_high_hours,
        settings.sla_medium_hours,
        settings.sla_low_hours,
    )
    now = clock.now()
    password_hash = hasher.hash(settings.seed_user_password.get_secret_value())

    async with SqlAlchemyUnitOfWork(session_factory, tz) as uow:
        admin = await uow.users.get_by_email(settings.seed_admin_email)
        base_user = await uow.users.get_by_email(settings.seed_user_email)
        usuario_role = await uow.roles.get_by_name("usuario")
        assert admin and base_user and usuario_role

        techs: list[User] = [base_user]
        requesters: list[User] = [base_user]
        for i in range(7):
            first, last = fake.first_name(), fake.last_name()
            email = f"{first}.{last}".lower().replace(" ", "")
            ascii_email = unicodedata.normalize("NFKD", email).encode("ascii", "ignore").decode()
            email = f"{ascii_email}{i}@helpdesk.test"
            user = User.register(
                email=email,
                full_name=f"{first} {last}",
                password_hash=password_hash,
                role=usuario_role,
                now=now - timedelta(days=70),
            )
            await uow.users.add(user)
            (techs if i < 3 else requesters).append(user)

        priorities, weights = zip(*PRIORITY_WEIGHTS, strict=True)
        for _ in range(200):
            category = rng.choice(list(TITLES))
            priority: Priority = rng.choices(priorities, weights)[0]
            age_days = min(60.0, rng.expovariate(1 / 18))
            created = now - timedelta(days=age_days, hours=rng.uniform(0, 8))
            requester = rng.choice(requesters)
            ticket = Ticket.open(
                title=rng.choice(TITLES[category]),
                description=fake.paragraph(nb_sentences=3) + " " + fake.sentence(),
                category_id=categories[category],
                priority=priority,
                requester=requester,
                sla=sla,
                now=created,
            )
            _simulate_lifecycle(ticket, rng, fake, admin, requester, techs, sla, now)
            await uow.tickets.add(ticket)
        await uow.commit()
    log.info("seed_demo_tickets_created", count=200)


def _simulate_lifecycle(
    ticket: Ticket,
    rng: random.Random,
    fake: Faker,
    admin: User,
    requester: User,
    techs: list[User],
    sla: SlaPolicy,
    now: datetime,
) -> None:
    t = ticket.created_at

    def step(hours: float) -> bool:
        nonlocal t
        t = t + timedelta(hours=hours)
        return t < now

    if rng.random() < 0.05 and step(rng.uniform(0.2, 3)):
        ticket.transition(
            TicketStatus.CANCELLED, actor=requester, comment="Ya no es necesario.", now=t
        )
        return
    if not step(rng.uniform(0.1, 4)):
        return
    tech = rng.choice(techs)
    ticket.assign(tech, actor=admin, now=t)
    if not step(rng.uniform(0.1, 3)):
        return
    ticket.transition(TicketStatus.IN_PROGRESS, actor=tech, comment=None, now=t)
    if rng.random() < 0.3 and step(rng.uniform(0.2, 2)):
        ticket.add_comment(fake.sentence(), actor=tech, now=t)
    if rng.random() < 0.2:
        if not step(rng.uniform(0.5, 3)):
            return
        ticket.transition(
            TicketStatus.ON_HOLD, actor=tech, comment="En espera de respuesta del usuario.", now=t
        )
        if not step(rng.uniform(2, 24)):
            return
        ticket.transition(TicketStatus.IN_PROGRESS, actor=tech, comment=None, now=t)
    # ~75 % se resuelve dentro del SLA
    budget = sla.hours_for(ticket.priority)
    target = (
        rng.uniform(0.2, 0.95) * budget if rng.random() < 0.75 else rng.uniform(1.1, 2.5) * budget
    )
    remaining = max(0.2, target - (t - ticket.created_at).total_seconds() / 3600)
    if not step(remaining):
        return
    ticket.transition(
        TicketStatus.RESOLVED, actor=tech, comment="Se aplicó la solución y se validó.", now=t
    )
    if rng.random() < 0.85 and step(rng.uniform(1, 48)):
        ticket.transition(TicketStatus.CLOSED, actor=requester, comment=None, now=t)
