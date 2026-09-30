"use client";

import { Loader2 } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/features/auth/auth-provider";
import { SingleTabGate } from "@/features/single-tab/single-tab-gate";

export default function AppLayout({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (status === "anonymous") router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [status, router, pathname]);

  if (status !== "authenticated") {
    return (
      <div className="grid min-h-dvh place-items-center">
        <Loader2 className="size-5 animate-spin text-muted-foreground" aria-label="Cargando" />
      </div>
    );
  }

  return (
    <SingleTabGate>
      <AppShell>{children}</AppShell>
    </SingleTabGate>
  );
}
