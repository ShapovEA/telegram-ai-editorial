import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FlaskConical, History, Lock, RotateCcw } from "lucide-react"
import { useState } from "react"
import { useNavigate } from "react-router"
import { toast } from "sonner"

import { LoadingRows, Spinner, ToneBadge } from "@/components/common"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Textarea } from "@/components/ui/textarea"
import { api } from "@/lib/api"
import { fmtDateTime } from "@/lib/format"
import { roleLabel } from "@/lib/labels"
import type { Role } from "@/lib/types"

type PromptSpec = {
  role: Role
  key: string
  title: string
  description: string
  text: string
  default_text: string
  overridden: boolean
  version: number
  closed: string
  placeholders: string[]
  testable: boolean
}

type Version = { version: number; text: string | null; reset: boolean; created_at: string }

function PromptItem({ channelId, spec }: { channelId: number; spec: PromptSpec }) {
  const client = useQueryClient()
  const navigate = useNavigate()
  const [text, setText] = useState(spec.text)
  const [showVersions, setShowVersions] = useState(false)
  const dirty = text !== spec.text
  const base = `/channels/${channelId}/prompts/${spec.role}/${spec.key}`
  const refresh = () => client.invalidateQueries({ queryKey: ["prompts", channelId] })

  const versions = useQuery({ queryKey: ["prompt-versions", channelId, spec.role, spec.key], queryFn: () => api<Version[]>(`${base}/versions`), enabled: showVersions })
  const missing = spec.placeholders.filter((p) => !text.includes(`{${p}}`))

  const save = useMutation({
    mutationFn: () => api<{ version: number }>(base, { method: "PUT", body: { text } }),
    onSuccess: (r) => {
      toast.success(`Сохранено, версия ${r.version}`)
      refresh()
    },
    onError: (e) => toast.error((e as Error).message),
  })
  const reset = useMutation({
    mutationFn: () => api<{ text: string }>(`${base}/reset`, { method: "POST" }),
    onSuccess: (r) => {
      setText(r.text)
      toast.success("Возвращён промпт по умолчанию")
      refresh()
    },
    onError: (e) => toast.error((e as Error).message),
  })
  const test = useMutation({
    mutationFn: () => api<{ run_id: string }>(`/channels/${channelId}/prompts/writer/main/test`, { body: { text, samples: 2 } }),
    onSuccess: ({ run_id }) => navigate(`/runs/${run_id}`),
    onError: (e) => toast.error((e as Error).message),
  })

  return (
    <AccordionItem value={`${spec.role}:${spec.key}`}>
      <AccordionTrigger className="hover:no-underline">
        <div className="flex flex-1 flex-wrap items-center gap-2 text-left">
          <span className="font-medium">{spec.title}</span>
          <span className="text-xs text-muted-foreground">{roleLabel[spec.role] ?? spec.role}</span>
          {spec.overridden && <ToneBadge tone="info">изменён · v{spec.version}</ToneBadge>}
        </div>
      </AccordionTrigger>
      <AccordionContent className="space-y-3">
        {spec.description && <p className="text-sm text-muted-foreground">{spec.description}</p>}
        <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={14} className="font-mono text-xs" />
        {spec.placeholders.length > 0 && (
          <p className="text-xs text-muted-foreground">
            Подстановки: {spec.placeholders.map((p) => `{${p}}`).join(", ")}
            {missing.length > 0 && <span className="text-amber-600 dark:text-amber-400"> · пропали: {missing.map((p) => `{${p}}`).join(", ")}</span>}
          </p>
        )}
        {spec.closed && (
          <Collapsible>
            <CollapsibleTrigger className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
              <Lock className="size-3.5" /> Закрытая часть: правила безопасности и формат ответа, её править нельзя
            </CollapsibleTrigger>
            <CollapsibleContent>
              <pre className="mt-2 max-h-60 overflow-auto rounded-lg bg-muted/50 p-3 font-mono text-xs whitespace-pre-wrap">{spec.closed}</pre>
            </CollapsibleContent>
          </Collapsible>
        )}
        <div className="flex flex-wrap justify-between gap-2">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="ghost" onClick={() => setShowVersions((v) => !v)}>
              <History /> Версии
            </Button>
            {spec.overridden && (
              <Button size="sm" variant="ghost" onClick={() => reset.mutate()} disabled={reset.isPending}>
                <RotateCcw /> По умолчанию
              </Button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {spec.testable && (
              <Button size="sm" variant="outline" onClick={() => test.mutate()} disabled={test.isPending} title="Писатель напишет пробные посты по этому промпту, в канал ничего не уйдёт">
                {test.isPending ? <Spinner /> : <FlaskConical />} Пробный прогон
              </Button>
            )}
            <Button size="sm" onClick={() => save.mutate()} disabled={!dirty || text.length < 20 || save.isPending}>
              {save.isPending && <Spinner />} Сохранить
            </Button>
          </div>
        </div>
        {showVersions && (
          <div className="rounded-lg border">
            {versions.isLoading && <LoadingRows rows={2} className="p-2" />}
            {versions.data?.length === 0 && <p className="p-3 text-sm text-muted-foreground">Изменений не было</p>}
            <ul className="divide-y">
              {versions.data?.map((v) => (
                <li key={v.version} className="flex items-center justify-between gap-2 p-2 text-sm">
                  <span>
                    v{v.version} · {fmtDateTime(v.created_at)} {v.reset && <span className="text-muted-foreground">· сброс к умолчанию</span>}
                  </span>
                  {!v.reset && v.text && (
                    <Button size="sm" variant="ghost" onClick={() => setText(v.text ?? "")}>
                      Подставить
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </AccordionContent>
    </AccordionItem>
  )
}

export function PromptsEditor({ channelId }: { channelId: number }) {
  const { data, isLoading } = useQuery({ queryKey: ["prompts", channelId], queryFn: () => api<PromptSpec[]>(`/channels/${channelId}/prompts`) })
  if (isLoading || !data) return <LoadingRows rows={5} />
  return (
    <Accordion type="multiple" className="w-full">
      {data.map((s) => (
        <PromptItem key={`${s.role}:${s.key}:${s.version}`} channelId={channelId} spec={s} />
      ))}
    </Accordion>
  )
}
