import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ChevronRight, EyeOff, Link2, Newspaper, PenLine, Plus, ShieldAlert, Star } from "lucide-react"
import { useState, type FormEvent } from "react"
import { Link, useNavigate } from "react-router"
import { toast } from "sonner"

import { SourcesManager } from "@/components/channel/sources-manager"
import { EmptyState, LoadingRows, Spinner, StatusBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Checkbox } from "@/components/ui/checkbox"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Input } from "@/components/ui/input"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api } from "@/lib/api"
import { fmtAgo } from "@/lib/format"
import { storyStatusLabel } from "@/lib/labels"
import type { Story } from "@/lib/types"
import { cn } from "@/lib/utils"
import { useChannel } from "@/pages/channel/layout"

const WRITABLE: Story["status"][] = ["new", "rejected", "expired", "hidden"]
const MAX_WRITE_NOW = 10

function StoryRow({
  story,
  onPatch,
  selected,
  selectable,
  onSelect,
}: {
  story: Story
  onPatch: (body: { priority?: boolean; hidden?: boolean }) => void
  selected: boolean
  selectable: boolean
  onSelect: (checked: boolean) => void
}) {
  const [open, setOpen] = useState(false)
  return (
    <li className={cn("p-3", selected && "bg-accent/60")}>
      <Collapsible open={open} onOpenChange={setOpen}>
        <div className="flex flex-wrap items-start gap-3">
          <Checkbox
            checked={selected}
            onCheckedChange={(v) => onSelect(v === true)}
            disabled={!selectable}
            aria-label="Выбрать сюжет"
            title={selectable ? "Выбрать, чтобы написать пост немедленно" : "Сюжет уже в работе или опубликован"}
            className="mt-1"
          />
          <CollapsibleTrigger className="mt-0.5 rounded p-0.5 hover:bg-muted" aria-label="Материалы сюжета">
            <ChevronRight className={cn("size-4 transition-transform", open && "rotate-90")} />
          </CollapsibleTrigger>
          <div className="min-w-0 flex-1">
            <div className="font-medium">{story.title}</div>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <StatusBadge value={story.status} labels={storyStatusLabel} />
              {story.priority && (
                <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                  <Star className="size-3 fill-current" /> приоритет
                </span>
              )}
              <span>материалов {story.item_count}</span>
              {story.score !== null && <span>значимость {story.score}/10</span>}
              {story.relevance !== null && <span>близость к теме {Math.round(story.relevance * 100)}%</span>}
              <span>{fmtAgo(story.last_item_at)}</span>
              {story.related_post_id && (
                <Link to={`/posts/${story.related_post_id}`} className="text-sky-600 hover:underline dark:text-sky-400">
                  пост
                </Link>
              )}
            </div>
            {(story.reason || story.score_reason) && <p className="mt-1 text-sm text-muted-foreground">{story.reason || story.score_reason}</p>}
          </div>
          <div className="flex gap-1">
            <Button
              variant="ghost"
              size="icon"
              aria-label={story.priority ? "Снять приоритет" : "Взять в приоритет"}
              title={story.priority ? "Снять приоритет" : "Взять в приоритет: шеф-редактор выберет его в ближайший слот"}
              className={cn(story.priority && "text-amber-500")}
              onClick={() => onPatch({ priority: !story.priority })}
            >
              <Star className={cn(story.priority && "fill-current")} />
            </Button>
            {story.status !== "published" && (
              <Button variant="ghost" size="icon" aria-label={story.status === "hidden" ? "Показать" : "Скрыть"} title={story.status === "hidden" ? "Вернуть в пул" : "Скрыть сюжет"} onClick={() => onPatch({ hidden: story.status !== "hidden" })}>
                <EyeOff />
              </Button>
            )}
          </div>
        </div>
        <CollapsibleContent>
          <ul className="mt-3 ml-8 space-y-1.5 border-l pl-3 text-sm">
            {story.items.map((it, i) =>
              it.injection === "injection" ? (
                <li key={i} className="flex items-center gap-1.5 text-red-600 dark:text-red-400">
                  <ShieldAlert className="size-3.5" /> Материал отклонён: попытка prompt injection
                </li>
              ) : (
                <li key={i}>
                  <a href={it.url} target="_blank" rel="noreferrer noopener" className="hover:underline">
                    {it.title}
                  </a>
                  <span className="ml-2 text-xs text-muted-foreground">{fmtAgo(it.published_at)}</span>
                  {!it.full_text && (
                    <span className="ml-2 text-xs text-muted-foreground" title="Статья не открылась, у отдела есть только анонс из ленты">
                      · только анонс
                    </span>
                  )}
                </li>
              ),
            )}
          </ul>
        </CollapsibleContent>
      </Collapsible>
    </li>
  )
}

export function ChannelStories() {
  const { channel } = useChannel()
  const client = useQueryClient()
  const navigate = useNavigate()
  const [status, setStatus] = useState("new")
  const [url, setUrl] = useState("")
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const key = ["stories", channel.id, status]

  const { data: stories, isLoading } = useQuery({
    queryKey: key,
    queryFn: () => api<Story[]>(`/channels/${channel.id}/stories`, { query: { status: status === "all" ? undefined : status } }),
    refetchInterval: 30_000,
  })
  const refresh = () => client.invalidateQueries({ queryKey: ["stories", channel.id] })

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: { priority?: boolean; hidden?: boolean } }) => api(`/stories/${id}`, { method: "PATCH", body }),
    onSuccess: refresh,
    onError: (e) => toast.error((e as Error).message),
  })
  const manual = useMutation({
    mutationFn: () => api(`/channels/${channel.id}/stories/manual`, { body: { url } }),
    onSuccess: () => {
      toast.success("Сюжет добавлен в пул")
      setUrl("")
      refresh()
    },
    onError: (e) => toast.error((e as Error).message),
  })

  const writeNow = useMutation({
    mutationFn: () => api<{ run_ids: string[] }>(`/channels/${channel.id}/stories/write-now`, { body: { story_ids: [...selected] } }),
    onSuccess: (r) => {
      toast.success(`Отдел пишет постов: ${r.run_ids.length}`, {
        description: "Готовые посты пойдут по обычным правилам канала",
        action: { label: "Ход работы", onClick: () => navigate(`/channels/${channel.id}/runs`) },
      })
      setSelected(new Set())
      refresh()
    },
    onError: (e) => toast.error((e as Error).message),
  })

  const toggle = (storyId: number, checked: boolean) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (checked) next.add(storyId)
      else next.delete(storyId)
      return next
    })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (url.trim()) manual.mutate()
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
      <div className="space-y-4">
        <form onSubmit={submit} className="flex flex-wrap gap-2">
          <div className="relative min-w-60 flex-1">
            <Link2 className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="Ссылка на новость, которую стоит взять" className="pl-8" />
          </div>
          <Button type="submit" variant="outline" disabled={!url.trim() || manual.isPending}>
            {manual.isPending ? <Spinner /> : <Plus />} В пул
          </Button>
        </form>
        <Tabs
          value={status}
          onValueChange={(v) => {
            setStatus(v)
            setSelected(new Set())
          }}
        >
          <TabsList>
            <TabsTrigger value="new">Новые</TabsTrigger>
            <TabsTrigger value="in_work">В работе</TabsTrigger>
            <TabsTrigger value="published">Опубликованы</TabsTrigger>
            <TabsTrigger value="rejected">Отклонены</TabsTrigger>
            <TabsTrigger value="hidden">Скрыты</TabsTrigger>
            <TabsTrigger value="all">Все</TabsTrigger>
          </TabsList>
        </Tabs>
        {isLoading && <LoadingRows />}
        {stories && stories.length === 0 && (
          <EmptyState icon={<Newspaper />} title="Сюжетов нет" description="Сюжеты появляются, когда ленты приносят материалы по теме канала. Ленты опрашиваются по расписанию" />
        )}
        {selected.size > 0 && (
          <div className="sticky top-2 z-10 flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-background px-3 py-2 shadow-sm">
            <span className="text-sm">
              Выбрано сюжетов: <span className="font-medium tabular-nums">{selected.size}</span>
              {selected.size >= MAX_WRITE_NOW && <span className="text-muted-foreground"> · больше {MAX_WRITE_NOW} за раз нельзя</span>}
            </span>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>
                Снять выбор
              </Button>
              <Button size="sm" onClick={() => writeNow.mutate()} disabled={writeNow.isPending}>
                {writeNow.isPending ? <Spinner /> : <PenLine />} Написать немедленно
              </Button>
            </div>
          </div>
        )}
        {stories && stories.length > 0 && (
          <ul className="divide-y rounded-xl border">
            {stories.map((s) => {
              const checked = selected.has(s.story_id)
              return (
                <StoryRow
                  key={s.id}
                  story={s}
                  onPatch={(body) => patch.mutate({ id: s.id, body })}
                  selected={checked}
                  selectable={WRITABLE.includes(s.status) && (checked || selected.size < MAX_WRITE_NOW)}
                  onSelect={(v) => toggle(s.story_id, v)}
                />
              )
            })}
          </ul>
        )}
      </div>
      <Card className="h-fit">
        <CardHeader>
          <CardTitle>Источники</CardTitle>
          <CardDescription>Ленты, из которых собираются сюжеты</CardDescription>
        </CardHeader>
        <CardContent>
          <SourcesManager channelId={channel.id} />
        </CardContent>
      </Card>
    </div>
  )
}
