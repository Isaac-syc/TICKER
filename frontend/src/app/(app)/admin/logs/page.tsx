"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Download, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { RequirePermission } from "@/components/forbidden";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/form";
import { EmptyRow, Pagination, SkeletonRows, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/table";
import { useAuth } from "@/features/auth/auth-provider";
import { api, call, downloadCsv } from "@/lib/api/client";
import { AUDIT_ACTION_LABEL, LOGIN_REASON_LABEL, PERM } from "@/lib/labels";
import { cn, formatDateTime } from "@/lib/utils";

type Tab = "logins" | "audit";

function DateRange({
  from,
  to,
  onChange,
}: {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
}) {
  return (
    <div className="flex items-center gap-1">
      <Input type="date" value={from} onChange={(e) => onChange(e.target.value, to)} aria-label="Desde" className="w-36" />
      <Input type="date" value={to} onChange={(e) => onChange(from, e.target.value)} aria-label="Hasta" className="w-36" />
    </div>
  );
}

function LoginsTab() {
  const { can } = useAuth();
  const [email, setEmail] = useState("");
  const [success, setSuccess] = useState("");
  const [range, setRange] = useState({ from: "", to: "" });
  const [page, setPage] = useState(1);
  const filters = {
    email: email.trim() || undefined,
    success: success === "" ? undefined : success === "true",
    date_from: range.from || undefined,
    date_to: range.to || undefined,
  };
  const q = useQuery({
    queryKey: ["logs", "logins", filters, page],
    queryFn: () => call(api.GET("/api/v1/logs/logins", { params: { query: { ...filters, page, page_size: 20 } } })),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 p-3">
        <Input
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            setPage(1);
          }}
          placeholder="Filtrar por correo"
          className="w-60"
          aria-label="Correo"
        />
        <Select value={success} onChange={(e) => { setSuccess(e.target.value); setPage(1); }} className="w-40" aria-label="Resultado">
          <option value="">Todos</option>
          <option value="true">Exitosos</option>
          <option value="false">Fallidos</option>
        </Select>
        <DateRange from={range.from} to={range.to} onChange={(from, to) => { setRange({ from, to }); setPage(1); }} />
        {can(PERM.export) && (
          <Button
            variant="outline"
            className="ml-auto"
            onClick={() => downloadCsv("/api/v1/logs/logins/export.csv", filters).catch((e) => toast.error(e.message))}
          >
            <Download /> Exportar CSV
          </Button>
        )}
      </div>
      <Table>
        <THead>
          <Tr className="hover:bg-transparent">
            <Th>Fecha</Th>
            <Th>Correo</Th>
            <Th>Resultado</Th>
            <Th>Motivo</Th>
            <Th>IP</Th>
            <Th>Navegador</Th>
          </Tr>
        </THead>
        <TBody>
          {q.isLoading ? (
            <SkeletonRows cols={6} />
          ) : !q.data?.items.length ? (
            <EmptyRow colSpan={6}>Sin registros.</EmptyRow>
          ) : (
            q.data.items.map((e) => (
              <Tr key={e.id}>
                <Td className="whitespace-nowrap">{formatDateTime(e.created_at)}</Td>
                <Td>
                  <p>{e.email}</p>
                  {e.user_name && <p className="text-xs text-muted-foreground">{e.user_name}</p>}
                </Td>
                <Td>
                  {e.success ? (
                    <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                      <CheckCircle2 className="size-4" /> Exitoso
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-destructive">
                      <XCircle className="size-4" /> Fallido
                    </span>
                  )}
                </Td>
                <Td>{e.reason ? LOGIN_REASON_LABEL[e.reason] ?? e.reason : "—"}</Td>
                <Td className="font-mono text-xs">{e.ip ?? "—"}</Td>
                <Td className="max-w-64 truncate text-xs text-muted-foreground" title={e.user_agent ?? ""}>
                  {e.user_agent ?? "—"}
                </Td>
              </Tr>
            ))
          )}
        </TBody>
      </Table>
      {q.data && <Pagination page={q.data.page} pages={q.data.pages} total={q.data.total} onPage={setPage} />}
    </>
  );
}

function AuditTab() {
  const { can } = useAuth();
  const [action, setAction] = useState("");
  const [range, setRange] = useState({ from: "", to: "" });
  const [page, setPage] = useState(1);
  const actions = useQuery({
    queryKey: ["logs", "actions"],
    queryFn: () => call(api.GET("/api/v1/logs/audit/actions")),
  });
  const filters = {
    action: action || undefined,
    date_from: range.from || undefined,
    date_to: range.to || undefined,
  };
  const q = useQuery({
    queryKey: ["logs", "audit", filters, page],
    queryFn: () => call(api.GET("/api/v1/logs/audit", { params: { query: { ...filters, page, page_size: 20 } } })),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 p-3">
        <Select value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} className="w-60" aria-label="Acción">
          <option value="">Todas las acciones</option>
          {actions.data?.map((a) => (
            <option key={a} value={a}>
              {AUDIT_ACTION_LABEL[a] ?? a}
            </option>
          ))}
        </Select>
        <DateRange from={range.from} to={range.to} onChange={(from, to) => { setRange({ from, to }); setPage(1); }} />
        {can(PERM.export) && (
          <Button
            variant="outline"
            className="ml-auto"
            onClick={() => downloadCsv("/api/v1/logs/audit/export.csv", filters).catch((e) => toast.error(e.message))}
          >
            <Download /> Exportar CSV
          </Button>
        )}
      </div>
      <Table>
        <THead>
          <Tr className="hover:bg-transparent">
            <Th>Fecha</Th>
            <Th>Acción</Th>
            <Th>Actor</Th>
            <Th>Entidad</Th>
            <Th>Detalle</Th>
            <Th>Request ID</Th>
          </Tr>
        </THead>
        <TBody>
          {q.isLoading ? (
            <SkeletonRows cols={6} />
          ) : !q.data?.items.length ? (
            <EmptyRow colSpan={6}>Sin registros.</EmptyRow>
          ) : (
            q.data.items.map((e) => (
              <Tr key={e.id}>
                <Td className="whitespace-nowrap">{formatDateTime(e.created_at)}</Td>
                <Td className="whitespace-nowrap font-medium">{AUDIT_ACTION_LABEL[e.action] ?? e.action}</Td>
                <Td>{e.actor?.full_name ?? "Sistema"}</Td>
                <Td className="text-xs">
                  {e.entity_type}
                  {typeof e.metadata.code === "string" && <span className="ml-1 font-mono">{e.metadata.code}</span>}
                </Td>
                <Td className="max-w-80 truncate font-mono text-[11px] text-muted-foreground" title={JSON.stringify(e.metadata)}>
                  {Object.keys(e.metadata).length ? JSON.stringify(e.metadata) : "—"}
                </Td>
                <Td className="font-mono text-[11px] text-muted-foreground">{e.request_id?.slice(0, 12) ?? "—"}</Td>
              </Tr>
            ))
          )}
        </TBody>
      </Table>
      {q.data && <Pagination page={q.data.page} pages={q.data.pages} total={q.data.total} onPage={setPage} />}
    </>
  );
}

function LogsView() {
  const [tab, setTab] = useState<Tab>("logins");
  return (
    <>
      <PageHeader title="Bitácora" description="Inicios de sesión y auditoría de acciones del sistema." />
      <div role="tablist" className="mb-3 inline-flex rounded-lg bg-muted p-1">
        {(
          [
            ["logins", "Inicios de sesión"],
            ["audit", "Auditoría"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              "rounded-md px-4 py-1.5 text-sm font-medium text-muted-foreground transition-colors",
              tab === key && "bg-card text-foreground shadow-xs",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <Card className="overflow-hidden">{tab === "logins" ? <LoginsTab /> : <AuditTab />}</Card>
    </>
  );
}

export default function LogsPage() {
  return (
    <RequirePermission anyOf={[PERM.logs]}>
      <LogsView />
    </RequirePermission>
  );
}
