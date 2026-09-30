"use client";

import { Table2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/** Colores por rol; los valores vienen de la paleta validada en globals.css. */
const VIZ = {
  s1: "var(--viz-1)",
  s2: "var(--viz-2)",
  grid: "var(--viz-grid)",
  axis: "var(--viz-axis)",
};

const axisProps = {
  stroke: VIZ.axis,
  tick: { fill: VIZ.axis, fontSize: 11 },
  tickLine: false,
  axisLine: { stroke: VIZ.grid },
} as const;

function TooltipBox({
  active,
  label,
  payload,
}: {
  active?: boolean;
  label?: ReactNode;
  payload?: { name?: ReactNode; value?: number | string; color?: string }[];
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-foreground">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className="flex items-center gap-2 text-muted-foreground">
          <span className="size-2.5 rounded-full" style={{ background: p.color }} aria-hidden />
          {p.name}: <span className="font-medium text-foreground tabular-nums">{p.value}</span>
        </p>
      ))}
    </div>
  );
}

/** Tarjeta de gráfica con vista de tabla alternativa (accesibilidad y lectura exacta). */
export function ChartCard({
  title,
  description,
  table,
  children,
  className,
}: {
  title: string;
  description?: string;
  table: { headers: string[]; rows: (string | number)[][] };
  children: ReactNode;
  className?: string;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <Card className={className}>
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div className="grid gap-1">
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        <button
          type="button"
          onClick={() => setAsTable((v) => !v)}
          className={cn(
            "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted",
            asTable && "bg-muted text-foreground",
          )}
          aria-pressed={asTable}
        >
          <Table2 className="size-3.5" /> Tabla
        </button>
      </CardHeader>
      <CardContent>
        {asTable ? (
          <div className="max-h-64 overflow-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  {table.headers.map((h) => (
                    <th key={h} className="py-1.5 pr-3 font-medium">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((r, i) => (
                  <tr key={i} className="border-b border-border/60 last:border-0">
                    {r.map((cell, j) => (
                      <td key={j} className={cn("py-1.5 pr-3", j > 0 && "tabular-nums")}>
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}

export function TrendChart({ data }: { data: { day: string; created: number; resolved: number }[] }) {
  const fmt = (d: string) =>
    new Date(`${d}T12:00:00`).toLocaleDateString("es-MX", { day: "numeric", month: "short" });
  return (
    <div className="h-64" role="img" aria-label="Tickets creados contra resueltos por día">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -18 }}>
          <CartesianGrid vertical={false} stroke={VIZ.grid} />
          <XAxis dataKey="day" tickFormatter={fmt} {...axisProps} minTickGap={24} />
          <YAxis allowDecimals={false} {...axisProps} axisLine={false} />
          <Tooltip
            content={<TooltipBox />}
            labelFormatter={(l) => fmt(String(l))}
            cursor={{ stroke: VIZ.axis, strokeDasharray: "3 3" }}
          />
          <Legend
            verticalAlign="top"
            align="right"
            height={28}
            iconType="plainline"
            wrapperStyle={{ fontSize: 12 }}
          />
          <Line
            type="linear"
            dataKey="created"
            name="Creados"
            stroke={VIZ.s1}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }}
          />
          <Line
            type="linear"
            dataKey="resolved"
            name="Resueltos"
            stroke={VIZ.s2}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--card)" }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Barras horizontales de una sola serie: un solo color, la identidad la da la etiqueta. */
export function HBarChart({
  data,
  label,
  onSelect,
}: {
  data: { key: string; label: string; value: number }[];
  label: string;
  onSelect?: (key: string) => void;
}) {
  const height = Math.max(120, data.length * 34 + 16);
  return (
    <div style={{ height }} role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 36, bottom: 0, left: 0 }} barCategoryGap={6}>
          <XAxis type="number" hide allowDecimals={false} />
          <YAxis
            type="category"
            dataKey="label"
            width={110}
            {...axisProps}
            axisLine={false}
            tick={{ fill: "var(--muted-foreground)", fontSize: 12 }}
          />
          <Tooltip content={<TooltipBox />} cursor={{ fill: "var(--muted)", opacity: 0.6 }} />
          <Bar
            dataKey="value"
            name={label}
            fill={VIZ.s1}
            radius={[0, 4, 4, 0]}
            maxBarSize={22}
            onClick={onSelect ? (d) => onSelect(String((d as { key?: string }).key)) : undefined}
            className={onSelect ? "cursor-pointer" : undefined}
          >
            <LabelList dataKey="value" position="right" fill="var(--foreground)" fontSize={12} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
