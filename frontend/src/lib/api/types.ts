import type { components } from "./schema";

type S = components["schemas"];

export type Me = S["MeOut"];
export type TokenOut = S["TokenOut"];
export type Permission = Me["permissions"][number];
export type TicketStatus = S["TicketItemOut"]["status"];
export type Priority = S["TicketItemOut"]["priority"];
export type TicketItem = S["TicketItemOut"];
export type TicketDetail = S["TicketDetailOut"];
export type TicketEvent = S["TicketEventOut"];
export type Person = S["PersonOut"];
export type Category = S["CategoryOut"];
export type Dashboard = S["DashboardOut"];
export type User = S["UserOut"];
export type Role = S["RoleOut"];
export type PermissionInfo = S["PermissionOut"];
export type LoginEvent = S["LoginEventOut"];
export type AuditLog = S["AuditLogOut"];
export type TabStatus = S["TabStatusOut"];
export type ErrorOut = S["ErrorOut"];

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
