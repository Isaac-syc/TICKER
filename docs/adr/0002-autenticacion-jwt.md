# ADR 0002: JWT con refresh tokens rotativos

**Estado:** aceptado

## Decisión
- **Access token**: JWT HS256 de 15 min con `sub`, `sid`, `role`, `perms` y `stt`. El front lo guarda **solo en memoria** (nunca en `localStorage`) y lo manda como `Bearer`.
- **Refresh token**: valor aleatorio de 48 bytes en una cookie `httpOnly; SameSite=Strict; Path=/api/v1/auth` (más `Secure` en producción). En BD se guarda solo su SHA-256.
- **Rotación**: cada refresh emite un token nuevo y revoca el anterior. Todas las rotaciones de un login comparten `family_id`, que es el `sid` del JWT.
- **Detección de reuso**: si llega un refresh ya rotado **fuera de una ventana de gracia de 30 s**, se asume robo y se revoca toda la familia (queda en auditoría). La ventana y un Web Lock en el front (`hd-refresh`) evitan falsos positivos cuando dos pestañas refrescan a la vez.
- **Permisos siempre frescos**: en cada petición se recarga el usuario y se verifica que su familia de sesión siga activa. Desactivar un usuario, cambiar su rol o hacer logout surte efecto de inmediato, sin esperar a que expire el JWT.
- **CSRF**: los endpoints que usan la cookie exigen el header `X-Requested-With: helpdesk`. Como no se habilita CORS, un sitio externo no puede enviarlo.
- **Login**: argon2id, mensajes genéricos, verificación contra un hash señuelo si el correo no existe (evita enumeración por tiempo), bloqueo temporal tras N fallos (Redis) y registro de cada intento en `login_events`.

## Alternativas descartadas
- **JWT en `localStorage`**: expuesto a XSS.
- **JWT sin estado y sin revocación**: no permite logout real ni desactivar usuarios al instante.
