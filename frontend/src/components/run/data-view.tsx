import { cn } from "@/lib/utils"

const KEY_LABELS: Record<string, string> = {
  title: "Заголовок",
  text: "Текст",
  summary: "Итог",
  reason: "Причина",
  comment: "Комментарий",
  topic: "Тема",
  topics: "Темы",
  story: "Сюжет",
  facts: "Факты",
  sources: "Источники",
  issues: "Замечания",
  critical: "Критичных",
  status: "Статус",
  attempt: "Попытка",
  format: "Формат",
  key_idea: "Ключевая мысль",
  reader_goal: "Цель для читателя",
  rubric: "Рубрика",
  slots: "Слоты",
  publish_at: "Время публикации",
  local_at: "Время по поясу канала",
  outcome: "Итог",
  outcome_reason: "Причина",
  claim: "Утверждение",
  source_url: "Источник",
  url: "Ссылка",
  count: "Количество",
  rejected: "Отклонено",
  not_found: "Не найдено",
  pages: "Прочитанные страницы",
  calculations: "Расчёты",
  verdict: "Вердикт",
  rules: "Правила",
  structured: "Параметры",
  rubrics: "Рубрики",
  audience: "Аудитория",
  goal: "Цель",
  forbidden: "Запрещено",
  notes: "Заметки",
  change_note: "Что изменено",
  action: "Действие",
  scores: "Оценки",
  significance: "Значимость",
  posts: "Посты",
  ideas: "Идеи",
  samples: "Образцы",
  site: "Сайт",
  chars: "Символов",
  refreshed: "Лент обновлено",
  new: "Новых материалов",
  errors: "Ошибки",
  teaser_only: "Только анонс, статья не открылась",
}

function label(key: string) {
  return KEY_LABELS[key] ?? key.replace(/_/g, " ")
}

function isUrl(v: string) {
  return /^https?:\/\//.test(v)
}

export function DataView({ value, depth = 0, className }: { value: unknown; depth?: number; className?: string }) {
  if (value === null || value === undefined || value === "") return <span className="text-muted-foreground">—</span>
  if (typeof value === "boolean") return <span>{value ? "да" : "нет"}</span>
  if (typeof value === "number") return <span className="tabular-nums">{value}</span>
  if (typeof value === "string") {
    if (isUrl(value))
      return (
        <a href={value} target="_blank" rel="noreferrer noopener" className="break-all text-sky-600 underline-offset-2 hover:underline dark:text-sky-400">
          {value}
        </a>
      )
    return <span className="whitespace-pre-wrap break-words">{value}</span>
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground">пусто</span>
    if (value.every((v) => typeof v !== "object" || v === null))
      return (
        <ul className="list-disc space-y-0.5 pl-5">
          {value.map((v, i) => (
            <li key={i}>
              <DataView value={v} depth={depth + 1} />
            </li>
          ))}
        </ul>
      )
    return (
      <div className="space-y-2">
        {value.map((v, i) => (
          <div key={i} className="rounded-lg border bg-muted/30 p-2.5">
            <DataView value={v} depth={depth + 1} />
          </div>
        ))}
      </div>
    )
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).filter(([, v]) => v !== null && v !== undefined && v !== "")
    if (entries.length === 0) return <span className="text-muted-foreground">пусто</span>
    return (
      <dl className={cn("grid gap-x-3 gap-y-1.5 text-sm", depth < 3 && "sm:grid-cols-[minmax(7rem,max-content)_1fr]", className)}>
        {entries.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-xs font-medium text-muted-foreground sm:pt-0.5">{label(k)}</dt>
            <dd className="min-w-0">
              <DataView value={v} depth={depth + 1} />
            </dd>
          </div>
        ))}
      </dl>
    )
  }
  return <span>{String(value)}</span>
}
