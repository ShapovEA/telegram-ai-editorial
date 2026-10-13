import { useInvalidate } from "@refinedev/core"
import { useMutation } from "@tanstack/react-query"
import { Check, Radio, Tv } from "lucide-react"
import { useState } from "react"
import { useNavigate } from "react-router"
import { toast } from "sonner"

import { TelegramConnect } from "@/components/channel/telegram-connect"
import { PageHeader } from "@/components/common"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { api } from "@/lib/api"
import type { Channel, ChannelType } from "@/lib/types"
import { cn } from "@/lib/utils"

const TYPES: { value: ChannelType; title: string; icon: typeof Tv; points: string[] }[] = [
  {
    value: "smm",
    title: "SMM-канал",
    icon: Tv,
    points: [
      "Экспертный или авторский канал",
      "Недельный контент-план с рубриками",
      "Банк идей, исследование темы, опросы",
    ],
  },
  {
    value: "news",
    title: "Новостной канал",
    icon: Radio,
    points: ["Сюжеты из ваших RSS-лент", "Посты по сетке времени", "Проверка фактов и новизны темы"],
  },
]

export function NewChannelPage() {
  const navigate = useNavigate()
  const invalidate = useInvalidate()
  const [type, setType] = useState<ChannelType>("smm")

  const create = useMutation({
    mutationFn: (username: string) => api<Channel>("/channels", { body: { type, username } }),
    onSuccess: (c) => {
      invalidate({ resource: "channels", invalidates: ["list"] })
      navigate(`/channels/${c.id}`)
    },
    onError: (e) => toast.error((e as Error).message),
  })

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Новый канал" description="Выберите тип канала и подключите его Telegram. Дальше заполните бриф" />
      <div className="space-y-6">
        <div className="grid gap-4 sm:grid-cols-2">
          {TYPES.map((t) => {
            const active = type === t.value
            return (
              <button
                key={t.value}
                type="button"
                onClick={() => setType(t.value)}
                className={cn(
                  "relative rounded-xl border p-5 text-left transition-colors hover:border-foreground/30",
                  active && "border-primary ring-2 ring-primary/20",
                )}
              >
                {active && (
                  <span className="absolute top-4 right-4 flex size-5 items-center justify-center rounded-full bg-primary text-primary-foreground">
                    <Check className="size-3" />
                  </span>
                )}
                <t.icon className="mb-3 size-6" />
                <div className="font-semibold">{t.title}</div>
                <ul className="mt-2 space-y-1 text-sm text-muted-foreground">
                  {t.points.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </button>
            )
          })}
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Telegram-канал</CardTitle>
            <CardDescription>Бот сервиса публикует посты от имени канала</CardDescription>
          </CardHeader>
          <CardContent>
            <TelegramConnect submitLabel="Создать и перейти к брифу" pending={create.isPending} onSubmit={(username) => create.mutate(username)} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
