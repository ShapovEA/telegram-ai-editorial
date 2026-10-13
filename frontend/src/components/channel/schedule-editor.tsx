import { Plus, Trash2 } from "lucide-react"

import { TimezoneSelect } from "@/components/timezone-select"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { weekdayShort } from "@/lib/labels"
import type { ChannelType, NewsSchedule, SmmSchedule } from "@/lib/types"
import { cn } from "@/lib/utils"

function Days({ value, onChange }: { value: number[]; onChange: (v: number[]) => void }) {
  return (
    <div className="flex flex-wrap gap-1">
      {weekdayShort.map((d, i) => {
        const on = value.includes(i)
        return (
          <button
            key={d}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((x) => x !== i) : [...value, i].sort())}
            className={cn("h-8 w-10 rounded-md border text-sm transition-colors", on ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted")}
          >
            {d}
          </button>
        )
      })}
    </div>
  )
}

function Timezone({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor="sch-tz">Часовой пояс</Label>
      <TimezoneSelect id="sch-tz" value={value} onChange={onChange} />
    </div>
  )
}

export function ScheduleEditor({ type, value, onChange }: { type: ChannelType; value: NewsSchedule | SmmSchedule; onChange: (v: NewsSchedule | SmmSchedule) => void }) {
  if (type === "news") {
    const s = value as NewsSchedule
    return (
      <div className="space-y-5">
        <div className="grid gap-1.5">
          <Label>Дни выхода</Label>
          <Days value={s.days} onChange={(days) => onChange({ ...s, days })} />
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>Время публикаций</Label>
            <Button type="button" variant="ghost" size="sm" onClick={() => onChange({ ...s, times: [...s.times, "12:00"] })}>
              <Plus /> Время
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {s.times.map((t, i) => (
              <div key={i} className="flex items-center gap-1">
                <Input type="time" value={t} className="w-28" onChange={(e) => onChange({ ...s, times: s.times.map((x, j) => (j === i ? e.target.value : x)) })} />
                <Button type="button" variant="ghost" size="icon" aria-label="Убрать время" onClick={() => onChange({ ...s, times: s.times.filter((_, j) => j !== i) })}>
                  <Trash2 />
                </Button>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">В каждое время шеф-редактор выбирает лучший свежий сюжет. Если сюжетов нет, слот пропускается или занимается вечнозелёной темой.</p>
        </div>
        <Timezone value={s.timezone} onChange={(timezone) => onChange({ ...s, timezone })} />
      </div>
    )
  }

  const s = value as SmmSchedule
  return (
    <div className="space-y-5">
      <div className="grid max-w-48 gap-1.5">
        <Label htmlFor="sch-ppw">Постов в неделю</Label>
        <Input id="sch-ppw" type="number" min={1} max={28} value={s.posts_per_week} onChange={(e) => onChange({ ...s, posts_per_week: Number(e.target.value) || 1 })} />
      </div>
      <div className="grid gap-1.5">
        <Label>Дни выхода</Label>
        <Days value={s.days} onChange={(days) => onChange({ ...s, days })} />
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Окна публикаций</Label>
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange({ ...s, windows: [...s.windows, { start: "09:00", end: "21:00" }] })}>
            <Plus /> Окно
          </Button>
        </div>
        {s.windows.map((w, i) => (
          <div key={i} className="flex items-center gap-2">
            <Input type="time" value={w.start} className="w-28" onChange={(e) => onChange({ ...s, windows: s.windows.map((x, j) => (j === i ? { ...x, start: e.target.value } : x)) })} />
            <span className="text-muted-foreground">—</span>
            <Input type="time" value={w.end} className="w-28" onChange={(e) => onChange({ ...s, windows: s.windows.map((x, j) => (j === i ? { ...x, end: e.target.value } : x)) })} />
            <Button type="button" variant="ghost" size="icon" aria-label="Убрать окно" disabled={s.windows.length === 1} onClick={() => onChange({ ...s, windows: s.windows.filter((_, j) => j !== i) })}>
              <Trash2 />
            </Button>
          </div>
        ))}
        <p className="text-xs text-muted-foreground">Стратег расставляет посты внутри окон, когда составляет недельный план.</p>
      </div>
      <Timezone value={s.timezone} onChange={(timezone) => onChange({ ...s, timezone })} />
    </div>
  )
}
