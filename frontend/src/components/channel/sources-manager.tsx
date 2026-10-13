import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Plus, RefreshCw, Rss, Search, Trash2 } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { EmptyState, LoadingRows, Spinner, ToneBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { api } from "@/lib/api"
import { fmtAgo, fmtNumber } from "@/lib/format"
import type { FeedCheck, Source } from "@/lib/types"

type SourceRow = Source & { used_in_posts: number; stale: boolean; recent_items: number; recent_full_text: number }

export function SourcesManager({ channelId }: { channelId: number }) {
  const client = useQueryClient()
  const key = ["sources", channelId]
  const { data: sources, isLoading } = useQuery({ queryKey: key, queryFn: () => api<SourceRow[]>(`/channels/${channelId}/sources`) })
  const [url, setUrl] = useState("")
  const [found, setFound] = useState<FeedCheck[] | null>(null)

  const add = useMutation({
    mutationFn: (feedUrl: string) => api<Source & { full_text: boolean }>(`/channels/${channelId}/sources`, { body: { url: feedUrl } }),
    onSuccess: (s) => {
      if (s.full_text) toast.success(`Лента «${s.title}» добавлена`)
      else
        toast.warning(`Лента «${s.title}» добавлена, но в ней только анонсы`, {
          description: "Сайт не отдаёт статьи роботу. Новость из этой ленты пойдёт в работу, только если о том же напишет другая лента",
          duration: 12_000,
        })
      setUrl("")
      setFound(null)
      client.invalidateQueries({ queryKey: key })
    },
    onError: async (e, feedUrl) => {
      const res = await api<{ feeds: FeedCheck[] }>("/sources/discover", { body: { url: feedUrl } }).catch(() => null)
      if (res?.feeds.length) {
        setFound(res.feeds)
        toast.info("Это не лента, но на странице нашлись RSS. Выберите нужную")
        return
      }
      toast.error((e as Error).message)
    },
  })

  const remove = useMutation({
    mutationFn: (id: number) => api(`/channels/${channelId}/sources/${id}`, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: key }),
    onError: (e) => toast.error((e as Error).message),
  })

  const refresh = useMutation({
    mutationFn: () => api<{ queued: number }>(`/channels/${channelId}/sources/refresh`, { method: "POST" }),
    onSuccess: (r) => {
      toast.success(`Обновление запущено: ${r.queued}`)
      setTimeout(() => client.invalidateQueries({ queryKey: key }), 5000)
    },
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (url.trim()) add.mutate(url.trim())
  }

  return (
    <div className="space-y-4">
      <form onSubmit={submit} className="flex flex-wrap gap-2">
        <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Ссылка на RSS или на сайт — найдём ленту сами" className="min-w-60 flex-1" />
        <Button type="submit" disabled={!url.trim() || add.isPending}>
          {add.isPending ? <Spinner /> : <Plus />} Добавить
        </Button>
        {!!sources?.length && (
          <Button type="button" variant="outline" onClick={() => refresh.mutate()} disabled={refresh.isPending} title="Скачать свежие материалы из всех лент">
            <RefreshCw className={refresh.isPending ? "animate-spin" : undefined} /> Обновить
          </Button>
        )}
      </form>

      {found && (
        <div className="space-y-2 rounded-lg border p-3">
          <p className="flex items-center gap-1.5 text-sm font-medium">
            <Search className="size-4" /> Найденные ленты
          </p>
          {found.map((f) => (
            <div key={f.url} className="flex flex-wrap items-center justify-between gap-2 rounded-md bg-muted/40 p-2 text-sm">
              <div className="min-w-0">
                <div className="truncate font-medium">{f.title}</div>
                <div className="truncate text-xs text-muted-foreground">{f.url}</div>
              </div>
              <Button size="sm" onClick={() => f.url && add.mutate(f.url)} disabled={add.isPending}>
                Добавить
              </Button>
            </div>
          ))}
        </div>
      )}

      {isLoading && <LoadingRows rows={2} />}
      {sources && sources.length === 0 && <EmptyState icon={<Rss />} title="Лент пока нет" description="Добавьте 3–10 лент по теме канала: новостные сайты, блоги, официальные источники" />}
      {sources && sources.length > 0 && (
        <ul className="divide-y rounded-lg border">
          {sources.map((s) => (
            <li key={s.id} className="flex flex-wrap items-center gap-3 p-3">
              <Rss className="size-4 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate font-medium">{s.title || s.url}</span>
                  {s.status === "error" && <ToneBadge tone="danger">ошибка</ToneBadge>}
                  {s.stale && <ToneBadge tone="warning">давно не обновлялась</ToneBadge>}
                  {s.status === "new" && <ToneBadge tone="muted">ещё не скачана</ToneBadge>}
                  {s.recent_items > 0 && s.recent_full_text === 0 && <ToneBadge tone="warning">только анонсы</ToneBadge>}
                </div>
                <div className="truncate text-xs text-muted-foreground">
                  {s.url} · материалов {fmtNumber(s.items_total)} · в постах {s.used_in_posts}
                  {s.last_item_at && ` · последний ${fmtAgo(s.last_item_at)}`}
                  {s.recent_items > 0 && s.recent_full_text > 0 && s.recent_full_text < s.recent_items && ` · полный текст у ${s.recent_full_text} из ${s.recent_items} последних`}
                </div>
                {s.recent_items > 0 && s.recent_full_text === 0 && (
                  <div className="mt-1 text-xs text-muted-foreground">Сайт не отдаёт статьи роботу. Новость из этой ленты пойдёт в работу, только если о том же напишет другая лента.</div>
                )}
                {s.error && (
                  <div className="mt-1 flex items-center gap-1 text-xs text-red-600 dark:text-red-400">
                    <AlertTriangle className="size-3" /> {s.error}
                  </div>
                )}
              </div>
              <Button variant="ghost" size="icon" aria-label="Убрать ленту" onClick={() => remove.mutate(s.id)} disabled={remove.isPending}>
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
