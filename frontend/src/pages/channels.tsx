import { useList } from "@refinedev/core"
import { AlertTriangle, Plus, Radio, Tv } from "lucide-react"
import { Link } from "react-router"

import { EmptyState, ErrorState, PageHeader, StatusBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { fmtUsd } from "@/lib/format"
import { channelStatusLabel, channelTypeLabel, publishModeLabel } from "@/lib/labels"
import type { Channel } from "@/lib/types"

export type ChannelWithStats = Channel & {
  stats: { cost_month: number; published: number; attention: number; active_runs: number }
}

export function ChannelsPage() {
  const { result, query } = useList<ChannelWithStats>({
    resource: "channels",
    pagination: { mode: "off" },
    queryOptions: { refetchInterval: 15_000 },
  })

  return (
    <>
      <PageHeader
        title="Каналы"
        description="Каждый канал ведёт свой AI-отдел: от плана до публикации"
        actions={
          <Button asChild>
            <Link to="/channels/new">
              <Plus /> Новый канал
            </Link>
          </Button>
        }
      />
      {query.isError && <ErrorState error={query.error} />}
      {query.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-44" />
          ))}
        </div>
      )}
      {!query.isLoading && result.data.length === 0 && (
        <EmptyState
          icon={<Tv />}
          title="Каналов пока нет"
          description="Создайте канал: подключите бота к Telegram-каналу, заполните бриф, и отдел возьмётся за работу"
          action={
            <Button asChild>
              <Link to="/channels/new">
                <Plus /> Создать канал
              </Link>
            </Button>
          }
        />
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {result.data.map((ch) => (
          <Link key={ch.id} to={`/channels/${ch.id}`} className="group">
            <Card className="h-full transition-colors group-hover:border-foreground/20">
              <CardHeader>
                <div className="flex min-w-0 items-start justify-between gap-3">
                  <div className="flex min-w-0 flex-1 items-center gap-3">
                    <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted">
                      {ch.type === "news" ? <Radio className="size-5" /> : <Tv className="size-5" />}
                    </div>
                    <div className="min-w-0">
                      <CardTitle className="truncate">{ch.title}</CardTitle>
                      <CardDescription className="truncate">
                        {channelTypeLabel[ch.type]} · {ch.telegram_username ? `@${ch.telegram_username}` : "Telegram не подключён"}
                      </CardDescription>
                    </div>
                  </div>
                  <StatusBadge value={ch.status} labels={channelStatusLabel} />
                </div>
              </CardHeader>
              <CardContent>
                <dl className="grid grid-cols-3 gap-3 text-sm">
                  <div>
                    <dt className="text-xs text-muted-foreground">Опубликовано</dt>
                    <dd className="font-medium tabular-nums">{ch.stats.published}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">В работе</dt>
                    <dd className="font-medium tabular-nums">{ch.stats.active_runs}</dd>
                  </div>
                  <div>
                    <dt className="text-xs text-muted-foreground">За месяц</dt>
                    <dd className="font-medium tabular-nums">
                      {fmtUsd(ch.stats.cost_month, 2)}
                      {ch.budget_month_usd ? <span className="text-muted-foreground"> / {fmtUsd(ch.budget_month_usd, 0)}</span> : null}
                    </dd>
                  </div>
                </dl>
                <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground">
                  <span>{publishModeLabel[ch.publish_mode]}</span>
                  {ch.stats.attention > 0 && (
                    <span className="flex items-center gap-1 font-medium text-amber-600 dark:text-amber-400">
                      <AlertTriangle className="size-3.5" /> Ждут решения: {ch.stats.attention}
                    </span>
                  )}
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </>
  )
}
