"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { useAuth } from "@/features/auth/auth-provider";
import { api, ApiError, call } from "@/lib/api/client";
import { formatDateTime } from "@/lib/utils";

export default function ProfilePage() {
  const { user } = useAuth();
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const mismatch = form.confirm.length > 0 && form.next !== form.confirm;

  const change = useMutation({
    mutationFn: () =>
      call(
        api.POST("/api/v1/auth/password", {
          body: { current_password: form.current, new_password: form.next },
        }),
      ),
    onSuccess: () => {
      toast.success("Contraseña actualizada");
      setForm({ current: "", next: "", confirm: "" });
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "No se pudo actualizar"),
  });

  if (!user) return null;
  return (
    <>
      <PageHeader title="Mi cuenta" />
      <div className="grid max-w-3xl gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Datos</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs text-muted-foreground">Nombre</dt>
                <dd>{user.full_name}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Correo</dt>
                <dd>{user.email}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Rol</dt>
                <dd className="capitalize">{user.role.name}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted-foreground">Último acceso</dt>
                <dd>{formatDateTime(user.last_login_at)}</dd>
              </div>
            </dl>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Cambiar contraseña</CardTitle>
            <CardDescription>Mínimo 10 caracteres y 3 de: minúsculas, mayúsculas, números, símbolos.</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-4 sm:max-w-sm"
              onSubmit={(e) => {
                e.preventDefault();
                change.mutate();
              }}
            >
              <Field label="Contraseña actual" htmlFor="p-current">
                <Input id="p-current" type="password" autoComplete="current-password" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} />
              </Field>
              <Field label="Nueva contraseña" htmlFor="p-next">
                <Input id="p-next" type="password" autoComplete="new-password" value={form.next} onChange={(e) => setForm({ ...form, next: e.target.value })} />
              </Field>
              <Field label="Confirmar" htmlFor="p-confirm" error={mismatch ? "No coincide" : undefined}>
                <Input id="p-confirm" type="password" autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} />
              </Field>
              <Button type="submit" loading={change.isPending} disabled={!form.current || form.next.length < 10 || mismatch}>
                Actualizar
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
