import { useTable } from "@refinedev/core"
import { FileText } from "lucide-react"
import { Link } from "react-router"

import { EmptyState, ErrorState, LoadingRows, StatusBadge, ToneBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { fmtUsd } from "@/lib/format"
import { formatLabel, postStatusLabel } from "@/lib/labels"
import type { Post } from "@/lib/types"
import { zonedDateTime } from "@/lib/tz"
import { useChannel } from "@/pages/channel/layout"

const FILTERS: { value: string; label: string }[] = [
  { value: "", label: "Все" },
  { value: "awaiting_approval,needs_attention", label: "Ждут решения" },
  { value: "scheduled", label: "Запланированы" },
  { value: "published", label: "Опубликованы" },
  { value: "rejected,failed", label: "Отклонены" },
]

export function ChannelPosts() {
  const { channel } = useChannel()
  const {
    result,
    tableQuery,
    currentPage,
    setCurrentPage,
    pageCount,
    filters,
    setFilters,
  } = useTable<Post>({
    resource: "posts",
    meta: { channelId: channel.id },
    pagination: { pageSize: 20 },
    syncWithLocation: true,
    filters: { initial: [{ field: "status", operator: "eq", value: "" }] },
  })

  const status = (filters.find((f) => "field" in f && f.field === "status")?.value as string | undefined) ?? ""

  return (
    <div className="space-y-4">
      <Tabs value={status} onValueChange={(v) => setFilters([{ field: "status", operator: "eq", value: v }], "replace")}>
        <TabsList className="flex-wrap">
          {FILTERS.map((f) => (
            <TabsTrigger key={f.value} value={f.value}>
              {f.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      {tableQuery.isError && <ErrorState error={tableQuery.error} />}
      {tableQuery.isLoading && <LoadingRows rows={6} />}
      {!tableQuery.isLoading && result.data.length === 0 && <EmptyState icon={<FileText />} title="Постов нет" description="Посты появятся, когда отдел возьмёт в работу первый слот" />}

      {result.data.length > 0 && (
        <ul className="divide-y rounded-xl border">
          {result.data.map((p) => (
            <li key={p.id}>
              <Link to={`/posts/${p.id}`} className="flex flex-wrap items-start gap-3 p-3 hover:bg-muted/40 sm:flex-nowrap">
                <div className="w-28 shrink-0 text-xs text-muted-foreground tabular-nums">{zonedDateTime(p.published_at ?? p.publish_at ?? p.created_at, channel.schedule.timezone)}</div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{p.title || "Без заголовка"}</div>
                  <p className="line-clamp-2 text-sm text-muted-foreground">{p.text}</p>
                  <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <StatusBadge value={p.status} labels={postStatusLabel} />
                    <span>{formatLabel[p.format]}</span>
                    {p.rubric && <span>{p.rubric}</span>}
                    {p.synthetic && <ToneBadge tone="muted">демо</ToneBadge>}
                    {p.status === "published" && <span>реакций {p.reactions_total}</span>}
                    {p.rating === 1 && <span className="text-emerald-600 dark:text-emerald-400">👍</span>}
                    {p.rating === -1 && <span className="text-red-600 dark:text-red-400">👎</span>}
                  </div>
                </div>
                <div className="shrink-0 text-xs text-muted-foreground tabular-nums">{fmtUsd(p.cost)}</div>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {pageCount > 1 && (
        <div className="flex items-center justify-end gap-2">
          <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setCurrentPage(currentPage - 1)}>
            Назад
          </Button>
          <span className="text-sm text-muted-foreground tabular-nums">
            {currentPage} / {pageCount}
          </span>
          <Button variant="outline" size="sm" disabled={currentPage >= pageCount} onClick={() => setCurrentPage(currentPage + 1)}>
            Дальше
          </Button>
        </div>
      )}
    </div>
  )
}
