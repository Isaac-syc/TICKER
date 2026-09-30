import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, call } from "@/lib/api/client";
import type { Priority, TicketDetail, TicketStatus } from "@/lib/api/types";

export interface TicketQuery {
  search?: string;
  status?: TicketStatus[];
  priority?: Priority[];
  category_id?: number;
  assignee_id?: string;
  unassigned?: boolean;
  requester_id?: string;
  overdue?: boolean;
  created_from?: string;
  created_to?: string;
  sort?: string;
  page?: number;
  page_size?: number;
}

export const ticketKeys = {
  all: ["tickets"] as const,
  list: (q: TicketQuery) => ["tickets", "list", q] as const,
  detail: (id: string) => ["tickets", "detail", id] as const,
};

export function useCategories() {
  return useQuery({
    queryKey: ["catalog", "categories"],
    queryFn: () => call(api.GET("/api/v1/catalog/categories")),
    staleTime: 5 * 60_000,
  });
}

export function useAssignees(enabled = true) {
  return useQuery({
    queryKey: ["catalog", "assignees"],
    queryFn: () => call(api.GET("/api/v1/catalog/assignees")),
    staleTime: 60_000,
    enabled,
  });
}

export function useTickets(query: TicketQuery) {
  return useQuery({
    queryKey: ticketKeys.list(query),
    queryFn: () => call(api.GET("/api/v1/tickets", { params: { query } })),
    placeholderData: keepPreviousData,
  });
}

export function useTicket(id: string) {
  return useQuery({
    queryKey: ticketKeys.detail(id),
    queryFn: () => call(api.GET("/api/v1/tickets/{ticket_id}", { params: { path: { ticket_id: id } } })),
  });
}

export function useCreateTicket() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { title: string; description: string; category_id: number; priority: Priority }) =>
      call(api.POST("/api/v1/tickets", { body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ticketKeys.all }),
  });
}

/** Mutaciones del detalle: todas devuelven el detalle actualizado. */
function useDetailMutation<V>(id: string, fn: (vars: V) => Promise<TicketDetail>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (detail) => {
      qc.setQueryData(ticketKeys.detail(id), detail);
      void qc.invalidateQueries({ queryKey: ["tickets", "list"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useTransition(id: string) {
  return useDetailMutation(id, (body: { status: TicketStatus; comment?: string | null }) =>
    call(
      api.POST("/api/v1/tickets/{ticket_id}/transitions", {
        params: { path: { ticket_id: id } },
        body,
      }),
    ),
  );
}

export function useAssign(id: string) {
  return useDetailMutation(id, (assignee_id: string | null) =>
    call(
      api.POST("/api/v1/tickets/{ticket_id}/assign", {
        params: { path: { ticket_id: id } },
        body: { assignee_id },
      }),
    ),
  );
}

export function useComment(id: string) {
  return useDetailMutation(id, (body: string) =>
    call(
      api.POST("/api/v1/tickets/{ticket_id}/comments", {
        params: { path: { ticket_id: id } },
        body: { body },
      }),
    ),
  );
}

export function useUpdateTicket(id: string) {
  return useDetailMutation(
    id,
    (body: { title?: string; description?: string; category_id?: number; priority?: Priority }) =>
      call(
        api.PATCH("/api/v1/tickets/{ticket_id}", {
          params: { path: { ticket_id: id } },
          body,
        }),
      ),
  );
}
