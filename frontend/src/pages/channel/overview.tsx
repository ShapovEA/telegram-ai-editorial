import { useInvalidate } from "@refinedev/core"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowRight, CheckCircle2, Circle, FileText, Hourglass, Loader2, Play, RefreshCw, Rocket } from "lucide-react"
import { useEffect, useState, type ReactNode } from "react"
import { Link, useNavigate } from "react-router"
import { toast } from "sonner"

import { BriefForm } from "@/components/channel/brief-form"
import { StrategyEditor, emptyStrategy, rubricShareTotal } from "@/components/channel/strategy-editor"
import { StyleguideEditor } from "@/components/channel/styleguide-editor"
import { ChannelTelegram } from "@/components/channel/telegram-connect"
import { Callout, LoadingRows, SectionHeader, Spinner, StatusBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import { briefMissing } from "@/lib/brief"
import { fmtAgo, fmtDateTime } from "@/lib/format"
import { postStatusLabel, runKindLabel, runStatusLabel } from "@/lib/labels"
import type { Channel, Post, Run, Source, Strategy, Styleguide } from "@/lib/types"
import { zonedDateTime } from "@/lib/tz"
import { cn } from "@/lib/utils"
import { useChannel } from "@/pages/channel/layout"

function SetupStep({
  n,
  title,
  description,
  done,
  children,
}: {
  n: number
  title: string
  description: string
  done: boolean
  children: ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3">
          <span
            className={cn(
              "flex size-7 shrink-0 items-center justify-center rounded-full border text-sm font-medium",
              done && "border-emerald-500 bg-emerald-500 text-white",
            )}
          >
            {done ? <CheckCircle2 className="size-4" /> : n}
          </span>
          <div>
            <CardTitle>{title}</CardTitle>
            <CardDescription>{description}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

function SetupWizard({ channel, refetch }: { channel: Channel; refetch: () => void }) {
  const navigate = useNavigate()
  const { data: sources } = useQuery({
    queryKey: ["sources", channel.id],
    queryFn: () => api<Source[]>(`/channels/${channel.id}/sources`),
  })
  const missing = briefMissing(channel.brief, channel.type)
  const feedsMissing = channel.type === "news" && (sources?.length ?? 0) === 0
  const briefDone = missing.length === 0 && !feedsMissing
  const blocker = missing.length
    ? "Сначала заполните обязательные поля брифа."
    : feedsMissing
      ? "Сначала добавьте хотя бы одну RSS-ленту."
      : !channel.telegram_connected
        ? "Сначала подключите Telegram-канал."
        : null
  const smm = channel.type === "smm"

  const start = useMutation({
    mutationFn: () => api<{ run_id: string }>(`/channels/${channel.id}/onboarding`, { method: "POST" }),
    onSuccess: ({ run_id }) => {
      refetch()
      navigate(`/runs/${run_id}`)
    },
    onError: (e) => toast.error((e as Error).message),
  })

  return (
    <div className="space-y-6">
      <Callout tone="gray" icon={<Rocket />} title={<>Настройка канала</>}>
        Заполните бриф, затем запустите отдел: оформитель составит стайлгайд{smm ? ", стратег — стратегию" : ""}. Вы проверите и утвердите.
      </Callout>
      <SetupStep
        n={1}
        title="Бриф"
        description={smm ? "Главный документ канала: о чём, для кого и каким голосом" : "О чём канал, для кого и откуда брать новости"}
        done={briefDone}
      >
        <BriefForm channel={channel} onSaved={refetch} />
      </SetupStep>
      {!channel.telegram_connected && (
        <SetupStep n={2} title="Telegram" description="Бот сервиса публикует посты от имени канала, название канала берётся из Telegram" done={false}>
          <ChannelTelegram channel={channel} onConnected={refetch} />
        </SetupStep>
      )}
      <Card className={cn(!blocker && "ring-primary")}>
        <CardContent className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="font-medium">Запустить отдел</div>
            <p className="text-sm text-muted-foreground">{blocker ?? "Всё готово. Займёт несколько минут, за ходом работы можно следить в реальном времени."}</p>
          </div>
          <Button size="lg" disabled={!!blocker || start.isPending} onClick={() => start.mutate()}>
            {start.isPending ? <Spinner /> : <Play />} {smm ? "Составить стайлгайд и стратегию" : "Составить стайлгайд"}
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

function OnboardingApproval({ channel, run, onDone }: { channel: Channel; run: Run; onDone: () => void }) {
  const w = run.waiting_for as { styleguide?: Styleguide; strategy?: Strategy | null }
  const [styleguide, setStyleguide] = useState<Styleguide>(w.styleguide ?? channel.styleguide)
  const [strategy, setStrategy] = useState<Strategy>(w.strategy ?? emptyStrategy)
  const [comment, setComment] = useState("")
  const hasStrategy = channel.type === "smm"

  const decide = useMutation({
    mutationFn: (action: "approve" | "regenerate") =>
      api<{ run_id: string }>(`/channels/${channel.id}/onboarding/decision`, {
        body: { action, comment, styleguide, strategy: hasStrategy ? strategy : undefined },
      }),
    onSuccess: (_, action) => {
      toast.success(action === "approve" ? "Утверждено. Отдел готовит первые идеи" : "Отправлено на доработку")
      onDone()
    },
    onError: (e) => toast.error((e as Error).message),
  })

  const shareOk = !hasStrategy || strategy.rubrics.length === 0 || rubricShareTotal(strategy) === 100

  return (
    <div className="space-y-6">
      <Callout tone="yellow" icon={<Hourglass />} title={<>Проверьте и утвердите</>}>
        Отдел подготовил {hasStrategy ? "стайлгайд и стратегию" : "стайлгайд"}. Поправьте что нужно прямо здесь и утвердите, или опишите, что переделать.
      </Callout>
      <Tabs defaultValue="styleguide">
        <TabsList>
          <TabsTrigger value="styleguide">Стайлгайд</TabsTrigger>
          {hasStrategy && <TabsTrigger value="strategy">Стратегия</TabsTrigger>}
        </TabsList>
        <TabsContent value="styleguide">
          <Card>
            <CardContent>
              <StyleguideEditor value={styleguide} onChange={setStyleguide} />
            </CardContent>
          </Card>
        </TabsContent>
        {hasStrategy && (
          <TabsContent value="strategy">
            <Card>
              <CardContent>
                <StrategyEditor value={strategy} onChange={setStrategy} />
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>
      <Card>
        <CardContent className="space-y-3">
          <Label htmlFor="ob-comment">Что переделать</Label>
          <Textarea
            id="ob-comment"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={3}
            placeholder="Например: тон слишком официальный, рубрика про новости лишняя"
          />
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="outline" disabled={!comment.trim() || decide.isPending} onClick={() => decide.mutate("regenerate")}>
              <RefreshCw /> Переделать
            </Button>
            <Button disabled={!shareOk || decide.isPending} onClick={() => decide.mutate("approve")}>
              {decide.isPending ? <Spinner /> : <CheckCircle2 />} Утвердить и запустить канал
            </Button>
          </div>
          {!shareOk && <p className="text-right text-sm text-destructive">Сумма долей рубрик должна быть 100%</p>}
        </CardContent>
      </Card>
    </div>
  )
}

function OnboardingPanel({ channel, refetch }: { channel: Channel; refetch: () => void }) {
  const client = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ["onboarding", channel.id],
    queryFn: () => api<{ run: Run | null }>(`/channels/${channel.id}/onboarding`),
    refetchInterval: (q) => (q.state.data?.run?.status === "waiting" ? false : 4000),
  })
  const run = data?.run
  const retry = useMutation({
    mutationFn: () => api<{ run_id: string }>(`/channels/${channel.id}/onboarding`, { method: "POST" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["onboarding", channel.id] }),
    onError: (e) => toast.error((e as Error).message),
  })

  useEffect(() => {
    if (run?.status === "done") refetch()
  }, [run?.status, refetch])

  if (isLoading) return <LoadingRows rows={3} />
  if (!run) return null

  if (run.status === "waiting" && run.waiting_for?.type === "onboarding_approval")
    return (
      <OnboardingApproval
        key={run.id + JSON.stringify(run.waiting_for).length}
        channel={channel}
        run={run}
        onDone={() => {
          client.invalidateQueries({ queryKey: ["onboarding", channel.id] })
          refetch()
        }}
      />
    )

  if (run.status === "failed" || run.status === "cancelled")
    return (
      <Callout tone="red" title={<>Настройка не завершилась</>}>
        <div className="space-y-3">
          <p>{run.error ?? "Запуск остановлен"}</p>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => retry.mutate()} disabled={retry.isPending}>
              {retry.isPending && <Spinner />} Запустить заново
            </Button>
            <Button size="sm" variant="outline" asChild>
              <Link to={`/runs/${run.id}`}>Подробности</Link>
            </Button>
          </div>
        </div>
      </Callout>
    )

  if (run.status === "deferred")
    return (
      <Callout tone="yellow" icon={<Hourglass />} title={<>Настройка приостановлена: модель недоступна</>}>
        <div className="space-y-3">
          <p>
            {run.error}
            {run.next_attempt_at && `. Следующая попытка ${fmtDateTime(run.next_attempt_at)}`}
          </p>
          <Button size="sm" variant="outline" asChild>
            <Link to={`/runs/${run.id}`}>Подробности</Link>
          </Button>
        </div>
      </Callout>
    )

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Loader2 className="size-5 animate-spin text-sky-500" />
          <div>
            <div className="font-medium">Отдел готовит стайлгайд{channel.type === "smm" ? " и стратегию" : ""}</div>
            <p className="text-sm text-muted-foreground">{run.current_label ?? "Запуск в очереди"}</p>
          </div>
        </div>
        <Button variant="outline" asChild>
          <Link to={`/runs/${run.id}`}>
            Смотреть ход работы <ArrowRight />
          </Link>
        </Button>
      </CardContent>
    </Card>
  )
}

function Dashboard({ channel }: { channel: Channel }) {
  const { data: attention, isLoading: l1 } = useQuery({
    queryKey: ["posts", channel.id, "attention"],
    queryFn: () => api<{ items: Post[] }>(`/channels/${channel.id}/posts`, { query: { status: "awaiting_approval,needs_attention", limit: 20 } }),
  })
  const { data: upcoming } = useQuery({
    queryKey: ["posts", channel.id, "scheduled"],
    queryFn: () => api<{ items: Post[] }>(`/channels/${channel.id}/posts`, { query: { status: "scheduled", limit: 10 } }),
  })
  const { data: runs, isLoading: l2 } = useQuery({
    queryKey: ["runs", channel.id, "active"],
    queryFn: () => api<Run[]>(`/channels/${channel.id}/runs`, { query: { status: "queued,running,waiting,deferred", limit: 20 } }),
  })

  const waitingRuns = (runs ?? []).filter((r) => r.status === "waiting" && r.waiting_for?.type !== "post_approval")
  const activeRuns = (runs ?? []).filter((r) => r.status !== "waiting")
  const attentionPosts = attention?.items ?? []

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Ждут вашего решения</CardTitle>
          <CardDescription>Посты на согласование, планы и предложения отдела</CardDescription>
        </CardHeader>
        <CardContent>
          {(l1 || l2) && <LoadingRows rows={2} />}
          {!l1 && !l2 && attentionPosts.length === 0 && waitingRuns.length === 0 && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <CheckCircle2 className="size-4 text-emerald-500" /> Ничего не ждёт. Отдел работает сам
            </p>
          )}
          <ul className="divide-y">
            {waitingRuns.map((r) => (
              <li key={r.id}>
                <Link
                  to={r.waiting_for?.type === "plan_approval" ? `/channels/${channel.id}/plan` : `/runs/${r.id}`}
                  className="flex items-center gap-3 py-3 hover:bg-muted/40"
                >
                  <Hourglass className="size-4 shrink-0 text-amber-500" />
                  <span className="min-w-0 flex-1 truncate">{r.title || runKindLabel[r.kind]}</span>
                  <span className="text-xs text-muted-foreground">{fmtAgo(r.created_at)}</span>
                  <ArrowRight className="size-4 text-muted-foreground" />
                </Link>
              </li>
            ))}
            {attentionPosts.map((p) => (
              <li key={p.id}>
                <Link to={`/posts/${p.id}`} className="flex items-center gap-3 py-3 hover:bg-muted/40">
                  <FileText className="size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate">{p.title || p.text.slice(0, 80)}</span>
                  <StatusBadge value={p.status} labels={postStatusLabel} />
                  <span className="hidden text-xs text-muted-foreground sm:inline">{p.publish_at ? `выход ${zonedDateTime(p.publish_at, channel.schedule.timezone)}` : ""}</span>
                  <ArrowRight className="size-4 text-muted-foreground" />
                </Link>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Сейчас в работе</CardTitle>
        </CardHeader>
        <CardContent>
          {activeRuns.length === 0 ? (
            <p className="text-sm text-muted-foreground">Активных запусков нет</p>
          ) : (
            <ul className="space-y-2">
              {activeRuns.map((r) => (
                <li key={r.id}>
                  <Link to={`/runs/${r.id}`} className="flex items-center gap-3 rounded-lg border p-3 hover:bg-muted/40">
                    {r.status === "running" ? <Loader2 className="size-4 animate-spin text-sky-500" /> : <Circle className="size-4 text-muted-foreground" />}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium">{r.title || runKindLabel[r.kind]}</div>
                      <div className="truncate text-xs text-muted-foreground">{r.current_label ?? runStatusLabel[r.status][0]}</div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Ближайшие публикации</CardTitle>
        </CardHeader>
        <CardContent>
          {!upcoming?.items.length ? (
            <p className="text-sm text-muted-foreground">Запланированных постов нет</p>
          ) : (
            <ul className="space-y-2">
              {upcoming.items.map((p) => (
                <li key={p.id}>
                  <Link to={`/posts/${p.id}`} className="flex items-center gap-3 rounded-lg border p-3 hover:bg-muted/40">
                    <div className="w-24 shrink-0 text-xs text-muted-foreground tabular-nums">{p.publish_at && zonedDateTime(p.publish_at, channel.schedule.timezone)}</div>
                    <div className="min-w-0 flex-1 truncate text-sm">{p.title || p.text.slice(0, 80)}</div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function ChannelSwitch({ channel, refetch }: { channel: Channel; refetch: () => void }) {
  const invalidate = useInvalidate()
  const toggle = useMutation({
    mutationFn: (active: boolean) => api<Channel>(`/channels/${channel.id}`, { method: "PATCH", body: { status: active ? "active" : "paused" } }),
    onSuccess: (c) => {
      toast.success(c.status === "active" ? "Канал включён" : "Канал поставлен на паузу")
      refetch()
      invalidate({ resource: "channels", invalidates: ["list"] })
    },
    onError: (e) => toast.error((e as Error).message),
  })
  const paused = channel.status === "paused"

  return (
    <Card className={cn("mb-6", paused && "ring-amber-500/60")}>
      <CardContent className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="font-medium">{paused ? "Канал на паузе" : "Канал работает"}</div>
          <p className="text-sm text-muted-foreground">На паузе отдел не создаёт и не публикует посты. Запланированное остаётся.</p>
        </div>
        <Switch checked={!paused} disabled={toggle.isPending} onCheckedChange={(v) => toggle.mutate(v)} aria-label="Канал работает" />
      </CardContent>
    </Card>
  )
}

export function ChannelOverview() {
  const { channel, refetch } = useChannel()

  if (channel.status === "draft") return <SetupWizard channel={channel} refetch={refetch} />
  if (channel.status === "onboarding") return <OnboardingPanel channel={channel} refetch={refetch} />

  return (
    <>
      <ChannelSwitch channel={channel} refetch={refetch} />
      {!channel.telegram_connected && (
        <Callout tone="gray" title={<>Telegram не подключён</>} className="mb-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            Посты готовятся, но публиковать их некуда.
            <Button size="sm" variant="outline" asChild>
              <Link to="settings?section=telegram">Подключить</Link>
            </Button>
          </div>
        </Callout>
      )}
      <SectionHeader title="Обзор" />
      <Dashboard channel={channel} />
    </>
  )
}
