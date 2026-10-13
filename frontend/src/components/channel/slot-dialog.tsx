import { useMutation } from "@tanstack/react-query"
import { Lightbulb } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { Spinner } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import type { Channel, Slot } from "@/lib/types"
import { zonedDayKey, zonedTime, zonedToUtc } from "@/lib/tz"

type Topic = {
  topic: string
  rubric?: string
  reader_goal?: string
  key_idea?: string
  novelty?: string
  similar_post?: { date: string; title: string } | null
}

function noveltyNote(t: Topic) {
  if (!t.novelty || t.novelty === "new") return null
  const p = t.similar_post
  const prefix = t.novelty === "same" ? "Повтор поста" : "Похоже на пост"
  return p ? `${prefix} от ${p.date} «${p.title}»` : `${prefix}, который уже был`
}

export function SlotDialog({
  channel,
  slot,
  dayKey,
  open,
  onOpenChange,
  onSaved,
}: {
  channel: Channel
  slot: Slot | null
  dayKey: string | null
  open: boolean
  onOpenChange: (v: boolean) => void
  onSaved: () => void
}) {
  const tz = channel.schedule.timezone
  const rubrics = channel.strategy?.rubrics ?? []
  const [form, setForm] = useState(() =>
    slot
      ? {
          day: zonedDayKey(slot.publish_at, tz),
          time: zonedTime(slot.publish_at, tz),
          rubric: slot.rubric ?? "",
          topic: slot.topic,
          reader_goal: slot.reader_goal,
          key_idea: slot.key_idea,
          comment: slot.comment,
          locked: slot.locked,
        }
      : { day: dayKey ?? "", time: "12:00", rubric: rubrics[0]?.name ?? "", topic: "", reader_goal: "", key_idea: "", comment: "", locked: false },
  )
  const [topics, setTopics] = useState<Topic[] | null>(null)

  const set = <K extends keyof typeof form>(k: K, v: (typeof form)[K]) => setForm((f) => ({ ...f, [k]: v }))

  const save = useMutation({
    mutationFn: () => {
      const publish_at = zonedToUtc(form.day, form.time, tz).toISOString()
      const body = { publish_at, rubric: form.rubric || null, topic: form.topic, reader_goal: form.reader_goal, key_idea: form.key_idea }
      return slot
        ? api(`/slots/${slot.id}`, { method: "PATCH", body: { ...body, comment: form.comment, locked: form.locked } })
        : api("/slots", { body: { ...body, channel_id: channel.id } })
    },
    onSuccess: () => {
      toast.success(slot ? "Слот обновлён" : "Слот добавлен")
      onSaved()
      onOpenChange(false)
    },
    onError: (e) => toast.error((e as Error).message),
  })

  const suggest = useMutation({
    mutationFn: () => api<{ topics: Topic[] }>(`/channels/${channel.id}/topics/suggest`, { body: { hint: form.topic, rubric: form.rubric || null, count: 4 } }),
    onSuccess: (r) => setTopics(r.topics),
    onError: (e) => toast.error((e as Error).message),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90svh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{slot ? "Слот" : "Новый слот"}</DialogTitle>
          <DialogDescription>Время указано в часовом поясе канала: {tz}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="grid gap-1.5">
              <Label htmlFor="slot-day">День</Label>
              <Input id="slot-day" type="date" value={form.day} onChange={(e) => set("day", e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="slot-time">Время</Label>
              <Input id="slot-time" type="time" value={form.time} onChange={(e) => set("time", e.target.value)} />
            </div>
            <div className="grid gap-1.5">
              <Label>Рубрика</Label>
              <Select value={form.rubric} onValueChange={(v) => set("rubric", v)}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Без рубрики" />
                </SelectTrigger>
                <SelectContent>
                  {rubrics.map((r) => (
                    <SelectItem key={r.name} value={r.name}>
                      {r.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid gap-1.5">
            <div className="flex items-end justify-between gap-2">
              <Label htmlFor="slot-topic">Тема</Label>
              <Button type="button" variant="ghost" size="sm" className="h-7 text-xs" onClick={() => suggest.mutate()} disabled={suggest.isPending}>
                {suggest.isPending ? <Spinner className="size-3" /> : <Lightbulb className="size-3" />} Предложить темы
              </Button>
            </div>
            <Textarea id="slot-topic" value={form.topic} onChange={(e) => set("topic", e.target.value)} rows={2} placeholder="Оставьте пустым — стратег подберёт тему сам" />
            {topics && (
              <div className="space-y-1.5 rounded-lg border p-2">
                {topics.length === 0 && <p className="p-1 text-sm text-muted-foreground">Ничего нового не нашлось</p>}
                {topics.map((t, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => {
                      setForm((f) => ({ ...f, topic: t.topic, rubric: t.rubric || f.rubric, reader_goal: t.reader_goal ?? f.reader_goal, key_idea: t.key_idea ?? f.key_idea }))
                      setTopics(null)
                    }}
                    className="block w-full rounded-md p-2 text-left text-sm hover:bg-muted"
                  >
                    <div className="font-medium">{t.topic}</div>
                    {t.reader_goal && <div className="text-xs text-muted-foreground">{t.reader_goal}</div>}
                    {noveltyNote(t) && <div className="text-xs text-amber-600 dark:text-amber-400">{noveltyNote(t)}</div>}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor="slot-goal">Что получит читатель</Label>
              <Textarea id="slot-goal" value={form.reader_goal} onChange={(e) => set("reader_goal", e.target.value)} rows={2} />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="slot-idea">Ключевая мысль</Label>
              <Textarea id="slot-idea" value={form.key_idea} onChange={(e) => set("key_idea", e.target.value)} rows={2} />
            </div>
          </div>
          {slot && (
            <>
              <div className="grid gap-1.5">
                <Label htmlFor="slot-comment">Комментарий для писателя</Label>
                <Textarea id="slot-comment" value={form.comment} onChange={(e) => set("comment", e.target.value)} rows={2} placeholder="Пожелания к посту" />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={form.locked} onCheckedChange={(v) => set("locked", v)} />
                Закрепить: не менять слот при перепланировании
              </label>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Отмена
          </Button>
          <Button onClick={() => save.mutate()} disabled={!form.day || !form.time || save.isPending}>
            {save.isPending && <Spinner />} Сохранить
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
