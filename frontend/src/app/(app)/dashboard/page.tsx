"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlarmClock,
  CheckCircle2,
  CircleDot,
  Clock3,
  Gauge,
  Inbox,
  PauseCircle,
  PlayCircle,
  UserX,
  type LucideIcon,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { RequirePermission } from "@/components/forbidden";
import { PageHeader } from "@/components/page-header";
import { Card } from "@/components/ui/card";
import { Select } from "@/components/ui/form";
import { Table, TBody, Td, Th, THead, Tr } from "@/components/ui/table";
import { ChartCard, HBarChart, TrendChart } from "@/features/dashboard/charts";
import { useCategories } from "@/features/tickets/api";
import { api, call } from "@/lib/api/client";
import { PERM } from "@/lib/labels";
import { cn, isoDay } from "@/lib/utils";

const RANGES = [
  { days: 7, label: "Últimos 7 días" },
  { days: 30, label: "Últimos 30 días" },
  { days: 90, label: "Últimos 90 días" },
];

function Kpi({
  label,
  value,
  icon: Icon,
  hint,
  tone,
  onClick,
}: {
  label: string;
  value: string | number;
  icon: LucideIcon;
  hint?: string;
  tone?: "critical" | "good";
  onClick?: () => void;
}) {
  const Comp = onClick ? "button" : "div";
  return (
    <Comp
      onClick={onClick}
      className={cn(
        "flex flex-col gap-2 rounded-xl border border-border bg-card p-4 text-left shadow-xs",
        onClick && "transition-colors hover:border-primary/40 hover:bg-muted/40",
      )}
    >
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Icon
          className={cn(
            "size-3.5",
            tone === "critical" && "text-[#d03b3b]",
            tone === "good" && "text-[#0ca30c]",
          )}
          aria-hidden
        />
        {label}
      </span>
      <span className="text-2xl font-semibold tracking-tight">{value}</span>
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </Comp>
  );
}

function DashboardView() {
  const router = useRouter();
  const [days, setDays] = useState(30);
  const [category, setCategory] = useState("");
  const categories = useCategories();

  const range = useMemo(() => {
    const to = new Date();
    const from = new Date();
    from.setDate(to.getDate() - (days - 1));
    return { date_from: isoDay(from), date_to: isoDay(to) };
  }, [days]);

  const { data, isLoading } = useQuery({
    queryKey: ["dashboard", range, category],
    queryFn: () =>
      call(
        api.GET("/api/v1/dashboard", {
          params: { query: { ...range, category_id: category ? Number(category) : undefined } },
        }),
      ),
  });

  const goTickets = (params: Record<string, string>) =>
    router.push(`/tickets?${new URLSearchParams(params).toString()}`);

  const k = data?.kpis;
  return (
    <>
      <PageHeader
        title="Dashboard"
        description={
          data?.scope === "own"
            ? "Métricas de los tickets que levantaste o tienes asignados."
            : "Métricas de toda la mesa de ayuda."
        }
        actions={
          <>
            <Select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Periodo" className="w-44">
              {RANGES.map((r) => (
                <option key={r.days} value={r.days}>
                  {r.label}
                </option>
              ))}
            </Select>
            <Select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Categoría" className="w-48">
              <option value="">Todas las categorías</option>
              {categories.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </>
        }
      />

      {isLoading || !data || !k ? (
        <div className="grid gap-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
            {Array.from({ length: 8 }, (_, i) => (
              <div key={i} className="h-24 animate-pulse rounded-xl bg-muted" />
            ))}
          </div>
          <div className="h-80 animate-pulse rounded-xl bg-muted" />
        </div>
      ) : (
        <div className="grid gap-4">
          <section aria-label="Indicadores" className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
            <Kpi label="Abiertos" value={k.open} icon={Inbox} onClick={() => goTickets({ status: "OPEN" })} />
            <Kpi label="En progreso" value={k.in_progress} icon={PlayCircle} onClick={() => goTickets({ status: "IN_PROGRESS" })} />
            <Kpi label="En espera" value={k.on_hold} icon={PauseCircle} onClick={() => goTickets({ status: "ON_HOLD" })} />
            <Kpi
              label="Vencidos (SLA)"
              value={k.overdue}
              icon={AlarmClock}
              tone={k.overdue > 0 ? "critical" : "good"}
              hint={k.overdue > 0 ? "Requieren atención" : "Al corriente"}
              onClick={() => goTickets({ overdue: "1" })}
            />
            <Kpi label="Sin asignar" value={k.unassigned} icon={UserX} onClick={() => goTickets({ unassigned: "1", status: "ACTIVE" })} />
            <Kpi label="Creados" value={k.created_in_period} icon={CircleDot} hint="En el periodo" />
            <Kpi label="Resueltos" value={k.resolved_in_period} icon={CheckCircle2} hint="En el periodo" />
            <Kpi
              label="Cumplimiento SLA"
              value={k.sla_compliance === null ? "—" : `${k.sla_compliance}%`}
              icon={Gauge}
              hint={k.mttr_hours === null ? "Sin resoluciones" : `MTTR ${k.mttr_hours} h`}
            />
          </section>

          <ChartCard
            title="Creados vs. resueltos"
            description="Tickets por día en el periodo seleccionado"
            table={{
              headers: ["Día", "Creados", "Resueltos"],
              rows: data.trend.map((p) => [p.day, p.created, p.resolved]),
            }}
          >
            <TrendChart data={data.trend} />
          </ChartCard>

          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard
              title="Por estatus"
              description="Tickets creados en el periodo · clic para filtrar"
              table={{ headers: ["Estatus", "Tickets"], rows: data.by_status.map((x) => [x.label, x.value]) }}
            >
              <HBarChart data={data.by_status} label="Tickets" onSelect={(key) => goTickets({ status: key })} />
            </ChartCard>
            <ChartCard
              title="Por prioridad"
              description="Tickets creados en el periodo · clic para filtrar"
              table={{ headers: ["Prioridad", "Tickets"], rows: data.by_priority.map((x) => [x.label, x.value]) }}
            >
              <HBarChart data={data.by_priority} label="Tickets" onSelect={(key) => goTickets({ priority: key })} />
            </ChartCard>
            <ChartCard
              title="Por categoría"
              description="Tickets creados en el periodo"
              table={{ headers: ["Categoría", "Tickets"], rows: data.by_category.map((x) => [x.label, x.value]) }}
            >
              {data.by_category.length ? (
                <HBarChart data={data.by_category} label="Tickets" onSelect={(key) => goTickets({ category: key })} />
              ) : (
                <p className="py-10 text-center text-sm text-muted-foreground">Sin tickets en el periodo.</p>
              )}
            </ChartCard>
            <ChartCard
              title="Antigüedad del backlog"
              description="Tickets activos según su edad"
              table={{ headers: ["Antigüedad", "Tickets"], rows: data.backlog_aging.map((x) => [x.label, x.value]) }}
            >
              <HBarChart data={data.backlog_aging} label="Tickets activos" />
            </ChartCard>
          </div>

          <Card className="overflow-hidden">
            <div className="flex items-center gap-2 px-5 pt-5 pb-3">
              <Clock3 className="size-4 text-muted-foreground" />
              <h3 className="text-sm font-semibold">Top de asignados</h3>
            </div>
            <Table>
              <THead>
                <Tr className="hover:bg-transparent">
                  <Th>Responsable</Th>
                  <Th className="text-right">Activos</Th>
                  <Th className="text-right">Resueltos (periodo)</Th>
                  <Th className="text-right">Tiempo prom. de resolución</Th>
                </Tr>
              </THead>
              <TBody>
                {data.top_assignees.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-3 py-8 text-center text-sm text-muted-foreground">
                      Aún no hay tickets asignados.
                    </td>
                  </tr>
                ) : (
                  data.top_assignees.map((a) => (
                    <Tr key={a.user.id}>
                      <Td>
                        <p className="font-medium">{a.user.full_name}</p>
                        <p className="text-xs text-muted-foreground">{a.user.email}</p>
                      </Td>
                      <Td className="text-right tabular-nums">{a.open}</Td>
                      <Td className="text-right tabular-nums">{a.resolved}</Td>
                      <Td className="text-right tabular-nums">
                        {a.avg_resolution_hours === null ? "—" : `${a.avg_resolution_hours} h`}
                      </Td>
                    </Tr>
                  ))
                )}
              </TBody>
            </Table>
          </Card>
        </div>
      )}
    </>
  );
}

export default function DashboardPage() {
  return (
    <RequirePermission anyOf={[PERM.dashboard]}>
      <DashboardView />
    </RequirePermission>
  );
}
