import { useMutation, useQuery } from "@tanstack/react-query"
import { CheckCircle2, FileText, Globe, HelpCircle, Link2, Plus, Send, Sparkles, X } from "lucide-react"
import { useState, type ReactNode } from "react"
import { toast } from "sonner"

import { SourcesManager } from "@/components/channel/sources-manager"
import { Callout, Spinner } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import { BRIEF_SPEC, sampleKind, type BriefTextField, type FieldCopy, type SampleKind } from "@/lib/brief"
import type { Brief, Channel, Source } from "@/lib/types"

type Question = { field: string; question: string }

function Questions({ items }: { items: Question[] }) {
  return items.map((q, i) => (
    <p key={i} data-brief-question className="flex gap-1.5 text-sm text-amber-700 dark:text-amber-400">
      <HelpCircle className="mt-0.5 size-4 shrink-0" /> {q.question}
    </p>
  ))
}

function FieldHeader({ htmlFor, label, hint, required, action }: { htmlFor?: string; label: string; hint: string; required: boolean; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-2">
      <div className="space-y-0.5">
        <Label htmlFor={htmlFor} className="text-[15px] font-semibold">
          {label}
          {required ? <span className="text-destructive">*</span> : <span className="ml-1.5 text-xs font-normal text-muted-foreground">необязательно</span>}
        </Label>
        <p className="text-sm text-muted-foreground">{hint}</p>
      </div>
      {action}
    </div>
  )
}

function TextField({
  channelId,
  name,
  copy,
  required,
  value,
  onChange,
  questions,
}: {
  channelId: number
  name: BriefTextField
  copy: FieldCopy
  required: boolean
  value: string
  onChange: (text: string) => void
  questions: Question[]
}) {
  const [suggestion, setSuggestion] = useState<{ text: string; hint: string } | null>(null)
  const assist = useMutation({
    mutationFn: () => api<{ text: string; hint: string }>(`/channels/${channelId}/brief/assist`, { body: { field: name, draft: value } }),
    onSuccess: setSuggestion,
    onError: (e) => toast.error((e as Error).message),
  })

  return (
    <div className="grid gap-2">
      <FieldHeader
        htmlFor={`brief-${name}`}
        label={copy.label}
        hint={copy.hint}
        required={required}
        action={
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 text-xs"
            disabled={value.trim().length < 3 || assist.isPending}
            onClick={() => assist.mutate()}
            title="Аккаунт-менеджер сформулирует ваш черновик точнее"
          >
            {assist.isPending ? <Spinner className="size-3" /> : <Sparkles className="size-3" />} Помочь сформулировать
          </Button>
        }
      />
      <Textarea id={`brief-${name}`} value={value} onChange={(e) => onChange(e.target.value)} placeholder={copy.placeholder} rows={3} className="min-h-20" />
      {suggestion && (
        <div className="rounded-lg border border-sky-500/30 bg-sky-500/5 p-3 text-sm">
          <p className="whitespace-pre-wrap">{suggestion.text}</p>
          {suggestion.hint && <p className="mt-2 text-xs text-muted-foreground">{suggestion.hint}</p>}
          <div className="mt-3 flex gap-2">
            <Button
              type="button"
              size="sm"
              onClick={() => {
                onChange(suggestion.text)
                setSuggestion(null)
              }}
            >
              Заменить
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setSuggestion(null)}>
              Оставить моё
            </Button>
          </div>
        </div>
      )}
      <Questions items={questions} />
    </div>
  )
}

const SAMPLE_META: Record<SampleKind, { icon: typeof FileText; label: string }> = {
  channel: { icon: Send, label: "Telegram-канал" },
  post: { icon: Send, label: "Пост в Telegram" },
  page: { icon: Link2, label: "Статья" },
  text: { icon: FileText, label: "Текст" },
}

function SamplesEditor({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [draft, setDraft] = useState("")
  const add = () => {
    const item = draft.trim()
    if (!item || value.includes(item)) return
    onChange([...value, item])
    setDraft("")
  }

  return (
    <div className="grid gap-2">
      <FieldHeader
        htmlFor="brief-sample"
        label="Образцы текстов"
        hint="Тексты, которые звучат так, как должен звучать канал: @канал, ссылка на пост или статью, или сам текст. По ним оформитель составит стайлгайд"
        required={false}
      />
      {value.length > 0 && (
        <ul className="grid gap-2">
          {value.map((item) => {
            const meta = SAMPLE_META[sampleKind(item)]
            return (
              <li key={item} className="flex items-start gap-3 rounded-lg border bg-muted/30 px-3 py-2.5">
                <meta.icon className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <div className="text-xs text-muted-foreground">{meta.label}</div>
                  <div className="line-clamp-3 text-sm break-words whitespace-pre-wrap">{item}</div>
                </div>
                <button
                  type="button"
                  aria-label="Убрать образец"
                  onClick={() => onChange(value.filter((v) => v !== item))}
                  className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <X className="size-4" />
                </button>
              </li>
            )
          })}
        </ul>
      )}
      <Textarea
        id="brief-sample"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={draft.includes("\n") || draft.length > 80 ? 5 : 2}
        placeholder="@channel, https://t.me/channel/123, ссылка на статью или текст поста целиком"
      />
      <div>
        <Button type="button" variant="outline" size="sm" onClick={add} disabled={!draft.trim()}>
          <Plus /> Добавить образец
        </Button>
      </div>
    </div>
  )
}

export function BriefForm({ channel, onSaved }: { channel: Channel; onSaved?: (c: Channel) => void }) {
  const spec = BRIEF_SPEC[channel.type]
  const [brief, setBrief] = useState<Brief>(channel.brief)
  const [questions, setQuestions] = useState<Question[] | null>(null)
  const dirty = JSON.stringify(brief) !== JSON.stringify(channel.brief)
  const rssRequired = channel.type === "news"
  const { data: sources } = useQuery({
    queryKey: ["sources", channel.id],
    queryFn: () => api<Source[]>(`/channels/${channel.id}/sources`),
  })

  const set = <K extends keyof Brief>(key: K, value: Brief[K]) => setBrief((b) => ({ ...b, [key]: value }))

  const save = useMutation({
    mutationFn: () => api<Channel>(`/channels/${channel.id}`, { method: "PATCH", body: { brief } }),
    onSuccess: (c) => {
      toast.success("Бриф сохранён")
      onSaved?.(c)
    },
    onError: (e) => toast.error((e as Error).message),
  })

  const check = useMutation({
    mutationFn: () => api<{ ok: boolean; questions: Question[] }>(`/channels/${channel.id}/brief/check`, { body: brief }),
    onSuccess: (res) => {
      const qs = res.ok ? [] : res.questions
      setQuestions(qs)
      const noFeeds = rssRequired && (sources?.length ?? 0) === 0
      if (qs.length === 0 && !noFeeds) {
        toast.success("Бриф понятен, вопросов нет")
        return
      }
      toast.warning(`Есть вопросы по брифу: ${qs.length + (noFeeds ? 1 : 0)}`, { description: "Они показаны под полями" })
      requestAnimationFrame(() => document.querySelector("[data-brief-question]")?.scrollIntoView({ behavior: "smooth", block: "center" }))
    },
    onError: (e) => toast.error((e as Error).message),
  })

  const questionsFor = (field: string) => questions?.filter((q) => q.field === field) ?? []
  const feedsMissing = rssRequired && questions !== null && sources?.length === 0

  return (
    <div className="space-y-8">
      {spec.fields.map((name) => (
        <TextField
          key={name}
          channelId={channel.id}
          name={name}
          copy={spec.copy[name]}
          required={spec.required.includes(name)}
          value={brief[name]}
          onChange={(t) => set(name, t)}
          questions={questionsFor(name)}
        />
      ))}

      <SamplesEditor value={brief.samples} onChange={(v) => set("samples", v)} />

      <div className="grid gap-2">
        <FieldHeader htmlFor="brief-site" label="Сайт" hint="Если есть: оттуда отдел возьмёт факты о вас" required={false} />
        <div className="relative">
          <Globe className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input id="brief-site" type="url" value={brief.site_url} onChange={(e) => set("site_url", e.target.value)} placeholder="https://" className="pl-9" />
        </div>
      </div>

      <div className="grid gap-2">
        <FieldHeader
          label="RSS-ленты"
          hint={
            rssRequired
              ? "Отсюда отдел берёт новости. Вставьте ссылку на ленту или просто адрес сайта — ленту найдём сами. Сохраняется сразу"
              : "Свежие сюжеты из лент стратег учтёт, когда подбирает темы. Вставьте ссылку на ленту или адрес сайта. Сохраняется сразу"
          }
          required={rssRequired}
        />
        <SourcesManager channelId={channel.id} />
        {feedsMissing && <Questions items={[{ field: "rss", question: "Добавьте хотя бы одну ленту: без неё новостному каналу не из чего писать." }]} />}
      </div>

      {questions && questions.length === 0 && !feedsMissing && (
        <Callout tone="green" icon={<CheckCircle2 />} title={<>Бриф понятен</>}>
          Аккаунт-менеджеру хватает информации, чтобы составить {channel.type === "smm" ? "стайлгайд и стратегию" : "стайлгайд"}.
        </Callout>
      )}

      <div className="flex flex-wrap justify-end gap-2 border-t pt-5">
        <Button type="button" variant="outline" onClick={() => check.mutate()} disabled={check.isPending}>
          {check.isPending ? <Spinner /> : <HelpCircle />} Проверить бриф
        </Button>
        <Button type="button" onClick={() => save.mutate()} disabled={!dirty || save.isPending}>
          {save.isPending ? <Spinner /> : !dirty && <CheckCircle2 />} {dirty ? "Сохранить" : "Сохранено"}
        </Button>
      </div>
    </div>
  )
}
