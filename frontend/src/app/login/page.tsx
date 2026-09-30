"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { ClipboardCheck, LockKeyhole } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { homePathFor, useAuth } from "@/features/auth/auth-provider";
import { ApiError } from "@/lib/api/client";

const schema = z.object({
  email: z.string().trim().min(1, "Escribe tu correo").email("Correo inválido"),
  password: z.string().min(1, "Escribe tu contraseña"),
});
type FormValues = z.infer<typeof schema>;

function safeNext(next: string | null): string | null {
  // Evita open redirects: solo rutas internas.
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

function LoginForm() {
  const { status, user, login } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  useEffect(() => {
    if (status === "authenticated") router.replace(safeNext(params.get("next")) ?? homePathFor(user));
  }, [status, user, router, params]);

  const onSubmit = handleSubmit(async ({ email, password }) => {
    setError(null);
    try {
      await login(email, password);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "No se pudo conectar con el servidor.");
    }
  });

  return (
    <form onSubmit={onSubmit} className="grid gap-4" noValidate>
      <Field label="Correo" htmlFor="email" error={errors.email?.message}>
        <Input
          id="email"
          type="email"
          autoComplete="username"
          autoFocus
          aria-invalid={Boolean(errors.email)}
          {...register("email")}
        />
      </Field>
      <Field label="Contraseña" htmlFor="password" error={errors.password?.message}>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          aria-invalid={Boolean(errors.password)}
          {...register("password")}
        />
      </Field>
      {error && (
        <p
          className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          role="alert"
        >
          {error}
        </p>
      )}
      <Button type="submit" loading={isSubmitting} className="mt-2 w-full">
        Iniciar sesión
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="grid min-h-dvh lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-sidebar p-10 text-sidebar-foreground lg:flex">
        <div className="flex items-center gap-2">
          <div className="grid size-9 place-items-center rounded-lg bg-primary font-bold text-primary-foreground">
            TI
          </div>
          <span className="font-semibold">Helpdesk TI</span>
        </div>
        <div className="max-w-md">
          <ClipboardCheck className="mb-6 size-10 text-primary" />
          <h2 className="text-3xl font-semibold leading-tight">
            Seguimiento de tickets de TI, de la solicitud a la solución.
          </h2>
          <p className="mt-4 text-sm text-sidebar-muted">
            Flujo de estatus con SLA, roles con permisos granulares, bitácora de auditoría y
            analítica en tiempo real.
          </p>
        </div>
        <p className="text-xs text-sidebar-muted">© {new Date().getFullYear()} Helpdesk TI</p>
        <div className="pointer-events-none absolute -right-24 -bottom-24 size-96 rounded-full bg-primary/20 blur-3xl" />
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div className="mb-8 grid gap-2">
            <LockKeyhole className="size-6 text-primary" />
            <h1 className="text-2xl font-semibold tracking-tight">Inicia sesión</h1>
            <p className="text-sm text-muted-foreground">Usa tu cuenta corporativa.</p>
          </div>
          <Suspense>
            <LoginForm />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
