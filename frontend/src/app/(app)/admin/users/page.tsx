"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, KeyRound, Pencil, Plus, Search, UserCheck, UserX } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { RequirePermission } from "@/components/forbidden";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/form";
import { EmptyRow, Pagination, SkeletonRows, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/table";
import { useAuth } from "@/features/auth/auth-provider";
import { api, ApiError, call, downloadCsv } from "@/lib/api/client";
import type { Role, User } from "@/lib/api/types";
import { PERM, ROLE_TONE } from "@/lib/labels";
import { cn, formatDateTime, fromNow } from "@/lib/utils";

const PASSWORD_HINT = "Mínimo 10 caracteres y 3 de: minúsculas, mayúsculas, números, símbolos.";

function useRoles() {
  return useQuery({ queryKey: ["roles"], queryFn: () => call(api.GET("/api/v1/roles")) });
}

function errorText(e: unknown) {
  return e instanceof ApiError ? e.message : "Ocurrió un error inesperado";
}

function UserDialog({ user, roles, onClose }: { user: User | "new"; roles: Role[]; onClose: () => void }) {
  const qc = useQueryClient();
  const isNew = user === "new";
  const [form, setForm] = useState({
    email: isNew ? "" : user.email,
    full_name: isNew ? "" : user.full_name,
    role_id: isNew ? (roles.find((r) => r.name === "usuario")?.id ?? roles[0]?.id ?? "") : user.role.id,
    password: "",
  });

  const save = useMutation({
    mutationFn: () =>
      isNew
        ? call(api.POST("/api/v1/users", { body: form }))
        : call(
            api.PATCH("/api/v1/users/{user_id}", {
              params: { path: { user_id: user.id } },
              body: { email: form.email, full_name: form.full_name, role_id: form.role_id },
            }),
          ),
    onSuccess: () => {
      toast.success(isNew ? "Usuario creado" : "Usuario actualizado");
      void qc.invalidateQueries({ queryKey: ["users"] });
      void qc.invalidateQueries({ queryKey: ["roles"] });
      onClose();
    },
    onError: (e) => toast.error(errorText(e)),
  });

  return (
    <Dialog
      open
      onClose={onClose}
      title={isNew ? "Nuevo usuario" : `Editar a ${user.full_name}`}
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
      <div className="grid gap-4">
        <Field label="Nombre completo" htmlFor="u-name">
          <Input id="u-name" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
        </Field>
        <Field label="Correo" htmlFor="u-email">
          <Input id="u-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <Field label="Rol" htmlFor="u-role" hint={roles.find((r) => r.id === form.role_id)?.description}>
          <Select id="u-role" value={form.role_id} onChange={(e) => setForm({ ...form, role_id: e.target.value })}>
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </Select>
        </Field>
        {isNew && (
          <Field label="Contraseña inicial" htmlFor="u-pass" hint={PASSWORD_HINT}>
            <Input
              id="u-pass"
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </Field>
        )}
      </div>
    </Dialog>
  );
}

function ResetPasswordDialog({ user, onClose }: { user: User; onClose: () => void }) {
  const [password, setPassword] = useState("");
  const reset = useMutation({
    mutationFn: () =>
      call(
        api.POST("/api/v1/users/{user_id}/reset-password", {
          params: { path: { user_id: user.id } },
          body: { new_password: password },
        }),
      ),
    onSuccess: () => {
      toast.success("Contraseña restablecida. Sus sesiones activas se cerraron.");
      onClose();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  return (
    <Dialog
      open
      onClose={onClose}
      title={`Restablecer contraseña`}
      description={`${user.full_name} (${user.email}) tendrá que iniciar sesión de nuevo.`}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={() => reset.mutate()} loading={reset.isPending} disabled={password.length < 10}>
            Restablecer
          </Button>
        </>
      }
    >
      <Field label="Nueva contraseña" htmlFor="r-pass" hint={PASSWORD_HINT}>
        <Input id="r-pass" type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
    </Dialog>
  );
}

function UsersView() {
  const { user: me } = useAuth();
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [roleId, setRoleId] = useState("");
  const [active, setActive] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<User | "new" | null>(null);
  const [resetting, setResetting] = useState<User | null>(null);
  const roles = useRoles();

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const query = {
    search: debounced || undefined,
    role_id: roleId || undefined,
    is_active: active === "" ? undefined : active === "true",
  };
  const users = useQuery({
    queryKey: ["users", query, page],
    queryFn: () => call(api.GET("/api/v1/users", { params: { query: { ...query, page, page_size: 15 } } })),
    placeholderData: keepPreviousData,
  });

  const toggle = useMutation({
    mutationFn: (u: User) =>
      call(
        api.PATCH("/api/v1/users/{user_id}", {
          params: { path: { user_id: u.id } },
          body: { is_active: !u.is_active },
        }),
      ),
    onSuccess: (u) => {
      toast.success(u.is_active ? "Usuario activado" : "Usuario desactivado y sesiones cerradas");
      void qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e) => toast.error(errorText(e)),
  });

  return (
    <>
      <PageHeader
        title="Usuarios"
        description="Alta, roles y estado de las cuentas."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => downloadCsv("/api/v1/users/export.csv", query).catch((e) => toast.error(errorText(e)))}
            >
              <Download /> Exportar CSV
            </Button>
            <Button onClick={() => setEditing("new")} disabled={!roles.data}>
              <Plus /> Nuevo usuario
            </Button>
          </>
        }
      />
      <Card className="mb-4 grid gap-2 p-3 sm:grid-cols-[1fr_12rem_10rem]">
        <div className="relative">
          <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar por nombre o correo" className="pl-8" aria-label="Buscar" />
        </div>
        <Select value={roleId} onChange={(e) => { setRoleId(e.target.value); setPage(1); }} aria-label="Rol">
          <option value="">Todos los roles</option>
          {roles.data?.map((r) => (
            <option key={r.id} value={r.id}>
              {r.name}
            </option>
          ))}
        </Select>
        <Select value={active} onChange={(e) => { setActive(e.target.value); setPage(1); }} aria-label="Estado">
          <option value="">Todos</option>
          <option value="true">Activos</option>
          <option value="false">Inactivos</option>
        </Select>
      </Card>
      <Card className="overflow-hidden">
        <Table>
          <THead>
            <Tr className="hover:bg-transparent">
              <Th>Usuario</Th>
              <Th>Rol</Th>
              <Th>Estado</Th>
              <Th>Último acceso</Th>
              <Th>Alta</Th>
              <Th className="text-right">Acciones</Th>
            </Tr>
          </THead>
          <TBody>
            {users.isLoading ? (
              <SkeletonRows cols={6} />
            ) : !users.data?.items.length ? (
              <EmptyRow colSpan={6}>No hay usuarios con esos filtros.</EmptyRow>
            ) : (
              users.data.items.map((u) => (
                <Tr key={u.id} className={cn(!u.is_active && "opacity-60")}>
                  <Td>
                    <p className="font-medium">{u.full_name}</p>
                    <p className="text-xs text-muted-foreground">{u.email}</p>
                  </Td>
                  <Td>
                    <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", ROLE_TONE[u.role.name] ?? "bg-secondary text-secondary-foreground")}>
                      {u.role.name}
                    </span>
                  </Td>
                  <Td>
                    <Badge className={u.is_active ? "text-emerald-700 dark:text-emerald-300" : "text-muted-foreground"}>
                      {u.is_active ? "Activo" : "Inactivo"}
                    </Badge>
                  </Td>
                  <Td title={formatDateTime(u.last_login_at)}>{u.last_login_at ? fromNow(u.last_login_at) : "Nunca"}</Td>
                  <Td>{formatDateTime(u.created_at)}</Td>
                  <Td>
                    <div className="flex justify-end gap-1">
                      <Button size="icon" variant="ghost" onClick={() => setEditing(u)} aria-label={`Editar a ${u.full_name}`}>
                        <Pencil />
                      </Button>
                      <Button size="icon" variant="ghost" onClick={() => setResetting(u)} aria-label={`Restablecer contraseña de ${u.full_name}`}>
                        <KeyRound />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        disabled={u.id === me?.id || toggle.isPending}
                        onClick={() => toggle.mutate(u)}
                        aria-label={u.is_active ? `Desactivar a ${u.full_name}` : `Activar a ${u.full_name}`}
                        title={u.id === me?.id ? "No puedes desactivarte a ti mismo" : undefined}
                      >
                        {u.is_active ? <UserX className="text-destructive" /> : <UserCheck />}
                      </Button>
                    </div>
                  </Td>
                </Tr>
              ))
            )}
          </TBody>
        </Table>
        {users.data && <Pagination page={users.data.page} pages={users.data.pages} total={users.data.total} onPage={setPage} />}
      </Card>
      {editing && roles.data && <UserDialog user={editing} roles={roles.data} onClose={() => setEditing(null)} />}
      {resetting && <ResetPasswordDialog user={resetting} onClose={() => setResetting(null)} />}
    </>
  );
}

export default function UsersPage() {
  return (
    <RequirePermission anyOf={[PERM.users]}>
      <UsersView />
    </RequirePermission>
  );
}
