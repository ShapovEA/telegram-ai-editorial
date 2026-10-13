import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Lightbulb, Plus, Sparkles, ThumbsDown, ThumbsUp, Trash2, X } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"

import { EmptyState, LoadingRows, Spinner, StatusBadge } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { api } from "@/lib/api"
import { fmtAgo } from "@/lib/format"
import { ideaStatusLabel } from "@/lib/labels"
import type { Idea } from "@/lib/types"
import { cn } from "@/lib/utils"
import { useChannel } from "@/pages/channel/layout"

const ORIGIN: Record<string, string> = { strategy: "стратег", user: "вы" }

export function ChannelIdeas() {
  const { channel } = useChannel()
  const client = useQueryClient()
  const [status, setStatus] = useState("new")
  const [topic, setTopic] = useState("")
  const [hint, setHint] = useState("")
  const [rubric, setRubric] = useState<string>("any")
  const key = ["ideas", channel.id, status]
  const rubrics = channel.strategy?.rubrics ?? []

  const { data: ideas, isLoading } = useQuery({
    queryKey: key,
    queryFn: () => api<Idea[]>(`/channels/${channel.id}/ideas`, { query: { status: status === "all" ? undefined : status } }),
  })
  const refresh = () => client.invalidateQueries({ queryKey: ["ideas", channel.id] })

  const add = useMutation({
    mutationFn: () => api<Idea>(`/channels/${channel.id}/ideas`, { body: { topic, rubric: rubric === "any" ? null : rubric } }),
    onSuccess: () => {
      setTopic("")
      refresh()
    },
    onError: (e) => toast.error((e as Error).message),
  })
  const generate = useMutation({
    mutationFn: () => api<Idea[]>(`/channels/${channel.id}/ideas/generate`, { body: { hint, rubric: rubric === "any" ? null : rubric, count: 5 } }),
    onSuccess: (r) => {
      toast.success(r.length ? `Новых идей: ${r.length}` : "Новых идей не нашлось: всё похожее уже было")
      refresh()
    },
    onError: (e) => toast.error((e as Error).message),
  })
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<Pick<Idea, "vote" | "status">> }) => api(`/ideas/${id}`, { method: "PATCH", body }),
    onSuccess: refresh,
    onError: (e) => toast.error((e as Error).message),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api(`/ideas/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
    onError: (e) => toast.error((e as Error).message),
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (topic.trim().length >= 3) add.mutate()
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="space-y-3">
          <form onSubmit={submit} className="flex flex-wrap gap-2">
            <Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Своя идея поста" className="min-w-60 flex-1" />
            <Select value={rubric} onValueChange={setRubric}>
              <SelectTrigger className="w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="any">Любая рубрика</SelectItem>
                {rubrics.map((r) => (
                  <SelectItem key={r.name} value={r.name}>
                    {r.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button type="submit" disabled={topic.trim().length < 3 || add.isPending}>
              <Plus /> Добавить
            </Button>
          </form>
          <div className="flex flex-wrap gap-2">
            <Input value={hint} onChange={(e) => setHint(e.target.value)} placeholder="Подсказка стратегу: о чём подумать (необязательно)" className="min-w-60 flex-1" />
            <Button variant="outline" onClick={() => generate.mutate()} disabled={generate.isPending}>
              {generate.isPending ? <Spinner /> : <Sparkles />} Придумать идеи
            </Button>
          </div>
        </CardContent>
      </Card>

      <Tabs value={status} onValueChange={setStatus}>
        <TabsList>
          <TabsTrigger value="new">Новые</TabsTrigger>
          <TabsTrigger value="planned">В плане</TabsTrigger>
          <TabsTrigger value="used">Использованы</TabsTrigger>
          <TabsTrigger value="rejected">Отклонены</TabsTrigger>
          <TabsTrigger value="all">Все</TabsTrigger>
        </TabsList>
      </Tabs>

      {isLoading && <LoadingRows />}
      {ideas && ideas.length === 0 && (
        <EmptyState icon={<Lightbulb />} title="Идей нет" description="Добавьте свою или попросите стратега придумать. Стратег берёт идеи из банка, когда составляет план" />
      )}
      {ideas && ideas.length > 0 && (
        <ul className="divide-y rounded-xl border">
          {ideas.map((i) => (
            <li key={i.id} className="flex flex-wrap items-start gap-3 p-3">
              <div className="min-w-0 flex-1">
                <div className="font-medium">{i.topic}</div>
                {(i.reader_goal || i.note) && <div className="mt-0.5 text-sm text-muted-foreground">{i.reader_goal || i.note}</div>}
                <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <StatusBadge value={i.status} labels={ideaStatusLabel} />
                  {i.rubric && <span>{i.rubric}</span>}
                  <span>от: {ORIGIN[i.origin] ?? i.origin}</span>
                  <span>{fmtAgo(i.created_at)}</span>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Нравится"
                  className={cn(i.vote === 1 && "text-emerald-600 dark:text-emerald-400")}
                  onClick={() => patch.mutate({ id: i.id, body: { vote: i.vote === 1 ? 0 : 1 } })}
                >
                  <ThumbsUp />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Не нравится"
                  className={cn(i.vote === -1 && "text-red-600 dark:text-red-400")}
                  onClick={() => patch.mutate({ id: i.id, body: { vote: i.vote === -1 ? 0 : -1 } })}
                >
                  <ThumbsDown />
                </Button>
                {i.status === "new" && (
                  <Button variant="ghost" size="icon" aria-label="Отклонить" onClick={() => patch.mutate({ id: i.id, body: { status: "rejected" } })}>
                    <X />
                  </Button>
                )}
                {i.status === "rejected" && (
                  <Button variant="ghost" size="sm" onClick={() => patch.mutate({ id: i.id, body: { status: "new" } })}>
                    Вернуть
                  </Button>
                )}
                <Button variant="ghost" size="icon" aria-label="Удалить" onClick={() => remove.mutate(i.id)}>
                  <Trash2 />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
