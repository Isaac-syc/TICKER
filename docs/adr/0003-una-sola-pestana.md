# ADR 0003: Regla de una sola pestaña para el observador

**Estado:** aceptado

## Requisito
Los observadores solo pueden trabajar en una pestaña del navegador. Además se acordó limitarlos a **una sesión activa en total**, y que una segunda pestaña quede **bloqueada con la opción "Usar aquí"**.

## Decisión: dos capas
1. **Navegador (UX inmediata): Web Locks API.**
   - La pestaña pide `navigator.locks.request('hd-single-tab', { ifAvailable: true })`. Si otra pestaña del mismo origen lo tiene, muestra la pantalla de bloqueo.
   - Si la pestaña se cierra o se cae, el navegador libera el lock solo, sin heartbeats ni `beforeunload`.
   - "Usar aquí" usa `{ steal: true }`. La pestaña anterior recibe un `AbortError` y se congela. BroadcastChannel se usa como aviso redundante.
   - El `tabId` vive en memoria y no en `sessionStorage`, porque "Duplicar pestaña" copia el `sessionStorage`.
2. **Servidor (fuente de verdad): lease en Redis.**
   - La clave `hd:tab-lease:{user_id}` guarda `{tab_id, session_id}` con un TTL de 90 s, que se renueva con cada petición y con un heartbeat cada 20 s.
   - Las operaciones son atómicas con scripts Lua.
   - Toda petición de negocio de un rol con `single_tab_session` debe traer `X-Tab-Id` igual al dueño del lease. Si no, responde `409 tab_conflict`.
   - Esto cubre otro navegador u otro dispositivo, y evita saltarse la regla desactivando JS o llamando a la API a mano.
   - "Usar aquí" desde otro dispositivo **revoca la otra sesión** (sesión única) y queda en auditoría.

La regla es un **atributo del rol** (`single_tab_session`), no un `if rol == "observador"`. Se puede activar en cualquier rol desde la pantalla de roles.

## Consecuencias
- El TTL de 90 s tolera el *throttling* de timers en pestañas en segundo plano.
- Si una pestaña se cierra sin liberar el lease (por ejemplo, un crash), "Usar aquí" lo resuelve al instante.
- Si Web Locks no está disponible (contexto no seguro), el front usa solo el lease del servidor.
