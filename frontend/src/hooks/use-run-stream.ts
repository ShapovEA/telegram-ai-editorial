import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useRef, useState } from "react"

import { api, streamUrl } from "@/lib/api"
import type { Run, RunEvent } from "@/lib/types"

export type RunDetail = Run & {
  events: RunEvent[]
  llm: { calls: number; cost: number; prompt_tokens: number; completion_tokens: number; latency_ms: number }
}

export type LiveCall = {
  call_id: string
  node: string | null
  role?: string
  model?: string
  label?: string
  text: string
  reasoning: string
}

const FINAL = new Set(["done", "failed", "cancelled"])

export function useRunStream(runId: string | undefined) {
  const client = useQueryClient()
  const queryKey = ["run", runId]
  const query = useQuery({
    queryKey,
    queryFn: () => api<RunDetail>(`/runs/${runId}`),
    enabled: !!runId,
  })
  const [events, setEvents] = useState<RunEvent[]>([])
  const [live, setLive] = useState<Record<string, LiveCall>>({})
  const [connected, setConnected] = useState(false)
  const lastSeq = useRef(0)

  useEffect(() => {
    if (!query.data) return
    setEvents((prev) => {
      const map = new Map<number, RunEvent>()
      for (const e of query.data.events) map.set(e.seq, e)
      for (const e of prev) map.set(e.seq, e)
      const merged = [...map.values()].sort((a, b) => a.seq - b.seq)
      lastSeq.current = merged.length ? merged[merged.length - 1].seq : 0
      return merged
    })
  }, [query.data])

  const status = query.data?.status
  const isFinal = status ? FINAL.has(status) : false
  const loaded = !!query.data

  useEffect(() => {
    if (!runId || !loaded || isFinal) return
    const source = new EventSource(streamUrl(`/runs/${runId}/stream`, { since: lastSeq.current }))
    let refetchTimer: ReturnType<typeof setTimeout> | undefined

    const scheduleRefetch = () => {
      clearTimeout(refetchTimer)
      refetchTimer = setTimeout(() => client.invalidateQueries({ queryKey: ["run", runId] }), 400)
    }

    source.onopen = () => setConnected(true)
    source.onerror = () => setConnected(false)
    source.addEventListener("event", (msg) => {
      const payload = JSON.parse((msg as MessageEvent<string>).data) as Partial<RunEvent> & { type: string; data: Record<string, unknown> }
      if (payload.type === "llm_start") {
        const d = payload.data as { call_id: string; role?: string; model?: string; label?: string }
        setLive((prev) => ({ ...prev, [d.call_id]: { call_id: d.call_id, node: payload.node ?? null, role: d.role, model: d.model, label: d.label, text: "", reasoning: "" } }))
        return
      }
      if (payload.type === "llm_delta") {
        const d = payload.data as { call_id: string; text: string; reasoning: string }
        setLive((prev) => {
          const cur = prev[d.call_id] ?? { call_id: d.call_id, node: payload.node ?? null, text: "", reasoning: "" }
          return { ...prev, [d.call_id]: { ...cur, text: d.text || cur.text, reasoning: d.reasoning || cur.reasoning } }
        })
        return
      }
      if (payload.seq === undefined) return
      const event: RunEvent = { seq: payload.seq, ts: payload.ts ?? new Date().toISOString(), type: payload.type, node: payload.node ?? null, data: payload.data ?? {} }
      lastSeq.current = Math.max(lastSeq.current, event.seq)
      setEvents((prev) => (prev.some((e) => e.seq === event.seq) ? prev : [...prev, event].sort((a, b) => a.seq - b.seq)))
      if (event.type === "llm_call") {
        const callId = String(event.data.call_id ?? "")
        setLive((prev) => {
          if (!(callId in prev)) return prev
          const next = { ...prev }
          delete next[callId]
          return next
        })
      }
      if (["node_start", "node_end", "node_wait", "node_error", "run_end"].includes(event.type)) scheduleRefetch()
    })
    source.addEventListener("end", () => {
      source.close()
      setConnected(false)
      setLive({})
      client.invalidateQueries({ queryKey: ["run", runId] })
    })

    return () => {
      clearTimeout(refetchTimer)
      source.close()
      setConnected(false)
    }
  }, [runId, loaded, isFinal, client])

  return { query, run: query.data, events, live, connected, isFinal }
}
