"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AppWindow, Lock, Pencil, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { RequirePermission } from "@/components/forbidden";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Checkbox, Field, Input } from "@/components/ui/form";
import { api, ApiError, call } from "@/lib/api/client";
import type { Permission, PermissionInfo, Role } from "@/lib/api/types";
import { PERM } from "@/lib/labels";

function errorText(e: unknown) {
  return e instanceof ApiError ? e.message : "Ocurrió un error inesperado";
}

function groupPermissions(perms: PermissionInfo[]) {
  const groups = new Map<string, PermissionInfo[]>();
  for (const p of perms) groups.set(p.group, [...(groups.get(p.group) ?? []), p]);
  return [...groups.entries()];
}

function RoleDialog({
  role,
  permissions,
  onClose,
}: {
  role: Role | "new";
  permissions: PermissionInfo[];
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const isNew = role === "new";
  const lockedAdmin = !isNew && role.is_system && role.name === "admin";
  const [form, setForm] = useState({
    name: isNew ? "" : role.name,
    description: isNew ? "" : role.description,
    permissions: new Set<Permission>(isNew ? [] : role.permissions),
    single_tab_session: isNew ? false : role.single_tab_session,
  });

  const save = useMutation({
    mutationFn: () => {
      const body = {
        name: form.name,
        description: form.description,
        permissions: [...form.permissions],
        single_tab_session: form.single_tab_session,
      };
      return isNew
        ? call(api.POST("/api/v1/roles", { body }))
        : call(api.PATCH("/api/v1/roles/{role_id}", { params: { path: { role_id: role.id } }, body }));
    },
    onSuccess: () => {
      toast.success(isNew ? "Rol creado" : "Rol actualizado");
      void qc.invalidateQueries({ queryKey: ["roles"] });
      onClose();
    },
    onError: (e) => toast.error(errorText(e)),
  });

  const toggle = (code: Permission) => {
    const next = new Set(form.permissions);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setForm({ ...form, permissions: next });
  };

  return (
    <Dialog
      open
      onClose={onClose}
      className="w-[min(40rem,calc(100vw-2rem))]"
      title={isNew ? "Nuevo rol" : `Editar rol “${role.name}”`}
      description="Los permisos se evalúan en el servidor en cada petición; los cambios aplican de inmediato."
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={() => save.mutate()} loading={save.isPending}>
            Guardar
          </Button>
        </>
      }
    >
      <div className="grid gap-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Nombre" htmlFor="r-name" hint="Minúsculas, números, '-' o '_'">
            <Input
              id="r-name"
              value={form.name}
              disabled={!isNew && role.is_system}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <Field label="Descripción" htmlFor="r-desc">
            <Input id="r-desc" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          </Field>
        </div>
        <Checkbox
          label="Limitar a una sola pestaña y sesión"
          description="El usuario solo podrá trabajar en una pestaña del navegador y en un dispositivo a la vez."
          checked={form.single_tab_session}
          onChange={(e) => setForm({ ...form, single_tab_session: e.target.checked })}
        />
        <div className="grid gap-4">
          {groupPermissions(permissions).map(([group, perms]) => (
            <fieldset key={group} className="grid gap-2.5 rounded-lg border border-border p-3" disabled={lockedAdmin}>
              <legend className="px-1 text-xs font-semibold text-muted-foreground uppercase">{group}</legend>
              {perms.map((p) => (
                <Checkbox
                  key={p.code}
                  label={p.description}
                  description={p.code}
                  checked={form.permissions.has(p.code)}
                  onChange={() => toggle(p.code)}
                />
              ))}
            </fieldset>
          ))}
          {lockedAdmin && (
            <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Lock className="size-3.5" /> El rol admin siempre conserva todos los permisos.
            </p>
          )}
        </div>
      </div>
    </Dialog>
  );
}

function RolesView() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<Role | "new" | null>(null);
  const roles = useQuery({ queryKey: ["roles"], queryFn: () => call(api.GET("/api/v1/roles")) });
  const permissions = useQuery({
    queryKey: ["permissions"],
    queryFn: () => call(api.GET("/api/v1/roles/permissions")),
    staleTime: Infinity,
  });
  const labels = useMemo(
    () => new Map(permissions.data?.map((p) => [p.code, p.description]) ?? []),
    [permissions.data],
  );

  const remove = useMutation({
    mutationFn: (role: Role) =>
      call(api.DELETE("/api/v1/roles/{role_id}", { params: { path: { role_id: role.id } } })),
    onSuccess: () => {
      toast.success("Rol eliminado");
      void qc.invalidateQueries({ queryKey: ["roles"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });

  return (
    <>
      <PageHeader
        title="Roles y permisos"
        description="Los roles agrupan permisos. Crea roles nuevos sin tocar código."
        actions={
          <Button onClick={() => setEditing("new")} disabled={!permissions.data}>
            <Plus /> Nuevo rol
          </Button>
        }
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {roles.isLoading &&
          Array.from({ length: 3 }, (_, i) => <div key={i} className="h-56 animate-pulse rounded-xl bg-muted" />)}
        {roles.data?.map((role) => (
          <Card key={role.id} className="flex flex-col">
            <CardHeader>
              <div className="flex items-start justify-between gap-2">
                <CardTitle className="text-base capitalize">{role.name}</CardTitle>
                <div className="flex gap-1">
                  {role.is_system && <Badge>Sistema</Badge>}
                  {role.single_tab_session && (
                    <Badge className="text-amber-700 dark:text-amber-300">
                      <AppWindow className="size-3" /> 1 pestaña
                    </Badge>
                  )}
                </div>
              </div>
              <CardDescription>{role.description || "Sin descripción"}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-4">
              <ul className="flex flex-wrap gap-1.5">
                {role.permissions.map((p) => (
                  <li key={p} className="rounded bg-muted px-1.5 py-0.5 text-[11px]" title={p}>
                    {labels.get(p) ?? p}
                  </li>
                ))}
                {!role.permissions.length && <li className="text-xs text-muted-foreground">Sin permisos</li>}
              </ul>
              <div className="mt-auto flex items-center justify-between border-t border-border pt-3">
                <span className="text-xs text-muted-foreground">
                  {role.user_count} {role.user_count === 1 ? "usuario" : "usuarios"}
                </span>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => setEditing(role)}>
                    <Pencil /> Editar
                  </Button>
                  {!role.is_system && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-destructive"
                      disabled={role.user_count > 0 || remove.isPending}
                      title={role.user_count > 0 ? "Reasigna sus usuarios antes de eliminarlo" : undefined}
                      onClick={() => {
                        if (confirm(`¿Eliminar el rol “${role.name}”?`)) remove.mutate(role);
                      }}
                    >
                      <Trash2 /> Eliminar
                    </Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      {editing && permissions.data && (
        <RoleDialog role={editing} permissions={permissions.data} onClose={() => setEditing(null)} />
      )}
    </>
  );
}

export default function RolesPage() {
  return (
    <RequirePermission anyOf={[PERM.roles]}>
      <RolesView />
    </RequirePermission>
  );
}
