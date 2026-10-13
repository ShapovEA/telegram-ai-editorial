import type { BaseRecord, CrudFilter, DataProvider, MetaQuery } from "@refinedev/core"

import { api } from "@/lib/api"

type Query = Record<string, string | number | boolean | undefined>

function listPath(resource: string, meta?: MetaQuery): string {
  if (meta?.path) return String(meta.path)
  if (meta?.channelId !== undefined) return `/channels/${meta.channelId}/${resource}`
  return `/${resource}`
}

function itemPath(resource: string, id: string | number, meta?: MetaQuery): string {
  if (meta?.itemPath) return String(meta.itemPath)
  return `/${resource}/${id}`
}

function filtersToQuery(filters: CrudFilter[] | undefined): Query {
  const out: Query = {}
  for (const f of filters ?? []) {
    if (!("field" in f)) continue
    const value = f.value
    if (value === undefined || value === null || value === "") continue
    out[f.field] = Array.isArray(value) ? value.join(",") : value
  }
  return out
}

function normalizeList<T>(res: unknown): { data: T[]; total: number } {
  if (Array.isArray(res)) return { data: res as T[], total: res.length }
  const obj = res as { items?: T[]; total?: number }
  const data = obj.items ?? []
  return { data, total: obj.total ?? data.length }
}

export const dataProvider: DataProvider = {
  getApiUrl: () => "/api",

  getList: async ({ resource, pagination, filters, meta }) => {
    const query: Query = { ...filtersToQuery(filters), ...(meta?.query as Query | undefined) }
    if (pagination && pagination.mode !== "off") {
      const size = pagination.pageSize ?? 20
      const page = pagination.currentPage ?? 1
      query.limit = size
      query.offset = (page - 1) * size
    }
    const res = await api(listPath(resource, meta), { query })
    const { data, total } = normalizeList<BaseRecord>(res)
    return { data: data as never, total }
  },

  getOne: async ({ resource, id, meta }) => {
    const data = await api<BaseRecord>(itemPath(resource, id, meta))
    return { data: data as never }
  },

  getMany: async ({ resource, ids, meta }) => {
    const data = await Promise.all(ids.map((id) => api<BaseRecord>(itemPath(resource, id, meta))))
    return { data: data as never }
  },

  create: async ({ resource, variables, meta }) => {
    const data = await api<BaseRecord>(listPath(resource, meta), { method: "POST", body: variables })
    return { data: data as never }
  },

  update: async ({ resource, id, variables, meta }) => {
    const data = await api<BaseRecord>(itemPath(resource, id, meta), {
      method: (meta?.method as string | undefined) ?? "PATCH",
      body: variables,
    })
    return { data: data as never }
  },

  deleteOne: async ({ resource, id, meta }) => {
    const data = await api<BaseRecord>(itemPath(resource, id, meta), { method: "DELETE" })
    return { data: (data ?? { id }) as never }
  },

  custom: async ({ url, method, payload, query, meta }) => {
    const data = await api<BaseRecord>(url, {
      method: method.toUpperCase(),
      body: payload,
      query: { ...(query as Query | undefined), ...(meta?.query as Query | undefined) },
    })
    return { data: data as never }
  },
}
