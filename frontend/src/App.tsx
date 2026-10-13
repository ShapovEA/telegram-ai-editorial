import { Authenticated, Refine } from "@refinedev/core"
import routerProvider, { CatchAllNavigate, NavigateToResource, UnsavedChangesNotifier } from "@refinedev/react-router"
import { ThemeProvider } from "@/components/theme"
import { Navigate, Outlet, Route, Routes } from "react-router"

import { AppLayout } from "@/components/layout/app-layout"
import { Toaster } from "@/components/ui/sonner"
import { TooltipProvider } from "@/components/ui/tooltip"
import { ChannelLayout } from "@/pages/channel/layout"
import { ChannelAnalytics } from "@/pages/channel/analytics"
import { ChannelOverview } from "@/pages/channel/overview"
import { ChannelCosts } from "@/pages/channel/costs"
import { ChannelIdeas } from "@/pages/channel/ideas"
import { ChannelPlan } from "@/pages/channel/plan"
import { ChannelPosts } from "@/pages/channel/posts"
import { ChannelRuns } from "@/pages/channel/runs"
import { ChannelSettings } from "@/pages/channel/settings"
import { ChannelStories } from "@/pages/channel/stories"
import { ChannelsPage } from "@/pages/channels"
import { LoginPage, RegisterPage } from "@/pages/auth"
import { NewChannelPage } from "@/pages/new-channel"
import { PostPage } from "@/pages/post"
import { RunPage } from "@/pages/run"
import { ServiceSettingsPage } from "@/pages/service-settings"
import { authProvider } from "@/providers/auth"
import { dataProvider } from "@/providers/data"
import { notificationProvider } from "@/providers/notification"

export default function App() {
  return (
    <ThemeProvider>
      <TooltipProvider delayDuration={200}>
        <Refine
          routerProvider={routerProvider}
          dataProvider={dataProvider}
          authProvider={authProvider}
          notificationProvider={notificationProvider}
          resources={[
            { name: "channels", list: "/channels", create: "/channels/new", show: "/channels/:id" },
            { name: "posts", show: "/posts/:id" },
            { name: "runs", show: "/runs/:id" },
          ]}
          options={{
            syncWithLocation: true,
            warnWhenUnsavedChanges: true,
            disableTelemetry: true,
            reactQuery: { clientConfig: { defaultOptions: { queries: { staleTime: 5_000, retry: 1 } } } },
          }}
        >
          <Routes>
            <Route
              element={
                <Authenticated key="app" fallback={<CatchAllNavigate to="/login" />}>
                  <AppLayout>
                    <Outlet />
                  </AppLayout>
                </Authenticated>
              }
            >
              <Route index element={<NavigateToResource resource="channels" />} />
              <Route path="/channels" element={<ChannelsPage />} />
              <Route path="/channels/new" element={<NewChannelPage />} />
              <Route path="/channels/:id" element={<ChannelLayout />}>
                <Route index element={<ChannelOverview />} />
                <Route path="plan" element={<ChannelPlan />} />
                <Route path="ideas" element={<ChannelIdeas />} />
                <Route path="stories" element={<ChannelStories />} />
                <Route path="posts" element={<ChannelPosts />} />
                <Route path="runs" element={<ChannelRuns />} />
                <Route path="costs" element={<ChannelCosts />} />
                <Route path="analytics" element={<ChannelAnalytics />} />
                <Route path="settings" element={<ChannelSettings />} />
              </Route>
              <Route path="/posts/:id" element={<PostPage />} />
              <Route path="/runs/:id" element={<RunPage />} />
              <Route path="/settings" element={<ServiceSettingsPage />} />
            </Route>
            <Route
              element={
                <Authenticated key="auth" fallback={<Outlet />}>
                  <Navigate to="/" replace />
                </Authenticated>
              }
            >
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          <UnsavedChangesNotifier />
          <Toaster richColors closeButton position="bottom-right" />
        </Refine>
      </TooltipProvider>
    </ThemeProvider>
  )
}
