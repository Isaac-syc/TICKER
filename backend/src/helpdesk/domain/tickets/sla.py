from dataclasses import dataclass
from datetime import datetime, timedelta

from helpdesk.domain.tickets.workflow import Priority


@dataclass(frozen=True)
class SlaPolicy:
    """Horas máximas de resolución por prioridad."""

    critical_hours: int = 4
    high_hours: int = 8
    medium_hours: int = 24
    low_hours: int = 72

    def hours_for(self, priority: Priority) -> int:
        return {
            Priority.CRITICAL: self.critical_hours,
            Priority.HIGH: self.high_hours,
            Priority.MEDIUM: self.medium_hours,
            Priority.LOW: self.low_hours,
        }[priority]

    def due_at(self, priority: Priority, opened_at: datetime) -> datetime:
        return opened_at + timedelta(hours=self.hours_for(priority))
