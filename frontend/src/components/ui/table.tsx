import { ChevronLeft, ChevronRight } from "lucide-react";
import type { HTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

import { Button } from "./button";

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="relative w-full overflow-x-auto">
      <table className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  );
}

export function THead(props: HTMLAttributes<HTMLTableSectionElement>) {
  return <thead className="border-b border-border bg-muted/40 [&_tr]:border-0" {...props} />;
}

export function TBody(props: HTMLAttributes<HTMLTableSectionElement>) {
  return <tbody className="[&_tr:last-child]:border-0" {...props} />;
}

export function Tr({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn("border-b border-border transition-colors hover:bg-muted/40", className)}
      {...props}
    />
  );
}

export function Th({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        "h-10 whitespace-nowrap px-3 text-left align-middle text-xs font-medium text-muted-foreground",
        className,
      )}
      {...props}
    />
  );
}

export function Td({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-3 py-2.5 align-middle", className)} {...props} />;
}

export function Pagination({
  page,
  pages,
  total,
  onPage,
}: {
  page: number;
  pages: number;
  total: number;
  onPage: (page: number) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-t border-border px-3 py-2.5 text-xs text-muted-foreground">
      <span>
        {total.toLocaleString("es-MX")} {total === 1 ? "registro" : "registros"}
      </span>
      <div className="flex items-center gap-2">
        <span>
          Página {page} de {pages}
        </span>
        <Button
          size="icon"
          variant="outline"
          className="size-8"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          aria-label="Página anterior"
        >
          <ChevronLeft />
        </Button>
        <Button
          size="icon"
          variant="outline"
          className="size-8"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
          aria-label="Página siguiente"
        >
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}

export function EmptyRow({ colSpan, children }: { colSpan: number; children: React.ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-12 text-center text-sm text-muted-foreground">
        {children}
      </td>
    </tr>
  );
}

export function SkeletonRows({ cols, rows = 6 }: { cols: number; rows?: number }) {
  return (
    <>
      {Array.from({ length: rows }, (_, r) => (
        <tr key={r} className="border-b border-border">
          {Array.from({ length: cols }, (_, c) => (
            <td key={c} className="px-3 py-3">
              <div className="h-3.5 animate-pulse rounded bg-muted" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
