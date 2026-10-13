import { X } from "lucide-react"
import { useState, type KeyboardEvent } from "react"

import { cn } from "@/lib/utils"

export function TagInput({
  value,
  onChange,
  placeholder,
  className,
  id,
}: {
  value: string[]
  onChange: (value: string[]) => void
  placeholder?: string
  className?: string
  id?: string
}) {
  const [draft, setDraft] = useState("")

  const commit = () => {
    const items = draft
      .split(/[,\n]/)
      .map((s) => s.trim())
      .filter(Boolean)
    if (items.length) onChange([...value, ...items.filter((i) => !value.includes(i))])
    setDraft("")
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault()
      commit()
    } else if (e.key === "Backspace" && !draft && value.length) {
      onChange(value.slice(0, -1))
    }
  }

  return (
    <div
      className={cn(
        "flex min-h-9 w-full flex-wrap items-center gap-1.5 rounded-md border border-input bg-transparent px-2 py-1.5 text-sm shadow-xs focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/50 dark:bg-input/30",
        className,
      )}
    >
      {value.map((tag) => (
        <span key={tag} className="flex items-center gap-1 rounded-md bg-secondary py-0.5 pr-1 pl-2 text-xs">
          {tag}
          <button type="button" aria-label={`Убрать ${tag}`} onClick={() => onChange(value.filter((t) => t !== tag))} className="rounded p-0.5 hover:bg-background/60">
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
        placeholder={value.length ? undefined : placeholder}
        className="min-w-32 flex-1 bg-transparent py-0.5 outline-none placeholder:text-muted-foreground/55"
      />
    </div>
  )
}
