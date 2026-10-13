import { useGetIdentity, useList, useLogout } from "@refinedev/core"
import { LogOut, Monitor, Moon, Plus, Radio, Settings, Sun, Tv } from "lucide-react"
import { useTheme } from "@/components/theme"
import type { ReactNode } from "react"
import { Link, useLocation } from "react-router"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar"
import type { Channel, User } from "@/lib/types"

type ChannelWithStats = Channel & { stats?: { attention: number; active_runs: number } }

function ChannelsNav() {
  const { pathname } = useLocation()
  const { result, query } = useList<ChannelWithStats>({
    resource: "channels",
    pagination: { mode: "off" },
    queryOptions: { refetchInterval: 15_000 },
  })

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Каналы</SidebarGroupLabel>
      <SidebarGroupAction asChild title="Новый канал">
        <Link to="/channels/new">
          <Plus />
        </Link>
      </SidebarGroupAction>
      <SidebarGroupContent>
        <SidebarMenu>
          {query.isLoading &&
            Array.from({ length: 3 }).map((_, i) => (
              <SidebarMenuItem key={i}>
                <SidebarMenuSkeleton showIcon />
              </SidebarMenuItem>
            ))}
          {result.data.map((ch) => {
            const href = `/channels/${ch.id}`
            const attention = ch.stats?.attention ?? 0
            return (
              <SidebarMenuItem key={ch.id}>
                <SidebarMenuButton asChild isActive={pathname === href || pathname.startsWith(`${href}/`)} tooltip={ch.title}>
                  <Link to={href}>
                    {ch.type === "news" ? <Radio /> : <Tv />}
                    <span>{ch.title}</span>
                  </Link>
                </SidebarMenuButton>
                {attention > 0 && <SidebarMenuBadge className="text-destructive">{attention}</SidebarMenuBadge>}
              </SidebarMenuItem>
            )
          })}
          {!query.isLoading && result.data.length === 0 && (
            <SidebarMenuItem>
              <SidebarMenuButton asChild>
                <Link to="/channels/new">
                  <Plus />
                  <span>Создать первый канал</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          )}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}

function UserMenu() {
  const { data: user } = useGetIdentity<User>()
  const { mutate: logout } = useLogout()
  const { theme, setTheme } = useTheme()
  const initials = (user?.name || user?.email || "?").slice(0, 2).toUpperCase()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <SidebarMenuButton size="lg">
          <Avatar className="size-8 rounded-lg">
            <AvatarFallback className="rounded-lg">{initials}</AvatarFallback>
          </Avatar>
          <div className="grid flex-1 text-left text-sm leading-tight">
            <span className="truncate font-medium">{user?.name || "Без имени"}</span>
            <span className="truncate text-xs text-muted-foreground">{user?.email}</span>
          </div>
        </SidebarMenuButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent side="top" align="start" className="w-60">
        <DropdownMenuLabel>Тема</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme} onValueChange={setTheme}>
          <DropdownMenuRadioItem value="light">
            <Sun /> Светлая
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <Moon /> Тёмная
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <Monitor /> Как в системе
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => logout()}>
          <LogOut /> Выйти
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function AppLayout({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()

  return (
    <SidebarProvider>
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" asChild>
                <Link to="/channels">
                  <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                    <Tv className="size-4" />
                  </div>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-semibold">AI SMM</span>
                    <span className="truncate text-xs text-muted-foreground">Отдел для Telegram-каналов</span>
                  </div>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>
        <SidebarContent>
          <ChannelsNav />
          <SidebarGroup className="mt-auto">
            <SidebarGroupContent>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton asChild isActive={pathname === "/settings"} tooltip="Настройки сервиса">
                    <Link to="/settings">
                      <Settings />
                      <span>Настройки сервиса</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <SidebarMenu>
            <SidebarMenuItem>
              <UserMenu />
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset className="min-w-0">
        <header className="sticky top-0 z-10 flex h-12 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur md:hidden">
          <SidebarTrigger />
          <span className="font-semibold">AI SMM</span>
        </header>
        <div className="mx-auto w-full max-w-7xl min-w-0 flex-1 p-4 md:p-6">{children}</div>
      </SidebarInset>
    </SidebarProvider>
  )
}
