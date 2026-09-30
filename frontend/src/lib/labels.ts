import type { Permission, Priority, TicketStatus } from "@/lib/api/types";

export const STATUS_LABEL: Record<TicketStatus, string> = {
  OPEN: "Abierto",
  IN_PROGRESS: "En progreso",
  ON_HOLD: "En espera",
  RESOLVED: "Resuelto",
  CLOSED: "Cerrado",
  CANCELLED: "Cancelado",
};

/** Verbo del botón para mover a cada estatus. */
export const TRANSITION_LABEL: Record<TicketStatus, string> = {
  OPEN: "Reabrir",
  IN_PROGRESS: "Trabajar",
  ON_HOLD: "Poner en espera",
  RESOLVED: "Resolver",
  CLOSED: "Cerrar",
  CANCELLED: "Cancelar",
};

export const REQUIRES_COMMENT: TicketStatus[] = ["ON_HOLD", "RESOLVED"];

export const STATUS_ORDER: TicketStatus[] = [
  "OPEN",
  "IN_PROGRESS",
  "ON_HOLD",
  "RESOLVED",
  "CLOSED",
  "CANCELLED",
];

export const STATUS_TONE: Record<TicketStatus, string> = {
  OPEN: "bg-sky-100 text-sky-800 ring-sky-600/20 dark:bg-sky-500/15 dark:text-sky-300",
  IN_PROGRESS:
    "bg-violet-100 text-violet-800 ring-violet-600/20 dark:bg-violet-500/15 dark:text-violet-300",
  ON_HOLD: "bg-amber-100 text-amber-800 ring-amber-600/20 dark:bg-amber-500/15 dark:text-amber-300",
  RESOLVED:
    "bg-emerald-100 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-500/15 dark:text-emerald-300",
  CLOSED: "bg-zinc-100 text-zinc-700 ring-zinc-500/20 dark:bg-zinc-500/15 dark:text-zinc-300",
  CANCELLED: "bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/15 dark:text-rose-300",
};

export const PRIORITY_LABEL: Record<Priority, string> = {
  LOW: "Baja",
  MEDIUM: "Media",
  HIGH: "Alta",
  CRITICAL: "Crítica",
};

export const PRIORITY_ORDER: Priority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

export const PRIORITY_TONE: Record<Priority, string> = {
  LOW: "bg-zinc-100 text-zinc-700 ring-zinc-500/20 dark:bg-zinc-500/15 dark:text-zinc-300",
  MEDIUM: "bg-sky-50 text-sky-700 ring-sky-600/20 dark:bg-sky-500/15 dark:text-sky-300",
  HIGH: "bg-orange-100 text-orange-800 ring-orange-600/20 dark:bg-orange-500/15 dark:text-orange-300",
  CRITICAL: "bg-red-100 text-red-800 ring-red-600/25 dark:bg-red-500/20 dark:text-red-300",
};

export const ROLE_TONE: Record<string, string> = {
  admin: "bg-indigo-600 text-white",
  usuario: "bg-teal-600 text-white",
  observador: "bg-amber-500 text-zinc-950",
};

export const PERM = {
  ticketsCreate: "tickets:create",
  ticketsReadOwn: "tickets:read_own",
  ticketsReadAll: "tickets:read_all",
  ticketsWork: "tickets:work",
  ticketsManage: "tickets:manage",
  ticketsComment: "tickets:comment",
  dashboard: "dashboard:view",
  export: "export:csv",
  users: "users:manage",
  roles: "roles:manage",
  logs: "logs:view",
} as const satisfies Record<string, Permission>;

export const AUDIT_ACTION_LABEL: Record<string, string> = {
  "ticket.created": "Ticket creado",
  "ticket.updated": "Ticket editado",
  "ticket.status_changed": "Cambio de estatus",
  "ticket.assigned": "Ticket asignado",
  "ticket.commented": "Comentario",
  "tickets.exported": "Exportación de tickets",
  "user.created": "Usuario creado",
  "user.updated": "Usuario editado",
  "user.password_reset": "Contraseña restablecida",
  "user.password_changed": "Contraseña cambiada",
  "users.exported": "Exportación de usuarios",
  "role.created": "Rol creado",
  "role.updated": "Rol editado",
  "role.deleted": "Rol eliminado",
  "auth.logout": "Cierre de sesión",
  "auth.refresh_reuse_detected": "Reuso de token detectado",
  "auth.session_takeover": "Sesión movida de pestaña",
  "logs.exported": "Exportación de bitácora",
};

export const LOGIN_REASON_LABEL: Record<string, string> = {
  invalid_credentials: "Credenciales inválidas",
  inactive_user: "Usuario desactivado",
  locked: "Bloqueado por intentos",
};
