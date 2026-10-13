import { Check, ChevronsUpDown } from "lucide-react"
import { useMemo, useRef, useState, type KeyboardEvent } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { timeZoneOption, timeZones } from "@/lib/tz"
import { cn } from "@/lib/utils"

export function TimezoneSelect({ id, value, onChange }: { id?: string; value: string; onChange: (value: string) => void }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const [active, setActive] = useState(0)
  const listRef = useRef<HTMLDivElement>(null)

  const zones = useMemo(() => {
    const all = timeZones()
    return all.some((z) => z.id === value) ? all : [timeZoneOption(value), ...all]
  }, [value])
  const current = zones.find((z) => z.id === value)
  const found = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? zones.filter((z) => z.search.includes(q)) : zones
  }, [query, zones])

  const highlight = (index: number) => {
    setActive(index)
    listRef.current?.children[index]?.scrollIntoView({ block: "nearest" })
  }

  const openChange = (next: boolean) => {
    setOpen(next)
    setQuery("")
    if (next) requestAnimationFrame(() => highlight(Math.max(0, zones.findIndex((z) => z.id === value))))
  }

  const pick = (zoneId: string) => {
    onChange(zoneId)
    openChange(false)
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault()
      highlight(Math.min(found.length - 1, Math.max(0, active + (e.key === "ArrowDown" ? 1 : -1))))
    } else if (e.key === "Enter") {
      e.preventDefault()
      if (found[active]) pick(found[active].id)
    }
  }

  return (
    <Popover open={open} onOpenChange={openChange}>
      <PopoverTrigger asChild>
        <Button id={id} type="button" variant="outline" role="combobox" aria-expanded={open} className="w-full max-w-md justify-between font-normal">
          <span className="truncate">
            {current ? (
              <>
                <span className="tabular-nums text-muted-foreground">{current.offset}</span> {current.name || current.id}
              </>
            ) : (
              "Выберите часовой пояс"
            )}
          </span>
          <ChevronsUpDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(30rem,calc(100vw-2rem))] p-0">
        <div className="border-b p-2">
          <Input
            autoFocus
            value={query}
            onChange={(e) => {
              setQuery(e.target.value)
              setActive(0)
            }}
            onKeyDown={onKeyDown}
            placeholder="Город, страна или смещение: Москва, Asia, +5"
            aria-label="Поиск часового пояса"
          />
        </div>
        <div ref={listRef} role="listbox" className="max-h-72 overflow-y-auto p-1">
          {found.map((z, i) => (
            <button
              key={z.id}
              type="button"
              role="option"
              aria-selected={z.id === value}
              onMouseMove={() => setActive(i)}
              onClick={() => pick(z.id)}
              className={cn("flex w-full items-center gap-3 rounded-sm px-2 py-1.5 text-left text-sm", i === active && "bg-accent")}
            >
              <span className="w-[5.5rem] shrink-0 text-muted-foreground tabular-nums">{z.offset}</span>
              <span className="min-w-0 flex-1 truncate">
                {z.name || z.id}
                <span className="ml-2 text-xs text-muted-foreground">{z.id}</span>
              </span>
              {z.id === value && <Check className="size-4 shrink-0" />}
            </button>
          ))}
        </div>
        {found.length === 0 && <div className="px-2 pb-6 text-center text-sm text-muted-foreground">Ничего не нашлось</div>}
      </PopoverContent>
    </Popover>
  )
}
