"use client";

import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { buttonVariants } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";
import type { Permission } from "@/lib/api/types";

/** Protege una pantalla completa por permiso (el backend vuelve a validar cada petición). */
export function RequirePermission({
  anyOf,
  children,
}: {
  anyOf: Permission[];
  children: ReactNode;
}) {
  const { can, homePath } = useAuth();
  if (anyOf.some(can)) return <>{children}</>;
  return (
    <div className="mx-auto mt-16 max-w-md text-center">
      <ShieldAlert className="mx-auto size-10 text-muted-foreground" />
      <h1 className="mt-4 text-lg font-semibold">No tienes acceso a esta sección</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Tu rol no incluye los permisos necesarios. Si crees que es un error, contacta a un
        administrador.
      </p>
      <Link href={homePath} className={buttonVariants({ variant: "outline", className: "mt-6" })}>
        Volver al inicio
      </Link>
    </div>
  );
}
