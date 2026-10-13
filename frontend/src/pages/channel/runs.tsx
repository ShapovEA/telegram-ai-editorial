import { useQuery } from "@tanstack/react-query"
import { Activity, Loader2 } from "lucide-react"
import { useState } from "react"
import { Link } from "react-router"

import { EmptyState, LoadingRows, StatusBadge } from "@/components/common"
import { RetryRunButton } from "@/components/run/retry-button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api } from "@/lib/api"
import { fmtDateTime, fmtDuration, fmtUsd } from "@/lib/format"
import { runKindLabel, runStatusLabel } from "@/lib/labels"
import type { Run, RunKind } from "@/lib/types"
import { useChannel } from "@/pages/channel/layout"

export function ChannelRuns() {
  const { channel } = useChannel()
  const [kind, setKind] = useState<string>("all")
  const [status, setStatus] = useState<string>("all")

  const { data: runs, isLoading } = useQuery({
    queryKey: ["runs", channel.id, kind, status],
    queryFn: () =>
      api<Run[]>(`/channels/${channel.id}/runs`, {
        query: { kind: kind === "all" ? undefined : kind, status: status === "all" ? undefined : status, limit: 200 },
      }),
    refetchInterval: 10_000,
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Select value={kind} onValueChange={setKind}>
          <SelectTrigger className="w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Все задачи</SelectItem>
            {(Object.keys(runKindLabel) as RunKind[]).map((k) => (
              <SelectItem key={k} value={k}>
                {runKindLabel[k]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-52">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Любой статус</SelectItem>
            <SelectItem value="queued,running">Идут</SelectItem>
            <SelectItem value="waiting">Ждут решения</SelectItem>
            <SelectItem value="done">Готовы</SelectItem>
            <SelectItem value="failed,deferred">С ошибкой</SelectItem>
            <SelectItem value="cancelled">Остановлены</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading && <LoadingRows rows={6} />}
      {runs && runs.length === 0 && <EmptyState icon={<Activity />} title="Запусков нет" />}
      {runs && runs.length > 0 && (
        <div className="rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Задача</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead className="hidden md:table-cell">Шаг</TableHead>
                <TableHead className="hidden sm:table-cell">Начат</TableHead>
                <TableHead className="hidden sm:table-cell text-right">Время</TableHead>
                <TableHead className="text-right">$</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.map((r) => (
                <TableRow key={r.id} className="cursor-pointer">
                  <TableCell className="max-w-72">
                    <Link to={`/runs/${r.id}`} className="block truncate font-medium hover:underline">
                      {r.title || runKindLabel[r.kind]}
                    </Link>
                    <span className="text-xs text-muted-foreground">{runKindLabel[r.kind]}</span>
                  </TableCell>
                  <TableCell>
                    <span className="flex flex-wrap items-center gap-1.5">
                      {r.status === "running" && <Loader2 className="size-3.5 animate-spin text-sky-500" />}
                      <StatusBadge value={r.status} labels={runStatusLabel} />
                      {(r.status === "failed" || r.status === "deferred") && <RetryRunButton runId={r.id} />}
                    </span>
                  </TableCell>
                  <TableCell className="hidden max-w-56 truncate text-sm text-muted-foreground md:table-cell">{r.current_label ?? (r.error ? r.error : "—")}</TableCell>
                  <TableCell className="hidden text-sm text-muted-foreground tabular-nums sm:table-cell">{fmtDateTime(r.started_at ?? r.created_at)}</TableCell>
                  <TableCell className="hidden text-right text-sm text-muted-foreground tabular-nums sm:table-cell">
                    {r.started_at ? fmtDuration(r.started_at, r.finished_at) : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{fmtUsd(r.cost_usd)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
