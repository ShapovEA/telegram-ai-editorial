import { useIsAuthenticated } from "@refinedev/core"
import { CatchAllNavigate } from "@refinedev/react-router"
import type { ReactNode } from "react"
import { Navigate } from "react-router"

export function RequireAuth({ children }: { children: ReactNode }) {
  const { data, isFetching } = useIsAuthenticated()
  if (data?.authenticated) return children
  if (isFetching) return null
  return <CatchAllNavigate to="/login" />
}

export function GuestOnly({ children }: { children: ReactNode }) {
  const { data, isFetching } = useIsAuthenticated()
  if (!data?.authenticated) return children
  if (isFetching) return null
  return <Navigate to="/" replace />
}
