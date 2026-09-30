# ADR 0004: Migraciones con Alembic ejecutadas por un servicio `migrate`

**Estado:** aceptado

## Contexto
¿Conviene crear el esquema con scripts en `docker-entrypoint-initdb.d` o con migraciones?

## Decisión
**Alembic**. Las migraciones las ejecuta un servicio `migrate` de una sola ejecución, que usa la misma imagen que la API:

```
db (healthy) → migrate: alembic upgrade head + seed idempotente → api (arranca solo si migrate terminó OK)
```

## Por qué no `docker-entrypoint-initdb.d`
- Esos scripts solo corren cuando el volumen está vacío. Un cambio de esquema posterior nunca se aplicaría.
- No tienen versionado, `downgrade` ni forma de detectar *drift*.

## Beneficios
- En CD el mismo job corre **antes** de actualizar la app. Si falla, la versión anterior sigue sirviendo.
- En CI, `alembic check` falla si los modelos y las migraciones divergen. Las pruebas de API ejecutan `upgrade → downgrade → upgrade` sobre una BD real.
- La API nunca corre migraciones al arrancar, así que con varias réplicas no hay carreras.
- El seed es idempotente: sincroniza el catálogo de permisos con el código y garantiza que el rol `admin` tenga todos los permisos nuevos.
