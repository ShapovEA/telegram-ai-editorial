import { format, parseISO, subDays } from "date-fns"
import { ru } from "date-fns/locale"
import { useMemo } from "react"
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from "recharts"

import { fmtUsd } from "@/lib/format"

export type DailyRow = { date: string; key: string; cost: number }

const SLOTS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)", "var(--series-5)", "var(--series-6)"]
const OTHER = "__other__"

type Series = { key: string; label: string; color: string }

function buildSeries(rows: DailyRow[], labelOf: (k: string) => string): Series[] {
  const totals = new Map<string, number>()
  for (const r of rows) totals.set(r.key, (totals.get(r.key) ?? 0) + r.cost)
  const ranked = [...totals.entries()].filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).map(([k]) => k)
  const fits = ranked.length <= SLOTS.length
  const top = fits ? ranked : ranked.slice(0, SLOTS.length - 1)
  const series = top.map((k, i) => ({ key: k, label: labelOf(k), color: SLOTS[i] }))
  if (!fits) series.push({ key: OTHER, label: "Прочее", color: "var(--series-other)" })
  return series
}

function RoundedTop(props: Record<string, unknown>) {
  const { x, y, width, height, fill, payload, dataKey, order } = props as {
    x: number
    y: number
    width: number
    height: number
    fill: string
    payload: Record<string, number>
    dataKey: string
    order: string[]
  }
  if (!height || height <= 0) return null
  const idx = order.indexOf(dataKey)
  const isTop = order.slice(idx + 1).every((k) => !payload[k])
  const r = isTop ? Math.min(4, width / 2, height) : 0
  const path = `M${x},${y + height} L${x},${y + r} Q${x},${y} ${x + r},${y} L${x + width - r},${y} Q${x + width},${y} ${x + width},${y + r} L${x + width},${y + height} Z`
  return <path d={path} fill={fill} stroke="var(--card)" strokeWidth={2} paintOrder="stroke" />
}

function ChartTooltip({ active, payload, label, series }: TooltipContentProps<number, string> & { series: Series[] }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload as Record<string, number>
  const total = series.reduce((s, x) => s + (row[x.key] ?? 0), 0)
  return (
    <div className="min-w-44 rounded-lg border bg-popover px-3 py-2 text-xs text-popover-foreground shadow-md">
      <div className="mb-1.5 font-medium">{format(parseISO(String(label)), "d MMMM", { locale: ru })}</div>
      <div className="space-y-1">
        {[...series].reverse().map((s) =>
          row[s.key] ? (
            <div key={s.key} className="flex items-center gap-2">
              <span className="h-0.5 w-3 rounded-full" style={{ background: s.color }} />
              <span className="font-semibold tabular-nums">{fmtUsd(row[s.key])}</span>
              <span className="text-muted-foreground">{s.label}</span>
            </div>
          ) : null,
        )}
      </div>
      <div className="mt-1.5 border-t pt-1.5 font-semibold tabular-nums">Всего {fmtUsd(total)}</div>
    </div>
  )
}

export function DailyStackChart({ rows, labelOf, days = 30, height = 260 }: { rows: DailyRow[]; labelOf: (k: string) => string; days?: number; height?: number }) {
  const series = useMemo(() => buildSeries(rows, labelOf), [rows, labelOf])
  const data = useMemo(() => {
    const keys = new Set(series.map((s) => s.key))
    const byDay = new Map<string, Record<string, number | string>>()
    for (let i = days - 1; i >= 0; i--) {
      const d = format(subDays(new Date(), i), "yyyy-MM-dd")
      byDay.set(d, { date: d })
    }
    for (const r of rows) {
      const row = byDay.get(r.date)
      if (!row) continue
      const k = keys.has(r.key) ? r.key : OTHER
      row[k] = Number(row[k] ?? 0) + r.cost
    }
    return [...byDay.values()]
  }, [rows, series, days])
  const order = series.map((s) => s.key)

  if (series.length === 0) return <p className="py-16 text-center text-sm text-muted-foreground">Расходов за 30 дней нет</p>

  return (
    <div>
      {series.length > 1 && (
        <ul className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm" style={{ background: s.color }} />
              {s.label}
            </li>
          ))}
        </ul>
      )}
      <div style={{ height }} role="img" aria-label="Расходы по дням за 30 дней, с разбивкой по ролям. Те же данные — в таблице ниже">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap="20%">
            <CartesianGrid vertical={false} stroke="var(--viz-grid)" strokeWidth={1} />
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={{ stroke: "var(--viz-axis)" }}
              tick={{ fill: "var(--viz-muted)", fontSize: 11 }}
              tickFormatter={(d: string) => format(parseISO(d), "d MMM", { locale: ru })}
              interval="preserveStartEnd"
              minTickGap={24}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--viz-muted)", fontSize: 11 }}
              tickFormatter={(v: number) => (v === 0 ? "0" : v < 1 ? `$${v.toFixed(2)}` : `$${v.toFixed(0)}`)}
              width={48}
            />
            <Tooltip cursor={{ fill: "var(--muted)", opacity: 0.6 }} content={(p) => <ChartTooltip {...(p as TooltipContentProps<number, string>)} series={series} />} />
            {series.map((s) => (
              <Bar key={s.key} dataKey={s.key} stackId="cost" fill={s.color} maxBarSize={24} isAnimationActive={false} shape={(p: unknown) => <RoundedTop {...(p as Record<string, unknown>)} dataKey={s.key} order={order} />} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
