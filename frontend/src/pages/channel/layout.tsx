import { useOne } from "@refinedev/core"
import { useQueryClient } from "@tanstack/react-query"
import { ExternalLink } from "lucide-react"
import { useEffect } from "react"
import { NavLink, Outlet, useOutletContext, useParams } from "react-router"

import { ErrorState, StatusBadge } from "@/components/common"
import { Skeleton } from "@/components/ui/skeleton"
import { streamUrl } from "@/lib/api"
import { channelStatusLabel, channelTypeLabel } from "@/lib/labels"
import type { Channel } from "@/lib/types"
import { cn } from "@/lib/utils"

export type ChannelContext = { channel: Channel; refetch: () => void }

export function useChannel() {
  return useOutletContext<ChannelContext>()
}

function useChannelEvents(channelId: number | undefined) {
  const client = useQueryClient()
  useEffect(() => {
    if (!channelId) return
    const source = new EventSource(streamUrl(`/channels/${channelId}/events`))
    let timer: ReturnType<typeof setTimeout> | undefined
    source.addEventListener("update", () => {
      clearTimeout(timer)
      timer = setTimeout(() => client.invalidateQueries(), 500)
    })
    return () => {
      clearTimeout(timer)
      source.close()
    }
  }, [channelId, client])
}

export function ChannelLayout() {
  const { id } = useParams()
  const { result: channel, query } = useOne<Channel>({ resource: "channels", id })
  useChannelEvents(channel?.id)

  if (query.isError) return <ErrorState error={query.error} />
  if (!channel)
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )

  const ready = channel.status === "active" || channel.status === "paused"
  const tabs = [
    { to: "", label: "Обзор", end: true, show: true },
    { to: "plan", label: "Контент-план", show: ready && channel.type === "smm" },
    { to: "ideas", label: "Идеи", show: ready && channel.type === "smm" },
    { to: "stories", label: "Сюжеты", show: ready && channel.type === "news" },
    { to: "posts", label: "Посты", show: ready },
    { to: "runs", label: "Запуски", show: channel.status !== "draft" },
    { to: "analytics", label: "Аналитика", show: ready && channel.type === "smm" },
    { to: "costs", label: "Расход", show: channel.status !== "draft" },
    { to: "settings", label: "Настройки", show: true },
  ].filter((t) => t.show)

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1">
        <h1 className="text-[32px] leading-tight font-bold tracking-tight">{channel.title}</h1>
        <StatusBadge value={channel.status} labels={channelStatusLabel} />
        <span className="text-sm text-muted-foreground">{channelTypeLabel[channel.type]}</span>
        {channel.telegram_username && (
          <a
            href={`https://t.me/${channel.telegram_username}`}
            target="_blank"
            rel="noreferrer noopener"
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            @{channel.telegram_username} <ExternalLink className="size-3.5" />
          </a>
        )}
      </div>
      <nav className="-mx-4 mb-8 overflow-x-auto overflow-y-hidden border-b px-4 [scrollbar-width:none] md:mx-0 md:px-0">
        <div className="flex min-w-max gap-1">
          {tabs.map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.end}
              className={({ isActive }) =>
                cn(
                  "-mb-px border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors",
                  isActive ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
                )
              }
            >
              {t.label}
            </NavLink>
          ))}
        </div>
      </nav>
      <Outlet context={{ channel, refetch: () => query.refetch() } satisfies ChannelContext} />
    </>
  )
}
