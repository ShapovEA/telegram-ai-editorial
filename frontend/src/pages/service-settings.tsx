import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { CheckCircle2, ExternalLink, RefreshCw, XCircle } from "lucide-react"
import { useCallback, useState } from "react"
import { toast } from "sonner"

import { DailyStackChart } from "@/components/charts/daily-stack"
import { RoleModelEditor } from "@/components/channel/model-picker"
import { LoadingRows, PageHeader, Spinner, Stat } from "@/components/common"
import { TagInput } from "@/components/tag-input"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useServiceSettings, type ServiceSettings } from "@/hooks/use-service-settings"
import { api } from "@/lib/api"
import { fmtAgo, fmtUsd } from "@/lib/format"
import { roleLabel } from "@/lib/labels"
import type { Role, RoleModel } from "@/lib/types"

const ROLE_ORDER: Role[] = ["scout", "chief", "factchecker", "researcher", "writer", "editor", "publisher", "guard", "novelty", "strategist", "account_manager", "designer", "analyst"]

function useSaveSettings() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<Pick<ServiceSettings, "langfuse_enabled" | "default_models" | "extra_stamps" | "latin_whitelist">>) =>
      api<ServiceSettings>("/settings", { method: "PUT", body }),
    onSuccess: (data) => {
      client.setQueryData(["service-settings"], data)
      toast.success("Сохранено")
    },
    onError: (e) => toast.error((e as Error).message),
  })
}

function Integration({ name, ok, hint }: { name: string; ok: boolean; hint: string }) {
  return (
    <li className="flex items-start gap-2.5 py-2.5">
      {ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-500" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-muted-foreground" />}
      <div>
        <div className="text-sm font-medium">
          {name} <span className="font-normal text-muted-foreground">· {ok ? "настроен" : "не настроен"}</span>
        </div>
        {!ok && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
    </li>
  )
}

function GeneralTab({ s }: { s: ServiceSettings }) {
  const save = useSaveSettings()
  const client = useQueryClient()
  const { data: catalog } = useQuery({ queryKey: ["models", "", undefined], queryFn: () => api<{ items: unknown[]; synced_at: string | null }>("/models", { query: { limit: 1 } }) })
  const sync = useMutation({
    mutationFn: () => api<{ synced: number }>("/models/sync", { method: "POST" }),
    onSuccess: (r) => {
      toast.success(`Каталог обновлён: ${r.synced} моделей`)
      client.invalidateQueries({ queryKey: ["models"] })
    },
    onError: (e) => toast.error((e as Error).message),
  })

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Интеграции</CardTitle>
          <CardDescription>Ключи задаются в .env на сервере</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y">
            <Integration name="OpenRouter" ok={s.openrouter_configured} hint="OPENROUTER_API_KEY — без него агенты не работают" />
            <Integration name="Telegram-бот" ok={s.telegram_configured} hint="TELEGRAM_BOT_TOKEN — публикация в каналы и проверка прав при подключении. Если токен задан, но здесь «не настроен», токен неверный" />
            <Integration name="Pexels" ok={s.pexels_configured} hint="PEXELS_API_KEY — стоковые фото к постам, необязательно" />
            <Integration name="Langfuse" ok={s.langfuse_configured} hint="LANGFUSE_PUBLIC_KEY и LANGFUSE_SECRET_KEY" />
          </ul>
        </CardContent>
      </Card>
      <div className="space-y-6">
        <Card>
          <CardContent className="flex items-start justify-between gap-4">
            <div>
              <div className="font-medium">Трассировка в Langfuse</div>
              <p className="text-sm text-muted-foreground">Для всех каналов. Учёт расходов и события запусков ведутся в своей базе независимо от этого.</p>
              {s.langfuse_configured && (
                <a
                  href={s.langfuse_base_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="mt-1 inline-flex items-center gap-1 text-sm text-sky-600 hover:underline dark:text-sky-400"
                >
                  Открыть Langfuse <ExternalLink className="size-3.5" />
                </a>
              )}
            </div>
            <Switch
              checked={s.langfuse_enabled}
              disabled={!s.langfuse_configured || save.isPending}
              onCheckedChange={(v) => save.mutate({ langfuse_enabled: v })}
              aria-label="Трассировка в Langfuse"
            />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="flex items-start justify-between gap-4">
            <div>
              <div className="font-medium">Каталог моделей OpenRouter</div>
              <p className="text-sm text-muted-foreground">Цены и возможности моделей. Обновляется при старте сервиса{catalog?.synced_at ? `, последний раз ${fmtAgo(catalog.synced_at)}` : ""}.</p>
            </div>
            <Button variant="outline" onClick={() => sync.mutate()} disabled={sync.isPending}>
              <RefreshCw className={sync.isPending ? "animate-spin" : undefined} /> Обновить
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function ModelsTab({ s }: { s: ServiceSettings }) {
  const save = useSaveSettings()
  const [models, setModels] = useState(s.default_models)
  const dirty = JSON.stringify(models) !== JSON.stringify(s.default_models)
  const roles = ROLE_ORDER.filter((r) => models[r])

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">Модели ролей для всех каналов, где нет своей настройки.</p>
      {roles.map((r) => (
        <Card key={r}>
          <CardHeader>
            <CardTitle className="text-base">{roleLabel[r]}</CardTitle>
          </CardHeader>
          <CardContent>
            <RoleModelEditor value={models[r] as RoleModel} onChange={(v) => setModels((m) => ({ ...m, [r]: v }))} />
          </CardContent>
        </Card>
      ))}
      <div className="flex justify-end">
        <Button onClick={() => save.mutate({ default_models: models })} disabled={!dirty || save.isPending}>
          {save.isPending && <Spinner />} Сохранить
        </Button>
      </div>
    </div>
  )
}

function QualityTab({ s }: { s: ServiceSettings }) {
  const save = useSaveSettings()
  const [stamps, setStamps] = useState(s.extra_stamps)
  const [latin, setLatin] = useState(s.latin_whitelist)
  const dirty = JSON.stringify(stamps) !== JSON.stringify(s.extra_stamps) || JSON.stringify(latin) !== JSON.stringify(s.latin_whitelist)
  return (
    <Card>
      <CardContent className="space-y-5">
        <div className="grid gap-1.5">
          <Label htmlFor="stamps">Дополнительные штампы</Label>
          <p className="text-xs text-muted-foreground">Слова и обороты, которые детектор считает штампом во всех каналах. Встроенный словарь работает всегда.</p>
          <TagInput id="stamps" value={stamps} onChange={setStamps} placeholder="Например: «давайте разберёмся»" />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="latin">Разрешённые латинские слова</Label>
          <p className="text-xs text-muted-foreground">Слова латиницей, которые детектор не считает жаргоном. Слова с заглавной буквы и так разрешены.</p>
          <TagInput id="latin" value={latin} onChange={setLatin} placeholder="cold brew, latte" />
        </div>
        <div className="flex justify-end">
          <Button onClick={() => save.mutate({ extra_stamps: stamps, latin_whitelist: latin })} disabled={!dirty || save.isPending}>
            {save.isPending && <Spinner />} Сохранить
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function CostsTab() {
  const { data: overhead } = useQuery({
    queryKey: ["overhead"],
    queryFn: () => api<{ total: number; series: { date: string; role: string; cost: number; calls: number }[] }>("/settings/overhead", { query: { days: 30 } }),
  })
  const { data: summary } = useQuery({
    queryKey: ["costs-summary"],
    queryFn: () => api<{ total: number; channels: { id: number; title: string; cost: number }[] }>("/costs/summary", { query: { period: "month" } }),
  })
  const labelOf = useCallback((k: string) => roleLabel[k as Role] ?? k, [])

  if (!overhead || !summary) return <LoadingRows rows={4} />
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Все каналы, с начала месяца" value={fmtUsd(summary.total, 2)} />
        <Stat label="Накладные сервиса, 30 дней" value={fmtUsd(overhead.total, 2)} hint="вызовы моделей вне каналов" />
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Накладные расходы по дням</CardTitle>
          <CardDescription>Вызовы моделей, не привязанные к каналу</CardDescription>
        </CardHeader>
        <CardContent>
          <DailyStackChart rows={overhead.series.map((r) => ({ date: r.date, key: r.role, cost: r.cost }))} labelOf={labelOf} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>По каналам</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Канал</TableHead>
                <TableHead className="text-right">С начала месяца</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {summary.channels.map((c) => (
                <TableRow key={c.id}>
                  <TableCell>{c.title}</TableCell>
                  <TableCell className="text-right tabular-nums">{fmtUsd(c.cost, 2)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}

export function ServiceSettingsPage() {
  const { data: s, isLoading } = useServiceSettings()
  return (
    <>
      <PageHeader title="Настройки сервиса" description="Общие для всех каналов. Доступны любому пользователю" />
      {isLoading || !s ? (
        <LoadingRows rows={4} />
      ) : (
        <Tabs defaultValue="general">
          <TabsList className="mb-4 flex-wrap">
            <TabsTrigger value="general">Общее</TabsTrigger>
            <TabsTrigger value="models">Модели по умолчанию</TabsTrigger>
            <TabsTrigger value="quality">Словарь штампов</TabsTrigger>
            <TabsTrigger value="costs">Накладные расходы</TabsTrigger>
          </TabsList>
          <TabsContent value="general">
            <GeneralTab s={s} />
          </TabsContent>
          <TabsContent value="models">
            <ModelsTab key={JSON.stringify(s.default_models)} s={s} />
          </TabsContent>
          <TabsContent value="quality">
            <QualityTab s={s} />
          </TabsContent>
          <TabsContent value="costs">
            <CostsTab />
          </TabsContent>
        </Tabs>
      )}
    </>
  )
}
