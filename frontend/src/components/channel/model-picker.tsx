import { useQuery } from "@tanstack/react-query"
import { Brain, Check, ChevronsUpDown, Search } from "lucide-react"
import { useEffect, useState } from "react"

import { TagInput } from "@/components/tag-input"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { api } from "@/lib/api"
import { fmtNumber } from "@/lib/format"
import type { ReasoningLevel, RoleModel } from "@/lib/types"
import { cn } from "@/lib/utils"

export type CatalogModel = {
  id: string
  name: string
  context_length: number
  input_per_million: number
  output_per_million: number
  supports_tools: boolean
  reasoning: boolean
  reasoning_mandatory: boolean
  reasoning_efforts: string[]
}

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

export function ModelSearch({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState("")
  const query = useDebounced(q, 250)
  const { data, isFetching } = useQuery({
    queryKey: ["models", query],
    queryFn: () => api<{ items: CatalogModel[] }>("/models", { query: { q: query, limit: 80 } }),
    enabled: open,
    staleTime: 60_000,
  })

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" role="combobox" aria-expanded={open} className="w-full justify-between font-mono text-xs">
          <span className="truncate">{value || "Выберите модель"}</span>
          <ChevronsUpDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(36rem,calc(100vw-2rem))] p-0" align="start">
        <div className="flex items-center gap-2 border-b px-3">
          <Search className="size-4 text-muted-foreground" />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="anthropic/claude, gpt, gemini…"
            className="h-10 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          {isFetching && <span className="text-xs text-muted-foreground">…</span>}
        </div>
        <ScrollArea className="h-80">
          <ul className="p-1">
            {data?.items.map((m) => (
              <li key={m.id}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(m.id)
                    setOpen(false)
                  }}
                  className={cn("flex w-full items-start gap-2 rounded-md p-2 text-left hover:bg-muted", m.id === value && "bg-muted")}
                >
                  <Check className={cn("mt-0.5 size-4 shrink-0", m.id === value ? "opacity-100" : "opacity-0")} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate font-mono text-xs">{m.id}</span>
                      {m.reasoning_mandatory ? (
                        <span className="shrink-0 rounded bg-amber-500/15 px-1.5 text-[11px] text-amber-700 dark:text-amber-300">рассуждение обязательно</span>
                      ) : (
                        m.reasoning && <Brain className="size-3.5 shrink-0 text-muted-foreground" aria-label="Умеет рассуждать" />
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground tabular-nums">
                      ${m.input_per_million} / ${m.output_per_million} за 1М токенов · контекст {fmtNumber(m.context_length)}
                    </div>
                  </div>
                </button>
              </li>
            ))}
            {data && data.items.length === 0 && <li className="p-3 text-center text-sm text-muted-foreground">Ничего не найдено</li>}
          </ul>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  )
}

const REASONING: { value: ReasoningLevel; label: string }[] = [
  { value: "none", label: "Без рассуждений" },
  { value: "minimal", label: "Минимальные" },
  { value: "low", label: "Короткие" },
  { value: "medium", label: "Средние" },
  { value: "high", label: "Глубокие" },
]

export function RoleModelEditor({ value, onChange }: { value: RoleModel; onChange: (v: RoleModel) => void }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_10rem_7rem]">
      <div className="grid gap-1.5">
        <Label className="text-xs text-muted-foreground">Модель</Label>
        <ModelSearch value={value.model} onChange={(model) => onChange({ ...value, model })} />
      </div>
      <div className="grid gap-1.5">
        <Label className="text-xs text-muted-foreground">Рассуждения</Label>
        <Select value={value.reasoning} onValueChange={(v) => onChange({ ...value, reasoning: v as ReasoningLevel })}>
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {REASONING.map((r) => (
              <SelectItem key={r.value} value={r.value}>
                {r.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="grid gap-1.5">
        <Label className="text-xs text-muted-foreground">Температура</Label>
        <Input
          type="number"
          min={0}
          max={2}
          step={0.1}
          value={value.temperature ?? ""}
          placeholder="авто"
          onChange={(e) => onChange({ ...value, temperature: e.target.value === "" ? null : Number(e.target.value) })}
        />
      </div>
      <div className="grid gap-1.5 sm:col-span-2 lg:col-span-3">
        <Label className="text-xs text-muted-foreground">Резервные модели, если основная недоступна</Label>
        <TagInput value={value.fallbacks} onChange={(fallbacks) => onChange({ ...value, fallbacks })} placeholder="openai/gpt-…" />
      </div>
    </div>
  )
}
