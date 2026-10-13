import { AlertCircle, Loader2 } from "lucide-react"
import type { ReactNode } from "react"

import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import type { Tone } from "@/lib/labels"
import { cn } from "@/lib/utils"

const toneClass: Record<Tone, string> = {
  neutral: "bg-tag-gray",
  info: "bg-tag-blue",
  success: "bg-tag-green",
  warning: "bg-tag-yellow",
  danger: "bg-tag-red",
  muted: "bg-tag-gray",
}

const TAG = "h-auto rounded-[4px] border-transparent px-1.5 py-px text-[13px] leading-5 font-normal text-tag-text"

export function StatusBadge<K extends string>({ value, labels, className }: { value: K; labels: Record<K, [string, Tone]>; className?: string }) {
  const [label, tone] = labels[value] ?? [value, "neutral"]
  return <Badge className={cn(TAG, toneClass[tone], className)}>{label}</Badge>
}

export function ToneBadge({ tone, children, className }: { tone: Tone; children: ReactNode; className?: string }) {
  return <Badge className={cn(TAG, toneClass[tone], className)}>{children}</Badge>
}

const calloutClass: Record<"gray" | "blue" | "green" | "yellow" | "red", string> = {
  gray: "bg-callout-gray",
  blue: "bg-callout-blue",
  green: "bg-callout-green",
  yellow: "bg-callout-yellow",
  red: "bg-callout-red",
}

const calloutIcon: Record<keyof typeof calloutClass, string> = {
  gray: "text-muted-foreground",
  blue: "text-primary",
  green: "text-[#448361] dark:text-[#4dab9a]",
  yellow: "text-[#cb912f] dark:text-[#ca9849]",
  red: "text-destructive",
}

export function Callout({
  tone = "gray",
  icon,
  title,
  children,
  action,
  className,
}: {
  tone?: keyof typeof calloutClass
  icon?: ReactNode
  title?: ReactNode
  children?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn("flex gap-3 rounded-md px-4 py-3.5", calloutClass[tone], className)}>
      {icon && <div className={cn("mt-0.5 shrink-0 [&>svg]:size-5", calloutIcon[tone])}>{icon}</div>}
      <div className="min-w-0 flex-1 space-y-1">
        {title && <div className="font-semibold">{title}</div>}
        {children && <div className="text-sm leading-relaxed">{children}</div>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  )
}

export function PageHeader({ title, description, actions, className }: { title: ReactNode; description?: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <div className={cn("mb-8 flex flex-wrap items-end justify-between gap-4", className)}>
      <div className="min-w-0 space-y-1.5">
        <h1 className="text-[32px] leading-tight font-bold tracking-tight">{title}</h1>
        {description && <div className="text-base text-muted-foreground">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function SectionHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold">{title}</h2>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

export function EmptyState({ icon, title, description, action }: { icon?: ReactNode; title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg bg-muted px-6 py-10 text-center">
      {icon && <div className="mb-3 text-muted-foreground [&>svg]:size-8">{icon}</div>}
      <p className="font-medium">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorState({ error, title = "Не удалось загрузить данные" }: { error: unknown; title?: string }) {
  return (
    <Callout tone="red" icon={<AlertCircle />} title={title}>
      {error instanceof Error ? error.message : String(error)}
    </Callout>
  )
}

export function LoadingRows({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-14 w-full" />
      ))}
    </div>
  )
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-4 animate-spin", className)} />
}

export function Stat({ label, value, hint, className }: { label: string; value: ReactNode; hint?: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-lg border bg-card px-4 py-3.5", className)}>
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="mt-1 text-[26px] leading-tight font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-muted-foreground">{hint}</div>}
    </div>
  )
}
