import { useGetIdentity, useInvalidate } from "@refinedev/core"
import { useMutation } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, ExternalLink, Send } from "lucide-react"
import { useEffect, useState, type FormEvent, type ReactNode } from "react"
import { toast } from "sonner"

import { Callout, Spinner } from "@/components/common"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useServiceSettings } from "@/hooks/use-service-settings"
import { api } from "@/lib/api"
import type { Channel, User } from "@/lib/types"

function StepTitle({ n, done, children }: { n: number; done: boolean; children: string }) {
  return (
    <div className="flex items-center gap-2 font-medium">
      {done ? (
        <CheckCircle2 className="size-5 text-emerald-500" />
      ) : (
        <span className="flex size-5 items-center justify-center rounded-full border text-xs">{n}</span>
      )}
      {children}
    </div>
  )
}

export function TelegramConnect({
  defaultUsername = "",
  connected = false,
  submitLabel,
  pending,
  onSubmit,
  children,
}: {
  defaultUsername?: string
  connected?: boolean
  submitLabel: string
  pending: boolean
  onSubmit: (username: string) => void
  children?: ReactNode
}) {
  const { data: settings } = useServiceSettings()
  const { data: user, refetch: refetchUser } = useGetIdentity<User>()
  const [waitingLink, setWaitingLink] = useState(false)
  const [username, setUsername] = useState(defaultUsername)
  const bot = settings?.telegram_bot_username?.replace(/^@/, "")

  useEffect(() => {
    if (!waitingLink) return
    const t = setInterval(async () => {
      const res = await refetchUser()
      if (res.data?.telegram_linked) {
        setWaitingLink(false)
        toast.success("Telegram привязан")
      }
    }, 3000)
    return () => clearInterval(t)
  }, [waitingLink, refetchUser])

  const link = useMutation({
    mutationFn: () => api<{ url: string }>("/auth/telegram-link", { method: "POST" }),
    onSuccess: ({ url }) => {
      window.open(url, "_blank", "noopener")
      setWaitingLink(true)
    },
    onError: (e) => toast.error((e as Error).message),
  })

  if (settings && !settings.telegram_configured)
    return (
      <Callout tone="red" icon={<AlertTriangle />} title={<>Бот сервиса не настроен</>}>
        Администратор сервиса должен задать рабочий TELEGRAM_BOT_TOKEN в .env и перезапустить сервис.
      </Callout>
    )

  const submit = (e: FormEvent) => {
    e.preventDefault()
    onSubmit(username)
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <StepTitle n={1} done={!!user?.telegram_linked}>
          Привяжите свой Telegram
        </StepTitle>
        <p className="pl-7 text-sm text-muted-foreground">Так сервис убедится, что вы администратор канала.</p>
        <div className="pl-7">
          {user?.telegram_linked ? (
            <p className="text-sm">Привязан{user.telegram_username ? ` как @${user.telegram_username}` : ""}</p>
          ) : (
            <Button type="button" variant="outline" onClick={() => link.mutate()} disabled={link.isPending}>
              {link.isPending || waitingLink ? <Spinner /> : <Send />}
              {waitingLink ? "Ждём нажатия «Start» в боте…" : "Открыть бота и привязать"}
            </Button>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <StepTitle n={2} done={connected}>
          Добавьте бота администратором канала
        </StepTitle>
        <p className="pl-7 text-sm text-muted-foreground">
          В настройках канала: Администраторы → Добавить → {bot ? <b className="text-foreground">@{bot}</b> : "бот сервиса"}. Нужно право «Публикация
          сообщений». Остальные права можно не давать.
        </p>
        {bot && (
          <div className="pl-7">
            <a
              href={`https://t.me/${bot}`}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-sm text-sky-600 hover:underline dark:text-sky-400"
            >
              Открыть @{bot} <ExternalLink className="size-3.5" />
            </a>
          </div>
        )}
      </div>

      <form onSubmit={submit} className="space-y-2">
        <StepTitle n={3} done={connected}>
          Укажите канал
        </StepTitle>
        <p className="pl-7 text-sm text-muted-foreground">Название канала сервис возьмёт из Telegram.</p>
        <div className="flex flex-wrap items-end gap-2 pl-7">
          <div className="grid min-w-60 flex-1 gap-1.5">
            <Label htmlFor="tg-username" className="sr-only">
              Username канала
            </Label>
            <Input
              id="tg-username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="@mychannel или https://t.me/mychannel"
              required
            />
          </div>
          <Button type="submit" disabled={!user?.telegram_linked || !username.trim() || pending}>
            {pending && <Spinner />} {submitLabel}
          </Button>
        </div>
        {children}
      </form>
    </div>
  )
}

export function ChannelTelegram({ channel, onConnected }: { channel: Channel; onConnected: () => void }) {
  const invalidate = useInvalidate()
  const connect = useMutation({
    mutationFn: (username: string) => api<Channel>(`/channels/${channel.id}/telegram`, { body: { username } }),
    onSuccess: (c) => {
      toast.success(`Канал «${c.title}» подключён`)
      invalidate({ resource: "channels", invalidates: ["list"] })
      onConnected()
    },
    onError: (e) => toast.error((e as Error).message),
  })

  return (
    <TelegramConnect
      defaultUsername={channel.telegram_username ?? ""}
      connected={channel.telegram_connected}
      submitLabel={channel.telegram_connected ? "Переподключить" : "Подключить"}
      pending={connect.isPending}
      onSubmit={(username) => connect.mutate(username)}
    >
      {channel.telegram_connected && (
        <p className="pl-7 text-sm text-emerald-700 dark:text-emerald-400">
          Подключён: {channel.title} (@{channel.telegram_username})
        </p>
      )}
    </TelegramConnect>
  )
}
