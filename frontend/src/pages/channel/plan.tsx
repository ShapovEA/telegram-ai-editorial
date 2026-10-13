import { DndContext, PointerSensor, useDraggable, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core"
import { CSS } from "@dnd-kit/utilities"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle,
  ArrowRight,
  CalendarPlus,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Lock,
  MoreHorizontal,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Shuffle,
  SkipForward,
  Trash2,
} from "lucide-react"
import { useState } from "react"
import { Link, useSearchParams } from "react-router"
import { toast } from "sonner"

import { SlotDialog } from "@/components/channel/slot-dialog"
import { Callout, ErrorState, Spinner, StatusBadge, ToneBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import { fmtDateTime } from "@/lib/format"
import { formatLabel, slotStatusLabel, weekdayShort } from "@/lib/labels"
import type { Channel, Plan, Run, Slot } from "@/lib/types"
import { addDaysKey, mondayKey, zonedDateTime, zonedDayKey, zonedTime, zonedToUtc } from "@/lib/tz"
import { cn } from "@/lib/utils"
import { useChannel } from "@/pages/channel/layout"

type PlanResponse = Omit<Plan, "id" | "status"> & { id: number | null; status: "none" | "draft" | "approved" | string }

const EDITABLE = new Set(["draft", "approved", "needs_attention", "failed", "skipped", "not_approved", "deferred"])

function SlotCard({ slot, channel, onEdit, onChanged }: { slot: Slot; channel: Channel; onEdit: () => void; onChanged: () => void }) {
  const editable = EDITABLE.has(slot.status)
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: slot.id, disabled: !editable })
  const tz = channel.schedule.timezone

  const act = useMutation({
    mutationFn: async (action: "start" | "replace" | "skip" | "approve" | "delete") => {
      if (action === "start") return api<{ run_id: string }>(`/slots/${slot.id}/start`, { method: "POST" })
      if (action === "replace") return api(`/slots/${slot.id}/replace`, { body: { hint: "" } })
      if (action === "skip") return api(`/slots/${slot.id}`, { method: "PATCH", body: { status: "skipped" } })
      if (action === "approve") return api(`/slots/${slot.id}`, { method: "PATCH", body: { status: "approved" } })
      return api(`/slots/${slot.id}`, { method: "DELETE" })
    },
    onSuccess: (res, action) => {
      const messages = { start: "Пост запущен в работу", replace: "Тема заменена", skip: "Слот пропущен", approve: "Слот утверждён", delete: "Слот удалён" }
      toast.success(messages[action])
      if (action === "start" && res && typeof res === "object" && "run_id" in res)
        toast(<Link to={`/runs/${(res as { run_id: string }).run_id}`}>Открыть запуск →</Link>)
      onChanged()
    },
    onError: (e) => toast.error((e as Error).message),
  })

  const warnings = slot.warnings ?? []

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform) }}
      className={cn(
        "group relative rounded-lg border bg-card p-2.5 text-sm shadow-xs transition-shadow",
        editable && "cursor-grab active:cursor-grabbing",
        isDragging && "z-50 shadow-lg ring-2 ring-primary/30",
        slot.status === "skipped" && "opacity-60",
      )}
      {...attributes}
      {...listeners}
    >
      <div className="mb-1 flex items-center gap-1.5 text-xs text-muted-foreground">
        <span className="font-medium text-foreground tabular-nums">{zonedTime(slot.publish_at, tz)}</span>
        {slot.rubric && <span className="truncate">· {slot.rubric}</span>}
        {slot.format !== "text" && <span>· {formatLabel[slot.format]}</span>}
        {slot.locked && <Lock className="size-3 shrink-0" />}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              onPointerDown={(e) => e.stopPropagation()}
              className="ml-auto rounded p-0.5 opacity-60 hover:bg-muted hover:opacity-100"
              aria-label="Действия со слотом"
            >
              {act.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <MoreHorizontal className="size-3.5" />}
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onEdit}>
              <Pencil /> {editable ? "Изменить" : "Открыть"}
            </DropdownMenuItem>
            {editable && (
              <>
                {slot.status === "draft" && (
                  <DropdownMenuItem onClick={() => act.mutate("approve")}>
                    <CheckCircle2 /> Утвердить
                  </DropdownMenuItem>
                )}
                <DropdownMenuItem onClick={() => act.mutate("replace")}>
                  <Shuffle /> Заменить тему
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => act.mutate("start")}>
                  <Play /> Писать сейчас
                </DropdownMenuItem>
                {slot.status !== "skipped" && (
                  <DropdownMenuItem onClick={() => act.mutate("skip")}>
                    <SkipForward /> Пропустить
                  </DropdownMenuItem>
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onClick={() => act.mutate("delete")}>
                  <Trash2 /> Удалить
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <button type="button" onPointerDown={(e) => e.stopPropagation()} onClick={onEdit} className="block w-full text-left">
        <div className={cn("line-clamp-3 font-medium", !slot.topic && "text-muted-foreground italic")}>{slot.topic || "Тему подберёт стратег"}</div>
      </button>
      <div className="mt-2 flex flex-wrap items-center gap-1">
        <StatusBadge value={slot.status} labels={slotStatusLabel} />
        {slot.post_id && (
          <Link to={`/posts/${slot.post_id}`} onPointerDown={(e) => e.stopPropagation()} className="text-xs text-sky-600 hover:underline dark:text-sky-400">
            пост
          </Link>
        )}
        {slot.run_id && !slot.post_id && (
          <Link to={`/runs/${slot.run_id}`} onPointerDown={(e) => e.stopPropagation()} className="text-xs text-sky-600 hover:underline dark:text-sky-400">
            запуск
          </Link>
        )}
      </div>
      {warnings.length > 0 && (
        <div className="mt-2 space-y-1">
          {warnings.slice(-2).map((w, i) => (
            <p key={i} className="flex gap-1 text-xs text-amber-700 dark:text-amber-400">
              <AlertTriangle className="mt-0.5 size-3 shrink-0" />
              <span className="line-clamp-2">{w.message}</span>
            </p>
          ))}
        </div>
      )}
    </div>
  )
}

function DayColumn({
  dayKey,
  index,
  today,
  slots,
  channel,
  onAdd,
  onEdit,
  onChanged,
}: {
  dayKey: string
  index: number
  today: boolean
  slots: Slot[]
  channel: Channel
  onAdd: () => void
  onEdit: (s: Slot) => void
  onChanged: () => void
}) {
  const { setNodeRef, isOver } = useDroppable({ id: dayKey })
  const [, m, d] = dayKey.split("-")
  return (
    <div ref={setNodeRef} className={cn("flex min-h-48 flex-col rounded-xl border bg-muted/30 p-2 transition-colors", isOver && "border-primary bg-primary/5")}>
      <div className="mb-2 flex items-center justify-between px-1">
        <div className={cn("text-sm font-medium", today && "text-primary")}>
          {weekdayShort[index]} <span className="text-muted-foreground tabular-nums">{`${d}.${m}`}</span>
        </div>
        <Button variant="ghost" size="icon" className="size-6" onClick={onAdd} aria-label="Добавить слот">
          <Plus className="size-3.5" />
        </Button>
      </div>
      <div className="flex flex-1 flex-col gap-2">
        {slots.map((s) => (
          <SlotCard key={s.id} slot={s} channel={channel} onEdit={() => onEdit(s)} onChanged={onChanged} />
        ))}
      </div>
    </div>
  )
}

function ReplanDialog({
  open,
  onOpenChange,
  onSubmit,
  pending,
  title,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onSubmit: (c: string) => void
  pending: boolean
  title: string
}) {
  const [comment, setComment] = useState("")
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>Закреплённые слоты останутся как есть. Остальные стратег составит заново с учётом комментария.</DialogDescription>
        </DialogHeader>
        <Textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={4}
          placeholder="Например: больше практики, меньше новостей; в четверг ничего не ставить"
        />
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button onClick={() => onSubmit(comment)} disabled={pending}>
            {pending && <Spinner />} Отправить
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function ChannelPlan() {
  const { channel } = useChannel()
  const client = useQueryClient()
  const [params, setParams] = useSearchParams()
  const week = params.get("week") ?? mondayKey()
  const tz = channel.schedule.timezone
  const queryKey = ["plan", channel.id, week]
  const [dialog, setDialog] = useState<{ slot: Slot | null; day: string | null } | null>(null)
  const [replanOpen, setReplanOpen] = useState(false)

  const {
    data: plan,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey,
    queryFn: () => api<PlanResponse>(`/channels/${channel.id}/plans`, { query: { week } }),
  })
  const { data: run } = useQuery({
    queryKey: ["run-brief", plan?.run_id],
    queryFn: () => api<Run>(`/runs/${plan?.run_id}`),
    enabled: !!plan?.run_id,
    refetchInterval: (q) => (q.state.data && ["running", "queued"].includes(q.state.data.status) ? 3000 : false),
  })

  const refresh = () => {
    client.invalidateQueries({ queryKey: ["plan", channel.id] })
    client.invalidateQueries({ queryKey: ["run-brief"] })
  }

  const create = useMutation({
    mutationFn: (comment: string) => api<{ run_id: string }>(`/channels/${channel.id}/plans`, { body: { week_start: week, comment } }),
    onSuccess: () => {
      toast.success("Стратег составляет план")
      setReplanOpen(false)
      refresh()
    },
    onError: (e) => toast.error((e as Error).message),
  })
  const approve = useMutation({
    mutationFn: () => api(`/plans/${plan?.id}/approve`, { method: "POST" }),
    onSuccess: () => {
      toast.success("План утверждён")
      refresh()
    },
    onError: (e) => toast.error((e as Error).message),
  })
  const replan = useMutation({
    mutationFn: (comment: string) => api(`/plans/${plan?.id}/replan`, { body: { comment } }),
    onSuccess: () => {
      toast.success("План отправлен на доработку")
      setReplanOpen(false)
      refresh()
    },
    onError: (e) => toast.error((e as Error).message),
  })
  const move = useMutation({
    mutationFn: ({ id, publish_at }: { id: number; publish_at: string }) => api(`/slots/${id}`, { method: "PATCH", body: { publish_at } }),
    onMutate: async ({ id, publish_at }) => {
      await client.cancelQueries({ queryKey })
      const prev = client.getQueryData<PlanResponse>(queryKey)
      if (prev) client.setQueryData<PlanResponse>(queryKey, { ...prev, slots: prev.slots.map((s) => (s.id === id ? { ...s, publish_at } : s)) })
      return { prev }
    },
    onError: (e, _, ctx) => {
      if (ctx?.prev) client.setQueryData(queryKey, ctx.prev)
      toast.error((e as Error).message)
    },
    onSettled: refresh,
  })

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }))

  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || !plan) return
    const slot = plan.slots.find((s) => s.id === e.active.id)
    const target = String(e.over.id)
    if (!slot || zonedDayKey(slot.publish_at, tz) === target) return
    move.mutate({ id: slot.id, publish_at: zonedToUtc(target, zonedTime(slot.publish_at, tz), tz).toISOString() })
  }

  const days = Array.from({ length: 7 }, (_, i) => addDaysKey(week, i))
  const todayKey = zonedDayKey(new Date(), tz)
  const runActive = run && ["running", "queued"].includes(run.status)
  const waiting = run?.status === "waiting" && run.waiting_for?.type === "plan_approval"
  const hasDraft = plan?.slots.some((s) => s.status === "draft")

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon" onClick={() => setParams({ week: addDaysKey(week, -7) })} aria-label="Предыдущая неделя">
            <ChevronLeft />
          </Button>
          <Button variant="outline" size="icon" onClick={() => setParams({ week: addDaysKey(week, 7) })} aria-label="Следующая неделя">
            <ChevronRight />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setParams({})} disabled={week === mondayKey()}>
            Эта неделя
          </Button>
          <span className="ml-2 font-medium">
            {week.split("-").reverse().slice(0, 2).join(".")} — {addDaysKey(week, 6).split("-").reverse().slice(0, 2).join(".")}
          </span>
          {plan?.status === "approved" && (
            <ToneBadge tone="success" className="ml-2">
              утверждён
            </ToneBadge>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {plan?.status === "none" && !runActive && (
            <Button onClick={() => create.mutate("")} disabled={create.isPending}>
              {create.isPending ? <Spinner /> : <CalendarPlus />} Составить план
            </Button>
          )}
          {plan?.id && !runActive && (
            <Button variant="outline" onClick={() => setReplanOpen(true)}>
              <RefreshCw /> Перепланировать
            </Button>
          )}
          {plan?.id && (waiting || hasDraft) && (
            <Button onClick={() => approve.mutate()} disabled={approve.isPending}>
              {approve.isPending ? <Spinner /> : <CheckCircle2 />} Утвердить план
            </Button>
          )}
        </div>
      </div>

      {runActive && run && (
        <Callout tone="gray" icon={<Loader2 className="animate-spin" />} title={<>Стратег составляет план</>} className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>{run.current_label ?? "В очереди"}</span>
            <Button size="sm" variant="outline" asChild>
              <Link to={`/runs/${run.id}`}>
                Ход работы <ArrowRight />
              </Link>
            </Button>
          </div>
        </Callout>
      )}
      {run?.status === "deferred" && (
        <Callout tone="yellow" icon={<AlertTriangle />} title={<>Стратег не смог составить план</>} className="mb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {run.error}
              {run.next_attempt_at && `. Следующая попытка ${fmtDateTime(run.next_attempt_at)}`}
            </span>
            <Button size="sm" variant="outline" asChild>
              <Link to={`/runs/${run.id}`}>Подробности</Link>
            </Button>
          </div>
        </Callout>
      )}
      {waiting && (
        <Callout tone="yellow" icon={<AlertTriangle />} title={<>План ждёт утверждения</>} className="mb-4">
          {plan?.auto_approve_at ? `Если не ответить, план утвердится сам ${zonedDateTime(plan.auto_approve_at, tz)}. ` : ""}Перетаскивайте слоты между днями, меняйте
          темы, затем утвердите.
        </Callout>
      )}
      {plan?.summary && (
        <Card className="mb-4">
          <CardContent className="text-sm whitespace-pre-wrap">{plan.summary}</CardContent>
        </Card>
      )}

      {isError && <ErrorState error={error} />}
      {isLoading ? (
        <div className="grid gap-2 sm:auto-cols-[minmax(10.5rem,1fr)] sm:grid-flow-col sm:overflow-x-auto sm:pb-2">
          {Array.from({ length: 7 }).map((_, i) => (
            <Skeleton key={i} className="h-64" />
          ))}
        </div>
      ) : (
        plan && (
          <DndContext sensors={sensors} onDragEnd={onDragEnd}>
            <div className="grid gap-2 sm:auto-cols-[minmax(10.5rem,1fr)] sm:grid-flow-col sm:overflow-x-auto sm:pb-2">
              {days.map((day, i) => (
                <DayColumn
                  key={day}
                  dayKey={day}
                  index={i}
                  today={day === todayKey}
                  slots={plan.slots.filter((s) => zonedDayKey(s.publish_at, tz) === day)}
                  channel={channel}
                  onAdd={() => setDialog({ slot: null, day })}
                  onEdit={(s) => setDialog({ slot: s, day: null })}
                  onChanged={refresh}
                />
              ))}
            </div>
          </DndContext>
        )
      )}

      {dialog && (
        <SlotDialog
          key={dialog.slot ? `slot-${dialog.slot.id}` : `new-${dialog.day}`}
          channel={channel}
          slot={dialog.slot}
          dayKey={dialog.day}
          open
          onOpenChange={(v) => !v && setDialog(null)}
          onSaved={refresh}
        />
      )}
      <ReplanDialog
        open={replanOpen}
        onOpenChange={setReplanOpen}
        title={plan?.id ? "Перепланировать неделю" : "Составить план"}
        pending={replan.isPending || create.isPending}
        onSubmit={(c) => (plan?.id ? replan.mutate(c) : create.mutate(c))}
      />
    </>
  )
}
