import { Plus, Trash2 } from "lucide-react"

import { TagInput } from "@/components/tag-input"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { formatLabel } from "@/lib/labels"
import type { PostFormat, Rubric, Strategy } from "@/lib/types"
import { cn } from "@/lib/utils"

export const emptyStrategy: Strategy = { audience: [], goal: "", rubrics: [], forbidden: [], notes: "" }

export function rubricShareTotal(s: Strategy) {
  return s.rubrics.reduce((sum, r) => sum + (Number(r.share) || 0), 0)
}

export function StrategyEditor({ value, onChange }: { value: Strategy; onChange: (v: Strategy) => void }) {
  const total = rubricShareTotal(value)
  const setRubric = (i: number, patch: Partial<Rubric>) => onChange({ ...value, rubrics: value.rubrics.map((r, j) => (j === i ? { ...r, ...patch } : r)) })

  return (
    <div className="space-y-6">
      <div className="grid gap-1.5">
        <Label htmlFor="st-goal">Цель</Label>
        <Textarea id="st-goal" value={value.goal} onChange={(e) => onChange({ ...value, goal: e.target.value })} rows={2} />
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Аудитория</Label>
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange({ ...value, audience: [...value.audience, { name: "", pains: [] }] })}>
            <Plus /> Сегмент
          </Button>
        </div>
        {value.audience.map((seg, i) => (
          <div key={i} className="grid gap-2 rounded-lg border p-3 sm:grid-cols-[14rem_1fr_auto]">
            <Input
              value={seg.name}
              placeholder="Сегмент"
              onChange={(e) => onChange({ ...value, audience: value.audience.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)) })}
            />
            <TagInput
              value={seg.pains}
              placeholder="Боли и вопросы"
              onChange={(pains) => onChange({ ...value, audience: value.audience.map((x, j) => (j === i ? { ...x, pains } : x)) })}
            />
            <Button type="button" variant="ghost" size="icon" aria-label="Удалить сегмент" onClick={() => onChange({ ...value, audience: value.audience.filter((_, j) => j !== i) })}>
              <Trash2 />
            </Button>
          </div>
        ))}
      </div>

      <div className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Label>
            Рубрики{" "}
            <span className={cn("ml-1 font-normal tabular-nums", total === 100 ? "text-muted-foreground" : "text-destructive")}>
              сумма долей {total}%{total !== 100 && " — должна быть 100%"}
            </span>
          </Label>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() =>
              onChange({
                ...value,
                rubrics: [...value.rubrics, { name: "", format: "text", share: Math.max(0, 100 - total), description: "", needs_research: true, opinion: false }],
              })
            }
          >
            <Plus /> Рубрика
          </Button>
        </div>
        {value.rubrics.map((r, i) => (
          <div key={i} className="space-y-2 rounded-lg border p-3">
            <div className="grid gap-2 sm:grid-cols-[1fr_9rem_6rem_auto]">
              <Input value={r.name} placeholder="Название рубрики" onChange={(e) => setRubric(i, { name: e.target.value })} />
              <Select value={r.format} onValueChange={(v) => setRubric(i, { format: v as PostFormat })}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(formatLabel) as PostFormat[]).map((f) => (
                    <SelectItem key={f} value={f}>
                      {formatLabel[f]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <div className="relative">
                <Input type="number" min={0} max={100} value={r.share} onChange={(e) => setRubric(i, { share: Number(e.target.value) || 0 })} className="pr-7" aria-label="Доля, %" />
                <span className="pointer-events-none absolute top-1/2 right-2.5 -translate-y-1/2 text-sm text-muted-foreground">%</span>
              </div>
              <Button type="button" variant="ghost" size="icon" aria-label="Удалить рубрику" onClick={() => onChange({ ...value, rubrics: value.rubrics.filter((_, j) => j !== i) })}>
                <Trash2 />
              </Button>
            </div>
            <Textarea value={r.description} placeholder="О чём рубрика и чем полезна читателю" rows={2} onChange={(e) => setRubric(i, { description: e.target.value })} />
            <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <label className="flex items-center gap-2">
                <Switch checked={r.needs_research} onCheckedChange={(v) => setRubric(i, { needs_research: v })} />
                Нужно исследование фактов
              </label>
              <label className="flex items-center gap-2">
                <Switch checked={r.opinion} onCheckedChange={(v) => setRubric(i, { opinion: v })} />
                Мнение канала
              </label>
            </div>
          </div>
        ))}
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor="st-forbidden">Запрещено</Label>
        <TagInput id="st-forbidden" value={value.forbidden} onChange={(forbidden) => onChange({ ...value, forbidden })} placeholder="Темы и приёмы, которых не должно быть" />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="st-notes">Заметки</Label>
        <Textarea id="st-notes" value={value.notes} onChange={(e) => onChange({ ...value, notes: e.target.value })} rows={3} />
      </div>
    </div>
  )
}
