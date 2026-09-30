"use client";

import { Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/features/auth/auth-provider";

export default function Home() {
  const { status, homePath } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status !== "loading") router.replace(homePath);
  }, [status, homePath, router]);

  return (
    <div className="grid min-h-dvh place-items-center">
      <Loader2 className="size-5 animate-spin text-muted-foreground" aria-label="Cargando" />
    </div>
  );
}
