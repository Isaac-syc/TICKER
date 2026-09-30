import { clsx, type ClassValue } from "clsx";
import { formatDistanceToNowStrict } from "date-fns";
import { es } from "date-fns/locale";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const dateTime = new Intl.DateTimeFormat("es-MX", { dateStyle: "medium", timeStyle: "short" });
const dateOnly = new Intl.DateTimeFormat("es-MX", { dateStyle: "medium" });

export function formatDateTime(value: string | null | undefined): string {
  return value ? dateTime.format(new Date(value)) : "—";
}

export function formatDate(value: string | null | undefined): string {
  return value ? dateOnly.format(new Date(value)) : "—";
}

export function fromNow(value: string | null | undefined): string {
  return value ? formatDistanceToNowStrict(new Date(value), { addSuffix: true, locale: es }) : "—";
}

export function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

/** Fecha local YYYY-MM-DD (para inputs type=date y parámetros de la API). */
export function isoDay(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}
