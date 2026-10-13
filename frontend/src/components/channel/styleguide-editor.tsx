import { Plus, Trash2 } from "lucide-react"

import { TagInput } from "@/components/tag-input"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import type { StyleStructured, Styleguide } from "@/lib/types"

function NumberField({ id, label, value, onChange, min = 0 }: { id: string; label: string; value: number; onChange: (v: number) => void; min?: number }) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type="number" min={min} value={value} onChange={(e) => onChange(Number(e.target.value) || 0)} />
    </div>
  )
}

export function StyleguideEditor({ value, onChange }: { value: Styleguide; onChange: (v: Styleguide) => void }) {
  const s = value.structured
  const setS = <K extends keyof StyleStructured>(key: K, v: StyleStructured[K]) => onChange({ ...value, structured: { ...s, [key]: v } })

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="grid gap-1.5">
          <Label>Обращение</Label>
          <Select value={s.address} onValueChange={(v) => setS("address", v as StyleStructured["address"])}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ty">На «ты»</SelectItem>
              <SelectItem value="vy">На «вы»</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <NumberField id="sg-min" label="Длина от, символов" value={s.length_min} onChange={(v) => setS("length_min", v)} />
        <NumberField id="sg-max" label="Длина до, символов" value={s.length_max} onChange={(v) => setS("length_max", v)} />
        <NumberField id="sg-emoji" label="Эмодзи на пост, не больше" value={s.emoji_max} onChange={(v) => setS("emoji_max", v)} />
      </div>

      <div className="flex flex-wrap gap-x-6 gap-y-3">
        {(
          [
            ["allow_bold", "Жирный шрифт"],
            ["allow_quotes", "Цитаты"],
            ["allow_lists", "Списки"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="flex items-center gap-2 text-sm">
            <Switch checked={s[key]} onCheckedChange={(v) => setS(key, v)} />
            {label}
          </label>
        ))}
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label>Ссылки в постах</Label>
          <Select value={s.links_policy} onValueChange={(v) => setS("links_policy", v as StyleStructured["links_policy"])}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="source_only">Только на источник</SelectItem>
              <SelectItem value="none">Без ссылок</SelectItem>
              <SelectItem value="free">Любые уместные</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="sg-sign">Подпись в конце поста</Label>
          <Input id="sg-sign" value={s.signature} onChange={(e) => setS("signature", e.target.value)} placeholder="Необязательно" />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-1.5">
          <Label htmlFor="sg-banned">Запрещённые слова и обороты</Label>
          <TagInput id="sg-banned" value={s.banned_phrases} onChange={(v) => setS("banned_phrases", v)} placeholder="Например: «в современном мире»" />
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="sg-tags">Хештеги</Label>
          <TagInput id="sg-tags" value={s.hashtags} onChange={(v) => setS("hashtags", v)} placeholder="#кофе" />
        </div>
      </div>

      <div className="grid gap-1.5">
        <Label htmlFor="sg-text">Описание голоса канала</Label>
        <Textarea id="sg-text" value={value.text} onChange={(e) => onChange({ ...value, text: e.target.value })} rows={8} className="min-h-40" />
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label>Правила</Label>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onChange({ ...value, rules: [...value.rules, { id: crypto.randomUUID().slice(0, 8), text: "", origin: "user" }] })}
          >
            <Plus /> Правило
          </Button>
        </div>
        {value.rules.length === 0 && <p className="text-sm text-muted-foreground">Правил нет. Они появятся из ваших правок постов или добавьте вручную.</p>}
        {value.rules.map((r, i) => (
          <div key={r.id} className="flex items-start gap-2">
            <Input
              value={r.text}
              onChange={(e) => onChange({ ...value, rules: value.rules.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)) })}
              placeholder="Например: не начинать пост с вопроса"
            />
            {r.origin === "edits" && (
              <Badge variant="secondary" className="mt-2 shrink-0" title="Выведено из ваших правок постов">
                из правок
              </Badge>
            )}
            <Button type="button" variant="ghost" size="icon" aria-label="Удалить правило" onClick={() => onChange({ ...value, rules: value.rules.filter((_, j) => j !== i) })}>
              <Trash2 />
            </Button>
          </div>
        ))}
      </div>
    </div>
  )
}
