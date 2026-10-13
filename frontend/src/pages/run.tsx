import { useMutation } from "@tanstack/react-query"
import { ArrowLeft, ArrowRight, Hourglass, Square, Wifi, WifiOff } from "lucide-react"
import { Link, useParams } from "react-router"
import { toast } from "sonner"

import { Callout, ErrorState, PageHeader, Spinner, Stat, StatusBadge } from "@/components/common"
import { GraphView } from "@/components/run/graph-view"
import { RetryRunButton } from "@/components/run/retry-button"
import { Timeline } from "@/components/run/timeline"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { type RunDetail, useRunStream } from "@/hooks/use-run-stream"
import { api } from "@/lib/api"
import { fmtDateTime, fmtDuration, fmtNumber, fmtUsd } from "@/lib/format"
import { runKindLabel, runStatusLabel } from "@/lib/labels"

function WaitingNotice({ run }: { run: RunDetail }) {
  const w = run.waiting_for
  if (!w) return null
  const links: Record<string, { text: string; to: string }> = {
    post_approval: { text: "Открыть пост", to: `/posts/${String(w.post_id)}` },
    plan_approval: { text: "Открыть контент-план", to: `/channels/${run.channel_id}/plan` },
    onboarding_approval: {
      text: run.channel_type === "smm" ? "Посмотреть стайлгайд и стратегию" : "Посмотреть стайлгайд",
      to: `/channels/${run.channel_id}`,
    },
    strategy_proposal: { text: "Открыть отчёт аналитика", to: `/channels/${run.channel_id}/analytics` },
  }
  const link = links[w.type]
  return (
    <Callout tone="yellow" icon={<Hourglass />} title={<>Ждёт вашего решения</>} className="mb-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>Отдел остановился и продолжит работу, когда вы примете решение.</span>
        {link && (
          <Button asChild size="sm">
            <Link to={link.to}>
              {link.text} <ArrowRight />
            </Link>
          </Button>
        )}
      </div>
    </Callout>
  )
}

export function RunPage() {
  const { id } = useParams()
  const { query, run, events, live, connected, isFinal } = useRunStream(id)

  const cancel = useMutation({
    mutationFn: () => api(`/runs/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Запуск останавливается")
      query.refetch()
    },
    onError: (e) => toast.error((e as Error).message),
  })

  if (query.isError) return <ErrorState error={query.error} />
  if (!run)
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="h-[460px] w-full" />
      </div>
    )

  const liveCost = run.llm.cost

  return (
    <>
      <Button variant="ghost" size="sm" asChild className="mb-2 -ml-2">
        <Link to={`/channels/${run.channel_id}/runs`}>
          <ArrowLeft /> Все запуски канала
        </Link>
      </Button>
      <PageHeader
        title={run.title || runKindLabel[run.kind]}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge value={run.status} labels={runStatusLabel} />
            <span>{runKindLabel[run.kind]}</span>
            <span>·</span>
            <span>начат {fmtDateTime(run.started_at ?? run.created_at)}</span>
            {run.current_label && !isFinal && (
              <>
                <span>·</span>
                <span className="font-medium text-foreground">{run.current_label}</span>
              </>
            )}
            {!isFinal && (
              <span className="flex items-center gap-1 text-xs" title={connected ? "Живые события подключены" : "Переподключение"}>
                {connected ? <Wifi className="size-3.5 text-emerald-500" /> : <WifiOff className="size-3.5 text-muted-foreground" />}
              </span>
            )}
          </span>
        }
        actions={
          !isFinal && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline" disabled={cancel.isPending}>
                  {cancel.isPending ? <Spinner /> : <Square />} Остановить
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Остановить запуск?</AlertDialogTitle>
                  <AlertDialogDescription>
                    Отдел прекратит работу после текущего шага. Уже потраченные деньги не вернутся, начатый пост не будет опубликован.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Продолжить работу</AlertDialogCancel>
                  <AlertDialogAction onClick={() => cancel.mutate()}>Остановить</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )
        }
      />

      {run.status === "waiting" && <WaitingNotice run={run} />}
      {run.error && run.status !== "done" && (
        <Callout
          tone="red"
          title={<>{run.status === "deferred" ? "Модель недоступна, запуск повторится позже" : "Запуск завершился ошибкой"}</>}
          action={(run.status === "failed" || run.status === "deferred") && <RetryRunButton runId={run.id} />}
          className="mb-6"
        >
          {run.error}
          {run.next_attempt_at && <div className="mt-1">Следующая попытка: {fmtDateTime(run.next_attempt_at)}</div>}
        </Callout>
      )}

      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Стоимость" value={fmtUsd(liveCost)} hint={`${run.llm.calls} вызовов моделей`} />
        <Stat
          label="Токены"
          value={fmtNumber(run.llm.prompt_tokens + run.llm.completion_tokens)}
          hint={`вход ${fmtNumber(run.llm.prompt_tokens)} · выход ${fmtNumber(run.llm.completion_tokens)}`}
        />
        <Stat label="Время" value={fmtDuration(run.started_at, run.finished_at)} hint={run.attempts > 1 ? `попытка ${run.attempts}` : undefined} />
        <Stat
          label="Результат"
          value={
            run.post_id ? (
              <Link to={`/posts/${run.post_id}`} className="text-base underline-offset-4 hover:underline">
                Пост #{run.post_id}
              </Link>
            ) : run.plan_id ? (
              <Link to={`/channels/${run.channel_id}/plan`} className="text-base underline-offset-4 hover:underline">
                План #{run.plan_id}
              </Link>
            ) : (
              <span className="text-base text-muted-foreground">{isFinal ? "—" : "в работе"}</span>
            )
          }
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <Card className="h-fit xl:sticky xl:top-6">
          <CardHeader>
            <CardTitle>Схема</CardTitle>
          </CardHeader>
          <CardContent>
            <GraphView runId={run.id} events={events} finished={isFinal} succeeded={run.status === "done"} />
            <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-sm border border-sky-500 bg-sky-500/20" /> сейчас
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-sm border border-emerald-500 bg-emerald-500/20" /> пройдено
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-sm border border-amber-500 bg-amber-500/20" /> ждёт решения
              </span>
              <span className="flex items-center gap-1.5">
                <span className="size-2.5 rounded-sm border border-red-500 bg-red-500/20" /> ошибка
              </span>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">Ход работы {!isFinal && <Spinner className="text-muted-foreground" />}</CardTitle>
          </CardHeader>
          <CardContent>
            <Timeline events={events} live={live} />
          </CardContent>
        </Card>
      </div>
    </>
  )
}
