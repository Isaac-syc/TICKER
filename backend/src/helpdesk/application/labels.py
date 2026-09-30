"""Etiquetas en español para reportes (CSV y dashboard)."""

from helpdesk.domain.tickets.workflow import Priority, TicketStatus

STATUS_LABELS: dict[TicketStatus, str] = {
    TicketStatus.OPEN: "Abierto",
    TicketStatus.IN_PROGRESS: "En progreso",
    TicketStatus.ON_HOLD: "En espera",
    TicketStatus.RESOLVED: "Resuelto",
    TicketStatus.CLOSED: "Cerrado",
    TicketStatus.CANCELLED: "Cancelado",
}

PRIORITY_LABELS: dict[Priority, str] = {
    Priority.LOW: "Baja",
    Priority.MEDIUM: "Media",
    Priority.HIGH: "Alta",
    Priority.CRITICAL: "Crítica",
}
