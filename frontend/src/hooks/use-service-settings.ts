import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { Role, RoleModel } from "@/lib/types"

export type ServiceSettings = {
  langfuse_enabled: boolean
  default_models: Partial<Record<Role, RoleModel>>
  extra_stamps: string[]
  latin_whitelist: string[]
  langfuse_configured: boolean
  langfuse_base_url: string
  openrouter_configured: boolean
  telegram_configured: boolean
  telegram_bot_username: string
  pexels_configured: boolean
}

export function useServiceSettings() {
  return useQuery({ queryKey: ["service-settings"], queryFn: () => api<ServiceSettings>("/settings"), staleTime: 60_000 })
}
