"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useForm, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { RequirePermission } from "@/components/forbidden";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { useCategories, useCreateTicket } from "@/features/tickets/api";
import { ApiError } from "@/lib/api/client";
import { PERM, PRIORITY_LABEL, PRIORITY_ORDER } from "@/lib/labels";

const schema = z.object({
  title: z.string().trim().min(5, "Mínimo 5 caracteres").max(160, "Máximo 160 caracteres"),
  description: z.string().trim().min(10, "Describe el problema (mínimo 10 caracteres)").max(5000),
  category_id: z.coerce.number<string>().int().positive("Selecciona una categoría"),
  priority: z.enum(["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
});
type FormInput = z.input<typeof schema>;
type FormValues = z.output<typeof schema>;

const SLA_HINT: Record<string, string> = {
  CRITICAL: "Servicio detenido o afecta a muchos usuarios. Objetivo: 4 h.",
  HIGH: "Impide trabajar a una persona. Objetivo: 8 h.",
  MEDIUM: "Hay un rodeo posible. Objetivo: 24 h.",
  LOW: "Solicitud o mejora sin urgencia. Objetivo: 72 h.",
};

function NewTicketForm() {
  const router = useRouter();
  const categories = useCategories();
  const create = useCreateTicket();
  const {
    register,
    handleSubmit,
    control,
    formState: { errors },
  } = useForm<FormInput, unknown, FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { title: "", description: "", category_id: "", priority: "MEDIUM" },
  });
  const priority = useWatch({ control, name: "priority" });

  const onSubmit = handleSubmit(async (values) => {
    try {
      const ticket = await create.mutateAsync(values);
      toast.success(`Ticket ${ticket.code} creado`);
      router.push(`/tickets/${ticket.id}`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "No se pudo crear el ticket");
    }
  });

  return (
    <Card className="max-w-3xl">
      <CardContent className="pt-5">
        <form onSubmit={onSubmit} className="grid gap-5" noValidate>
          <Field label="Título" htmlFor="title" error={errors.title?.message}>
            <Input id="title" placeholder="Ej. La impresora del piso 2 no imprime" aria-invalid={Boolean(errors.title)} {...register("title")} />
          </Field>
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Categoría" htmlFor="category_id" error={errors.category_id?.message}>
              <Select id="category_id" aria-invalid={Boolean(errors.category_id)} {...register("category_id")}>
                <option value="">Selecciona…</option>
                {categories.data?.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Prioridad" htmlFor="priority" hint={SLA_HINT[priority]}>
              <Select id="priority" {...register("priority")}>
                {PRIORITY_ORDER.map((p) => (
                  <option key={p} value={p}>
                    {PRIORITY_LABEL[p]}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Descripción" htmlFor="description" error={errors.description?.message}>
            <Textarea
              id="description"
              rows={7}
              placeholder="¿Qué pasa? ¿Desde cuándo? ¿A quién afecta? ¿Qué ya intentaste?"
              aria-invalid={Boolean(errors.description)}
              {...register("description")}
            />
          </Field>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={() => router.back()}>
              Cancelar
            </Button>
            <Button type="submit" loading={create.isPending}>
              Crear ticket
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export default function NewTicketPage() {
  return (
    <RequirePermission anyOf={[PERM.ticketsCreate]}>
      <PageHeader title="Nuevo ticket" description="Describe tu solicitud; el SLA se calcula según la prioridad." />
      <NewTicketForm />
    </RequirePermission>
  );
}
