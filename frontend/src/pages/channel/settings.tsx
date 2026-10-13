import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Clock, Trash2 } from "lucide-react"
import { useState, type ReactNode } from "react"
import { useNavigate, useSearchParams } from "react-router"
import { toast } from "sonner"

import { BriefForm } from "@/components/channel/brief-form"
import { RoleModelEditor, type CatalogModel } from "@/components/channel/model-picker"
import { PromptsEditor } from "@/components/channel/prompts-editor"
import { ScheduleEditor } from "@/components/channel/schedule-editor"
import { StrategyEditor, emptyStrategy, rubricShareTotal } from "@/components/channel/strategy-editor"
import { StyleguideEditor } from "@/components/channel/styleguide-editor"
import { ChannelTelegram } from "@/components/channel/telegram-connect"
import { Callout, LoadingRows, Spinner, ToneBadge } from "@/components/common"
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { api } from "@/lib/api"
import type { Channel, ChannelOptions, Role, RoleModel, Strategy, Styleguide } from "@/lib/types"
import { cn } from "@/lib/utils"
import { useChannel } from "@/pages/channel/layout"

function usePatch(channel: Channel, refetch: () => void) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Record<string, unknown>) => api<Channel>(`/channels/${channel.id}`, { method: "PATCH", body }),
    onSuccess: () => {
      toast.success("Сохранено")
      refetch()
      client.invalidateQueries({ queryKey: ["default", "list", "channels"] })
    },
    onError: (e) => toast.error((e as Error).message),
  })
}

function SaveBar({ dirty, pending, onSave, disabled, children }: { dirty: boolean; pending: boolean; onSave: () => void; disabled?: boolean; children?: ReactNode }) {
  return (
    <div className="mt-6 flex flex-wrap items-center justify-end gap-3">
      {children}
      <Button onClick={onSave} disabled={!dirty || pending || disabled}>
        {pending && <Spinner />} Сохранить
      </Button>
    </div>
  )
}

function NumberOption({ label, hint, value, onChange, suffix }: { label: string; hint?: string; value: number; onChange: (v: number) => void; suffix: string }) {
  return (
    <div className="grid gap-1.5">
      <Label>{label}</Label>
      <div className="flex items-center gap-2">
        <Input type="number" min={0} value={value} onChange={(e) => onChange(Number(e.target.value) || 0)} className="w-28" />
        <span className="text-sm text-muted-foreground">{suffix}</span>
      </div>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

function GeneralSection({ channel, refetch }: { channel: Channel; refetch: () => void }) {
  const [mode, setMode] = useState(channel.publish_mode)
  const [budget, setBudget] = useState(channel.budget_month_usd?.toString() ?? "")
  const [opts, setOpts] = useState<ChannelOptions>(channel.options)
  const patch = usePatch(channel, refetch)
  const set = <K extends keyof ChannelOptions>(k: K, v: ChannelOptions[K]) => setOpts((o) => ({ ...o, [k]: v }))
  const dirty = mode !== channel.publish_mode || budget !== (channel.budget_month_usd?.toString() ?? "") || JSON.stringify(opts) !== JSON.stringify(channel.options)
  const news = channel.type === "news"

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <div className="grid gap-1.5">
            <Label htmlFor="ch-budget">Бюджет на месяц, $</Label>
            <Input id="ch-budget" type="number" min={0} step={1} value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="Без лимита" />
            <p className="text-xs text-muted-foreground">Когда бюджет исчерпан, отдел не вызывает модели до начала следующего месяца</p>
          </div>
          <div className="grid gap-1.5 sm:col-span-2">
            <Label>Режим публикации</Label>
            <div className="grid gap-2 sm:grid-cols-2">
              {(
                [
                  ["approval", "С согласованием", "Каждый пост ждёт вашего решения в кабинете. Без ответа к сроку пост не выходит."],
                  ["autopilot", "Автопилот", "Посты выходят сами после проверок редактора. Вы можете отклонить пост до публикации."],
                ] as const
              ).map(([v, l, d]) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => setMode(v)}
                  className={cn("rounded-lg border p-3 text-left transition-colors hover:border-foreground/30", mode === v && "border-primary ring-2 ring-primary/20")}
                >
                  <div className="font-medium">{l}</div>
                  <div className="mt-0.5 text-xs text-muted-foreground">{d}</div>
                </button>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Сроки и лимиты</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {news ? (
            <>
              <NumberOption label="Начинать писать за" value={opts.news_lead_minutes} onChange={(v) => set("news_lead_minutes", v)} suffix="мин до выхода" />
              <NumberOption label="Окно согласования" value={opts.news_approval_window_minutes} onChange={(v) => set("news_approval_window_minutes", v)} suffix="мин" />
              <NumberOption label="Сюжет актуален" value={opts.story_ttl_hours} onChange={(v) => set("story_ttl_hours", v)} suffix="ч" />
            </>
          ) : (
            <>
              <NumberOption label="Начинать писать (согласование)" value={opts.smm_approval_lead_hours} onChange={(v) => set("smm_approval_lead_hours", v)} suffix="ч до выхода" />
              <NumberOption label="Начинать писать (автопилот)" value={opts.smm_autopilot_lead_hours} onChange={(v) => set("smm_autopilot_lead_hours", v)} suffix="ч до выхода" />
              <NumberOption label="План утверждается сам через" value={opts.plan_auto_approve_hours} onChange={(v) => set("plan_auto_approve_hours", v)} suffix="ч" />
            </>
          )}
          <NumberOption label="Кругов редактуры" value={opts.max_review_attempts} onChange={(v) => set("max_review_attempts", v)} suffix="макс." />
          <NumberOption label="Ваших доработок поста" value={opts.max_owner_revisions} onChange={(v) => set("max_owner_revisions", v)} suffix="макс." />
          <NumberOption label="Не повторять темы" value={opts.novelty_window_days} onChange={(v) => set("novelty_window_days", v)} suffix="дней" />
          <div className="grid gap-1.5">
            <Label>Пустой слот</Label>
            <Select value={opts.empty_slot_policy} onValueChange={(v) => set("empty_slot_policy", v as ChannelOptions["empty_slot_policy"])}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="evergreen">Общая тема</SelectItem>
                <SelectItem value="skip">Пропустить</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <label className="flex items-center gap-2 self-end text-sm">
            <Switch checked={opts.images} onCheckedChange={(v) => set("images", v)} />
            Картинки и графики к постам
          </label>
        </CardContent>
      </Card>

      <SaveBar
        dirty={dirty}
        pending={patch.isPending}
        onSave={() => patch.mutate({ publish_mode: mode, budget_month_usd: budget ? Number(budget) : null, options: opts })}
      />

      <DangerZone channel={channel} />
    </div>
  )
}

function DangerZone({ channel }: { channel: Channel }) {
  const navigate = useNavigate()
  const client = useQueryClient()
  const [confirm, setConfirm] = useState("")
  const remove = useMutation({
    mutationFn: () => api(`/channels/${channel.id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Канал удалён")
      client.invalidateQueries()
      navigate("/channels")
    },
    onError: (e) => toast.error((e as Error).message),
  })
  return (
    <Card className="border-destructive/40">
      <CardContent className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="font-medium">Удалить канал</div>
          <p className="text-sm text-muted-foreground">Удалятся бриф, планы, посты, история запусков. Сам Telegram-канал не пострадает.</p>
        </div>
        <AlertDialog onOpenChange={() => setConfirm("")}>
          <AlertDialogTrigger asChild>
            <Button variant="destructive">
              <Trash2 /> Удалить
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Удалить «{channel.title}»?</AlertDialogTitle>
              <AlertDialogDescription>Это нельзя отменить. Чтобы подтвердить, введите название канала.</AlertDialogDescription>
            </AlertDialogHeader>
            <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder={channel.title} />
            <AlertDialogFooter>
              <AlertDialogCancel>Отмена</AlertDialogCancel>
              <AlertDialogAction disabled={confirm !== channel.title || remove.isPending} onClick={() => remove.mutate()} className="bg-destructive text-white hover:bg-destructive/90">
                Удалить навсегда
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
  )
}

function StyleguideSection({ channel, refetch }: { channel: Channel; refetch: () => void }) {
  const [value, setValue] = useState<Styleguide>(channel.styleguide)
  const patch = usePatch(channel, refetch)
  return (
    <Card>
      <CardContent>
        <StyleguideEditor value={value} onChange={setValue} />
        <SaveBar dirty={JSON.stringify(value) !== JSON.stringify(channel.styleguide)} pending={patch.isPending} onSave={() => patch.mutate({ styleguide: value })} />
      </CardContent>
    </Card>
  )
}

function StrategySection({ channel, refetch }: { channel: Channel; refetch: () => void }) {
  const initial = channel.strategy ?? emptyStrategy
  const [value, setValue] = useState<Strategy>(initial)
  const patch = usePatch(channel, refetch)
  const ok = value.rubrics.length === 0 || rubricShareTotal(value) === 100
  return (
    <Card>
      <CardContent>
        <StrategyEditor value={value} onChange={setValue} />
        <SaveBar dirty={JSON.stringify(value) !== JSON.stringify(initial)} pending={patch.isPending} disabled={!ok} onSave={() => patch.mutate({ strategy: value })} />
      </CardContent>
    </Card>
  )
}

function ScheduleSection({ channel, refetch }: { channel: Channel; refetch: () => void }) {
  const [value, setValue] = useState(channel.schedule)
  const patch = usePatch(channel, refetch)
  return (
    <Card>
      <CardContent>
        <ScheduleEditor type={channel.type} value={value} onChange={setValue} />
        {value.timezone !== channel.schedule.timezone && (
          <Callout tone="yellow" icon={<Clock />} title={<>Посты сохранят местное время выхода</>} className="mt-5">
            Пост на 19:00 выйдет в 19:00 по новому поясу. Если в новом поясе это время уже прошло, готовый пост выйдет сразу, а неодобренный или ещё не начатый
            пропустится.
          </Callout>
        )}
        <SaveBar dirty={JSON.stringify(value) !== JSON.stringify(channel.schedule)} pending={patch.isPending} onSave={() => patch.mutate({ schedule: value })} />
      </CardContent>
    </Card>
  )
}

type ChannelModels = {
  roles: { role: Role; title: string; config: RoleModel; overridden: boolean; missing: boolean; model: CatalogModel | null }[]
}

function ModelsSection({ channel, refetch }: { channel: Channel; refetch: () => void }) {
  const client = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ["channel-models", channel.id], queryFn: () => api<ChannelModels>(`/channels/${channel.id}/models`) })
  const [overrides, setOverrides] = useState<Partial<Record<Role, RoleModel>>>(channel.models)
  const patch = useMutation({
    mutationFn: (models: Partial<Record<Role, RoleModel>>) => api<Channel>(`/channels/${channel.id}`, { method: "PATCH", body: { models } }),
    onSuccess: () => {
      toast.success("Модели сохранены")
      refetch()
      client.invalidateQueries({ queryKey: ["channel-models", channel.id] })
    },
    onError: (e) => toast.error((e as Error).message),
  })
  if (isLoading || !data) return <LoadingRows rows={6} />
  const dirty = JSON.stringify(overrides) !== JSON.stringify(channel.models)

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        По умолчанию роли берут модели из настроек сервиса. Здесь можно переопределить их для этого канала. Фактическая стоимость видна по каждому посту и
        запуску.
      </p>
      {data.roles.map((r) => {
        const own = overrides[r.role]
        return (
          <Card key={r.role}>
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="text-base">{r.title}</CardTitle>
                  {own ? <ToneBadge tone="info">своя настройка</ToneBadge> : <ToneBadge tone="muted">по умолчанию</ToneBadge>}
                  {r.missing && <ToneBadge tone="danger">модели нет в каталоге</ToneBadge>}
                  {r.model && (
                    <span className="text-xs text-muted-foreground tabular-nums">
                      ${r.model.input_per_million} / ${r.model.output_per_million} за 1М токенов
                    </span>
                  )}
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <Switch
                    checked={!!own}
                    onCheckedChange={(v) =>
                      setOverrides((o) => {
                        const next = { ...o }
                        if (v) next[r.role] = { ...r.config }
                        else delete next[r.role]
                        return next
                      })
                    }
                  />
                  Своя
                </label>
              </div>
            </CardHeader>
            <CardContent>
              {own ? (
                <RoleModelEditor value={own} onChange={(v) => setOverrides((o) => ({ ...o, [r.role]: v }))} />
              ) : (
                <div className="font-mono text-xs text-muted-foreground">
                  {r.config.model}
                  {r.config.fallbacks.length > 0 && ` → ${r.config.fallbacks.join(", ")}`}
                </div>
              )}
            </CardContent>
          </Card>
        )
      })}
      <SaveBar dirty={dirty} pending={patch.isPending} onSave={() => patch.mutate(overrides)} />
    </div>
  )
}

export function ChannelSettings() {
  const { channel, refetch } = useChannel()
  const [params, setParams] = useSearchParams()
  const sections = [
    { id: "general", label: "Основное", show: true },
    { id: "brief", label: "Бриф", show: true },
    { id: "styleguide", label: "Стайлгайд", show: channel.status !== "draft" },
    { id: "strategy", label: "Стратегия", show: channel.type === "smm" && channel.status !== "draft" },
    { id: "schedule", label: "Расписание", show: true },
    { id: "telegram", label: "Telegram", show: true },
    { id: "models", label: "Модели", show: true },
    { id: "prompts", label: "Промпты", show: true },
  ].filter((s) => s.show)
  const current = sections.find((s) => s.id === params.get("section"))?.id ?? "general"
  const key = `${current}-${channel.id}`

  const content: Record<string, ReactNode> = {
    general: <GeneralSection key={key} channel={channel} refetch={refetch} />,
    brief: (
      <Card key={key}>
        <CardContent>
          <BriefForm channel={channel} onSaved={refetch} />
        </CardContent>
      </Card>
    ),
    styleguide: <StyleguideSection key={key} channel={channel} refetch={refetch} />,
    strategy: <StrategySection key={key} channel={channel} refetch={refetch} />,
    schedule: <ScheduleSection key={key} channel={channel} refetch={refetch} />,
    telegram: (
      <Card key={key}>
        <CardHeader>
          <CardTitle>Подключение к Telegram</CardTitle>
          <CardDescription>Бот сервиса публикует посты в канал. Название канала берётся из Telegram</CardDescription>
        </CardHeader>
        <CardContent>
          <ChannelTelegram channel={channel} onConnected={refetch} />
        </CardContent>
      </Card>
    ),
    models: <ModelsSection key={key} channel={channel} refetch={refetch} />,
    prompts: (
      <Card key={key}>
        <CardHeader>
          <CardTitle>Промпты ролей</CardTitle>
          <CardDescription>Открытая часть промпта меняет поведение роли в этом канале. Каждое сохранение — новая версия</CardDescription>
        </CardHeader>
        <CardContent>
          <PromptsEditor channelId={channel.id} />
        </CardContent>
      </Card>
    ),
  }

  return (
    <div className="grid gap-6 md:grid-cols-[12rem_minmax(0,1fr)]">
      <nav className="-mx-4 flex gap-1 overflow-x-auto px-4 md:mx-0 md:flex-col md:px-0">
        {sections.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setParams({ section: s.id })}
            className={cn(
              "rounded-md px-3 py-1.5 text-left text-sm whitespace-nowrap transition-colors",
              current === s.id ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
            )}
          >
            {s.label}
          </button>
        ))}
      </nav>
      <div className="min-w-0">{content[current]}</div>
    </div>
  )
}
