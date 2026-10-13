import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, ArrowLeft, CheckCircle2, ExternalLink, MessageSquareText, Pencil, Send, ThumbsDown, ThumbsUp, X } from "lucide-react"
import { useMemo, useState } from "react"
import { Link, useParams } from "react-router"
import { toast } from "sonner"

import { DataView } from "@/components/run/data-view"
import { Callout, ErrorState, Spinner, StatusBadge, ToneBadge } from "@/components/common"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import { fmtDateTime, fmtNumber, fmtUsd } from "@/lib/format"
import { formatLabel, postStatusLabel, roleLabel } from "@/lib/labels"
import { sanitizeTelegramHtml } from "@/lib/sanitize"
import type { Post, Role } from "@/lib/types"
import { cn } from "@/lib/utils"

type QualityIssue = { code: string; message: string; fragment: string; critical: boolean; suggestion: string }

type PostDetail = Post & {
  cost_breakdown: { role: Role; calls: number; cost: number; prompt_tokens: number; completion_tokens: number; latency_ms: number }[]
  run_status: string | null
  revisions_left: number | null
  quality: { issues: QualityIssue[]; critical: number }
  channel: { id: number; title: string; type: string; publish_mode: string }
}

type Fact = { claim?: string; source_url?: string; quote?: string; value?: string }

function TelegramPreview({ post }: { post: PostDetail }) {
  const html = useMemo(() => sanitizeTelegramHtml(post.body_html || post.text), [post.body_html, post.text])
  const media = post.media as { kind?: string; media_id?: number; url?: string; credit?: string; page?: string }
  const poll = (post.content?.draft ?? {}) as { question?: string; options?: string[]; multiple?: boolean }
  const results = post.poll_results as { options?: { text: string; voter_count: number }[]; total_voter_count?: number }
  const total = results?.total_voter_count ?? 0

  return (
    <div className="rounded-2xl bg-[#e6ebee] p-3 sm:p-5 dark:bg-[#0e1621]">
      <div className="mx-auto max-w-md overflow-hidden rounded-2xl rounded-bl-md bg-white shadow-sm dark:bg-[#182533]">
        {media?.kind === "chart" && media.media_id && <img src={`/api/media/${media.media_id}`} alt="График к посту" className="w-full" />}
        {media?.kind === "stock" && media.url && (
          <figure>
            <img src={media.url} alt="Иллюстрация к посту" className="w-full" />
            {media.credit && (
              <figcaption className="px-3 pt-1 text-[11px] text-muted-foreground">
                Фото:{" "}
                {media.page ? (
                  <a href={media.page} target="_blank" rel="noreferrer noopener" className="hover:underline">
                    {media.credit}
                  </a>
                ) : (
                  media.credit
                )}{" "}
                / Pexels
              </figcaption>
            )}
          </figure>
        )}
        <div className="tg-post p-3 text-[#000] dark:text-[#f5f5f5]" dangerouslySetInnerHTML={{ __html: html }} />
        {post.format === "poll" && poll.question && (
          <div className="border-t p-3">
            <div className="font-medium">{poll.question}</div>
            <div className="mb-2 text-xs text-muted-foreground">{poll.multiple ? "Можно выбрать несколько" : "Анонимный опрос"}</div>
            <ul className="space-y-1.5">
              {(poll.options ?? []).map((o, i) => {
                const votes = results?.options?.[i]?.voter_count ?? 0
                const pct = total ? Math.round((votes / total) * 100) : 0
                return (
                  <li key={i} className="relative overflow-hidden rounded-md border px-3 py-1.5 text-sm">
                    {total > 0 && <div className="absolute inset-y-0 left-0 bg-sky-500/15" style={{ width: `${pct}%` }} />}
                    <span className="relative flex justify-between gap-2">
                      {o}
                      {total > 0 && <span className="text-muted-foreground tabular-nums">{pct}%</span>}
                    </span>
                  </li>
                )
              })}
            </ul>
            {total > 0 && <div className="mt-2 text-xs text-muted-foreground">Голосов: {total}</div>}
          </div>
        )}
        <div className="flex items-center justify-end gap-3 px-3 pb-2 text-[11px] text-muted-foreground">
          {post.reactions_total > 0 && <span>реакций {post.reactions_total}</span>}
          <span>{post.published_at ? fmtDateTime(post.published_at) : post.publish_at ? `выйдет ${fmtDateTime(post.publish_at)}` : ""}</span>
        </div>
      </div>
    </div>
  )
}

function EditDialog({ post, open, onOpenChange, onSaved }: { post: PostDetail; open: boolean; onOpenChange: (v: boolean) => void; onSaved: () => void }) {
  const [title, setTitle] = useState(post.title)
  const [text, setText] = useState(post.text)
  const save = useMutation({
    mutationFn: () => api(`/posts/${post.id}`, { method: "PUT", body: { title, text } }),
    onSuccess: () => {
      toast.success("Правка сохранена. Отдел учтёт её в следующих постах")
      onSaved()
      onOpenChange(false)
    },
    onError: (e) => toast.error((e as Error).message),
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Правка поста</DialogTitle>
          <DialogDescription>
            Текст публикуется как есть, без разметки. Источник, подпись и хештеги система добавит сама. Из ваших правок отдел выводит правила стайлгайда.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <div className="grid gap-1.5">
            <Label htmlFor="edit-title">Заголовок</Label>
            <Input id="edit-title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="edit-text">Текст</Label>
            <Textarea id="edit-text" value={text} onChange={(e) => setText(e.target.value)} rows={16} className="font-mono text-sm" />
            <p className="text-right text-xs text-muted-foreground tabular-nums">{text.length} симв.</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button onClick={() => save.mutate()} disabled={text.trim().length < 10 || save.isPending}>
            {save.isPending && <Spinner />} Сохранить
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ReviseDialog({ post, open, onOpenChange, onSent }: { post: PostDetail; open: boolean; onOpenChange: (v: boolean) => void; onSent: () => void }) {
  const [comment, setComment] = useState("")
  const send = useMutation({
    mutationFn: () => api<{ run_id: string }>(`/posts/${post.id}/revise`, { body: { comment } }),
    onSuccess: () => {
      toast.success("Писатель дорабатывает пост")
      onSent()
      onOpenChange(false)
    },
    onError: (e) => toast.error((e as Error).message),
  })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Доработать пост</DialogTitle>
          <DialogDescription>
            Опишите, что изменить. Писатель перепишет, редактор проверит.
            {post.revisions_left !== null && ` Осталось доработок: ${post.revisions_left}.`}
          </DialogDescription>
        </DialogHeader>
        <Textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={5}
          placeholder="Например: короче, без вступления, добавь пример из практики"
        />
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button onClick={() => send.mutate()} disabled={comment.trim().length < 3 || send.isPending}>
            {send.isPending && <Spinner />} Отправить писателю
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RatePanel({ post, onRated }: { post: PostDetail; onRated: () => void }) {
  const [comment, setComment] = useState(post.rating_comment ?? "")
  const rate = useMutation({
    mutationFn: (rating: number) => api(`/posts/${post.id}/rate`, { body: { rating, comment } }),
    onSuccess: () => {
      toast.success("Оценка сохранена")
      onRated()
    },
    onError: (e) => toast.error((e as Error).message),
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Ваша оценка</CardTitle>
        <CardDescription>Аналитик учитывает оценки, когда предлагает правки стратегии</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} placeholder="Что понравилось или нет (необязательно)" />
        <div className="flex gap-2">
          <Button variant={post.rating === 1 ? "default" : "outline"} onClick={() => rate.mutate(post.rating === 1 ? 0 : 1)} disabled={rate.isPending}>
            <ThumbsUp /> Хорошо
          </Button>
          <Button variant={post.rating === -1 ? "destructive" : "outline"} onClick={() => rate.mutate(post.rating === -1 ? 0 : -1)} disabled={rate.isPending}>
            <ThumbsDown /> Плохо
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export function PostPage() {
  const { id } = useParams()
  const client = useQueryClient()
  const [editOpen, setEditOpen] = useState(false)
  const [reviseOpen, setReviseOpen] = useState(false)
  const {
    data: post,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["post", id],
    queryFn: () => api<PostDetail>(`/posts/${id}`),
    refetchInterval: (q) => (q.state.data?.run_status === "running" ? 4000 : false),
  })

  const refresh = () => {
    refetch()
    client.invalidateQueries({ queryKey: ["posts"] })
  }

  const action = useMutation({
    mutationFn: (kind: "approve" | "reject" | "publish-now") => api(`/posts/${id}/${kind}`, { method: "POST" }),
    onSuccess: (_, kind) => {
      toast.success({ approve: "Пост согласован", reject: "Пост отклонён", "publish-now": "Публикуем" }[kind])
      setTimeout(refresh, 800)
    },
    onError: (e) => toast.error((e as Error).message),
  })

  if (isError) return <ErrorState error={error} />
  if (isLoading || !post)
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-96" />
        <Skeleton className="h-96 w-full" />
      </div>
    )

  const awaiting = (post.status === "awaiting_approval" || post.status === "needs_attention") && post.run_status === "waiting"
  const editable = ["awaiting_approval", "needs_attention", "scheduled", "draft"].includes(post.status) && post.format !== "poll"
  const rejectable = awaiting || ["scheduled", "needs_attention", "draft"].includes(post.status)
  const facts = ((post.content?.facts as Fact[] | undefined) ?? []).filter((f) => f.claim)
  const attention = post.content?.attention as { reason: string; issues: { issue: string; suggestion: string; fragment: string }[] } | undefined
  const revising = post.run_status === "running"

  return (
    <>
      <Button variant="ghost" size="sm" asChild className="mb-2 -ml-2">
        <Link to={`/channels/${post.channel_id}/posts`}>
          <ArrowLeft /> Посты канала «{post.channel.title}»
        </Link>
      </Button>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">{post.title || "Без заголовка"}</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <StatusBadge value={post.status} labels={postStatusLabel} />
            <span>{formatLabel[post.format]}</span>
            {post.rubric && <span>· {post.rubric}</span>}
            {post.synthetic && <ToneBadge tone="muted">демо</ToneBadge>}
            {post.link && (
              <a href={post.link} target="_blank" rel="noreferrer noopener" className="flex items-center gap-1 hover:text-foreground">
                в Telegram <ExternalLink className="size-3.5" />
              </a>
            )}
            {post.run_id && (
              <Link to={`/runs/${post.run_id}`} className="hover:text-foreground hover:underline">
                как писался
              </Link>
            )}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {editable && (
            <Button variant="outline" onClick={() => setEditOpen(true)}>
              <Pencil /> Править
            </Button>
          )}
          {awaiting && (
            <Button variant="outline" onClick={() => setReviseOpen(true)} disabled={post.revisions_left === 0}>
              <MessageSquareText /> Доработать
            </Button>
          )}
          {rejectable && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="outline">
                  <X /> Отклонить
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Отклонить пост?</AlertDialogTitle>
                  <AlertDialogDescription>Пост не выйдет, слот будет пропущен.</AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Отмена</AlertDialogCancel>
                  <AlertDialogAction onClick={() => action.mutate("reject")}>Отклонить</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
          {post.status === "scheduled" && (
            <Button variant="outline" onClick={() => action.mutate("publish-now")} disabled={action.isPending}>
              <Send /> Опубликовать сейчас
            </Button>
          )}
          {awaiting && (
            <Button onClick={() => action.mutate("approve")} disabled={action.isPending}>
              {action.isPending ? <Spinner /> : <CheckCircle2 />} Согласовать
            </Button>
          )}
        </div>
      </div>

      {revising && (
        <Callout tone="gray" icon={<Spinner />} title={<>Пост дорабатывается</>} className="mb-6">
          <Link to={`/runs/${post.run_id}`} className="underline-offset-4 hover:underline">
            Смотреть ход работы
          </Link>
        </Callout>
      )}
      {post.status === "needs_attention" && (
        <Callout tone="red" icon={<AlertTriangle />} title={<>Нужно ваше внимание</>} className="mb-6">
          <p>Автор не успел исправить замечания редактора за отведённые попытки. Посмотрите их и решите: согласовать как есть, поправить текст, отправить на доработку или отклонить.</p>
          {attention && !attention.issues.length && attention.reason && <p className="mt-2 text-muted-foreground">{attention.reason}</p>}
          {!!attention?.issues.length && (
            <ul className="mt-3 space-y-2">
              {attention.issues.map((i, n) => (
                <li key={n}>
                  <span className="font-medium">{i.issue}</span>
                  {i.suggestion && <span className="text-muted-foreground"> — {i.suggestion}</span>}
                  {i.fragment && <div className="mt-0.5 text-muted-foreground">«{i.fragment}»</div>}
                </li>
              ))}
            </ul>
          )}
        </Callout>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="space-y-6">
          <TelegramPreview post={post} />
          {post.writer_text && post.writer_text.trim() !== post.text.trim() && (
            <Card>
              <CardHeader>
                <CardTitle>Первый вариант писателя</CardTitle>
                <CardDescription>До правок редактора и ваших</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm whitespace-pre-wrap text-muted-foreground">{post.writer_text}</p>
              </CardContent>
            </Card>
          )}
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Проверка на штампы</CardTitle>
              <CardDescription>Детектор кода: канцелярит, клише, «нейросетевые» обороты</CardDescription>
            </CardHeader>
            <CardContent>
              {post.quality.issues.length === 0 ? (
                <p className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400">
                  <CheckCircle2 className="size-4" /> Замечаний нет
                </p>
              ) : (
                <ul className="space-y-2.5">
                  {post.quality.issues.map((i, n) => (
                    <li key={n} className="text-sm">
                      <div className={cn("flex gap-1.5", i.critical ? "text-red-700 dark:text-red-400" : "text-amber-700 dark:text-amber-400")}>
                        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                        {i.message}
                      </div>
                      {i.fragment && <div className="mt-0.5 ml-5.5 rounded bg-muted px-1.5 py-0.5 font-mono text-xs">«{i.fragment}»</div>}
                      {i.suggestion && <div className="mt-0.5 ml-5.5 text-xs text-muted-foreground">{i.suggestion}</div>}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          {(facts.length > 0 || post.source_url) && (
            <Card>
              <CardHeader>
                <CardTitle>Факты и источники</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                {post.source_url && (
                  <div>
                    <span className="text-muted-foreground">Источник сюжета: </span>
                    <DataView value={post.source_url} />
                  </div>
                )}
                {facts.length > 0 && (
                  <ul className="space-y-2">
                    {facts.map((f, i) => (
                      <li key={i} className="rounded-lg border p-2.5">
                        <div>{f.claim}</div>
                        {f.source_url && (
                          <a
                            href={f.source_url}
                            target="_blank"
                            rel="noreferrer noopener"
                            className="mt-1 block truncate text-xs text-sky-600 hover:underline dark:text-sky-400"
                          >
                            {f.source_url}
                          </a>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Стоимость: {fmtUsd(post.cost)}</CardTitle>
              {post.review_attempts > 0 && <CardDescription>Кругов редактуры: {post.review_attempts}</CardDescription>}
            </CardHeader>
            <CardContent>
              {post.cost_breakdown.length === 0 ? (
                <p className="text-sm text-muted-foreground">Вызовов моделей нет</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Роль</TableHead>
                      <TableHead className="text-right">Вызовы</TableHead>
                      <TableHead className="text-right">Токены</TableHead>
                      <TableHead className="text-right">$</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {post.cost_breakdown
                      .slice()
                      .sort((a, b) => b.cost - a.cost)
                      .map((b) => (
                        <TableRow key={b.role}>
                          <TableCell>{roleLabel[b.role] ?? b.role}</TableCell>
                          <TableCell className="text-right tabular-nums">{b.calls}</TableCell>
                          <TableCell className="text-right tabular-nums">{fmtNumber(b.prompt_tokens + b.completion_tokens)}</TableCell>
                          <TableCell className="text-right tabular-nums">{fmtUsd(b.cost)}</TableCell>
                        </TableRow>
                      ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {post.status === "published" && <RatePanel post={post} onRated={refresh} />}

          {post.reactions && Object.keys(post.reactions).length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Реакции</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                {Object.entries(post.reactions).map(([emoji, n]) => (
                  <span key={emoji} className="rounded-full border px-2.5 py-1 text-sm tabular-nums">
                    {emoji} {n}
                  </span>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      {editOpen && <EditDialog post={post} open={editOpen} onOpenChange={setEditOpen} onSaved={refresh} />}
      {reviseOpen && <ReviseDialog post={post} open={reviseOpen} onOpenChange={setReviseOpen} onSent={refresh} />}
    </>
  )
}
