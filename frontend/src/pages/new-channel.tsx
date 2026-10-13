import { useCreate, useInvalidate } from "@refinedev/core"
import { Check, Radio, Tv } from "lucide-react"
import { useState, type FormEvent } from "react"
import { useNavigate } from "react-router"

import { PageHeader, Spinner } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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
  const { mutate: create, mutation } = useCreate<Channel>()
  const [type, setType] = useState<ChannelType>("smm")
  const [title, setTitle] = useState("")

  const submit = (e: FormEvent) => {
    e.preventDefault()
    create(
      { resource: "channels", values: { type, title: title.trim() }, successNotification: false },
      {
        onSuccess: ({ data }) => {
          invalidate({ resource: "channels", invalidates: ["list"] })
          navigate(`/channels/${data.id}`)
        },
      },
    )
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Новый канал" description="Выберите тип канала. Дальше заполните бриф и подключите Telegram" />
      <form onSubmit={submit} className="space-y-6">
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
          <CardContent className="space-y-2">
            <Label htmlFor="title">Название в сервисе</Label>
            <Input
              id="title"
              required
              maxLength={200}
              placeholder="Например, «Кофе без пафоса»"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">Видно только вам. Название Telegram-канала подтянется при подключении</p>
          </CardContent>
        </Card>
        <div className="flex justify-end">
          <Button type="submit" disabled={!title.trim() || mutation.isPending}>
            {mutation.isPending && <Spinner />} Создать и перейти к брифу
          </Button>
        </div>
      </form>
    </div>
  )
}
