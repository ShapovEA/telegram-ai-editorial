import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  Clock,
  FileOutput,
  Hourglass,
  Loader2,
  Play,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  Wrench,
  XCircle,
} from "lucide-react"
import { useState, type ReactNode } from "react"

import { DataView } from "@/components/run/data-view"
import { Badge } from "@/components/ui/badge"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import type { LiveCall } from "@/hooks/use-run-stream"
import { fmtNumber, fmtTime, fmtUsd } from "@/lib/format"
import { roleLabel } from "@/lib/labels"
import type { Role, RunEvent } from "@/lib/types"
import { cn } from "@/lib/utils"

type StepStatus = "running" | "done" | "error" | "waiting"

type Step = {
  key: string
  node: string
  label: string
  status: StepStatus
  startTs: string
  durationMs?: number
  items: RunEvent[]
}

const OUTPUT_LABELS: Record<string, string> = {
  stats: "Статистика",
  report: "Отчёт",
  proposal: "Предложение по стратегии",
  samples: "Образцы текстов",
  styleguide: "Стайлгайд",
  strategy: "Стратегия",
  ideas: "Идеи",
  plan_context: "Контекст планирования",
  plan_draft: "Черновик плана",
  plan_checks: "Проверки плана",
  plan_approved: "План утверждён",
  topics: "Темы",
  post: "Пост создан",
  scheduled: "Запланировано",
  outcome: "Итог",
  feeds: "Обновление лент",
  stories: "Сюжеты",
  scout: "Оценка сюжетов",
  chief: "Решение шеф-редактора",
  sources: "Источники",
  factcheck: "Проверка фактов",
  chief_fix: "Правка шеф-редактора",
  rejected: "Сюжет отброшен",
  brief: "Задание писателю",
  research: "Исследование",
  goal_check: "Проверка цели",
  draft: "Черновик",
  auto_checks: "Проверки кодом",
  review: "Ревью редактора",
  formatted: "Вёрстка",
}

type Entry = { kind: "step"; step: Step } | { kind: "start"; event: RunEvent } | { kind: "end"; event: RunEvent }

function buildEntries(events: RunEvent[]): { entries: Entry[]; steps: Step[] } {
  const entries: Entry[] = []
  const steps: Step[] = []
  const open = new Map<string, Step>()
  let started = false
  for (const e of events) {
    if (e.type === "run_start") {
      if (started) entries.push({ kind: "start", event: e })
      started = true
      continue
    }
    if (e.type === "run_end") {
      entries.push({ kind: "end", event: e })
      open.clear()
      continue
    }
    if (e.type === "node_start" && e.node) {
      const step: Step = {
        key: `${e.node}-${e.seq}`,
        node: e.node,
        label: String(e.data.label ?? e.node),
        status: "running",
        startTs: e.ts,
        items: [],
      }
      steps.push(step)
      entries.push({ kind: "step", step })
      open.set(e.node, step)
      continue
    }
    const step = (e.node && open.get(e.node)) || steps[steps.length - 1]
    if (!step) continue
    if (e.type === "node_end") {
      step.status = "done"
      step.durationMs = Number(e.data.duration_ms ?? 0)
      open.delete(step.node)
    } else if (e.type === "node_error") {
      step.status = "error"
      step.items.push(e)
      open.delete(step.node)
    } else if (e.type === "node_wait") {
      step.status = "waiting"
    } else {
      step.items.push(e)
    }
  }
  return { entries, steps }
}

const END_TEXT: Record<string, (error: string) => string> = {
  done: () => "Запуск завершён",
  waiting: () => "Ждёт решения владельца",
  deferred: (error) => `Пауза до следующей попытки: ${error}`,
  cancelled: () => "Запуск остановлен пользователем",
  interrupted: () => "Запуск прерван",
}

function Marker({ icon, text, ts }: { icon: ReactNode; text: string; ts: string }) {
  return (
    <li className="relative pl-8 text-sm">
      <span className="absolute top-2 left-0 flex size-6 items-center justify-center rounded-full border bg-background">{icon}</span>
      <div className="px-2 py-2.5 text-muted-foreground">
        {text}
        <span className="ml-2 text-xs tabular-nums">{fmtTime(ts)}</span>
      </div>
    </li>
  )
}

const statusIcon: Record<StepStatus, ReactNode> = {
  running: <Loader2 className="size-4 animate-spin text-sky-500" />,
  done: <CheckCircle2 className="size-4 text-emerald-500" />,
  error: <XCircle className="size-4 text-red-500" />,
  waiting: <Hourglass className="size-4 text-amber-500" />,
}

function Row({ icon, children, className }: { icon: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex gap-2.5 text-sm", className)}>
      <div className="mt-0.5 shrink-0 text-muted-foreground [&>svg]:size-4">{icon}</div>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  )
}

function Expandable({ title, children, defaultOpen = false }: { title: ReactNode; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="group flex items-center gap-1 text-left text-sm hover:text-foreground">
        <ChevronRight className="size-3.5 shrink-0 transition-transform group-data-[state=open]:rotate-90" />
        {title}
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2">{children}</CollapsibleContent>
    </Collapsible>
  )
}

function roleName(role: unknown) {
  return roleLabel[role as Role] ?? String(role ?? "")
}

function EventItem({ e }: { e: RunEvent }) {
  const d = e.data as Record<string, unknown>
  switch (e.type) {
    case "tool_call":
      return (
        <Row icon={<Wrench />}>
          <Expandable title={<span className="font-medium">{String(d.label || d.tool)}</span>}>
            <div className="rounded-lg bg-muted/40 p-2.5">
              <DataView value={d.args} />
            </div>
          </Expandable>
        </Row>
      )
    case "tool_result":
      return (
        <Row icon={<FileOutput />}>
          <Expandable
            title={
              <span className="text-muted-foreground">
                Результат: {String(d.label || d.tool)} · {fmtNumber(Number(d.size ?? 0))} симв.
              </span>
            }
          >
            <pre className="max-h-72 overflow-auto rounded-lg bg-muted/40 p-2.5 font-mono text-xs whitespace-pre-wrap">{String(d.preview ?? "")}</pre>
          </Expandable>
        </Row>
      )
    case "llm_call":
      return (
        <Row icon={<Bot />}>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-medium">{roleName(d.role)}</span>
            <span className="font-mono text-xs text-muted-foreground">{String(d.model_used || d.model)}</span>
            {d.model_used && d.model_used !== d.model ? <Badge variant="outline">резервная модель</Badge> : null}
            <span className="text-xs text-muted-foreground tabular-nums">
              {fmtNumber(Number(d.prompt_tokens ?? 0))} → {fmtNumber(Number(d.completion_tokens ?? 0))} ток.
              {Number(d.reasoning_tokens ?? 0) > 0 && ` (рассуждения ${fmtNumber(Number(d.reasoning_tokens))})`}
            </span>
            <span className="text-xs tabular-nums">{fmtUsd(Number(d.cost ?? 0))}</span>
            <span className="text-xs text-muted-foreground tabular-nums">{(Number(d.latency_ms ?? 0) / 1000).toFixed(1)} с</span>
          </div>
          {d.reasoning ? (
            <div className="mt-1.5">
              <Expandable title={<span className="text-xs text-muted-foreground">Рассуждения модели</span>}>
                <p className="max-h-60 overflow-auto rounded-lg bg-muted/40 p-2.5 text-xs whitespace-pre-wrap">{String(d.reasoning)}</p>
              </Expandable>
            </div>
          ) : null}
        </Row>
      )
    case "output": {
      const { kind, ...rest } = d
      const title = OUTPUT_LABELS[String(kind)] ?? String(kind)
      if (kind === "draft" && typeof rest.text === "string") {
        return (
          <Row icon={<FileOutput />}>
            <div className="font-medium">
              {title}
              {rest.attempt ? <span className="font-normal text-muted-foreground"> · попытка {String(rest.attempt)}</span> : null}
            </div>
            {rest.title ? <div className="mt-1 font-semibold">{String(rest.title)}</div> : null}
            <p className="mt-1 rounded-lg border bg-card p-3 text-sm whitespace-pre-wrap">{rest.text}</p>
          </Row>
        )
      }
      return (
        <Row icon={<FileOutput />}>
          <Expandable title={<span className="font-medium">{title}</span>} defaultOpen={["review", "auto_checks", "outcome", "goal_check", "chief", "rejected"].includes(String(kind))}>
            <div className="rounded-lg bg-muted/40 p-2.5">
              <DataView value={rest} />
            </div>
          </Expandable>
        </Row>
      )
    }
    case "guard":
      return d.injection ? (
        <Row icon={<ShieldAlert className="text-red-500" />}>
          <span className="font-medium text-red-600 dark:text-red-400">Текст отклонён: попытка prompt injection.</span>{" "}
          <span className="text-muted-foreground">{String(d.reason ?? "")}</span>
          {d.source ? <div className="truncate text-xs text-muted-foreground">{String(d.source)}</div> : null}
        </Row>
      ) : (
        <Row icon={<ShieldCheck className="text-emerald-500" />}>
          <span className="text-muted-foreground">Проверка на инъекцию пройдена</span>
          {d.source ? <span className="ml-1 truncate text-xs text-muted-foreground">· {String(d.source)}</span> : null}
        </Row>
      )
    case "fact_rejected":
      return (
        <Row icon={<AlertTriangle className="text-amber-500" />}>
          <span className="font-medium">Факт отклонён:</span> {String(d.claim ?? "")}
          <div className="text-xs text-muted-foreground">{String(d.reason ?? "")}</div>
        </Row>
      )
    case "schema_retry":
    case "llm_retry":
    case "publisher_retry":
      return (
        <Row icon={<RotateCcw className="text-amber-500" />}>
          <span className="text-muted-foreground">
            {e.type === "llm_retry" ? "Повтор запроса к модели" : e.type === "schema_retry" ? "Ответ не по схеме, повтор" : "Повтор вёрстки"}
            {d.attempt ? ` · попытка ${String(d.attempt)}` : ""}
          </span>
          <Expandable title={<span className="text-xs text-muted-foreground">Подробности</span>}>
            <pre className="overflow-auto rounded-lg bg-muted/40 p-2 text-xs whitespace-pre-wrap">{JSON.stringify(d.error ?? d.errors, null, 2)}</pre>
            {d.raw ? <pre className="mt-2 max-h-60 overflow-auto rounded-lg bg-muted/40 p-2 font-mono text-xs whitespace-pre-wrap">{String(d.raw)}</pre> : null}
          </Expandable>
        </Row>
      )
    case "node_error":
      return (
        <Row icon={<XCircle className="text-red-500" />}>
          <pre className="overflow-auto rounded-lg bg-red-500/10 p-2.5 font-mono text-xs whitespace-pre-wrap text-red-700 dark:text-red-300">{String(d.error ?? "")}</pre>
        </Row>
      )
    default:
      return (
        <Row icon={<CircleDashed />}>
          <span className="text-muted-foreground">{e.type}</span>
        </Row>
      )
  }
}

function LiveOutput({ call }: { call: LiveCall }) {
  return (
    <Row icon={<Bot className="text-sky-500" />}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{roleName(call.role)}</span>
        {call.model && <span className="font-mono">{call.model}</span>}
        <span className="flex items-center gap-1">
          <Loader2 className="size-3 animate-spin" /> пишет
        </span>
      </div>
      {call.reasoning && !call.text && <p className="mt-1.5 line-clamp-4 text-xs whitespace-pre-wrap text-muted-foreground italic">{call.reasoning}</p>}
      {call.text && (
        <p className="mt-1.5 max-h-80 overflow-auto rounded-lg border border-sky-500/30 bg-sky-500/5 p-3 text-sm whitespace-pre-wrap">
          {call.text}
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-sky-500 align-text-bottom" />
        </p>
      )}
    </Row>
  )
}

function StepCard({ step, live }: { step: Step; live: LiveCall[] }) {
  const [open, setOpen] = useState(step.status !== "done")
  const calls = step.items.filter((i) => i.type === "llm_call")
  const cost = calls.reduce((s, c) => s + Number(c.data.cost ?? 0), 0)
  const hasBody = step.items.length > 0 || live.length > 0

  return (
    <li className="relative pl-8">
      <span className="absolute top-3 left-0 flex size-6 items-center justify-center rounded-full border bg-background">{statusIcon[step.status]}</span>
      <Collapsible open={open && hasBody} onOpenChange={setOpen}>
        <CollapsibleTrigger disabled={!hasBody} className="flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left hover:bg-muted/50 disabled:cursor-default disabled:hover:bg-transparent">
          <span className="min-w-0 flex-1 truncate font-medium">{step.label}</span>
          {calls.length > 0 && (
            <span className="hidden text-xs text-muted-foreground tabular-nums sm:inline">
              {calls.length} {calls.length === 1 ? "вызов" : "вызова"} · {fmtUsd(cost)}
            </span>
          )}
          <span className="flex items-center gap-1 text-xs text-muted-foreground tabular-nums">
            <Clock className="size-3" />
            {step.durationMs !== undefined ? `${(step.durationMs / 1000).toFixed(1)} с` : fmtTime(step.startTs)}
          </span>
          {hasBody && <ChevronRight className={cn("size-4 text-muted-foreground transition-transform", open && "rotate-90")} />}
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="space-y-3 px-2 pt-1 pb-3">
            {step.items.map((e) => (
              <EventItem key={e.seq} e={e} />
            ))}
            {live.map((c) => (
              <LiveOutput key={c.call_id} call={c} />
            ))}
          </div>
        </CollapsibleContent>
      </Collapsible>
    </li>
  )
}

export function Timeline({ events, live }: { events: RunEvent[]; live: Record<string, LiveCall> }) {
  const { entries, steps } = buildEntries(events)
  const liveCalls = Object.values(live)
  const lastRunning = [...steps].reverse().find((s) => s.status === "running")

  if (steps.length === 0 && liveCalls.length === 0)
    return <p className="py-10 text-center text-sm text-muted-foreground">Запуск ещё не начал работу</p>

  return (
    <ol className="relative space-y-1 before:absolute before:top-4 before:bottom-4 before:left-3 before:w-px before:bg-border">
      {entries.map((entry) => {
        if (entry.kind === "step") {
          const s = entry.step
          return (
            <StepCard
              key={s.key}
              step={s}
              live={liveCalls.filter((c) => c.node === s.node || (!steps.some((x) => x.node === c.node) && s === lastRunning))}
            />
          )
        }
        const e = entry.event
        if (entry.kind === "start") {
          const text = e.data.resume ? "Работа продолжена после решения владельца" : `Повторная попытка ${String(e.data.attempt ?? "")}`
          return <Marker key={e.seq} icon={<Play className="size-3.5 text-sky-500" />} text={text} ts={e.ts} />
        }
        const status = String(e.data.status ?? "")
        const error = String(e.data.error ?? status)
        const icon =
          status === "done" ? (
            <CheckCircle2 className="size-4 text-emerald-500" />
          ) : status === "waiting" || status === "deferred" || status === "interrupted" ? (
            <Hourglass className="size-4 text-amber-500" />
          ) : (
            <XCircle className="size-4 text-red-500" />
          )
        return <Marker key={e.seq} icon={icon} text={END_TEXT[status]?.(error) ?? `Запуск завершился ошибкой: ${error}`} ts={e.ts} />
      })}
    </ol>
  )
}
