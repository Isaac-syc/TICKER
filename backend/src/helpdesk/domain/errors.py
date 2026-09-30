"""Errores del dominio. Los adaptadores de entrada los traducen a su protocolo (p. ej. HTTP)."""


class DomainError(Exception):
    code = "domain_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFoundError(DomainError):
    code = "not_found"


class PermissionDeniedError(DomainError):
    code = "permission_denied"

    def __init__(self, message: str = "No tienes permiso para realizar esta acción.") -> None:
        super().__init__(message)


class ConflictError(DomainError):
    code = "conflict"


class ValidationError(DomainError):
    code = "validation_error"


class InvalidTransitionError(DomainError):
    code = "invalid_transition"


class AuthenticationError(DomainError):
    code = "authentication_failed"


class TooManyAttemptsError(DomainError):
    code = "too_many_attempts"


class TabConflictError(DomainError):
    code = "tab_conflict"
