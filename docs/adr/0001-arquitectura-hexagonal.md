# ADR 0001: Arquitectura hexagonal en el backend

**Estado:** aceptado

## Contexto
La prueba pide arquitectura hexagonal. Además, el dominio tiene reglas no triviales: máquina de estados, quién puede mover cada transición, SLA, sesión única por pestaña y protección contra quedarse sin administradores. Esas reglas deben probarse sin levantar infraestructura.

## Decisión
- **`domain/`**: entidades y reglas puras (`Ticket`, `User`, `Role`, `AuthSession`). No importa ningún framework.
- **`application/`**: casos de uso más **puertos** (`Protocol`s): repositorios, `UnitOfWork`, `TokenService`, `PasswordHasher`, `TabLeaseStore`, `LoginRateLimiter`, `Clock`, y consultas de lectura separadas (`TicketQueries`, `TicketAnalytics`, `LogQueries`), un CQRS ligero.
- **`adapters/inbound`**: HTTP (FastAPI) y CLI (seed). Traducen protocolo ↔ caso de uso y errores de dominio ↔ códigos HTTP.
- **`adapters/outbound`**: SQLAlchemy, Redis, PyJWT, argon2, CSV y structlog.
- **`container.py`**: composition root con inyección manual. Es el único lugar que conoce las clases concretas.
- **import-linter** hace cumplir en CI que las dependencias solo apunten hacia adentro y que `domain` y `application` no importen frameworks.

## Consecuencias
- Los casos de uso se prueban con fakes en memoria (`tests/unit/fakes.py`) en menos de un segundo.
- Cambiar Redis por otra cosa, o JWT por sesiones opacas, solo toca un adaptador.
- A cambio, hay más archivos y mapeos (ORM ↔ dominio). Para las lecturas pesadas (listas y dashboard), las consultas devuelven *read models* directamente, sin hidratar entidades.
