import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node } from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { useQuery } from "@tanstack/react-query"
import { useTheme } from "@/components/theme"
import { useMemo } from "react"

import { Skeleton } from "@/components/ui/skeleton"
import { api } from "@/lib/api"
import type { RunEvent } from "@/lib/types"
import { cn } from "@/lib/utils"

type GraphNode = { id: string; name: string; label: string; parent: string | null; terminal: boolean }
type GraphEdge = { source: string; target: string; conditional: boolean }
type GraphData = { kind: string; nodes: GraphNode[]; edges: GraphEdge[]; groups: Record<string, string> }

export type NodeState = "idle" | "active" | "done" | "error" | "waiting"

const NODE_W = 190
const NODE_H = 44
const GAP_X = 36
const GAP_Y = 64

function layout(nodes: GraphNode[], edges: GraphEdge[]) {
  const ids = new Set(nodes.map((n) => n.id))
  const out = new Map<string, string[]>()
  for (const e of edges) {
    if (!ids.has(e.source) || !ids.has(e.target)) continue
    out.set(e.source, [...(out.get(e.source) ?? []), e.target])
  }
  const start = nodes.find((n) => n.id === "__start__")?.id ?? nodes[0]?.id
  const back = new Set<string>()
  const state = new Map<string, 0 | 1 | 2>()
  const order: string[] = []
  const visit = (id: string) => {
    state.set(id, 1)
    for (const next of out.get(id) ?? []) {
      const s = state.get(next) ?? 0
      if (s === 1) back.add(`${id}->${next}`)
      else if (s === 0) visit(next)
    }
    state.set(id, 2)
    order.push(id)
  }
  if (start) visit(start)
  for (const n of nodes) if (!state.get(n.id)) visit(n.id)
  order.reverse()

  const rank = new Map<string, number>()
  for (const id of order) {
    const r = rank.get(id) ?? 0
    rank.set(id, r)
    for (const next of out.get(id) ?? []) {
      if (back.has(`${id}->${next}`)) continue
      rank.set(next, Math.max(rank.get(next) ?? 0, r + 1))
    }
  }
  const rows = new Map<number, string[]>()
  for (const id of order) {
    const r = rank.get(id) ?? 0
    rows.set(r, [...(rows.get(r) ?? []), id])
  }
  const pos = new Map<string, { x: number; y: number }>()
  for (const [r, row] of rows) {
    const width = row.length * NODE_W + (row.length - 1) * GAP_X
    row.forEach((id, i) => pos.set(id, { x: i * (NODE_W + GAP_X) - width / 2, y: r * (NODE_H + GAP_Y) }))
  }
  return { pos, back, depth: rows.size }
}

const stateClass: Record<NodeState, string> = {
  idle: "border-border bg-card text-muted-foreground",
  active: "border-sky-500 bg-sky-500/10 text-foreground ring-4 ring-sky-500/20 animate-pulse",
  done: "border-emerald-500/60 bg-emerald-500/10 text-foreground",
  error: "border-red-500 bg-red-500/10 text-foreground",
  waiting: "border-amber-500 bg-amber-500/10 text-foreground ring-4 ring-amber-500/20",
}

export function nodeStates(events: RunEvent[]): Map<string, NodeState> {
  const states = new Map<string, NodeState>()
  for (const e of events) {
    if (!e.node) continue
    if (e.type === "node_start") states.set(e.node, "active")
    else if (e.type === "node_end") states.set(e.node, "done")
    else if (e.type === "node_error") states.set(e.node, "error")
    else if (e.type === "node_wait") states.set(e.node, "waiting")
  }
  return states
}

export function GraphView({ runId, events, finished, succeeded }: { runId: string; events: RunEvent[]; finished: boolean; succeeded: boolean }) {
  const { resolvedTheme } = useTheme()
  const { data, isLoading } = useQuery({
    queryKey: ["run-graph", runId],
    queryFn: () => api<GraphData>(`/runs/${runId}/graph`),
    staleTime: Infinity,
  })

  const states = useMemo(() => nodeStates(events), [events])

  const { nodes, edges, depth } = useMemo(() => {
    if (!data) return { nodes: [] as Node[], edges: [] as Edge[], depth: 0 }
    const { pos, back, depth } = layout(data.nodes, data.edges)
    const passed = new Set<string>()
    for (const e of events) if (e.node && (e.type === "node_end" || e.type === "node_start")) passed.add(e.node)

    const rfNodes: Node[] = data.nodes.map((n) => {
      let st: NodeState = states.get(n.name) ?? "idle"
      if (n.terminal) st = n.id === "__start__" ? (events.length ? "done" : "idle") : succeeded && n.id === "__end__" ? "done" : "idle"
      if (finished && st === "active") st = "error"
      const width = n.terminal ? 110 : NODE_W
      const p = pos.get(n.id) ?? { x: 0, y: 0 }
      return {
        id: n.id,
        position: { x: p.x + (NODE_W - width) / 2, y: p.y },
        style: { width, padding: 0, border: "none", background: "transparent", boxShadow: "none" },
        data: {
          label: (
            <div
              title={n.parent ? (data.groups[n.parent] ?? n.parent) : undefined}
              className={cn(
                "flex h-11 items-center justify-center rounded-lg border px-2 text-center text-xs leading-tight font-medium",
                n.terminal && "rounded-full border-dashed",
                stateClass[st],
              )}
            >
              {n.label}
            </div>
          ),
        },
      }
    })

    const nameOf = new Map(data.nodes.map((n) => [n.id, n.name]))
    const rfEdges: Edge[] = data.edges.map((e, i) => {
      const walked = passed.has(nameOf.get(e.source) ?? "") && passed.has(nameOf.get(e.target) ?? "")
      return {
        id: `${e.source}-${e.target}-${i}`,
        source: e.source,
        target: e.target,
        type: back.has(`${e.source}->${e.target}`) ? "smoothstep" : "default",
        animated: walked && !finished,
        style: {
          strokeDasharray: e.conditional ? "5 4" : undefined,
          stroke: walked ? "var(--color-emerald-500, #10b981)" : "var(--border)",
          strokeWidth: walked ? 2 : 1.25,
        },
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: walked ? "#10b981" : "#9ca3af" },
      }
    })
    return { nodes: rfNodes, edges: rfEdges, depth }
  }, [data, events, states, finished, succeeded])

  if (isLoading) return <Skeleton className="h-[460px] w-full" />

  return (
    <div className="w-full overflow-hidden rounded-xl border bg-muted/20" style={{ height: Math.min(820, Math.max(320, depth * (NODE_H + GAP_Y) * 0.75 + 60)) }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.2}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
        colorMode={resolvedTheme === "dark" ? "dark" : "light"}
      >
        <Background gap={20} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
