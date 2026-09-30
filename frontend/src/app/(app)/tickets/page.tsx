"use client";

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { AlarmClock, ArrowDown, ArrowUp, ChevronsUpDown, Download, Plus, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { RequirePermission } from "@/components/forbidden";
import { PageHeader } from "@/components/page-header";
import { PriorityBadge, StatusBadge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox, Input, Select } from "@/components/ui/form";
import { EmptyRow, Pagination, SkeletonRows, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/table";
import { useAuth } from "@/features/auth/auth-provider";
import { useCategories, useTickets, type TicketQuery } from "@/features/tickets/api";
import { downloadCsv } from "@/lib/api/client";
import type { Priority, TicketItem, TicketStatus } from "@/lib/api/types";
import { PERM, PRIORITY_LABEL, PRIORITY_ORDER, STATUS_LABEL, STATUS_ORDER } from "@/lib/labels";
import { cn, formatDateTime, fromNow } from "@/lib/utils";

const ACTIVE = "ACTIVE";
const ACTIVE_STATUSES: TicketStatus[] = ["OPEN", "IN_PROGRESS", "ON_HOLD"];

/** Los filtros viven en la URL: se pueden compartir y sobreviven a recargas. */
function useTicketQuery() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const query = useMemo<TicketQuery>(() => {
    const status = params.get("status");
    return {
      search: params.get("search") ?? undefined,
      status: status === ACTIVE ? ACTIVE_STATUSES : status ? [status as TicketStatus] : undefined,
      priority: params.get("priority") ? [params.get("priority") as Priority] : undefined,
      category_id: params.get("category") ? Number(params.get("category")) : undefined,
      assignee_id: params.get("assignee") ?? undefined,
      unassigned: params.get("unassigned") === "1" || undefined,
      overdue: params.get("overdue") === "1" || undefined,
      created_from: params.get("from") ?? undefined,
      created_to: params.get("to") ?? undefined,
      sort: params.get("sort") ?? "-created_at",
      page: Number(params.get("page") ?? 1),
      page_size: 20,
    };
  }, [params]);

  const update = (patch: Record<string, string | null | undefined>, resetPage = true) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v);
      else next.delete(k);
    }
    if (resetPage) next.delete("page");
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  return { query, raw: params, update };
}

const col = createColumnHelper<TicketItem>();

function SortHeader({
  label,
  field,
  sort,
  onSort,
}: {
  label: string;
  field: string;
  sort: string;
  onSort: (s: string) => void;
}) {
  const active = sort.replace("-", "") === field;
  const desc = sort.startsWith("-");
  const Icon = !active ? ChevronsUpDown : desc ? ArrowDown : ArrowUp;
  return (
    <button
      type="button"
      className={cn("inline-flex items-center gap-1 hover:text-foreground", active && "text-foreground")}
      onClick={() => onSort(active && !desc ? `-${field}` : active ? field : `-${field}`)}
    >
      {label}
      <Icon className="size-3" />
    </button>
  );
}

function TicketsView() {
  const { user, can } = useAuth();
  const { query, raw, update } = useTicketQuery();
  const { data, isLoading, isFetching } = useTickets(query);
  const categories = useCategories();
  const [search, setSearch] = useState(query.search ?? "");
  const [exporting, setExporting] = useState(false);

  // Búsqueda con debounce para no disparar una petición por tecla.
  useEffect(() => {
    const t = setTimeout(() => {
      if ((query.search ?? "") !== search) update({ search: search.trim() || null });
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const sort = query.sort ?? "-created_at";
  const onSort = (s: string) => update({ sort: s });

  const columns = useMemo(
    () => [
      col.accessor("code", {
        header: () => <SortHeader label="Folio" field="number" sort={sort} onSort={onSort} />,
        cell: (c) => (
          <Link href={`/tickets/${c.row.original.id}`} className="font-mono text-xs font-medium text-primary hover:underline">
            {c.getValue()}
          </Link>
        ),
      }),
      col.accessor("title", {
        header: () => <SortHeader label="Título" field="title" sort={sort} onSort={onSort} />,
        cell: (c) => (
          <div className="grid max-w-[24rem] gap-0.5">
            <Link href={`/tickets/${c.row.original.id}`} className="truncate font-medium hover:underline">
              {c.getValue()}
            </Link>
            <span className="truncate text-xs text-muted-foreground">
              {c.row.original.requester.full_name} · {c.row.original.category_name}
            </span>
          </div>
        ),
      }),
      col.accessor("status", {
        header: () => <SortHeader label="Estatus" field="status" sort={sort} onSort={onSort} />,
        cell: (c) => <StatusBadge status={c.getValue()} />,
      }),
      col.accessor("priority", {
        header: () => <SortHeader label="Prioridad" field="priority" sort={sort} onSort={onSort} />,
        cell: (c) => <PriorityBadge priority={c.getValue()} />,
      }),

      col.accessor((t) => t.assignee?.full_name, {
        id: "assignee",
        header: "Asignado",
        cell: (c) => c.getValue() ?? <span className="text-muted-foreground">Sin asignar</span>,
      }),
      col.accessor("created_at", {
        header: () => <SortHeader label="Creado" field="created_at" sort={sort} onSort={onSort} />,
        cell: (c) => <span title={formatDateTime(c.getValue())}>{fromNow(c.getValue())}</span>,
      }),
      col.accessor("due_at", {
        header: () => <SortHeader label="Vence" field="due_at" sort={sort} onSort={onSort} />,
        cell: (c) =>
          c.row.original.is_overdue ? (
            <span className="inline-flex items-center gap-1 font-medium text-destructive" title={formatDateTime(c.getValue())}>
              <AlarmClock className="size-3.5" /> Vencido
            </span>
          ) : ["OPEN", "IN_PROGRESS", "ON_HOLD"].includes(c.row.original.status) ? (
            <span title={formatDateTime(c.getValue())}>{fromNow(c.getValue())}</span>
          ) : (
            <span className="text-muted-foreground">—</span>
          ),
      }),
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [sort],
  );

  const table = useReactTable({
    data: (data?.items ?? []) as TicketItem[],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
  });

  const hasFilters = ["status", "priority", "category", "assignee", "unassigned", "overdue", "from", "to", "search"].some(
    (k) => raw.get(k),
  );

  const onExport = async () => {
    setExporting(true);
    try {
      const filters = { ...query, page: undefined, page_size: undefined };
      await downloadCsv("/api/v1/tickets/export.csv", filters);
      toast.success("Exportación lista");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Tickets"
        description={
          can(PERM.ticketsReadAll)
            ? "Todos los tickets de la mesa de ayuda."
            : "Tickets que levantaste o que tienes asignados."
        }
        actions={
          <>
            {can(PERM.export) && (
              <Button variant="outline" onClick={onExport} loading={exporting}>
                <Download /> Exportar CSV
              </Button>
            )}
            {can(PERM.ticketsCreate) && (
              <Link href="/tickets/new" className={buttonVariants()}>
                <Plus /> Nuevo ticket
              </Link>
            )}
          </>
        }
      />

      <Card className="mb-4 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-64 flex-1">
            <Search className="pointer-events-none absolute top-2.5 left-2.5 size-4 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por folio, título o descripción"
              className="pl-8"
              aria-label="Buscar"
            />
          </div>
          <Select value={raw.get("status") ?? ""} onChange={(e) => update({ status: e.target.value })} aria-label="Estatus" className="w-auto min-w-40">
            <option value="">Todos los estatus</option>
            <option value={ACTIVE}>Activos</option>
            {STATUS_ORDER.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </Select>
          <Select value={raw.get("priority") ?? ""} onChange={(e) => update({ priority: e.target.value })} aria-label="Prioridad" className="w-auto min-w-40">
            <option value="">Todas las prioridades</option>
            {PRIORITY_ORDER.map((p) => (
              <option key={p} value={p}>
                {PRIORITY_LABEL[p]}
              </option>
            ))}
          </Select>
          <Select value={raw.get("category") ?? ""} onChange={(e) => update({ category: e.target.value })} aria-label="Categoría" className="w-auto min-w-40">
            <option value="">Todas las categorías</option>
            {categories.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </Select>
          <div className="flex items-center gap-1">
            <Input type="date" value={raw.get("from") ?? ""} onChange={(e) => update({ from: e.target.value })} aria-label="Creado desde" className="w-36" />
            <Input type="date" value={raw.get("to") ?? ""} onChange={(e) => update({ to: e.target.value })} aria-label="Creado hasta" className="w-36" />
          </div>
          {hasFilters && (
            <Button
              variant="ghost"
              onClick={() => {
                setSearch("");
                update({ status: null, priority: null, category: null, assignee: null, unassigned: null, overdue: null, from: null, to: null, search: null });
              }}
            >
              <X /> Limpiar
            </Button>
          )}
        </div>
        <div className="mt-3 flex flex-wrap gap-4 px-1">
          {can(PERM.ticketsWork) && user && (
            <Checkbox
              label="Asignados a mí"
              checked={raw.get("assignee") === user.id}
              onChange={(e) => update({ assignee: e.target.checked ? user.id : null, unassigned: null })}
            />
          )}
          {(can(PERM.ticketsManage) || can(PERM.ticketsReadAll)) && (
            <Checkbox
              label="Sin asignar"
              checked={raw.get("unassigned") === "1"}
              onChange={(e) => update({ unassigned: e.target.checked ? "1" : null, assignee: null })}
            />
          )}
          <Checkbox
            label="Vencidos (SLA)"
            checked={raw.get("overdue") === "1"}
            onChange={(e) => update({ overdue: e.target.checked ? "1" : null })}
          />
        </div>
      </Card>

      <Card className={cn("overflow-hidden transition-opacity", isFetching && !isLoading && "opacity-70")}>
        <Table>
          <THead>
            {table.getHeaderGroups().map((hg) => (
              <Tr key={hg.id} className="hover:bg-transparent">
                {hg.headers.map((h) => (
                  <Th key={h.id}>{flexRender(h.column.columnDef.header, h.getContext())}</Th>
                ))}
              </Tr>
            ))}
          </THead>
          <TBody>
            {isLoading ? (
              <SkeletonRows cols={columns.length} />
            ) : table.getRowModel().rows.length === 0 ? (
              <EmptyRow colSpan={columns.length}>No hay tickets que coincidan con los filtros.</EmptyRow>
            ) : (
              table.getRowModel().rows.map((row) => (
                <Tr key={row.id} data-testid="ticket-row">
                  {row.getVisibleCells().map((cell) => (
                    <Td key={cell.id} className="whitespace-nowrap">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </Td>
                  ))}
                </Tr>
              ))
            )}
          </TBody>
        </Table>
        {data && (
          <Pagination
            page={data.page}
            pages={data.pages}
            total={data.total}
            onPage={(p) => update({ page: String(p) }, false)}
          />
        )}
      </Card>
    </>
  );
}

export default function TicketsPage() {
  return (
    <RequirePermission anyOf={[PERM.ticketsReadAll, PERM.ticketsReadOwn]}>
      <Suspense>
        <TicketsView />
      </Suspense>
    </RequirePermission>
  );
}
