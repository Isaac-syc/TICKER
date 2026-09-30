import type { HTMLAttributes } from "react";

import type { Priority, TicketStatus } from "@/lib/api/types";
import { PRIORITY_LABEL, PRIORITY_TONE, STATUS_LABEL, STATUS_TONE } from "@/lib/labels";
import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ring-border",
        className,
      )}
      {...props}
    />
  );
}

export function StatusBadge({ status }: { status: TicketStatus }) {
  return <Badge className={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>;
}

export function PriorityBadge({ priority }: { priority: Priority }) {
  return <Badge className={PRIORITY_TONE[priority]}>{PRIORITY_LABEL[priority]}</Badge>;
}
