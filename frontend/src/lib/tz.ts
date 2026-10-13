function parts(date: Date, timeZone: string) {
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  })
  const out: Record<string, number> = {}
  for (const p of fmt.formatToParts(date)) if (p.type !== "literal") out[p.type] = Number(p.value)
  return out as { year: number; month: number; day: number; hour: number; minute: number; second: number }
}

function offsetMs(date: Date, timeZone: string) {
  const p = parts(date, timeZone)
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second)
  return asUtc - Math.floor(date.getTime() / 1000) * 1000
}

export function zonedDayKey(iso: string | Date, timeZone: string): string {
  const p = parts(typeof iso === "string" ? new Date(iso) : iso, timeZone)
  return `${p.year}-${String(p.month).padStart(2, "0")}-${String(p.day).padStart(2, "0")}`
}

export function zonedTime(iso: string | Date, timeZone: string): string {
  const p = parts(typeof iso === "string" ? new Date(iso) : iso, timeZone)
  return `${String(p.hour).padStart(2, "0")}:${String(p.minute).padStart(2, "0")}`
}

export function zonedToUtc(dayKey: string, time: string, timeZone: string): Date {
  const [y, m, d] = dayKey.split("-").map(Number)
  const [hh, mm] = time.split(":").map(Number)
  const guess = Date.UTC(y, m - 1, d, hh, mm)
  const first = guess - offsetMs(new Date(guess), timeZone)
  return new Date(guess - offsetMs(new Date(first), timeZone))
}

export type TimeZoneOption = { id: string; offsetMin: number; offset: string; name: string; search: string }

function formatOffset(minutes: number) {
  const abs = Math.abs(minutes)
  return `UTC${minutes < 0 ? "−" : "+"}${String(Math.floor(abs / 60)).padStart(2, "0")}:${String(abs % 60).padStart(2, "0")}`
}

export function timeZoneOption(id: string, now = new Date()): TimeZoneOption {
  const offsetMin = Math.round(offsetMs(now, id) / 60_000)
  const offset = formatOffset(offsetMin)
  const raw = new Intl.DateTimeFormat("ru-RU", { timeZone: id, timeZoneName: "longGeneric" }).formatToParts(now).find((p) => p.type === "timeZoneName")?.value ?? ""
  const name = raw.replace(/, (стандартное|летнее) время$/, "")
  return { id, offsetMin, offset, name, search: `${id} ${id.replace(/_/g, " ")} ${name} ${offset} ${offset.replace("−", "-")}`.toLowerCase() }
}

let zoneCache: TimeZoneOption[] | null = null

export function timeZones(): TimeZoneOption[] {
  if (!zoneCache) {
    const now = new Date()
    zoneCache = [...new Set(["UTC", ...Intl.supportedValuesOf("timeZone")])]
      .map((id) => timeZoneOption(id, now))
      .sort((a, b) => a.offsetMin - b.offsetMin || a.name.localeCompare(b.name, "ru"))
  }
  return zoneCache
}

export function addDaysKey(dayKey: string, days: number): string {
  const [y, m, d] = dayKey.split("-").map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d + days))
  return dt.toISOString().slice(0, 10)
}

export function mondayKey(date = new Date()): string {
  const dt = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()))
  const dow = (dt.getUTCDay() + 6) % 7
  dt.setUTCDate(dt.getUTCDate() - dow)
  return dt.toISOString().slice(0, 10)
}
