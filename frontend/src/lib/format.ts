import { format, formatDistanceToNowStrict, isSameYear, parseISO } from "date-fns"
import { ru } from "date-fns/locale"

export function toDate(value: string | Date | null | undefined): Date | null {
  if (!value) return null
  return typeof value === "string" ? parseISO(value) : value
}

export function fmtDateTime(value: string | Date | null | undefined): string {
  const d = toDate(value)
  if (!d) return "—"
  return format(d, isSameYear(d, new Date()) ? "d MMM, HH:mm" : "d MMM yyyy, HH:mm", { locale: ru })
}

export function fmtDate(value: string | Date | null | undefined): string {
  const d = toDate(value)
  if (!d) return "—"
  return format(d, isSameYear(d, new Date()) ? "d MMMM" : "d MMMM yyyy", { locale: ru })
}

export function fmtTime(value: string | Date | null | undefined): string {
  const d = toDate(value)
  return d ? format(d, "HH:mm") : "—"
}

export function fmtAgo(value: string | Date | null | undefined): string {
  const d = toDate(value)
  if (!d) return "—"
  return formatDistanceToNowStrict(d, { locale: ru, addSuffix: true })
}

export function fmtUsd(value: number | null | undefined, digits?: number): string {
  if (value === null || value === undefined) return "—"
  const d = digits ?? (Math.abs(value) < 1 ? 4 : 2)
  return `$${value.toFixed(d)}`
}

export function fmtDuration(from: string | null | undefined, to: string | null | undefined): string {
  const a = toDate(from)
  if (!a) return "—"
  const b = toDate(to) ?? new Date()
  const sec = Math.max(0, Math.round((b.getTime() - a.getTime()) / 1000))
  if (sec < 60) return `${sec} с`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} мин ${sec % 60} с`
  return `${Math.floor(min / 60)} ч ${min % 60} мин`
}

export function fmtNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—"
  return new Intl.NumberFormat("ru-RU").format(value)
}

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}
