import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react"

type Theme = "light" | "dark" | "system"
type ThemeContextValue = { theme: Theme; resolvedTheme: "light" | "dark"; setTheme: (t: string) => void }

const STORAGE_KEY = "ai-smm-theme"
const ThemeContext = createContext<ThemeContextValue>({ theme: "system", resolvedTheme: "light", setTheme: () => {} })

function readStored(): Theme {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    return v === "light" || v === "dark" ? v : "system"
  } catch {
    return "system"
  }
}

function systemDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readStored)
  const [prefersDark, setPrefersDark] = useState(systemDark)

  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const onChange = (e: MediaQueryListEvent) => setPrefersDark(e.matches)
    mq.addEventListener("change", onChange)
    return () => mq.removeEventListener("change", onChange)
  }, [])

  const resolvedTheme = theme === "system" ? (prefersDark ? "dark" : "light") : theme

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", resolvedTheme === "dark")
    root.style.colorScheme = resolvedTheme
  }, [resolvedTheme])

  const setTheme = useCallback((t: string) => {
    const next: Theme = t === "light" || t === "dark" ? t : "system"
    setThemeState(next)
    try {
      if (next === "system") localStorage.removeItem(STORAGE_KEY)
      else localStorage.setItem(STORAGE_KEY, next)
    } catch {
      return
    }
  }, [])

  const value = useMemo(() => ({ theme, resolvedTheme, setTheme }), [theme, resolvedTheme, setTheme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  return useContext(ThemeContext)
}
