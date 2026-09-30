"""Máquina de estados de los tickets y reglas de quién puede mover cada transición."""

from enum import StrEnum


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    ON_HOLD = "ON_HOLD"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class Priority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


PRIORITY_RANK: dict[Priority, int] = {
    Priority.LOW: 1,
    Priority.MEDIUM: 2,
    Priority.HIGH: 3,
    Priority.CRITICAL: 4,
}

Transition = tuple[TicketStatus, TicketStatus]

TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    TicketStatus.OPEN: frozenset({TicketStatus.IN_PROGRESS, TicketStatus.CANCELLED}),
    TicketStatus.IN_PROGRESS: frozenset({TicketStatus.ON_HOLD, TicketStatus.RESOLVED}),
    TicketStatus.ON_HOLD: frozenset({TicketStatus.IN_PROGRESS}),
    TicketStatus.RESOLVED: frozenset({TicketStatus.CLOSED, TicketStatus.IN_PROGRESS}),
    TicketStatus.CLOSED: frozenset(),
    TicketStatus.CANCELLED: frozenset(),
}

ACTIVE_STATUSES: frozenset[TicketStatus] = frozenset(
    {TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.ON_HOLD}
)
FINAL_STATUSES: frozenset[TicketStatus] = frozenset({TicketStatus.CLOSED, TicketStatus.CANCELLED})

# Estados destino que exigen comentario (motivo de espera / resolución aplicada).
REQUIRES_COMMENT: frozenset[TicketStatus] = frozenset({TicketStatus.ON_HOLD, TicketStatus.RESOLVED})

# Transiciones que puede hacer quien atiende el ticket (asignado con tickets:work).
ASSIGNEE_TRANSITIONS: frozenset[Transition] = frozenset(
    {
        (TicketStatus.OPEN, TicketStatus.IN_PROGRESS),
        (TicketStatus.IN_PROGRESS, TicketStatus.ON_HOLD),
        (TicketStatus.ON_HOLD, TicketStatus.IN_PROGRESS),
        (TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED),
    }
)

# Transiciones que puede hacer quien levantó el ticket.
REQUESTER_TRANSITIONS: frozenset[Transition] = frozenset(
    {
        (TicketStatus.OPEN, TicketStatus.CANCELLED),
        (TicketStatus.RESOLVED, TicketStatus.CLOSED),
        (TicketStatus.RESOLVED, TicketStatus.IN_PROGRESS),  # reabrir
    }
)


def is_valid_transition(source: TicketStatus, target: TicketStatus) -> bool:
    return target in TRANSITIONS[source]
