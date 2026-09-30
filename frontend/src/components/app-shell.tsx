"use client";

import {
  ClipboardList,
  Eye,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  PlusCircle,
  ScrollText,
  ShieldCheck,
  Sun,
  UserCog,
  Users,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";
import type { Permission } from "@/lib/api/types";
import { PERM, ROLE_TONE } from "@/lib/labels";
import { cn, initials } from "@/lib/utils";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  /** Sin permisos = visible para cualquier usuario autenticado. */
  anyOf?: Permission[];
}

function isActive(href: string, pathname: string): boolean {
  if (href === "/tickets") {
    return pathname === "/tickets" || (/^\/tickets\/[^/]+$/.test(pathname) && pathname !== "/tickets/new");
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

const MAIN_NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, anyOf: [PERM.dashboard] },
  {
    href: "/tickets",
    label: "Tickets",
    icon: ClipboardList,
    anyOf: [PERM.ticketsReadAll, PERM.ticketsReadOwn],
  },
  { href: "/tickets/new", label: "Nuevo ticket", icon: PlusCircle, anyOf: [PERM.ticketsCreate] },
];

const ADMIN_NAV: NavItem[] = [
  { href: "/admin/users", label: "Usuarios", icon: Users, anyOf: [PERM.users] },
  { href: "/admin/roles", label: "Roles y permisos", icon: ShieldCheck, anyOf: [PERM.roles] },
  { href: "/admin/logs", label: "Bitácora", icon: ScrollText, anyOf: [PERM.logs] },
];

function NavLinks({ items, onNavigate }: { items: NavItem[]; onNavigate: () => void }) {
  const pathname = usePathname();
  const { can } = useAuth();
  const visible = items.filter((item) => !item.anyOf || item.anyOf.some(can));
  if (!visible.length) return null;
  return (
    <ul className="grid gap-0.5">
      {visible.map(({ href, label, icon: Icon }) => {
        const active = isActive(href, pathname);
        return (
          <li key={href}>
            <Link
              href={href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-muted transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground",
                active && "bg-sidebar-accent font-medium text-sidebar-foreground",
              )}
            >
              <Icon className="size-4" />
              {label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const dark = resolvedTheme === "dark";
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(dark ? "light" : "dark")}
      aria-label={dark ? "Usar tema claro" : "Usar tema oscuro"}
    >
      {dark ? <Sun /> : <Moon />}
    </Button>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, can, logout } = useAuth();
  const [open, setOpen] = useState(false);
  if (!user) return null;

  const readOnly = !can(PERM.ticketsCreate) && !can(PERM.ticketsManage) && !can(PERM.ticketsWork);
  const hasAdmin = ADMIN_NAV.some((i) => i.anyOf?.some(can));

  const sidebar = (
    <nav className="flex h-full flex-col gap-6 bg-sidebar px-3 py-5 text-sidebar-foreground">
      <div className="flex items-center gap-2 px-3">
        <div className="grid size-8 place-items-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
          TI
        </div>
        <div className="leading-tight">
          <p className="text-sm font-semibold">Helpdesk TI</p>
          <p className="text-[11px] text-sidebar-muted">Mesa de ayuda</p>
        </div>
      </div>
      <NavLinks items={MAIN_NAV} onNavigate={() => setOpen(false)} />
      {hasAdmin && (
        <div className="grid gap-2">
          <p className="px-3 text-[11px] font-semibold uppercase tracking-wider text-sidebar-muted">
            Administración
          </p>
          <NavLinks items={ADMIN_NAV} onNavigate={() => setOpen(false)} />
        </div>
      )}
      <div className="mt-auto">
        <NavLinks
          items={[{ href: "/profile", label: "Mi cuenta", icon: UserCog }]}
          onNavigate={() => setOpen(false)}
        />
      </div>
    </nav>
  );

  return (
    <div className="flex min-h-dvh">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64">{sidebar}</aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/85 px-4 backdrop-blur lg:px-8">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setOpen((v) => !v)}
            aria-label="Menú"
          >
            {open ? <X /> : <Menu />}
          </Button>
          <div className="ml-auto flex items-center gap-2">
            <span
              className={cn(
                "rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize",
                ROLE_TONE[user.role.name] ?? "bg-secondary text-secondary-foreground",
              )}
              data-testid="role-badge"
            >
              {user.role.name}
            </span>
            <ThemeToggle />
            <div className="hidden items-center gap-2 sm:flex">
              <div className="grid size-8 place-items-center rounded-full bg-muted text-xs font-semibold">
                {initials(user.full_name)}
              </div>
              <div className="leading-tight">
                <p className="text-sm font-medium">{user.full_name}</p>
                <p className="text-xs text-muted-foreground">{user.email}</p>
              </div>
            </div>
            <Button variant="ghost" size="icon" onClick={() => void logout()} aria-label="Cerrar sesión">
              <LogOut />
            </Button>
          </div>
        </header>
        {readOnly && (
          <div className="flex items-center gap-2 border-b border-amber-300/60 bg-amber-50 px-4 py-2 text-xs text-amber-900 lg:px-8 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
            <Eye className="size-3.5" />
            <span>
              <strong>Modo solo lectura.</strong>{" "}
              {user.role.single_tab_session && "Tu sesión está limitada a una sola pestaña del navegador."}
            </span>
          </div>
        )}
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
