import type { AuthProvider } from "@refinedev/core"

import { api, ApiError, getToken, setToken } from "@/lib/api"
import type { User } from "@/lib/types"

type AuthResponse = { token: string; user: User }

export const authProvider: AuthProvider = {
  login: async ({ email, password }) => {
    try {
      const res = await api<AuthResponse>("/auth/login", { body: { email, password } })
      setToken(res.token)
      return { success: true, redirectTo: "/" }
    } catch (e) {
      return { success: false, error: { name: "Не удалось войти", message: (e as Error).message } }
    }
  },
  register: async ({ email, password, name }) => {
    try {
      const res = await api<AuthResponse>("/auth/register", { body: { email, password, name } })
      setToken(res.token)
      return { success: true, redirectTo: "/channels/new" }
    } catch (e) {
      return { success: false, error: { name: "Не удалось зарегистрироваться", message: (e as Error).message } }
    }
  },
  logout: async () => {
    setToken(null)
    return { success: true, redirectTo: "/login" }
  },
  check: async () => {
    if (!getToken()) return { authenticated: false, redirectTo: "/login" }
    try {
      await api("/auth/me")
      return { authenticated: true }
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setToken(null)
        return { authenticated: false, redirectTo: "/login", logout: true }
      }
      return { authenticated: true }
    }
  },
  getIdentity: async () => {
    if (!getToken()) return null
    try {
      return await api<User>("/auth/me")
    } catch {
      return null
    }
  },
  onError: async (error) => {
    if (error instanceof ApiError && error.status === 401) {
      setToken(null)
      return { logout: true, redirectTo: "/login", error }
    }
    return { error }
  },
}
