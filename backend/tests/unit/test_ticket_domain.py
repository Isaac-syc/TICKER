from datetime import timedelta

import pytest

from helpdesk.domain.errors import InvalidTransitionError, PermissionDeniedError, ValidationError
from helpdesk.domain.tickets.entities import Ticket, TicketEventType
from helpdesk.domain.tickets.workflow import Priority, TicketStatus
from tests.unit.conftest import World

S = TicketStatus


def open_ticket(w: World, priority: Priority = Priority.HIGH) -> Ticket:
    return Ticket.open(
        title="Laptop no enciende",
        description="Desde esta mañana no prende la laptop.",
        category_id=1,
        priority=priority,
        requester=w.user,
        sla=w.sla,
        now=w.clock.now(),
    )


def test_open_sets_sla_and_records_event(world: World) -> None:
    t = open_ticket(world, Priority.CRITICAL)
    assert t.status == S.OPEN
    assert t.due_at == world.clock.now() + timedelta(hours=4)
    events = t.pull_events()
    assert [e.type for e in events] == [TicketEventType.CREATED]
    assert t.pull_events() == []


def test_observer_cannot_create_tickets(world: World) -> None:
    with pytest.raises(PermissionDeniedError):
        Ticket.open(
            title="Algo",
            description="Descripción larga",
            category_id=1,
            priority=Priority.LOW,
            requester=world.observer,
            sla=world.sla,
            now=world.clock.now(),
        )


def test_title_and_description_are_validated(world: World) -> None:
    with pytest.raises(ValidationError):
        Ticket.open(
            title="  ",
            description="Descripción suficiente",
            category_id=1,
            priority=Priority.LOW,
            requester=world.user,
            sla=world.sla,
            now=world.clock.now(),
        )


def test_full_happy_path_with_assignee_and_requester(world: World) -> None:
    t = open_ticket(world)
    t.assign(world.tech, actor=world.admin, now=world.clock.now())
    t.transition(S.IN_PROGRESS, actor=world.tech, comment=None, now=world.clock.now())
    t.transition(S.ON_HOLD, actor=world.tech, comment="Esperando pieza", now=world.clock.now())
    t.transition(S.IN_PROGRESS, actor=world.tech, comment=None, now=world.clock.now())
    world.clock.advance(hours=2)
    t.transition(
        S.RESOLVED, actor=world.tech, comment="Se cambió la batería", now=world.clock.now()
    )
    assert t.resolved_at == world.clock.now()
    t.transition(S.CLOSED, actor=world.user, comment=None, now=world.clock.now())
    assert t.status == S.CLOSED
    assert t.closed_at is not None
    assert t.allowed_transitions_for(world.admin) == []


def test_invalid_transition_is_rejected(world: World) -> None:
    t = open_ticket(world)
    with pytest.raises(InvalidTransitionError):
        t.transition(S.RESOLVED, actor=world.admin, comment="x", now=world.clock.now())


def test_comment_required_for_on_hold_and_resolved(world: World) -> None:
    t = open_ticket(world)
    t.transition(S.IN_PROGRESS, actor=world.admin, comment=None, now=world.clock.now())
    with pytest.raises(ValidationError):
        t.transition(S.ON_HOLD, actor=world.admin, comment="  ", now=world.clock.now())


def test_non_assignee_cannot_work_ticket(world: World) -> None:
    t = open_ticket(world)
    t.assign(world.tech, actor=world.admin, now=world.clock.now())
    # el solicitante no puede ponerlo en progreso, solo el asignado o un admin
    assert S.IN_PROGRESS not in t.allowed_transitions_for(world.user)
    with pytest.raises(PermissionDeniedError):
        t.transition(S.IN_PROGRESS, actor=world.user, comment=None, now=world.clock.now())
    with pytest.raises(PermissionDeniedError):
        t.transition(S.IN_PROGRESS, actor=world.observer, comment=None, now=world.clock.now())


def test_requester_can_cancel_open_and_reopen_resolved(world: World) -> None:
    t = open_ticket(world)
    assert world.user.id == t.requester_id
    assert t.allowed_transitions_for(world.user) == [S.CANCELLED]

    t2 = open_ticket(world)
    t2.assign(world.tech, actor=world.admin, now=world.clock.now())
    t2.transition(S.IN_PROGRESS, actor=world.tech, comment=None, now=world.clock.now())
    t2.transition(S.RESOLVED, actor=world.tech, comment="Listo", now=world.clock.now())
    t2.transition(S.IN_PROGRESS, actor=world.user, comment="Sigue fallando", now=world.clock.now())
    assert t2.resolved_at is None


def test_only_managers_assign_and_only_to_workers(world: World) -> None:
    t = open_ticket(world)
    with pytest.raises(PermissionDeniedError):
        t.assign(world.tech, actor=world.user, now=world.clock.now())
    with pytest.raises(ValidationError):
        t.assign(world.observer, actor=world.admin, now=world.clock.now())


def test_overdue_and_visibility(world: World) -> None:
    t = open_ticket(world, Priority.HIGH)
    assert not t.is_overdue(world.clock.now())
    world.clock.advance(hours=9)
    assert t.is_overdue(world.clock.now())

    assert t.can_be_viewed_by(world.user)  # solicitante
    assert t.can_be_viewed_by(world.observer)  # read_all
    assert not t.can_be_viewed_by(world.tech)  # aún no asignado
    t.assign(world.tech, actor=world.admin, now=world.clock.now())
    assert t.can_be_viewed_by(world.tech)


def test_priority_change_recalculates_due_date(world: World) -> None:
    t = open_ticket(world, Priority.LOW)
    t.edit(actor=world.user, sla=world.sla, now=world.clock.now(), priority=Priority.CRITICAL)
    assert t.due_at == t.created_at + timedelta(hours=4)
    t.transition(S.IN_PROGRESS, actor=world.admin, comment=None, now=world.clock.now())
    with pytest.raises(PermissionDeniedError):  # el solicitante ya no edita fuera de ABIERTO
        t.edit(actor=world.user, sla=world.sla, now=world.clock.now(), title="Nuevo título")
