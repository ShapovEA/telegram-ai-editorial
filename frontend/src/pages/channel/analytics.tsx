import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { BarChart3, CheckCircle2, FlaskConical, Play, X } from "lucide-react"
import { useState } from "react"
import { Link, useNavigate } from "react-router"
import { toast } from "sonner"

import { StrategyEditor, emptyStrategy, rubricShareTotal } from "@/components/channel/strategy-editor"
import { Callout, EmptyState, LoadingRows, Spinner, ToneBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"
import { fmtDate, fmtNumber } from "@/lib/format"
import type { AnalyticsReport, Strategy } from "@/lib/types"
import { useChannel } from "@/pages/channel/layout"

type Report = {
  summary?: string
  findings?: string[]
  recommendations?: string[]
  preliminary?: boolean
  rubric_stats?: Record<string, unknown>[]
  charts?: number[]
}
type Proposal = { changes?: string[]; strategy?: Strategy }

function reportBadge(report: AnalyticsReport): ["success" | "warning" | "muted", string] | null {
  if (report.status === "approved") return ["success", "предложение принято"]
  if (report.status === "rejected") return ["muted", "предложение отклонено"]
  return (report.proposal as Proposal).changes?.length ? ["warning", "ждёт решения"] : null
}

function ProposalBlock({ report, onDone }: { report: AnalyticsReport; onDone: () => void }) {
  const proposal = report.proposal as Proposal
  const [editing, setEditing] = useState(false)
  const [strategy, setStrategy] = useState<Strategy>(proposal.strategy ?? emptyStrategy)
  const decide = useMutation({
    mutationFn: (action: "approve" | "reject") =>
      api(`/analytics/${report.id}/decision`, { body: { action, strategy: action === "approve" ? strategy : undefined } }),
    onSuccess: (_, action) => {
      toast.success(action === "approve" ? "Стратегия обновлена" : "Предложение отклонено")
      onDone()
    },
    onError: (e) => toast.error((e as Error).message),
  })
  if (!proposal.changes?.length) return null
  const pending = report.status !== "approved" && report.status !== "rejected"
  const shareOk = strategy.rubrics.length === 0 || rubricShareTotal(strategy) === 100

  return (
    <div className="space-y-3 rounded-lg border border-sky-500/30 bg-sky-500/5 p-4">
      <div className="font-medium">Стратег предлагает изменить стратегию</div>
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {proposal.changes.map((c, i) => (
          <li key={i}>{c}</li>
        ))}
      </ul>
      {pending && (
        <>
          {editing && (
            <div className="rounded-lg border bg-card p-4">
              <StrategyEditor value={strategy} onChange={setStrategy} />
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => decide.mutate("approve")} disabled={!shareOk || decide.isPending}>
              {decide.isPending ? <Spinner /> : <CheckCircle2 />} Принять{editing ? " с правками" : ""}
            </Button>
            {!editing && (
              <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
                Поправить перед принятием
              </Button>
            )}
            <Button size="sm" variant="ghost" onClick={() => decide.mutate("reject")} disabled={decide.isPending}>
              <X /> Отклонить
            </Button>
          </div>
        </>
      )}
    </div>
  )
}

function ReportCard({ report, onDone }: { report: AnalyticsReport; onDone: () => void }) {
  const r = report.report as Report
  const badge = reportBadge(report)
  const stats = r.rubric_stats ?? []
  const columns = stats.length ? Object.keys(stats[0]) : []
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>
            {fmtDate(report.period_start)} — {fmtDate(report.period_end)}
          </CardTitle>
          {badge && <ToneBadge tone={badge[0]}>{badge[1]}</ToneBadge>}
          {r.preliminary && <ToneBadge tone="warning">мало данных, выводы предварительные</ToneBadge>}
        </div>
        {report.run_id && (
          <CardDescription>
            <Link to={`/runs/${report.run_id}`} className="hover:underline">
              Как составлялся отчёт
            </Link>
          </CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {r.summary && <p className="text-sm whitespace-pre-wrap">{r.summary}</p>}
        {!!r.charts?.length && (
          <div className="grid gap-3 md:grid-cols-2">
            {r.charts.map((id) => (
              <img key={id} src={`/api/media/${id}`} alt="График аналитика" className="w-full rounded-lg border bg-white" />
            ))}
          </div>
        )}
        <div className="grid gap-4 md:grid-cols-2">
          {!!r.findings?.length && (
            <div>
              <div className="mb-1 text-sm font-medium">Наблюдения</div>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {r.findings.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          )}
          {!!r.recommendations?.length && (
            <div>
              <div className="mb-1 text-sm font-medium">Рекомендации</div>
              <ul className="list-disc space-y-1 pl-5 text-sm">
                {r.recommendations.map((f, i) => (
                  <li key={i}>{f}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
        {stats.length > 0 && (
          <Collapsible>
            <CollapsibleTrigger className="text-sm text-muted-foreground hover:text-foreground">Статистика по рубрикам ▸</CollapsibleTrigger>
            <CollapsibleContent className="mt-2">
              <Table>
                <TableHeader>
                  <TableRow>
                    {columns.map((c) => (
                      <TableHead key={c}>{c}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {stats.map((row, i) => (
                    <TableRow key={i}>
                      {columns.map((c) => (
                        <TableCell key={c} className="tabular-nums">
                          {typeof row[c] === "number" ? fmtNumber(Math.round((row[c] as number) * 10) / 10) : String(row[c] ?? "")}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CollapsibleContent>
          </Collapsible>
        )}
        <ProposalBlock report={report} onDone={onDone} />
      </CardContent>
    </Card>
  )
}

export function ChannelAnalytics() {
  const { channel } = useChannel()
  const client = useQueryClient()
  const navigate = useNavigate()
  const [days, setDays] = useState("30")
  const { data: reports, isLoading } = useQuery({
    queryKey: ["analytics", channel.id],
    queryFn: () => api<AnalyticsReport[]>(`/channels/${channel.id}/analytics`),
  })
  const refresh = () => client.invalidateQueries({ queryKey: ["analytics", channel.id] })

  const run = useMutation({
    mutationFn: () => api<{ run_id: string }>(`/channels/${channel.id}/analytics/run`, { body: { days: Number(days) } }),
    onSuccess: ({ run_id }) => navigate(`/runs/${run_id}`),
    onError: (e) => toast.error((e as Error).message),
  })
  const demo = useMutation({
    mutationFn: () => api<{ created: number }>(`/channels/${channel.id}/demo-history`, { body: { weeks: 6 } }),
    onSuccess: (r) => {
      toast.success(`Создана демо-история${r?.created ? `: ${r.created} постов` : ""}`)
      client.invalidateQueries()
    },
    onError: (e) => toast.error((e as Error).message),
  })

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="font-medium">Отчёт аналитика</div>
            <p className="text-sm text-muted-foreground">Реакции и оценки по рубрикам, выводы и предложения по стратегии. Раз в месяц составляется сам.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={days} onValueChange={setDays}>
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="14">за 14 дней</SelectItem>
                <SelectItem value="30">за 30 дней</SelectItem>
                <SelectItem value="60">за 60 дней</SelectItem>
                <SelectItem value="90">за 90 дней</SelectItem>
              </SelectContent>
            </Select>
            <Button onClick={() => run.mutate()} disabled={run.isPending}>
              {run.isPending ? <Spinner /> : <Play />} Составить отчёт
            </Button>
          </div>
        </CardContent>
      </Card>

      {isLoading && <LoadingRows rows={3} />}
      {reports && reports.length === 0 && (
        <>
          <EmptyState
            icon={<BarChart3 />}
            title="Отчётов пока нет"
            description="Аналитику нужны опубликованные посты с реакциями. Первый отчёт появится через месяц работы канала"
          />
          <Callout tone="gray" icon={<FlaskConical />} title={<>Демо-история для проверки</>}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>Создаст синтетические опубликованные посты с реакциями за 6 недель, чтобы посмотреть работу аналитика. Они помечаются как «демо».</span>
              <Button size="sm" variant="outline" onClick={() => demo.mutate()} disabled={demo.isPending}>
                {demo.isPending && <Spinner />} Создать
              </Button>
            </div>
          </Callout>
        </>
      )}
      {reports?.map((r) => (
        <ReportCard key={r.id} report={r} onDone={refresh} />
      ))}
    </div>
  )
}
