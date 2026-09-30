"use client";

import {
  AlarmClock,
  ArrowLeft,
  ArrowRightLeft,
  MessageSquare,
  Pencil,
  PlusCircle,
  UserCheck,
} from "lucide-react";
import Link from "next/link";
import { use, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { PriorityBadge, StatusBadge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import {
  useAssign,
  useAssignees,
  useCategories,
  useComment,
  useTicket,
  useTransition,
  useUpdateTicket,
} from "@/features/tickets/api";
import { ApiError } from "@/lib/api/client";
import type { Priority, TicketDetail, TicketEvent, TicketStatus } from "@/lib/api/types";
import {
  PRIORITY_LABEL,
  PRIORITY_ORDER,
  REQUIRES_COMMENT,
  STATUS_LABEL,
  TRANSITION_LABEL,
} from "@/lib/labels";
import { cn, formatDateTime, fromNow, initials } from "@/lib/utils";

function errorMessage(e: unknown) {
  return e instanceof ApiError ? e.message : "Ocurrió un error inesperado";
}

function TransitionDialog({
  detail,
  target,
  onClose,
}: {
  detail: TicketDetail;
  target: TicketStatus | null;
  onClose: () => void;
}) {
  const transition = useTransition(detail.ticket.id);
  const [comment, setComment] = useState("");
  const required = target ? REQUIRES_COMMENT.includes(target) : false;

  const submit = async () => {
    if (!target) return;
    try {
      await transition.mutateAsync({ status: target, comment: comment.trim() || null });
      toast.success(`Ticket ${STATUS_LABEL[target].toLowerCase()}`);
      setComment("");
      onClose();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  return (
    <Dialog
      open={target !== null}
      onClose={onClose}
      title={target ? `${TRANSITION_LABEL[target]} ${detail.ticket.code}` : ""}
      description={
        target
          ? `El ticket pasará de “${STATUS_LABEL[detail.ticket.status]}” a “${STATUS_LABEL[target]}”.`
          : undefined
      }
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={submit} loading={transition.isPending} disabled={required && !comment.trim()}>
            Confirmar
          </Button>
        </>
      }
    >
      <Field
        label={required ? "Comentario (obligatorio)" : "Comentario (opcional)"}
        htmlFor="transition-comment"
        hint={
          target === "RESOLVED"
            ? "Describe la solución aplicada."
            : target === "ON_HOLD"
              ? "¿Qué se está esperando?"
              : undefined
        }
      >
        <Textarea id="transition-comment" value={comment} onChange={(e) => setComment(e.target.value)} rows={4} />
      </Field>
    </Dialog>
  );
}

function EditDialog({ detail, open, onClose }: { detail: TicketDetail; open: boolean; onClose: () => void }) {
  const update = useUpdateTicket(detail.ticket.id);
  const categories = useCategories();
  const [form, setForm] = useState({
    title: detail.ticket.title,
    description: detail.description,
    category_id: detail.ticket.category_id,
    priority: detail.ticket.priority,
  });

  const submit = async () => {
    try {
      await update.mutateAsync(form);
      toast.success("Ticket actualizado");
      onClose();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={`Editar ${detail.ticket.code}`}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={submit} loading={update.isPending}>
            Guardar
          </Button>
        </>
      }
    >
      <div className="grid gap-4">
        <Field label="Título" htmlFor="edit-title">
          <Input id="edit-title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Categoría" htmlFor="edit-category">
            <Select
              id="edit-category"
              value={form.category_id}
              onChange={(e) => setForm({ ...form, category_id: Number(e.target.value) })}
            >
              {categories.data?.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Prioridad" htmlFor="edit-priority" hint="Cambiarla recalcula el SLA.">
            <Select
              id="edit-priority"
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value as Priority })}
            >
              {PRIORITY_ORDER.map((p) => (
                <option key={p} value={p}>
                  {PRIORITY_LABEL[p]}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Descripción" htmlFor="edit-description">
          <Textarea
            id="edit-description"
            rows={6}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </Field>
      </div>
    </Dialog>
  );
}

function eventText(e: TicketEvent): ReactNode {
  switch (e.type) {
    case "CREATED":
      return "creó el ticket";
    case "STATUS_CHANGED":
      return (
        <>
          cambió el estatus{" "}
          {e.from_status && <StatusBadge status={e.from_status} />} →{" "}
          {e.to_status && <StatusBadge status={e.to_status} />}
        </>
      );
    case "ASSIGNED": {
      const to = (e.data as { to_name?: string | null }).to_name;
      return to ? (
        <>
          asignó el ticket a <strong className="font-medium">{to}</strong>
        </>
      ) : (
        "quitó la asignación"
      );
    }
    case "COMMENTED":
      return "comentó";
    case "UPDATED":
      return "editó el ticket";
    default:
      return e.type;
  }
}

const EVENT_ICON = {
  CREATED: PlusCircle,
  STATUS_CHANGED: ArrowRightLeft,
  ASSIGNED: UserCheck,
  COMMENTED: MessageSquare,
  UPDATED: Pencil,
} as const;

function Timeline({ events }: { events: TicketEvent[] }) {
  return (
    <ol className="relative grid gap-5 border-l border-border pl-6" data-testid="timeline">
      {events.map((e) => {
        const Icon = EVENT_ICON[e.type];
        return (
          <li key={e.id} className="relative">
            <span className="absolute top-0.5 -left-[33px] grid size-5 place-items-center rounded-full border border-border bg-card">
              <Icon className="size-3 text-muted-foreground" />
            </span>
            <p className="text-sm">
              <strong className="font-medium">{e.actor.full_name}</strong> {eventText(e)}
              <span className="ml-2 text-xs text-muted-foreground" title={formatDateTime(e.created_at)}>
                {fromNow(e.created_at)}
              </span>
            </p>
            {e.comment && (
              <p className="mt-2 rounded-lg bg-muted/60 px-3 py-2 text-sm whitespace-pre-wrap">{e.comment}</p>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function CommentBox({ ticketId }: { ticketId: string }) {
  const comment = useComment(ticketId);
  const [body, setBody] = useState("");
  const submit = async () => {
    try {
      await comment.mutateAsync(body.trim());
      setBody("");
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };
  return (
    <div className="grid gap-2">
      <Textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Escribe un comentario…" rows={3} aria-label="Comentario" />
      <div className="flex justify-end">
        <Button size="sm" onClick={submit} disabled={!body.trim()} loading={comment.isPending}>
          Comentar
        </Button>
      </div>
    </div>
  );
}

function AssigneePicker({ detail }: { detail: TicketDetail }) {
  const assignees = useAssignees(detail.can_assign);
  const assign = useAssign(detail.ticket.id);
  if (!detail.can_assign) {
    return <span>{detail.ticket.assignee?.full_name ?? <span className="text-muted-foreground">Sin asignar</span>}</span>;
  }
  return (
    <Select
      aria-label="Asignar a"
      value={detail.ticket.assignee?.id ?? ""}
      disabled={assign.isPending}
      onChange={async (e) => {
        try {
          await assign.mutateAsync(e.target.value || null);
          toast.success("Asignación actualizada");
        } catch (err) {
          toast.error(errorMessage(err));
        }
      }}
    >
      <option value="">Sin asignar</option>
      {assignees.data?.map((a) => (
        <option key={a.id} value={a.id}>
          {a.full_name}
        </option>
      ))}
    </Select>
  );
}

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-1">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{children}</dd>
    </div>
  );
}

export default function TicketDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data: detail, isLoading, error } = useTicket(id);
  const [target, setTarget] = useState<TicketStatus | null>(null);
  const [editing, setEditing] = useState(false);

  if (isLoading) return <div className="h-64 animate-pulse rounded-xl bg-muted" />;
  if (error || !detail) {
    return (
      <div className="mx-auto mt-16 max-w-md text-center">
        <h1 className="text-lg font-semibold">Ticket no disponible</h1>
        <p className="mt-1 text-sm text-muted-foreground">{errorMessage(error)}</p>
        <Link href="/tickets" className={buttonVariants({ variant: "outline", className: "mt-6" })}>
          Volver a tickets
        </Link>
      </div>
    );
  }

  const t = detail.ticket;
  return (
    <>
      <Link href="/tickets" className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Tickets
      </Link>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="grid gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-muted-foreground">{t.code}</span>
            <StatusBadge status={t.status} />
            <PriorityBadge priority={t.priority} />
            {t.is_overdue && (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-destructive">
                <AlarmClock className="size-3.5" /> SLA vencido
              </span>
            )}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight" data-testid="ticket-title">
            {t.title}
          </h1>
        </div>
        <div className="flex flex-wrap gap-2" data-testid="transitions">
          {detail.can_edit && (
            <Button variant="outline" onClick={() => setEditing(true)}>
              <Pencil /> Editar
            </Button>
          )}
          {detail.allowed_transitions.map((s) => (
            <Button
              key={s}
              variant={s === "CANCELLED" ? "outline" : s === "RESOLVED" || s === "CLOSED" ? "default" : "secondary"}
              className={cn(s === "CANCELLED" && "text-destructive")}
              onClick={() => setTarget(s)}
            >
              {TRANSITION_LABEL[s]}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="grid content-start gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Descripción</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed whitespace-pre-wrap">{detail.description}</p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Actividad</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-6">
              <Timeline events={detail.events} />
              {detail.can_comment && <CommentBox ticketId={t.id} />}
            </CardContent>
          </Card>
        </div>

        <Card className="h-fit">
          <CardContent className="pt-5">
            <dl className="grid gap-4">
              <Meta label="Solicitante">
                <span className="flex items-center gap-2">
                  <span className="grid size-6 place-items-center rounded-full bg-muted text-[10px] font-semibold">
                    {initials(t.requester.full_name)}
                  </span>
                  {t.requester.full_name}
                </span>
              </Meta>
              <Meta label="Asignado a">
                <AssigneePicker detail={detail} />
              </Meta>
              <Meta label="Categoría">{t.category_name}</Meta>
              <Meta label="Creado">{formatDateTime(t.created_at)}</Meta>
              <Meta label="Vence (SLA)">
                <span className={cn(t.is_overdue && "font-medium text-destructive")}>{formatDateTime(t.due_at)}</span>
              </Meta>
              {t.resolved_at && <Meta label="Resuelto">{formatDateTime(t.resolved_at)}</Meta>}
              {t.closed_at && <Meta label="Cerrado">{formatDateTime(t.closed_at)}</Meta>}
              <Meta label="Última actualización">{fromNow(t.updated_at)}</Meta>
            </dl>
          </CardContent>
        </Card>
      </div>

      <TransitionDialog detail={detail} target={target} onClose={() => setTarget(null)} />
      {editing && <EditDialog detail={detail} open={editing} onClose={() => setEditing(false)} />}
    </>
  );
}
