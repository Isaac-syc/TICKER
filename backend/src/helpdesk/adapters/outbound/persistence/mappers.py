from helpdesk.adapters.outbound.persistence.models import (
    RoleModel,
    TicketEventModel,
    TicketModel,
    UserModel,
)
from helpdesk.domain.identity.entities import Role, User
from helpdesk.domain.identity.permissions import Permission
from helpdesk.domain.tickets.entities import Ticket, TicketEvent
from helpdesk.domain.tickets.workflow import Priority, TicketStatus

_KNOWN_PERMISSIONS = {p.value for p in Permission}


def role_to_domain(model: RoleModel) -> Role:
    return Role(
        id=model.id,
        name=model.name,
        description=model.description,
        # Se ignoran permisos que existan en BD pero ya no en el código.
        permissions=frozenset(
            Permission(link.permission_code)
            for link in model.permission_links
            if link.permission_code in _KNOWN_PERMISSIONS
        ),
        single_tab_session=model.single_tab_session,
        is_system=model.is_system,
    )


def user_to_domain(model: UserModel) -> User:
    return User(
        id=model.id,
        email=model.email,
        full_name=model.full_name,
        password_hash=model.password_hash,
        role=role_to_domain(model.role),
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
        last_login_at=model.last_login_at,
    )


def apply_user(model: UserModel, user: User) -> None:
    model.email = user.email
    model.full_name = user.full_name
    model.password_hash = user.password_hash
    model.role_id = user.role.id
    model.is_active = user.is_active
    model.last_login_at = user.last_login_at
    model.created_at = user.created_at
    model.updated_at = user.updated_at


def ticket_to_domain(model: TicketModel) -> Ticket:
    return Ticket(
        id=model.id,
        number=model.number,
        title=model.title,
        description=model.description,
        category_id=model.category_id,
        priority=Priority(model.priority),
        status=TicketStatus(model.status),
        requester_id=model.requester_id,
        assignee_id=model.assignee_id,
        due_at=model.due_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
        resolved_at=model.resolved_at,
        closed_at=model.closed_at,
    )


def apply_ticket(model: TicketModel, ticket: Ticket) -> None:
    model.title = ticket.title
    model.description = ticket.description
    model.category_id = ticket.category_id
    model.priority = ticket.priority.value
    model.status = ticket.status.value
    model.requester_id = ticket.requester_id
    model.assignee_id = ticket.assignee_id
    model.due_at = ticket.due_at
    model.created_at = ticket.created_at
    model.updated_at = ticket.updated_at
    model.resolved_at = ticket.resolved_at
    model.closed_at = ticket.closed_at


def event_to_model(event: TicketEvent) -> TicketEventModel:
    return TicketEventModel(
        id=event.id,
        ticket_id=event.ticket_id,
        actor_id=event.actor_id,
        type=event.type.value,
        from_status=event.from_status.value if event.from_status else None,
        to_status=event.to_status.value if event.to_status else None,
        comment=event.comment,
        data=event.data,
        created_at=event.created_at,
    )
