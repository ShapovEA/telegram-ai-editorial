import { useQuery } from "@tanstack/react-query"
import { useCallback, useState } from "react"

import { DailyStackChart } from "@/components/charts/daily-stack"
import { LoadingRows, Stat } from "@/components/common"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api } from "@/lib/api"
import { fmtNumber, fmtUsd } from "@/lib/format"
import { roleLabel, runKindLabel } from "@/lib/labels"
import type { Role, RunKind } from "@/lib/types"
import { cn } from "@/lib/utils"
import { useChannel } from "@/pages/channel/layout"

type Costs = {
  period: "day" | "week" | "month"
  total: number
  calls: number
  prompt_tokens: number
  completion_tokens: number
  overhead: number
  published_posts: number
  avg_post_cost: number | null
  by_role: { role: Role; title: string; cost: number; calls: number }[]
  by_kind: { kind: RunKind; cost: number }[]
  series: { date: string; role: Role; cost: number }[]
  budget: number | null
  month_spent: number
}

const PERIOD_LABEL = { day: "сегодня", week: "за 7 дней", month: "с начала месяца" }

export function ChannelCosts() {
  const { channel } = useChannel()
  const [period, setPeriod] = useState<Costs["period"]>("month")
  const { data, isLoading } = useQuery({
    queryKey: ["costs", channel.id, period],
    queryFn: () => api<Costs>(`/channels/${channel.id}/costs`, { query: { period } }),
  })
  const labelOf = useCallback((k: string) => roleLabel[k as Role] ?? k, [])

  if (isLoading || !data) return <LoadingRows rows={5} />

  const budgetPct = data.budget ? Math.min(100, (data.month_spent / data.budget) * 100) : null

  return (
    <div className="space-y-6">
      <Tabs value={period} onValueChange={(v) => setPeriod(v as Costs["period"])}>
        <TabsList>
          <TabsTrigger value="day">День</TabsTrigger>
          <TabsTrigger value="week">Неделя</TabsTrigger>
          <TabsTrigger value="month">Месяц</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label={`Потрачено ${PERIOD_LABEL[period]}`} value={fmtUsd(data.total, 2)} hint={`${fmtNumber(data.calls)} вызовов моделей`} />
        <Stat
          label="Средний опубликованный пост"
          value={data.avg_post_cost !== null ? fmtUsd(data.avg_post_cost, 3) : "—"}
          hint={data.published_posts ? `фактически, по ${data.published_posts} постам` : "ещё нет опубликованных постов"}
        />
        <Stat label="Накладные расходы" value={fmtUsd(data.overhead, 2)} hint="планы, идеи, аналитика — без привязки к посту" />
        <div className="rounded-xl border bg-card p-4">
          <div className="text-xs font-medium text-muted-foreground">Бюджет на месяц</div>
          {data.budget ? (
            <>
              <div className="mt-1 text-2xl font-semibold">
                {fmtUsd(data.month_spent, 2)} <span className="text-base font-normal text-muted-foreground">из {fmtUsd(data.budget, 0)}</span>
              </div>
              <Progress value={budgetPct ?? 0} className={cn("mt-2", (budgetPct ?? 0) >= 90 && "[&>div]:bg-destructive")} aria-label="Доля потраченного бюджета" />
            </>
          ) : (
            <div className="mt-1 text-sm text-muted-foreground">Не задан. Можно указать в настройках канала</div>
          )}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Расходы по дням</CardTitle>
          <CardDescription>Последние 30 дней, по ролям отдела</CardDescription>
        </CardHeader>
        <CardContent>
          <DailyStackChart rows={data.series.map((s) => ({ date: s.date, key: s.role, cost: s.cost }))} labelOf={labelOf} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Card>
          <CardHeader>
            <CardTitle>По ролям</CardTitle>
            <CardDescription>{PERIOD_LABEL[period]}</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Роль</TableHead>
                  <TableHead className="text-right">Вызовы</TableHead>
                  <TableHead className="text-right">Доля</TableHead>
                  <TableHead className="text-right">$</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.by_role.map((r) => (
                  <TableRow key={r.role}>
                    <TableCell>{r.title}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtNumber(r.calls)}</TableCell>
                    <TableCell className="text-right tabular-nums">{data.total ? `${Math.round((r.cost / data.total) * 100)}%` : "—"}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtUsd(r.cost)}</TableCell>
                  </TableRow>
                ))}
                {data.by_role.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center text-muted-foreground">
                      Расходов нет
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
              {data.by_role.length > 0 && (
                <TableFooter>
                  <TableRow>
                    <TableCell>Всего</TableCell>
                    <TableCell className="text-right tabular-nums">{fmtNumber(data.calls)}</TableCell>
                    <TableCell />
                    <TableCell className="text-right tabular-nums">{fmtUsd(data.total)}</TableCell>
                  </TableRow>
                </TableFooter>
              )}
            </Table>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>По задачам</CardTitle>
            </CardHeader>
            <CardContent>
              {data.by_kind.length === 0 ? (
                <p className="text-sm text-muted-foreground">Расходов нет</p>
              ) : (
                <ul className="space-y-2 text-sm">
                  {[...data.by_kind]
                    .sort((a, b) => b.cost - a.cost)
                    .map((k) => (
                      <li key={k.kind} className="flex justify-between gap-2">
                        <span>{runKindLabel[k.kind] ?? k.kind}</span>
                        <span className="tabular-nums">{fmtUsd(k.cost)}</span>
                      </li>
                    ))}
                </ul>
              )}
            </CardContent>
          </Card>

        </div>
      </div>
    </div>
  )
}
